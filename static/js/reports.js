// Reports page charts
(function () {
  var data = Pulse.readJSON("chart-data");

  function monthLabel(iso) {
    return new Date(iso + "T00:00:00").toLocaleDateString("en-US", { month: "short", year: "2-digit" });
  }

  Pulse.charts(function () {
    var grid = Pulse.color("--grid");
    var primary = Pulse.color("--primary");
    var accent = Pulse.color("--accent");
    var moneyTicks = { callback: function (v) { return Pulse.compact.format(v); } };
    var moneyTip = function (c) { return " " + c.dataset.label + ": " + Pulse.money.format(c.parsed.y); };
    var charts = [];

    charts.push(new Chart(document.getElementById("yoyChart"), {
      type: "bar",
      data: {
        labels: data.yoy.labels,
        datasets: [
          { label: String(data.yoy.year), data: data.yoy.thisYear, backgroundColor: primary, borderRadius: 4, maxBarThickness: 18 },
          { label: String(data.yoy.year - 1), data: data.yoy.lastYear, backgroundColor: Pulse.color("--series-muted"), borderRadius: 4, maxBarThickness: 18 },
        ],
      },
      options: {
        interaction: { mode: "index", intersect: false },
        scales: {
          x: { grid: { display: false }, border: { display: false } },
          y: { grid: { color: grid }, border: { display: false }, beginAtZero: true, ticks: moneyTicks },
        },
        plugins: { tooltip: { callbacks: { label: moneyTip } } },
      },
    }));

    var fc = data.forecast;
    if (fc) {
      charts.push(new Chart(document.getElementById("forecastChart"), {
        type: "line",
        data: {
          labels: fc.labels.map(monthLabel),
          datasets: [
            { label: "High", data: fc.high, borderWidth: 0, pointRadius: 0, fill: "+1", backgroundColor: Pulse.color("--accent-fade") },
            { label: "Low", data: fc.low, borderWidth: 0, pointRadius: 0, fill: false },
            { label: "Actual", data: fc.actual, borderColor: primary, backgroundColor: primary, tension: 0.3, borderWidth: 2.5, pointRadius: 0, pointHoverRadius: 4 },
            { label: "Forecast", data: fc.predicted, borderColor: accent, backgroundColor: accent, borderDash: [6, 4], tension: 0.3, borderWidth: 2.5, pointRadius: 3 },
          ],
        },
        options: {
          interaction: { mode: "index", intersect: false },
          scales: {
            x: { grid: { display: false }, border: { display: false }, ticks: { maxRotation: 0, autoSkipPadding: 12 } },
            y: { grid: { color: grid }, border: { display: false }, beginAtZero: true, ticks: moneyTicks },
          },
          plugins: {
            tooltip: {
              filter: function (item) { return item.parsed.y !== null && item.dataset.label !== "High" && item.dataset.label !== "Low"; },
              callbacks: { label: moneyTip },
            },
          },
        },
      }));
    }

    var paymentColors = [primary, accent, Pulse.color("--status-pending")];
    charts.push(new Chart(document.getElementById("paymentChart"), {
      type: "doughnut",
      data: { labels: data.payments.labels, datasets: [{ data: data.payments.values, backgroundColor: paymentColors, borderColor: Pulse.color("--surface"), borderWidth: 3 }] },
      options: {
        cutout: "66%",
        plugins: {
          legend: { display: true, position: "right", labels: { usePointStyle: true, pointStyle: "circle", boxWidth: 8, padding: 14 } },
          tooltip: { callbacks: { label: function (c) { return " " + c.label + ": " + c.parsed.toLocaleString() + " orders"; } } },
        },
      },
    }));
    return charts;
  });
})();
