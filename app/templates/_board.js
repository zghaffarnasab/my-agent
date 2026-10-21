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
