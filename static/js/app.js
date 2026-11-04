// Shared behaviour: theme, filter bar, dropdowns, toasts, Ctrl+K palette, chart helpers
(function () {
  var root = document.documentElement;

  /* ---------- Theme ---------- */
  function isDark() {
    var t = root.dataset.theme;
    if (t) return t === "dark";
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  }
  var toggle = document.getElementById("theme-toggle");
  if (toggle) {
    toggle.addEventListener("click", function () {
      var next = isDark() ? "light" : "dark";
      root.dataset.theme = next;
      try { localStorage.setItem("theme", next); } catch (e) {}
      document.dispatchEvent(new CustomEvent("themechange"));
    });
  }
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () {
    document.dispatchEvent(new CustomEvent("themechange"));
  });

  /* ---------- Chart helpers ---------- */
  var probe;
  function resolveColor(varName) {
    // Custom properties may hold color-mix(); let the browser resolve them to rgb()
    if (!probe) {
      probe = document.createElement("span");
      probe.style.display = "none";
      document.body.appendChild(probe);
    }
    probe.style.color = "var(" + varName + ")";
    return getComputedStyle(probe).color;
  }
  var code = document.body.dataset.currency || "USD";
  window.Pulse = {
    isDark: isDark,
    color: resolveColor,
    money: new Intl.NumberFormat("en-US", { style: "currency", currency: code, maximumFractionDigits: 0 }),
    compact: new Intl.NumberFormat("en-US", { style: "currency", currency: code, notation: "compact", maximumFractionDigits: 1 }),
    applyChartDefaults: function () {
      if (!window.Chart) return;
      var C = window.Chart.defaults;
      C.font.family = "Inter, system-ui, sans-serif";
      C.font.size = 12;
      C.color = resolveColor("--text-muted");
      C.plugins.legend.display = false;
      C.plugins.tooltip.backgroundColor = resolveColor("--tooltip-bg");
      C.plugins.tooltip.titleColor = resolveColor("--tooltip-text");
      C.plugins.tooltip.bodyColor = resolveColor("--tooltip-text");
      C.plugins.tooltip.padding = 10;
      C.plugins.tooltip.cornerRadius = 8;
      C.plugins.tooltip.boxPadding = 4;
      C.maintainAspectRatio = false;
    },
    // Rebuild charts when the theme changes so colors follow
    charts: function (build) {
      var list = [];
      function run() {
        list.forEach(function (c) { c.destroy(); });
        window.Pulse.applyChartDefaults();
        list = build() || [];
      }
      run();
      document.addEventListener("themechange", run);
    },
    readJSON: function (id) {
      var el = document.getElementById(id);
      return el ? JSON.parse(el.textContent) : null;
    },
  };

  /* ---------- Dropdowns ---------- */
  document.addEventListener("click", function (e) {
    var toggleBtn = e.target.closest("[data-dropdown-toggle]");
    document.querySelectorAll("[data-dropdown].open").forEach(function (d) {
      if (!toggleBtn || !d.contains(toggleBtn)) d.classList.remove("open");
    });
    if (toggleBtn) toggleBtn.closest("[data-dropdown]").classList.toggle("open");
  });

  /* ---------- Clickable table rows ---------- */
  document.addEventListener("click", function (e) {
    var row = e.target.closest("tr[data-href]");
    if (row && !e.target.closest("a, button, input, select, form")) window.location = row.dataset.href;
  });

  /* ---------- Toasts ---------- */
  setTimeout(function () {
    document.querySelectorAll(".toast").forEach(function (t) { t.classList.add("hide"); });
  }, 5000);

  /* ---------- Confirm buttons ---------- */
  document.addEventListener("submit", function (e) {
    var msg = e.target.dataset.confirm;
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  /* ---------- Filter bar ---------- */
  var form = document.getElementById("filters");
  if (form) {
    var start = form.querySelector('input[name="start"]');
    var end = form.querySelector('input[name="end"]');
    form.querySelectorAll(".segmented button").forEach(function (btn) {
      // A preset click must not be overridden by stale custom dates
      btn.addEventListener("click", function () { start.value = ""; end.value = ""; });
    });
    [start, end].forEach(function (input) {
      input.addEventListener("change", function () {
        if (start.value && end.value) form.requestSubmit();
      });
    });
  }
  // Drop empty fields from every GET form so URLs stay short and shareable
  document.querySelectorAll('form[method="get"]').forEach(function (f) {
    f.addEventListener("formdata", function (e) {
      var data = e.formData;
      Array.from(data.keys()).forEach(function (k) {
        if (!data.getAll(k).some(Boolean)) data.delete(k);
      });
    });
  });

  /* ---------- Command palette ---------- */
  var palette = document.getElementById("palette");
  if (!palette) return;
  var input = document.getElementById("palette-q");
  var results = document.getElementById("palette-results");
  var timer, active = 0, controller;

  function items() { return results.querySelectorAll(".palette-item"); }
  function highlight(i) {
    var list = items();
    if (!list.length) return;
    active = (i + list.length) % list.length;
    list.forEach(function (el, k) { el.classList.toggle("active", k === active); });
    list[active].scrollIntoView({ block: "nearest" });
  }
  function load() {
    if (controller) controller.abort();
    controller = new AbortController();
    fetch(results.dataset.url + "?q=" + encodeURIComponent(input.value), { signal: controller.signal })
      .then(function (r) { return r.text(); })
      .then(function (html) { results.innerHTML = html; highlight(0); })
      .catch(function () {});
  }
  function open() {
    palette.hidden = false;
    document.body.classList.add("palette-open");
    input.value = "";
    input.focus();
    load();
  }
  function close() {
    palette.hidden = true;
    document.body.classList.remove("palette-open");
  }
  document.querySelectorAll("[data-open-search]").forEach(function (b) { b.addEventListener("click", open); });
  palette.addEventListener("click", function (e) { if (e.target === palette) close(); });
  input.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(load, 150); });
  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      palette.hidden ? open() : close();
      return;
    }
    if (palette.hidden) return;
    if (e.key === "Escape") close();
    else if (e.key === "ArrowDown") { e.preventDefault(); highlight(active + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); highlight(active - 1); }
    else if (e.key === "Enter") {
      var el = items()[active];
      if (el) { e.preventDefault(); window.location = el.href; }
    }
  });
})();
