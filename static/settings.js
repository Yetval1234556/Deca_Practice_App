document.addEventListener("DOMContentLoaded", () => {
  if (window.Theme && typeof window.Theme.init === "function") {
    window.Theme.init();
  }
  const RANDOM_KEY = "deca-random-order";
  const label = document.getElementById("theme-label");
  const themeButtons = Array.from(document.querySelectorAll("[data-theme-option]"));
  const randomToggle = document.getElementById("random-order-toggle");
  const prettyNames = {
    light: "Light",
    dark: "Dark",
    midnight: "Midnight",
    forest: "Forest",
    ocean: "Ocean",
  };

  function updateLabel(theme) {
    if (label) {
      label.textContent = prettyNames[theme] || "Light";
    }
    themeButtons.forEach((btn) => {
      const isActive = btn.dataset.theme === theme;
      btn.classList.toggle("active", isActive);
      btn.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
  }

  const initial = window.Theme ? window.Theme.get() : "light";
  updateLabel(initial);

  themeButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const nextTheme = btn.dataset.theme || "light";
      if (window.Theme && typeof window.Theme.apply === "function") {
        window.Theme.apply(nextTheme);
      } else {
        document.documentElement.setAttribute("data-theme", nextTheme);
      }
      updateLabel(nextTheme);
    });
  });

  function getRandomPref() {
    const fallback =
      typeof window !== "undefined" && typeof window.DEFAULT_RANDOM_ORDER !== "undefined"
        ? String(window.DEFAULT_RANDOM_ORDER).toLowerCase() === "true"
        : false;
    try {
      const stored = localStorage.getItem(RANDOM_KEY);
      if (stored === null) return fallback;
      return stored === "true";
    } catch (err) {
      return fallback;
    }
  }

  function setRandomPref(value) {
    try {
      localStorage.setItem(RANDOM_KEY, value ? "true" : "false");
    } catch (err) {
      // ignore
    }
  }

  function updateRandomToggle() {
    const enabled = getRandomPref();
    if (randomToggle) {
      randomToggle.textContent = enabled ? "Enabled" : "Disabled";
      randomToggle.classList.toggle("active", enabled);
      randomToggle.ariaPressed = enabled ? "true" : "false";
    }
  }

  if (randomToggle) {
    randomToggle.addEventListener("click", () => {
      const next = !getRandomPref();
      setRandomPref(next);
      updateRandomToggle();
    });
    updateRandomToggle();
  }
});
