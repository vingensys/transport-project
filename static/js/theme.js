// static/js/theme.js
// Simple client-side theme switcher using CSS variables + data-theme

document.addEventListener("DOMContentLoaded", function () {
  const THEME_KEY = "ta-theme";
  const body = document.body;

  function applyTheme(theme) {
    if (!theme) return;
    body.setAttribute("data-theme", theme);
  }

  // Load saved theme from localStorage, fallback to body data-theme (purple)
  const savedTheme = window.localStorage.getItem(THEME_KEY);
  const initialTheme = savedTheme || body.getAttribute("data-theme") || "purple";
  applyTheme(initialTheme);

  // Hook up menu items
  document.querySelectorAll("[data-theme-choice]").forEach((el) => {
    el.addEventListener("click", function (e) {
      e.preventDefault();
      const theme = this.getAttribute("data-theme-choice");
      if (!theme) return;
      applyTheme(theme);
      window.localStorage.setItem(THEME_KEY, theme);
    });
  });
});
