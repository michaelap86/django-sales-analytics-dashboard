// Overview page charts, drawn from the JSON embedded by the view
(function () {
  var data = Pulse.readJSON("chart-data");

  function formatLabel(iso) {
    var d = new Date(iso + "T00:00:00");
    if (data.unit === "month") return d.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }

  Pulse.charts(function () {
    var grid = Pulse.color("--grid");
    var primary = Pulse.color("--primary");
    var surface = Pulse.color("--surface");
    var labels = data.labels.map(formatLabel);
    var moneyAxis = { callback: function (v) { return Pulse.compact.format(v); } };
    var charts = [];

    var revCtx = document.getElementById("revenueChart").getContext("2d");
    var gradient = revCtx.createLinearGradient(0, 0, 0, 320);
    gradient.addColorStop(0, Pulse.color("--primary-fade"));
    gradient.addColorStop(1, "rgba(0,0,0,0)");
    charts.push(new Chart(revCtx, {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          {
            label: "This period", data: data.revenue, borderColor: primary, backgroundColor: gradient,
            fill: true, tension: 0.35, borderWidth: 2.5, pointRadius: 0, pointHoverRadius: 5,
            pointHoverBackgroundColor: primary, pointHoverBorderColor: surface, pointHoverBorderWidth: 2,
          },
          {
            label: "Previous period", data: data.previousRevenue, borderColor: Pulse.color("--series-muted"),
            borderDash: [5, 5], borderWidth: 1.5, tension: 0.35, pointRadius: 0, pointHoverRadius: 4, fill: false,
          },
        ],
      },
      options: {
        interaction: { mode: "index", intersect: false },
        scales: {
          x: { grid: { display: false }, border: { display: false }, ticks: { maxRotation: 0, autoSkipPadding: 16 } },
          y: { grid: { color: grid }, border: { display: false }, ticks: moneyAxis, beginAtZero: true },
        },
        plugins: { tooltip: { callbacks: { label: function (c) { return " " + c.dataset.label + ": " + Pulse.money.format(c.parsed.y || 0); } } } },
      },
    }));

    charts.push(new Chart(document.getElementById("categoryChart"), {
      type: "doughnut",
      data: {
        labels: data.categories.labels,
        datasets: [{ data: data.categories.values, backgroundColor: data.categories.colors, borderColor: surface, borderWidth: 3, hoverOffset: 6 }],
      },
      options: {
        cutout: "70%",
        plugins: { tooltip: { callbacks: { label: function (c) { return " " + c.label + ": " + Pulse.money.format(c.parsed); } } } },
      },
    }));

    charts.push(new Chart(document.getElementById("regionChart"), {
      type: "bar",
      data: { labels: data.regions.labels, datasets: [{ data: data.regions.values, backgroundColor: primary, borderRadius: 6, barThickness: 18 }] },
      options: {
        indexAxis: "y",
        scales: {
          x: { grid: { color: grid }, border: { display: false }, ticks: moneyAxis },
          y: { grid: { display: false }, border: { display: false } },
        },
        plugins: { tooltip: { displayColors: false, callbacks: { label: function (c) { return Pulse.money.format(c.parsed.x); } } } },
      },
    }));

    charts.push(new Chart(document.getElementById("ordersChart"), {
      type: "bar",
      data: { labels: labels, datasets: [{ label: "Orders", data: data.orders, backgroundColor: Pulse.color("--accent"), borderRadius: 4, maxBarThickness: 22 }] },
      options: {
        scales: {
          x: { grid: { display: false }, border: { display: false }, ticks: { maxRotation: 0, autoSkipPadding: 16 } },
          y: { grid: { color: grid }, border: { display: false }, beginAtZero: true, ticks: { precision: 0 } },
        },
        plugins: { tooltip: { displayColors: false } },
      },
    }));

    var statusColors = ["--status-pending", "--status-paid", "--status-shipped", "--status-delivered", "--status-refunded"].map(Pulse.color);
    charts.push(new Chart(document.getElementById("statusChart"), {
      type: "bar",
      data: { labels: data.statuses.labels, datasets: [{ data: data.statuses.values, backgroundColor: statusColors, borderRadius: 6, maxBarThickness: 34 }] },
      options: {
        scales: {
          x: { grid: { display: false }, border: { display: false } },
          y: { grid: { color: grid }, border: { display: false }, beginAtZero: true, ticks: { precision: 0 } },
        },
        plugins: { tooltip: { displayColors: false, callbacks: { label: function (c) { return c.parsed.y.toLocaleString() + " orders"; } } } },
      },
    }));
    return charts;
  });
})();
