/* Accordion rows. Plain JavaScript, no libraries. Without it the page still works: every row header is a
   GET form that reloads the page with that row open, and the actions are normal form posts. */
(function () {
  var list = document.getElementById('rows');
  if (!list) return;
  var tab = list.dataset.tab, archived = list.dataset.archived;
  var status = document.getElementById('list-status');
  var empty = document.getElementById('empty-state');
  var T = {};
  try { T = JSON.parse(document.getElementById('js-i18n').textContent); } catch (e) {}

  function say(el, text, kind) {
    el.classList.remove('ok', 'error');
    el.classList.add(kind === 'error' ? 'error' : 'ok');
    el.textContent = text || '';
    el.hidden = !text;
  }
  function rowOf(el) { return el.closest('li.row'); }
  function bodyOf(row) { return row.querySelector(':scope > .body'); }
  function headOf(row) { return row.querySelector('.head'); }

  // A fetch that was sent to the login page means the session ended.
  function check(r) {
    if (r.redirected && /\/login/.test(r.url)) { location.href = '/login'; throw new Error('login'); }
    if (!r.ok) throw new Error('http ' + r.status);
    return r;
  }

  function setOpen(row, on) {
    row.classList.toggle('open', on);
    headOf(row).setAttribute('aria-expanded', on ? 'true' : 'false');
    bodyOf(row).hidden = !on;
  }
  function closeAll(except) {
    list.querySelectorAll('li.row.open').forEach(function (r) { if (r !== except) setOpen(r, false); });
  }

  // The details are fetched the first time a row opens and then stay in the page,
  // so text typed into a draft survives closing and re-opening the row.
  function load(row) {
    var body = bodyOf(row);
    if (body.dataset.loaded === '1' || body.dataset.loading === '1') return;
    body.dataset.loading = '1';
    var note = document.createElement('p');
    note.className = 'loading';
    note.setAttribute('role', 'status');
    note.textContent = T.loading || '';
    body.replaceChildren(note);
    fetch(body.dataset.src, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } })
      .then(check)
      .then(function (r) { return r.text(); })
      .then(function (html) { body.innerHTML = html; body.dataset.loaded = '1'; })
      .catch(function (err) {
        if (err.message === 'login') return;
        var p = document.createElement('p');
        p.className = 'loading err';
        p.textContent = (T.failed || '') + ' ';
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'retry';
        b.textContent = T.retry || '';
        p.appendChild(b);
        body.replaceChildren(p);
      })
      .then(function () { delete body.dataset.loading; });
  }

  function setUrl(hash) {
    var u = new URL(location.href);
    u.searchParams.delete('open');
    u.hash = hash || '';
    history.replaceState(null, '', u);
  }
  function toggle(row) {
    var on = !row.classList.contains('open');
    closeAll(on ? row : null);          // only one row is open at a time
    setOpen(row, on);
    if (on) load(row);
    setUrl(on ? row.id : '');
  }

  function updateCounts(counts) {
    Object.keys(counts).forEach(function (k) {
      var n = document.querySelector('.tab[data-tab="' + k + '"] .n');
      if (n) { n.textContent = counts[k]; n.hidden = !counts[k]; }
    });
  }
  function removeRow(row) {
    row.remove();
    if (!list.querySelector('li.row')) { list.hidden = true; empty.hidden = false; }
  }
  function replaceRow(row, html) {
    var tpl = document.createElement('template');
    tpl.innerHTML = html.trim();
    var fresh = tpl.content.firstElementChild;
    row.replaceWith(fresh);
    closeAll(fresh);
    return fresh;
  }
  function message(row, text, kind) {
    var el = row.querySelector('.panel-inner .inline-msg');
    if (!el) return;
    say(el, text, kind);
    if (text) el.scrollIntoView({ block: 'nearest' });
  }

  // Draft text typed but not saved must not vanish when only an event card changed.
  function rememberDraft(row, url) {
    if (!/\/events\/|\/find-events/.test(url)) return null;
    var ta = row.querySelector('textarea[name="draft_body"]');
    var ins = row.querySelector('input[name="instruction"]');
    return {
      draft: ta && ta.value !== ta.defaultValue ? ta.value : null,
      instruction: ins ? ins.value : ''
    };
  }
  function restoreDraft(row, kept) {
    if (!kept) return;
    var ta = row.querySelector('textarea[name="draft_body"]');
    var ins = row.querySelector('input[name="instruction"]');
    if (ta && kept.draft !== null) ta.value = kept.draft;
    if (ins) ins.value = kept.instruction;
  }

  function apply(row, res, kept) {
    if (res.counts) updateCounts(res.counts);
    if (res.remove) {                    // the row no longer belongs to this tab (sent, rejected, done, added, ...)
      removeRow(row);
      say(status, res.message, res.kind);
      status.focus({ preventScroll: true });
      return;
    }
    if (res.html) {
      var fresh = replaceRow(row, res.html);
      restoreDraft(fresh, kept);
      message(fresh, res.message, res.kind);
      headOf(fresh).focus({ preventScroll: true });
    } else {
      message(row, res.message, res.kind);
    }
  }

  function act(form, submitter, row) {
    var url = (submitter && submitter.getAttribute('formaction')) || form.getAttribute('action');
    var data = new FormData(form);
    if (submitter && submitter.name) data.append(submitter.name, submitter.value);
    var kept = rememberDraft(row, url);
    var buttons = form.querySelectorAll('button');
    buttons.forEach(function (b) { b.disabled = true; });
    fetch(url, {
      method: 'POST', body: data, credentials: 'same-origin',
      headers: { 'X-Requested-With': 'fetch', 'Accept': 'application/json',
                 'X-Row': row.dataset.row, 'X-Tab': tab, 'X-Archived': archived }
    })
      .then(check)
      .then(function (r) { return r.json(); })
      .then(function (res) { apply(row, res, kept); })
      .catch(function (err) { if (err.message !== 'login') message(row, T.failed, 'error'); })
      .then(function () { buttons.forEach(function (b) { b.disabled = false; }); });
  }

  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (form.classList.contains('head-form')) { e.preventDefault(); toggle(rowOf(form)); return; }
    if (!form.closest('#rows .body')) return;
    e.preventDefault();
    act(form, e.submitter, rowOf(form));
  });
  list.addEventListener('click', function (e) {
    var retry = e.target.closest('.retry');
    if (retry) load(rowOf(retry));
  });
  document.addEventListener('keydown', function (e) {
    var form = e.target.closest && e.target.closest('.draft-form');
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && form) {
      var btn = form.querySelector('[data-send]');
      if (btn) { e.preventDefault(); btn.click(); }
    }
  });

  // Deep link: /#task-123 opens that row (if it is in another tab, the server picks the tab).
  function openFromHash() {
    var id = location.hash.slice(1);
    if (!/^(task|event)-\d+$/.test(id)) return;
    var row = document.getElementById(id);
    if (row && list.contains(row)) {
      if (!row.classList.contains('open')) { closeAll(row); setOpen(row, true); load(row); }
      row.scrollIntoView({ block: 'start' });
    } else if (id.indexOf('task-') === 0 && !/[?&]open=/.test(location.search)) {
      location.replace('/?open=' + id.slice(5) + '#' + id);
    }
  }
  window.addEventListener('hashchange', openFromHash);
  openFromHash();
})();
