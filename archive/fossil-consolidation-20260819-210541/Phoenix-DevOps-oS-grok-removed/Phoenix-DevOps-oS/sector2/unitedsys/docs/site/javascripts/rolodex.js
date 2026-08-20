document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.az-bar a').forEach(function (a) {
    a.addEventListener('click', function (e) {
      e.preventDefault();
      const target = document.getElementById(this.getAttribute('href').slice(1));
      if (target) target.scrollIntoView({ behavior: 'smooth' });
    });
  });
});
