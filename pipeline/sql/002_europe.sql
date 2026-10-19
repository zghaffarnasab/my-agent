-- Filmmaker dashboard: migration 002, Europe-wide scope.
--
-- * open_to: who may apply, as stated on the page. ISO 3166-1 alpha-2 codes ('DE', 'GB') or a group:
--   'EU' (EU member states), 'EEA' (EU + IS, LI, NO), 'MEDIA' (Creative Europe MEDIA countries),
--   'EUROPE' (any European country), 'WORLD' (no country limit). Empty = the page does not say.
--   uk_eligible stays: it is the quick "can a UK-based company apply" answer.
-- * country no longer defaults to 'GB': organisations and events outside the UK are now watched.
--   Organisation country may also be 'EU', 'EUROPE' or 'INT' for pan-European and international bodies.

BEGIN;

ALTER TABLE funds  ADD COLUMN open_to text[] NOT NULL DEFAULT '{}';
ALTER TABLE events ADD COLUMN open_to text[] NOT NULL DEFAULT '{}';

ALTER TABLE organisations ALTER COLUMN country DROP DEFAULT;
ALTER TABLE events        ALTER COLUMN country DROP DEFAULT;

COMMIT;
