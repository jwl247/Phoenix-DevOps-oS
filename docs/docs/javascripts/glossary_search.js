// Client-side glossary search.
// Adds a search box and filters glossary list items as you type.

(function () {
  function hasGlossary() {
    return !!document.querySelector('.az-bar') || Array.from(document.querySelectorAll('h1,h2')).some(h => (h.textContent || '').includes('Glossary'));
  }

  function createSearchUI() {
    const container = document.createElement('div');
    container.className = 'glossary-search';

    const input = document.createElement('input');
    input.type = 'search';
    input.placeholder = 'Search glossary terms…';
    input.setAttribute('aria-label', 'Search glossary terms');

    const hint = document.createElement('span');
    hint.className = 'hint';
    hint.textContent = 'Tip: Press A–Z to jump letters.';

    container.appendChild(input);
    container.appendChild(hint);

    return { container, input };
  }

  function normalize(s) { return (s || '').toLowerCase(); }

  function getMainContent() {
    return document.querySelector('main') || document.querySelector('article') || document.body;
  }

  function getListItems() {
    const main = getMainContent();
    return Array.from(main.querySelectorAll('li'));
  }

  function attachSearch() {
    if (!hasGlossary()) return;
    if (document.querySelector('.glossary-search')) return;

    const h1 = document.querySelector('h1');
    if (!h1) return;

    const { container, input } = createSearchUI();
    h1.insertAdjacentElement('afterend', container);

    const items = getListItems();

    function applyFilter() {
      const q = normalize(input.value).trim();
      if (!q) {
        items.forEach(li => li.classList.remove('glossary-hidden'));
        return;
      }
      items.forEach(li => {
        const text = normalize(li.textContent);
        if (text.includes(q)) li.classList.remove('glossary-hidden');
        else li.classList.add('glossary-hidden');
      });
    }

    input.addEventListener('input', applyFilter);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', attachSearch);
  else attachSearch();
})();
