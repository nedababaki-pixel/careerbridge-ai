// Applies the saved theme before the page is painted (avoids a flash of the wrong theme).
(function () {
  try {
    var saved = localStorage.getItem("cb-theme");
    if (saved === "light" || saved === "dark") document.documentElement.dataset.theme = saved;
  } catch (e) { /* storage unavailable: follow the system setting */ }
})();
