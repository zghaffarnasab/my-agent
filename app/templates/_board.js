/* Pictures in a task's form: paste a screenshot into the notes box or drop image files on the form, and they join
   the form's file input (shown as small previews). Clicking a card's picture opens it large. */
(function () {
  function addFiles(form, files) {
    var input = form.querySelector('input[type=file][name=images]');
    var pics = Array.prototype.filter.call(files, function (f) { return /^image\//.test(f.type); });
    if (!input || !pics.length || typeof DataTransfer === 'undefined') return false;
    var dt = new DataTransfer();
    Array.prototype.forEach.call(input.files, function (f) { dt.items.add(f); });
    pics.forEach(function (f, i) {
      var name = f.name && f.name !== 'image.png' ? f.name : 'screenshot-' + Date.now() + '-' + i + '.png';
      dt.items.add(new File([f], name, { type: f.type }));
    });
    input.files = dt.files;
    input.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  }
  function preview(input) {
    var list = input.parentNode.querySelector('.new-pics');
    if (!list) return;
    list.querySelectorAll('img').forEach(function (img) { URL.revokeObjectURL(img.src); });
    list.replaceChildren();
    Array.prototype.forEach.call(input.files, function (f) {
      if (!/^image\//.test(f.type)) return;
      var li = document.createElement('li'), img = document.createElement('img');
      img.src = URL.createObjectURL(f);
      img.alt = '';
      li.appendChild(img);
      list.appendChild(li);
    });
    list.hidden = !list.children.length;
  }
  document.addEventListener('change', function (e) {
    if (e.target.matches && e.target.matches('.card-form input[type=file][name=images]')) preview(e.target);
  });
  document.addEventListener('paste', function (e) {
    var form = e.target.closest && e.target.closest('.card-form');
    if (form && e.clipboardData && e.clipboardData.files.length && addFiles(form, e.clipboardData.files)) e.preventDefault();
  });
  function hasFiles(e) { return e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types, 'Files') >= 0; }
  document.addEventListener('dragover', function (e) {
    if (!hasFiles(e)) return;
    e.preventDefault();   // never let a dropped file replace the page
    var form = e.target.closest && e.target.closest('.card-form');
    e.dataTransfer.dropEffect = form ? 'copy' : 'none';
    document.querySelectorAll('.card-form.drop-files').forEach(function (f) { if (f !== form) f.classList.remove('drop-files'); });
    if (form) form.classList.add('drop-files');
  });
  document.addEventListener('drop', function (e) {
    if (!hasFiles(e)) return;
    e.preventDefault();
    document.querySelectorAll('.card-form.drop-files').forEach(function (f) { f.classList.remove('drop-files'); });
    var form = e.target.closest && e.target.closest('.card-form');
    if (form) addFiles(form, e.dataTransfer.files);
  });

  var view = document.getElementById('pic-view');
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a.pic-open');
    if (!a || !view || !view.showModal) return;
    e.preventDefault();
    view.querySelector('img').src = a.href;
    view.showModal();
  });
  if (view) view.addEventListener('click', function (e) { if (e.target === view) view.close(); });
})();

/* Task board: drag a card to another column (or another place in its column). Plain JavaScript, no libraries.
   Without it the board still works: the arrow buttons and the edit form are normal form posts. */
(function () {
  var board = document.getElementById('board');
  if (!board) return;
  var who = board.dataset.who || '';
  var msg = document.getElementById('board-msg');
  var T = {};
  try { T = JSON.parse(document.getElementById('board-i18n').textContent); } catch (e) {}
  var dragged = null;
  var placeholder = document.createElement('li');
  placeholder.className = 'card placeholder';

  // Ask before deleting a card.
  board.addEventListener('click', function (e) {
    var b = e.target.closest('[data-confirm]');
    if (b && !window.confirm(b.dataset.confirm)) e.preventDefault();
  });

  function counts() {
    board.querySelectorAll('.col').forEach(function (col) {
      col.querySelector('h2 .n').textContent = col.querySelectorAll('.card:not(.placeholder)').length;
    });
  }
  function clearDrop() {
    board.querySelectorAll('.col.drop-on').forEach(function (c) { c.classList.remove('drop-on'); });
    if (placeholder.parentNode) placeholder.remove();
  }
  // The card that the dragged one should go just above, from the pointer's height.
  function cardBelow(list, y) {
    var cards = list.querySelectorAll('.card:not(.dragging):not(.placeholder)');
    for (var i = 0; i < cards.length; i++) {
      var r = cards[i].getBoundingClientRect();
      if (y < r.top + r.height / 2) return cards[i];
    }
    return null;
  }

  board.addEventListener('dragstart', function (e) {
    var card = e.target.closest && e.target.closest('.card');
    if (!card || e.target.closest('details[open]')) { if (card) e.preventDefault(); return; }
    dragged = card;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', card.dataset.id);
    placeholder.style.height = card.offsetHeight + 'px';
    setTimeout(function () { card.classList.add('dragging'); }, 0);
  });
  board.addEventListener('dragend', function () {
    if (dragged) dragged.classList.remove('dragging');
    dragged = null;
    clearDrop();
  });
  board.addEventListener('dragover', function (e) {
    if (!dragged) return;
    var col = e.target.closest('.col');
    if (!col) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    if (!col.classList.contains('drop-on')) { clearDrop(); col.classList.add('drop-on'); }
    var list = col.querySelector('.cards');
    var below = cardBelow(list, e.clientY);
    if (below) { if (placeholder.nextSibling !== below) list.insertBefore(placeholder, below); }
    else if (list.lastElementChild !== placeholder) list.appendChild(placeholder);
  });
  board.addEventListener('drop', function (e) {
    if (!dragged || !placeholder.parentNode) return;
    e.preventDefault();
    var card = dragged, list = placeholder.parentNode;
    list.insertBefore(card, placeholder);
    clearDrop();
    var next = card.nextElementSibling;
    var status = list.dataset.status;
    card.classList.toggle('is-done', status === 'done');
    counts();
    // A card put in Blocked opens its form at the "waiting on" field, so the reason is written straight away.
    var details = card.querySelector('details');
    var reason = card.querySelector('input[name=blocked_reason]');
    if (status === 'blocked' && details && reason && !reason.value) {
      details.open = true;
      reason.focus();
    }
    var body = new URLSearchParams({ status: status, before: next && next.dataset.id ? next.dataset.id : '', who: who });
    fetch('/board/cards/' + card.dataset.id + '/move', {
      method: 'POST', credentials: 'same-origin', body: body,
      headers: { 'X-Requested-With': 'fetch' }
    }).then(function (r) {
      if (r.redirected && /\/login/.test(r.url)) { location.href = '/login'; return; }
      if (!r.ok) throw new Error('http ' + r.status);
    }).catch(function () {
      msg.textContent = T.failed || '';
      msg.hidden = false;
      setTimeout(function () { location.reload(); }, 1500);
    });
  });
})();
