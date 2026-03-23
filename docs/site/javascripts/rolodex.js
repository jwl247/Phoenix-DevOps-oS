// Rolodex letter-jump for MkDocs pages.
// Press a-z to jump to the matching anchor id (#a, #b, ...).
// Skips when typing in input/textarea/contentEditable.

(function () {
  function isTypingContext(el) {
    if (!el) return false;
    const tag = (el.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return true;
    if (el.isContentEditable) return true;
    return false;
  }

  function jumpTo(letter) {
    const target = document.getElementById(letter);
    if (!target) return;
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    history.replaceState(null, '', '#' + letter);
  }

  document.addEventListener('keydown', function (ev) {
    if (ev.altKey || ev.ctrlKey || ev.metaKey) return;
    if (isTypingContext(document.activeElement)) return;
    const k = ev.key;
    if (!k || k.length !== 1) return;
    const lower = k.toLowerCase();
    if (lower < 'a' || lower > 'z') return;
    if (!document.getElementById(lower)) return;
    ev.preventDefault();
    jumpTo(lower);
  });
})();
