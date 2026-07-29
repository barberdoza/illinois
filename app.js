(function () {
  "use strict";

  const CATEGORY_ORDER = ["BARBER", "SALON_SHOP", "UNKNOWN"];

  const state = {
    data: null,
    selectedCounty: null,
    map: null,
  };

  const els = {
    search: document.getElementById("county-search"),
    countyList: document.getElementById("county-list"),
    finderHint: document.getElementById("finder-hint"),
    summary: document.getElementById("summary"),
    rankTitle: document.getElementById("rank-title"),
    rankChart: document.getElementById("rank-chart"),
    tableBody: document.getElementById("data-table-body"),
    sampleBanner: document.getElementById("sample-banner"),
    unclassifiedBanner: document.getElementById("unclassified-banner"),
    unclassifiedText: document.getElementById("unclassified-text"),
    sourceLabel: document.getElementById("source-label"),
    updatedLabel: document.getElementById("updated-label"),
  };

  function fmtNumber(n) {
    if (n === null || n === undefined) return "—";
    return n.toLocaleString("en-US");
  }

  function findRollup(countyName) {
    const q = countyName.trim().toLowerCase();
    if (!q) return null;
    return (
      state.data.rollup.find((r) => r.county.toLowerCase() === q) ||
      state.data.rollup.find((r) => r.county.toLowerCase().startsWith(q)) ||
      null
    );
  }

  function statewideTotals() {
    const totals = { total: 0 };
    CATEGORY_ORDER.forEach((code) => (totals[code] = 0));
    state.data.rollup.forEach((r) => {
      totals.total += r.total;
      CATEGORY_ORDER.forEach((code) => (totals[code] += r[code] || 0));
    });
    return totals;
  }

  function renderSummary() {
    const sel = state.selectedCounty ? findRollup(state.selectedCounty) : null;
    const title = sel ? `${sel.county} County` : "Illinois (all counties)";
    const totals = sel || statewideTotals();

    let rankBadge = "";
    if (sel) {
      const sorted = [...state.data.rollup].sort((a, b) => b.total - a.total);
      const rank = sorted.findIndex((r) => r.county === sel.county) + 1;
      rankBadge = `<span class="rank-badge">#${rank} of ${sorted.length} counties</span>`;
    }

    const boards = ["BARBER", "SALON_SHOP"]
      .map((code) => `
        <div class="board">
          <h3>${state.data.categories[code] || code}</h3>
          <dl><div class="row"><dt>Active licensed shops</dt><dd>${fmtNumber(totals[code] || 0)}</dd></div></dl>
        </div>`)
      .join("");

    els.summary.innerHTML = `
      <div class="detail-heading">
        <h2>${title}</h2>
        ${rankBadge}
      </div>
      <p class="summary-total">
        <span class="summary-total-value">${fmtNumber(totals.total)}</span>
        total active licensed shops
      </p>
      <div class="board-grid">${boards}</div>
    `;
  }

  function renderRankChart() {
    const ranked = [...state.data.rollup].sort((a, b) => b.total - a.total);
    const max = ranked[0] ? ranked[0].total : 1;
    const showCount = 15;
    let list = ranked.slice(0, showCount);

    if (state.selectedCounty) {
      const sel = findRollup(state.selectedCounty);
      if (sel && !list.find((r) => r.county === sel.county)) list = list.concat([sel]);
    }

    els.rankChart.innerHTML = list
      .map((r) => {
        const pct = Math.max(2, (r.total / max) * 100);
        const isCurrent = state.selectedCounty && r.county.toLowerCase() === state.selectedCounty.trim().toLowerCase();
        return `
          <div class="rank-row${isCurrent ? " is-current" : ""}">
            <div class="rank-name">${r.county}</div>
            <div class="rank-bar-track"><div class="rank-bar-fill" style="width:${pct}%"></div></div>
            <div class="rank-value">${fmtNumber(r.total)}</div>
          </div>`;
      })
      .join("");

    if (ranked.length > showCount) {
      const more = document.createElement("p");
      more.className = "rank-more";
      more.textContent = `Showing top ${showCount} of ${ranked.length} counties. Full list in the table below.`;
      els.rankChart.appendChild(more);
    }
  }

  function renderTable() {
    const query = els.search.value.trim().toLowerCase();
    const rows = state.data.rollup
      .filter((r) => !query || r.county.toLowerCase().includes(query))
      .map((r) => {
        const isCurrent = state.selectedCounty && r.county.toLowerCase() === state.selectedCounty.trim().toLowerCase();
        return `
          <tr class="${isCurrent ? "is-current-row" : ""}" data-county="${r.county}">
            <td>${r.county}</td>
            <td>${fmtNumber(r.BARBER || 0)}</td>
            <td>${fmtNumber(r.SALON_SHOP || 0)}</td>
            <td class="td-total">${fmtNumber(r.total)}</td>
          </tr>`;
      })
      .join("");

    els.tableBody.innerHTML = rows || `<tr><td colspan="4">No counties match "${els.search.value}".</td></tr>`;
  }

  function radiusFor(total, maxTotal) {
    // area-proportional circle sizing, clamped to a sane visual range
    const minR = 4, maxR = 40;
    const scale = Math.sqrt(total / maxTotal || 0);
    return Math.max(minR, scale * maxR);
  }

  function buildMap() {
    state.map = L.map("map", { scrollWheelZoom: true }).setView([40.0, -89.2], 6);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
      maxZoom: 18,
    }).addTo(state.map);

    const maxTotal = Math.max(...state.data.rollup.map((r) => r.total), 1);
    state.data.rollup.forEach((r) => {
      if (r.lat == null || r.lon == null) return;
      const circle = L.circleMarker([r.lat, r.lon], {
        radius: radiusFor(r.total, maxTotal),
        color: "#183E43",
        weight: 1,
        fillColor: "#C79A3E",
        fillOpacity: 0.65,
      }).addTo(state.map);
      circle.bindPopup(`<strong>${r.county} County</strong><br />${fmtNumber(r.total)} active licensed shops`);
    });
  }

  function flyToCounty(countyName) {
    if (!state.map) return;
    const r = findRollup(countyName);
    if (r && r.lat != null && r.lon != null) {
      state.map.flyTo([r.lat, r.lon], 9, { duration: 0.8 });
    }
  }

  function renderAll() {
    renderSummary();
    renderRankChart();
    renderTable();
  }

  function selectFromSearch() {
    const q = els.search.value.trim();
    const match = q ? findRollup(q) : null;
    state.selectedCounty = match ? match.county : null;
    els.finderHint.textContent = state.selectedCounty
      ? `Showing ${state.selectedCounty} County. Clear the search to see statewide totals.`
      : "Showing statewide totals until you pick a county.";
    renderAll();
    if (match) flyToCounty(match.county);
  }

  function init(data) {
    state.data = data;

    if (data.is_sample) els.sampleBanner.hidden = false;

    const unknownTypes = Object.keys(data.unclassified_license_types || {});
    if (unknownTypes.length) {
      els.unclassifiedBanner.hidden = false;
      const totalUnknown = Object.values(data.unclassified_license_types).reduce((a, b) => a + b, 0);
      els.unclassifiedText.textContent =
        `Heads up: ${totalUnknown.toLocaleString()} records had a license description this app didn't recognize ` +
        `(${unknownTypes.slice(0, 5).join(", ")}${unknownTypes.length > 5 ? ", …" : ""}) — ` +
        `they're counted under "Unclassified" rather than dropped.`;
    }

    els.sourceLabel.textContent = data.source;
    els.updatedLabel.textContent = new Date(data.generated_at).toLocaleDateString("en-US", {
      year: "numeric", month: "long", day: "numeric",
    });

    els.countyList.innerHTML = data.rollup.map((r) => `<option value="${r.county}"></option>`).join("");
    els.search.addEventListener("input", selectFromSearch);

    els.tableBody.addEventListener("click", (e) => {
      const row = e.target.closest("tr[data-county]");
      if (!row) return;
      els.search.value = row.dataset.county;
      selectFromSearch();
    });

    buildMap();
    renderAll();
  }

  fetch("data/il_shops.json")
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(init)
    .catch((err) => {
      els.summary.innerHTML = `<p class="muted">Couldn't load data/il_shops.json (${err.message}). If you're running this locally, serve the folder with a local server (e.g. <code>python3 -m http.server</code>) rather than opening the file directly.</p>`;
    });
})();
