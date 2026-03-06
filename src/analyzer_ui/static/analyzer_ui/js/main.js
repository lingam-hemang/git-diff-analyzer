/* main.js — copy-to-clipboard and form spinner helpers */

document.addEventListener('DOMContentLoaded', function () {
  // Copy-to-clipboard for SQL blocks (global fallback; detail page also has inline handler)
  document.querySelectorAll('.copy-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var targetId = btn.getAttribute('data-target');
      var pre = document.getElementById(targetId);
      if (pre && navigator.clipboard) {
        navigator.clipboard.writeText(pre.innerText).then(function () {
          btn.textContent = 'Copied!';
          setTimeout(function () { btn.textContent = 'Copy'; }, 1500);
        });
      }
    });
  });
});
