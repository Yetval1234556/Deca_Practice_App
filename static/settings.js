document.addEventListener("DOMContentLoaded", () => {
  if (window.Theme && typeof window.Theme.init === "function") {
    window.Theme.init();
  }
  const label = document.getElementById("theme-label");
  const themeButtons = Array.from(document.querySelectorAll("[data-theme-option]"));
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
});
