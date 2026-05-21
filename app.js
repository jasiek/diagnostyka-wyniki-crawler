"use strict";

const PALETTE = [
  "#2d6cdf", "#dc3545", "#28a745", "#fd7e14", "#6f42c1",
  "#20c997", "#e83e8c", "#17a2b8", "#ffc107", "#6610f2",
  "#198754", "#d63384", "#0dcaf0", "#fd5e53", "#795548",
  "#607d8b", "#8bc34a", "#9c27b0", "#3f51b5", "#cddc39",
];

const state = {
  parameters: new Map(),      // key -> { label, group, unit, points: [{date, raw, normalized, ref}], ref }
  selected: new Map(),        // key -> color
  colorPool: [...PALETTE],
};

let chart = null;

function cleanLabel(label) {
  return label.replace(/\s*\(ICD-9:[^)]+\)\s*$/, "").trim();
}

function pickCanonicalUnit(entries) {
  const counts = new Map();
  for (const e of entries) {
    const u = e.measurement.original.unit;
    if (!u) continue;
    counts.set(u, (counts.get(u) || 0) + 1);
  }
  let best = null;
  let bestN = -1;
  for (const [u, n] of counts) {
    if (n > bestN) { best = u; bestN = n; }
  }
  return best;
}

function extractValueInUnit(entry, unit) {
  const orig = entry.measurement.original;
  if (orig.unit === unit) {
    return { value: orig.value, refLow: orig.reference_low, refHigh: orig.reference_high };
  }
  for (const alt of entry.measurement.alternatives || []) {
    if (alt.unit === unit) {
      return { value: alt.value, refLow: alt.reference_low, refHigh: alt.reference_high };
    }
  }
  return null;
}

function buildParameters(data) {
  const byLabel = new Map();
  for (const e of data) {
    if (!byLabel.has(e.parameter_label)) byLabel.set(e.parameter_label, []);
    byLabel.get(e.parameter_label).push(e);
  }

  const params = new Map();
  for (const [label, entries] of byLabel) {
    const unit = pickCanonicalUnit(entries);
    if (!unit) continue;

    // Determine canonical reference range: take the most-common (low, high) pair seen in this unit.
    const refCounts = new Map();
    for (const e of entries) {
      const v = extractValueInUnit(e, unit);
      if (!v) continue;
      if (v.refLow == null || v.refHigh == null || v.refLow === v.refHigh) continue;
      const k = `${v.refLow}|${v.refHigh}`;
      refCounts.set(k, (refCounts.get(k) || 0) + 1);
    }
    if (refCounts.size === 0) continue; // skip params with no usable reference range

    let bestRef = null;
    let bestRefN = -1;
    for (const [k, n] of refCounts) {
      if (n > bestRefN) { bestRef = k; bestRefN = n; }
    }
    const [refLow, refHigh] = bestRef.split("|").map(Number);
    const mid = (refLow + refHigh) / 2;
    const halfRange = (refHigh - refLow) / 2;

    const points = [];
    for (const e of entries) {
      const v = extractValueInUnit(e, unit);
      if (!v || typeof v.value !== "number") continue;
      const date = new Date(e.date_time);
      if (isNaN(date.getTime())) continue;
      const normalized = (v.value - mid) / halfRange;
      points.push({
        date,
        raw: v.value,
        normalized,
        refLow: v.refLow,
        refHigh: v.refHigh,
      });
    }
    if (points.length === 0) continue;
    points.sort((a, b) => a.date - b.date);

    const group = entries[0].group;
    const key = label;
    params.set(key, {
      key,
      label: cleanLabel(label),
      rawLabel: label,
      group,
      unit,
      refLow,
      refHigh,
      points,
    });
  }
  return params;
}

function renderSidebar() {
  const container = document.getElementById("parameter-list");
  container.innerHTML = "";

  const byGroup = new Map();
  for (const p of state.parameters.values()) {
    if (!byGroup.has(p.group)) byGroup.set(p.group, []);
    byGroup.get(p.group).push(p);
  }

  const groupNames = [...byGroup.keys()].sort();
  for (const groupName of groupNames) {
    const groupEl = document.createElement("div");
    groupEl.className = "group";
    const title = document.createElement("div");
    title.className = "group-title";
    title.textContent = groupName;
    groupEl.appendChild(title);

    const params = byGroup.get(groupName).sort((a, b) => a.label.localeCompare(b.label));
    for (const p of params) {
      const row = document.createElement("label");
      row.className = "param";
      row.dataset.key = p.key;
      row.dataset.search = (p.label + " " + groupName).toLowerCase();

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.addEventListener("change", () => toggleParameter(p.key, cb.checked, row));

      const swatch = document.createElement("span");
      swatch.className = "swatch";

      const labelEl = document.createElement("span");
      labelEl.className = "label";
      labelEl.textContent = p.label;

      const count = document.createElement("span");
      count.className = "count";
      count.textContent = `${p.points.length}× ${p.unit}`;

      row.append(cb, swatch, labelEl, count);
      groupEl.appendChild(row);
    }
    container.appendChild(groupEl);
  }
}

function toggleParameter(key, on, rowEl) {
  if (on) {
    let color = state.colorPool.shift();
    if (!color) color = `hsl(${Math.floor(Math.random() * 360)}, 65%, 50%)`;
    state.selected.set(key, color);
    rowEl.querySelector(".swatch").style.background = color;
  } else {
    const c = state.selected.get(key);
    if (c && PALETTE.includes(c)) state.colorPool.push(c);
    state.selected.delete(key);
    rowEl.querySelector(".swatch").style.background = "transparent";
  }
  document.getElementById("selection-count").textContent =
    `${state.selected.size} selected`;
  renderChart();
}

function clearAll() {
  state.selected.clear();
  state.colorPool = [...PALETTE];
  document.querySelectorAll(".param").forEach(row => {
    row.querySelector("input").checked = false;
    row.querySelector(".swatch").style.background = "transparent";
  });
  document.getElementById("selection-count").textContent = "0 selected";
  renderChart();
}

function applyFilter(q) {
  const needle = q.trim().toLowerCase();
  document.querySelectorAll(".param").forEach(row => {
    row.classList.toggle("hidden", needle && !row.dataset.search.includes(needle));
  });
  // Hide group titles whose children are all hidden
  document.querySelectorAll(".group").forEach(g => {
    const visible = [...g.querySelectorAll(".param")].some(p => !p.classList.contains("hidden"));
    g.style.display = visible ? "" : "none";
  });
}

function buildReferenceBandPlugin() {
  return {
    id: "referenceBand",
    beforeDatasetsDraw(c) {
      const { ctx, chartArea, scales } = c;
      const y = scales.y;
      if (!y) return;
      const top = y.getPixelForValue(1);
      const bottom = y.getPixelForValue(-1);
      ctx.save();
      ctx.fillStyle = "rgba(46, 160, 67, 0.08)";
      ctx.fillRect(chartArea.left, top, chartArea.right - chartArea.left, bottom - top);
      ctx.strokeStyle = "rgba(46, 160, 67, 0.35)";
      ctx.setLineDash([4, 4]);
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(chartArea.left, top);
      ctx.lineTo(chartArea.right, top);
      ctx.moveTo(chartArea.left, bottom);
      ctx.lineTo(chartArea.right, bottom);
      ctx.stroke();
      // Midline
      const mid = y.getPixelForValue(0);
      ctx.setLineDash([]);
      ctx.strokeStyle = "rgba(0, 0, 0, 0.08)";
      ctx.beginPath();
      ctx.moveTo(chartArea.left, mid);
      ctx.lineTo(chartArea.right, mid);
      ctx.stroke();
      ctx.restore();
    },
  };
}

function renderChart() {
  const emptyEl = document.getElementById("empty-state");
  emptyEl.classList.toggle("hidden", state.selected.size > 0);

  const datasets = [];
  for (const [key, color] of state.selected) {
    const p = state.parameters.get(key);
    if (!p) continue;
    datasets.push({
      label: `${p.label} (${p.unit})`,
      borderColor: color,
      backgroundColor: color,
      pointRadius: 4,
      pointHoverRadius: 6,
      borderWidth: 2,
      tension: 0,
      spanGaps: true,
      data: p.points.map(pt => ({
        x: pt.date,
        y: pt.normalized,
        raw: pt.raw,
        refLow: pt.refLow,
        refHigh: pt.refHigh,
        unit: p.unit,
      })),
    });
  }

  if (chart) {
    chart.data.datasets = datasets;
    chart.update();
    return;
  }

  const ctx = document.getElementById("chart").getContext("2d");
  chart = new Chart(ctx, {
    type: "line",
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "index", intersect: false, axis: "x" },
      plugins: {
        legend: { position: "top", labels: { boxWidth: 12, boxHeight: 12 } },
        tooltip: {
          mode: "index",
          intersect: false,
          callbacks: {
            title(items) {
              if (!items.length) return "";
              const d = new Date(items[0].parsed.x);
              return d.toLocaleString(undefined, {
                year: "numeric", month: "short", day: "2-digit",
                hour: "2-digit", minute: "2-digit",
              });
            },
            label(item) {
              const raw = item.raw;
              const fmt = v => (v == null ? "" : Number(v.toPrecision(4)).toString());
              const refTxt = (raw.refLow != null && raw.refHigh != null)
                ? ` (ref ${fmt(raw.refLow)}–${fmt(raw.refHigh)} ${raw.unit})`
                : "";
              const flag = Math.abs(item.parsed.y) > 1 ? "  ⚠" : "";
              const name = item.dataset.label.replace(/ \(.*\)$/, "");
              return `${name}: ${fmt(raw.raw)} ${raw.unit}${refTxt}${flag}`;
            },
          },
        },
      },
      scales: {
        x: {
          type: "time",
          time: { tooltipFormat: "PP HH:mm" },
          ticks: { maxRotation: 0, autoSkipPadding: 20 },
          grid: { color: "rgba(0,0,0,0.04)" },
        },
        y: {
          title: { display: true, text: "Normalized (−1 = ref low, +1 = ref high)" },
          grid: { color: "rgba(0,0,0,0.04)" },
        },
      },
    },
    plugins: [buildReferenceBandPlugin()],
  });
}

async function main() {
  const res = await fetch("lab_results.json");
  if (!res.ok) throw new Error(`Failed to load lab_results.json: ${res.status}`);
  const data = await res.json();
  state.parameters = buildParameters(data);
  renderSidebar();
  renderChart();

  document.getElementById("filter").addEventListener("input", e => applyFilter(e.target.value));
  document.getElementById("clear-all").addEventListener("click", clearAll);
}

main().catch(err => {
  console.error(err);
  document.getElementById("empty-state").textContent = `Error: ${err.message}`;
});
