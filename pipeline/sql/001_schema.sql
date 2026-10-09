-- Filmmaker dashboard: Postgres schema (migration 001)
-- Pipeline: Discovery -> Fetch -> Extract (Claude) -> Dedupe/Verify -> Postgres -> Review UI -> Sync -> Wix CMS
-- Postgres is the source of truth. Wix only displays what is published here.
--
-- Core rules (from the brief and the UK research report, Oct 2026):
--   * Every date and amount carries its own status and a verbatim source quote.
--     Claude never invents a date; a date without a quote cannot be stored.
--   * date_status: confirmed | expected | unverified | conflict | closed
--   * uk_eligible: yes | no | partial | unknown
--   * Each record has source_url, source_tier, last_verified_at, content_hash.
--   * Publication status is draft | published | rejected; "expired" is computed (see *_v views).
--   * Articles store title, link and our own summary only. Never the full text.
--
-- Target: PostgreSQL 14+. Tested on 16.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- fuzzy name matching for dedupe
CREATE EXTENSION IF NOT EXISTS citext;    -- case-insensitive URLs / names

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------

CREATE TYPE date_status    AS ENUM ('confirmed', 'expected', 'unverified', 'conflict', 'closed');
CREATE TYPE uk_eligibility AS ENUM ('yes', 'no', 'partial', 'unknown');
CREATE TYPE source_tier    AS ENUM ('official', 'aggregator', 'press', 'newsletter', 'unofficial');
CREATE TYPE publish_status AS ENUM ('draft', 'published', 'rejected');
CREATE TYPE record_kind    AS ENUM ('event', 'fund', 'article');

CREATE TYPE fetch_method   AS ENUM ('html', 'html_js', 'rss', 'wp_json', 'pdf', 'email', 'portal');
CREATE TYPE event_type     AS ENUM ('festival', 'market', 'lab', 'workshop', 'pitch', 'award', 'talent_programme', 'other');
CREATE TYPE event_format   AS ENUM ('in_person', 'online', 'hybrid', 'unknown');
CREATE TYPE fund_stage     AS ENUM ('development', 'production', 'post_production', 'distribution', 'festival_travel', 'talent', 'other');
CREATE TYPE deadline_mode  AS ENUM ('fixed', 'rolling', 'rounds', 'unknown');
CREATE TYPE submit_platform AS ENUM ('filmfreeway', 'own_site', 'email', 'bfi_portal', 'other', 'unknown');
CREATE TYPE learn_level    AS ENUM ('beginner', 'intermediate', 'advanced', 'all');

-- What a dated row means. One record can have many (Sheffield DocFest: early/standard/late).
CREATE TYPE date_kind AS ENUM (
  'opens',            -- call / round opens
  'deadline',         -- generic submission or application deadline
  'deadline_early',
  'deadline_regular',
  'deadline_late',
  'deadline_extended',
  'event_start',
  'event_end',
  'results',          -- selection / decision announced
  'closure_start',    -- e.g. BFI Development annual closure 1-30 April
  'closure_end',
  'other'
);

-- ---------------------------------------------------------------------------
-- Sources and snapshots (Discovery + Fetch + change detection)
-- ---------------------------------------------------------------------------

CREATE TABLE organisations (
  id           bigserial PRIMARY KEY,
  name         citext NOT NULL UNIQUE,         -- 'BFI', 'Doc Society', 'Screen Scotland'
  website      text,
  country      text DEFAULT 'GB',
  notes        text,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX organisations_name_trgm ON organisations USING gin (name gin_trgm_ops);

-- A page, feed, PDF or mailbox we watch.
CREATE TABLE sources (
  id                 bigserial PRIMARY KEY,
  url                citext NOT NULL UNIQUE,   -- canonical URL (or 'gmail:label/...' for newsletters)
  organisation_id    bigint REFERENCES organisations(id),
  title              text,
  tier               source_tier NOT NULL,
  method             fetch_method NOT NULL,
  feeds_kind         record_kind,              -- what this source mostly yields
  check_interval     interval NOT NULL DEFAULT '7 days',
  is_active          boolean NOT NULL DEFAULT true,
  paywalled          boolean NOT NULL DEFAULT false,   -- store title + link only
  needs_server_check boolean NOT NULL DEFAULT true,    -- report: RSS/static claims untested from EC2
  content_selector   text,                     -- CSS selector for the main block that gets hashed
  last_fetched_at    timestamptz,
  last_changed_at    timestamptz,
  last_content_hash  text,                     -- sha256 of cleaned main content
  last_http_status   int,
  last_error         text,
  notes              text,
  created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX sources_due ON sources (is_active, last_fetched_at);

-- One row per fetch whose content hash differs from the previous one.
CREATE TABLE snapshots (
  id            bigserial PRIMARY KEY,
  source_id     bigint NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  fetched_at    timestamptz NOT NULL DEFAULT now(),
  http_status   int,
  content_hash  text NOT NULL,
  clean_text    text NOT NULL,                 -- trafilatura output; what Claude reads
  page_modified text,                          -- 'last updated' / article:modified_time if the page shows one
  email_message_id text,                       -- Gmail message id when method = 'email'
  UNIQUE (source_id, content_hash)
);
CREATE INDEX snapshots_source_time ON snapshots (source_id, fetched_at DESC);

-- Every Claude call, for audit and replay.
CREATE TABLE extraction_runs (
  id             bigserial PRIMARY KEY,
  snapshot_id    bigint NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
  model          text NOT NULL,
  prompt_version text NOT NULL,                -- e.g. 'extract-v1'
  started_at     timestamptz NOT NULL DEFAULT now(),
  finished_at    timestamptz,
  ok             boolean,
  raw_output     jsonb,                        -- the tool-call input exactly as returned
  rejected_items jsonb,                        -- items dropped by validation, with reason
  input_tokens   int,
  output_tokens  int,
  error          text
);

-- ---------------------------------------------------------------------------
-- Columns shared by events, funds and articles (copied into each table)
--   source_url, source_tier, last_verified_at, content_hash, status, review fields, Wix sync fields
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- Events: festivals, markets, labs, workshops
-- ---------------------------------------------------------------------------

CREATE TABLE events (
  id                bigserial PRIMARY KEY,
  slug              citext NOT NULL UNIQUE,    -- for the Wix dynamic page, e.g. 'sheffield-docfest-2027'
  name              text NOT NULL,             -- 'Sheffield DocFest'
  edition           text,                      -- '2027', '34th'
  edition_year      int,
  organisation_id   bigint REFERENCES organisations(id),
  event_type        event_type NOT NULL,
  format            event_format NOT NULL DEFAULT 'unknown',
  city              text,
  venue             text,
  country           text DEFAULT 'GB',
  -- Fees as stated; ranges because of early/standard/late tiers.
  fee_min           numeric(10,2),
  fee_max           numeric(10,2),
  fee_currency      char(3),
  fee_note          text,                      -- 'feature £40/£48/£58; VAT wording unclear'
  genres            text[] NOT NULL DEFAULT '{}',  -- 'documentary','experimental','short','animation','xr',...
  accepts_lengths   text,                      -- 'features over 60 min only'
  submit_platform   submit_platform NOT NULL DEFAULT 'unknown',
  submit_url        text,
  uk_eligible       uk_eligibility NOT NULL DEFAULT 'unknown',
  eligibility_note  text,
  summary           text,                      -- our own words

  source_url        citext NOT NULL,
  source_id         bigint REFERENCES sources(id),
  source_tier       source_tier NOT NULL,
  last_verified_at  timestamptz,
  content_hash      text,                      -- hash of the snapshot this record was last extracted from
  confidence        numeric(3,2) CHECK (confidence BETWEEN 0 AND 1),

  status            publish_status NOT NULL DEFAULT 'draft',
  reviewed_by       text,
  reviewed_at       timestamptz,
  review_note       text,

  wix_item_id       text,
  wix_synced_at     timestamptz,
  wix_sync_hash     text,                      -- hash of the payload last sent to Wix

  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (name, edition_year)
);
CREATE INDEX events_name_trgm ON events USING gin (name gin_trgm_ops);
CREATE INDEX events_status ON events (status);

-- BAFTA / BIFA / Oscar qualifying status, scoped to a list year.
CREATE TABLE event_qualifications (
  id            bigserial PRIMARY KEY,
  event_id      bigint NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  body          text NOT NULL CHECK (body IN ('BAFTA', 'BIFA', 'Oscars', 'BAFTA Cymru', 'Other')),
  category      text,                          -- 'British Short Film', 'Live Action Short'
  list_period   daterange,                     -- BIFA 2026 list: [2025-11-01, 2026-11-30]
  source_url    text NOT NULL,
  source_quote  text NOT NULL CHECK (length(btrim(source_quote)) > 0),
  last_verified_at timestamptz,
  UNIQUE (event_id, body, category, list_period)
);

-- ---------------------------------------------------------------------------
-- Funds
-- ---------------------------------------------------------------------------

CREATE TABLE funds (
  id                bigserial PRIMARY KEY,
  slug              citext NOT NULL UNIQUE,    -- 'bfi-discovery'
  name              text NOT NULL,             -- 'BFI Discovery'
  strand            text,                      -- 'Round 3', 'IBF Classic'
  organisation_id   bigint REFERENCES organisations(id),
  stages            fund_stage[] NOT NULL DEFAULT '{}',
  forms             text[] NOT NULL DEFAULT '{}',  -- 'feature','short','documentary','animation','immersive','experimental'
  genres            text[] NOT NULL DEFAULT '{}',
  -- Amount as stated. Exact figures and their quotes live in field_evidence.
  amount_min        numeric(14,2),
  amount_max        numeric(14,2),
  amount_currency   char(3),
  amount_status     date_status NOT NULL DEFAULT 'unverified',  -- reuse: confirmed/conflict/unverified...
  amount_note       text,                      -- 'up to £1m for budgets £1m-£3.5m'
  deadline_mode     deadline_mode NOT NULL DEFAULT 'unknown',
  residency_rule    text,                      -- 'director resident in England'
  nationality_rule  text,
  other_eligibility text,                      -- 'first feature', 'Companies House registered producer'
  uk_eligible       uk_eligibility NOT NULL DEFAULT 'unknown',
  uk_not_eligible_reason text,                 -- shown as the "UK not eligible" badge text
  is_accepting      boolean,                   -- false for e.g. Catapult "not accepting"
  apply_url         text,
  apply_email       text,
  summary           text,

  source_url        citext NOT NULL,
  source_id         bigint REFERENCES sources(id),
  source_tier       source_tier NOT NULL,
  last_verified_at  timestamptz,
  content_hash      text,
  confidence        numeric(3,2) CHECK (confidence BETWEEN 0 AND 1),

  status            publish_status NOT NULL DEFAULT 'draft',
  reviewed_by       text,
  reviewed_at       timestamptz,
  review_note       text,

  wix_item_id       text,
  wix_synced_at     timestamptz,
  wix_sync_hash     text,

  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  CHECK (amount_min IS NULL OR amount_max IS NULL OR amount_min <= amount_max),
  CHECK (uk_eligible <> 'no' OR uk_not_eligible_reason IS NOT NULL),
  UNIQUE (name, strand)
);
CREATE INDEX funds_name_trgm ON funds USING gin (name gin_trgm_ops);
CREATE INDEX funds_status ON funds (status);

-- ---------------------------------------------------------------------------
-- Dates for events and funds, versioned.
-- A date is never a bare column on events/funds: it lives here with its status and quote.
-- When a page changes a date, the old row gets superseded_at and a new row is inserted.
-- ---------------------------------------------------------------------------

CREATE TABLE record_dates (
  id              bigserial PRIMARY KEY,
  event_id        bigint REFERENCES events(id) ON DELETE CASCADE,
  fund_id         bigint REFERENCES funds(id)  ON DELETE CASCADE,
  kind            date_kind NOT NULL,
  label           text,                         -- 'Round 3 closes', 'Late deadline'
  status          date_status NOT NULL,
  -- Exact date when known. For 'expected' rows use approx_* instead.
  date_value      date,
  time_value      time,
  tz              text,                         -- IANA, e.g. 'Europe/London'
  approx_text     text,                         -- 'Spring 2027', 'around June'
  approx_from     date,                         -- window used for sorting expected rows
  approx_to       date,
  basis           text,                         -- for 'expected': '2026 deadline was 1 June'
  source_url      text NOT NULL,
  source_tier     source_tier NOT NULL,
  source_quote    text NOT NULL CHECK (length(btrim(source_quote)) > 0),
  snapshot_id     bigint REFERENCES snapshots(id),
  extraction_run_id bigint REFERENCES extraction_runs(id),
  last_verified_at timestamptz,
  superseded_at   timestamptz,                  -- NULL = current
  superseded_by   bigint REFERENCES record_dates(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  CHECK ((event_id IS NULL) <> (fund_id IS NULL)),
  -- confirmed and closed need a real date; expected must not pretend to have one.
  CHECK (status NOT IN ('confirmed', 'closed') OR date_value IS NOT NULL),
  CHECK (status <> 'expected' OR (date_value IS NULL AND (approx_text IS NOT NULL OR approx_from IS NOT NULL))),
  CHECK (approx_from IS NULL OR approx_to IS NULL OR approx_from <= approx_to)
);
CREATE INDEX record_dates_event   ON record_dates (event_id) WHERE superseded_at IS NULL;
CREATE INDEX record_dates_fund    ON record_dates (fund_id)  WHERE superseded_at IS NULL;
CREATE INDEX record_dates_upcoming ON record_dates (date_value) WHERE superseded_at IS NULL;

-- ---------------------------------------------------------------------------
-- Field-level evidence: a verbatim quote for every extracted field value.
-- The Review UI shows these next to each field. Two current rows with different
-- values for the same field = a conflict for a human to settle (Whickers £120k vs £100k).
-- ---------------------------------------------------------------------------

CREATE TABLE field_evidence (
  id                bigserial PRIMARY KEY,
  record_kind       record_kind NOT NULL,
  record_id         bigint NOT NULL,             -- events.id / funds.id / articles.id
  field_name        text NOT NULL,               -- 'amount_max', 'residency_rule', 'fee_note', ...
  value_text        text,                        -- normalised value as text
  source_quote      text NOT NULL CHECK (length(btrim(source_quote)) > 0),
  source_url        text NOT NULL,
  source_tier       source_tier NOT NULL,
  snapshot_id       bigint REFERENCES snapshots(id),
  extraction_run_id bigint REFERENCES extraction_runs(id),
  confidence        numeric(3,2) CHECK (confidence BETWEEN 0 AND 1),
  accepted          boolean,                     -- NULL = not reviewed; true = reviewer picked this one
  superseded_at     timestamptz,
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX field_evidence_record ON field_evidence (record_kind, record_id, field_name) WHERE superseded_at IS NULL;

-- ---------------------------------------------------------------------------
-- Learn: articles from RSS feeds. Title, link, our own short summary. No full text.
-- ---------------------------------------------------------------------------

CREATE TABLE articles (
  id                bigserial PRIMARY KEY,
  slug              citext NOT NULL UNIQUE,
  title             text NOT NULL,
  url               citext NOT NULL UNIQUE,     -- canonical link to the original
  publisher         text NOT NULL,              -- 'BFI', 'Sight and Sound', 'Stephen Follows'
  author            text,
  published_at      timestamptz,
  topics            text[] NOT NULL DEFAULT '{}',  -- 'funding','festival strategy','cinematography','distribution',...
  level             learn_level,
  summary           text,                       -- written by our pipeline (Haiku), max ~60 words
  paywalled         boolean NOT NULL DEFAULT false,
  is_gear           boolean NOT NULL DEFAULT false,  -- separate 'Tools' tab, capped per day
  relevance         numeric(3,2) CHECK (relevance BETWEEN 0 AND 1),

  source_url        citext NOT NULL,            -- the feed URL
  source_id         bigint REFERENCES sources(id),
  source_tier       source_tier NOT NULL,
  last_verified_at  timestamptz,
  content_hash      text,                       -- hash of title+link, for dedupe

  status            publish_status NOT NULL DEFAULT 'draft',
  reviewed_by       text,
  reviewed_at       timestamptz,
  review_note       text,

  wix_item_id       text,
  wix_synced_at     timestamptz,
  wix_sync_hash     text,

  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  CHECK (summary IS NULL OR length(summary) <= 600)
);
CREATE INDEX articles_published ON articles (published_at DESC);
CREATE INDEX articles_title_trgm ON articles USING gin (title gin_trgm_ops);

-- Feed-level blocklist (No Film School style listicles).
CREATE TABLE title_filters (
  id         bigserial PRIMARY KEY,
  source_id  bigint REFERENCES sources(id) ON DELETE CASCADE,  -- NULL = all feeds
  pattern    text NOT NULL,                     -- POSIX regex, e.g. '^\d+ ', 'Gen Z', 'Of All Time'
  action     text NOT NULL DEFAULT 'drop' CHECK (action IN ('drop', 'keep')),
  note       text
);

-- ---------------------------------------------------------------------------
-- updated_at trigger
-- ---------------------------------------------------------------------------

CREATE FUNCTION touch_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END $$;

CREATE TRIGGER events_touch   BEFORE UPDATE ON events   FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER funds_touch    BEFORE UPDATE ON funds    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER articles_touch BEFORE UPDATE ON articles FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- ---------------------------------------------------------------------------
-- Views: current dates, computed "expired", what goes to Wix and to the .ics feed
-- ---------------------------------------------------------------------------

-- Current (not superseded) dates only.
CREATE VIEW current_dates AS
SELECT * FROM record_dates WHERE superseded_at IS NULL;

-- A date row has a conflict if another current row of the same kind and label disagrees.
CREATE VIEW date_conflicts AS
SELECT a.id AS date_id, b.id AS other_id, a.event_id, a.fund_id, a.kind,
       a.date_value, b.date_value AS other_value, a.source_url, b.source_url AS other_source
FROM current_dates a
JOIN current_dates b
  ON a.id < b.id
 AND a.kind = b.kind
 AND coalesce(a.label, '') = coalesce(b.label, '')
 AND a.event_id IS NOT DISTINCT FROM b.event_id
 AND a.fund_id  IS NOT DISTINCT FROM b.fund_id
 AND a.date_value IS DISTINCT FROM b.date_value
 AND a.status <> 'expected' AND b.status <> 'expected';

-- Event: expired once its end date (or start date if no end) has passed and no deadline is still ahead.
CREATE VIEW events_v AS
SELECT e.*,
  CASE
    WHEN e.status = 'published' AND last_day.d IS NOT NULL AND last_day.d < current_date
         AND NOT EXISTS (SELECT 1 FROM current_dates d
                         WHERE d.event_id = e.id AND d.date_value >= current_date)
      THEN 'expired'
    ELSE e.status::text
  END AS display_status,
  next_dl.date_value AS next_deadline,
  next_dl.status     AS next_deadline_status
FROM events e
LEFT JOIN LATERAL (
  SELECT max(d.date_value) AS d FROM current_dates d
  WHERE d.event_id = e.id AND d.kind IN ('event_end', 'event_start')
) last_day ON true
LEFT JOIN LATERAL (
  SELECT d.date_value, d.status FROM current_dates d
  WHERE d.event_id = e.id AND d.kind::text LIKE 'deadline%' AND d.date_value >= current_date
  ORDER BY d.date_value LIMIT 1
) next_dl ON true;

-- Fund: rolling funds never expire by date. Fixed/rounds funds expire when every current
-- deadline is in the past and no 'opens' or 'expected' row points forward.
CREATE VIEW funds_v AS
SELECT f.*,
  CASE
    WHEN f.status = 'published' AND f.deadline_mode IN ('fixed', 'rounds')
         AND EXISTS (SELECT 1 FROM current_dates d WHERE d.fund_id = f.id AND d.kind::text LIKE 'deadline%')
         AND NOT EXISTS (SELECT 1 FROM current_dates d
                         WHERE d.fund_id = f.id
                           AND (d.date_value >= current_date
                                OR (d.status = 'expected' AND coalesce(d.approx_to, d.approx_from) >= current_date)))
      THEN 'expired'
    ELSE f.status::text
  END AS display_status,
  next_dl.date_value AS next_deadline,
  next_dl.status     AS next_deadline_status
FROM funds f
LEFT JOIN LATERAL (
  SELECT d.date_value, d.status FROM current_dates d
  WHERE d.fund_id = f.id AND d.kind::text LIKE 'deadline%' AND d.date_value >= current_date
  ORDER BY d.date_value LIMIT 1
) next_dl ON true;

-- "Upcoming deadlines" view on Wix and the .ics feed: confirmed dates only, published records only.
CREATE VIEW upcoming_confirmed AS
SELECT 'fund'::record_kind AS record_kind, f.id AS record_id, f.slug, f.name, d.kind, d.label,
       d.date_value, d.time_value, d.tz, d.source_url, f.uk_eligible
FROM current_dates d JOIN funds f ON f.id = d.fund_id
WHERE d.status = 'confirmed' AND f.status = 'published' AND d.date_value >= current_date
UNION ALL
SELECT 'event', e.id, e.slug, e.name, d.kind, d.label,
       d.date_value, d.time_value, d.tz, d.source_url, e.uk_eligible
FROM current_dates d JOIN events e ON e.id = d.event_id
WHERE d.status = 'confirmed' AND e.status = 'published' AND d.date_value >= current_date;

-- Separate "Not announced yet" view on Wix.
CREATE VIEW expected_dates AS
SELECT coalesce(f.name, e.name) AS name, coalesce(f.slug, e.slug) AS slug,
       CASE WHEN d.fund_id IS NOT NULL THEN 'fund' ELSE 'event' END AS record_kind,
       d.kind, d.label, d.approx_text, d.approx_from, d.approx_to, d.basis, d.source_url
FROM current_dates d
LEFT JOIN funds  f ON f.id = d.fund_id  AND f.status = 'published'
LEFT JOIN events e ON e.id = d.event_id AND e.status = 'published'
WHERE d.status = 'expected' AND (f.id IS NOT NULL OR e.id IS NOT NULL);

-- Review queue: drafts, plus anything whose evidence or dates are in conflict.
CREATE VIEW review_queue AS
SELECT 'event'::record_kind AS record_kind, id AS record_id, name, status::text, source_url, updated_at
FROM events WHERE status = 'draft'
UNION ALL
SELECT 'fund', id, name, status::text, source_url, updated_at FROM funds WHERE status = 'draft'
UNION ALL
SELECT 'article', id, title, status::text, source_url, updated_at FROM articles WHERE status = 'draft'
UNION ALL
SELECT DISTINCT
       CASE WHEN c.fund_id IS NOT NULL THEN 'fund'::record_kind ELSE 'event'::record_kind END,
       coalesce(c.fund_id, c.event_id), 'date conflict', 'conflict', c.source_url, now()
FROM date_conflicts c;

-- Records not re-verified recently (stale data warning in the Review UI).
CREATE VIEW stale_records AS
SELECT 'event'::record_kind AS record_kind, id, name, last_verified_at FROM events
WHERE status = 'published' AND (last_verified_at IS NULL OR last_verified_at < now() - interval '14 days')
UNION ALL
SELECT 'fund', id, name, last_verified_at FROM funds
WHERE status = 'published' AND (last_verified_at IS NULL OR last_verified_at < now() - interval '14 days');

COMMIT;
