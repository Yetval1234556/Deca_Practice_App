(function () {
  const KEY = "deca-theme";
  const THEMES = ["light", "dark", "midnight", "forest", "ocean"];

  function applyTheme(value) {
    const normalized = typeof value === "string" ? value.toLowerCase() : "";
    const theme = THEMES.includes(normalized) ? normalized : "light";
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(KEY, theme);
    } catch (err) {
      // ignore storage errors
    }
    return theme;
  }

  function currentTheme() {
    const cached = localStorage.getItem(KEY);
    if (THEMES.includes(cached)) return cached;
    return (
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
    list: () => [...THEMES],
  };

  initTheme();

  // Performance Mode Init
  (function () {
    try {
      const perf = localStorage.getItem("deca-perf-mode") === "true";
      if (perf) document.documentElement.classList.add("perf-mode");
    } catch (e) { }
  })();
})();
