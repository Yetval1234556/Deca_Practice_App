(function () {
  const KEY = "deca-theme";

  function applyTheme(value) {
    const theme = value === "dark" ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(KEY, theme);
    } catch (err) {
      // ignore storage errors
    }
    return theme;
  }

  function currentTheme() {
    return (
      localStorage.getItem(KEY) ||
      document.documentElement.getAttribute("data-theme") ||
      (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
    );
  }

  function initTheme() {
    applyTheme(currentTheme());
  }

  window.Theme = {
    apply: applyTheme,
    init: initTheme,
    get: currentTheme,
  };

  initTheme();
})();
