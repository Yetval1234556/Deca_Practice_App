document.addEventListener("DOMContentLoaded", () => {
  if (window.Theme && typeof window.Theme.init === "function") {
    window.Theme.init();
  }
  const toggle = document.getElementById("theme-toggle");
  const label = document.getElementById("theme-label");

  function updateLabel(theme) {
    if (label) {
      label.textContent = theme === "dark" ? "Dark" : "Light";
    }
    if (toggle) {
      toggle.checked = theme === "dark";
    }
  }

  const initial = window.Theme ? window.Theme.get() : "light";
  updateLabel(initial);

  if (toggle) {
    toggle.addEventListener("change", () => {
      const nextTheme = toggle.checked ? "dark" : "light";
      if (window.Theme && typeof window.Theme.apply === "function") {
        window.Theme.apply(nextTheme);
      } else {
        document.documentElement.setAttribute("data-theme", nextTheme);
      }
      updateLabel(nextTheme);
    });
  }
});
