document.addEventListener('DOMContentLoaded', function () {
  const input = document.getElementById('gloss-search');
  if (!input) return;
  input.addEventListener('keyup', function () {
    const q = this.value.toLowerCase();
    document.querySelectorAll('.gloss-entry').forEach(function (el) {
      el.style.display = el.textContent.toLowerCase().includes(q) ? '' : 'none';
    });
  });
});
