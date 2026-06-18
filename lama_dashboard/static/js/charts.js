// Intelligence page charts

Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.color = '#6B7280';

const CHART_PURPLE = '#6B5CF6';

// ── A: Funding by year ──────────────────────────────────────────────────────

function buildFundingCharts() {
  const years = Object.keys(YEARLY_FUNDING).sort();
  const totals = years.map(y => Math.round(YEARLY_FUNDING[y].total));
  const counts = years.map(y => YEARLY_FUNDING[y].count);

  new Chart(document.getElementById('chart-funding-year'), {
    type: 'bar',
    data: {
      labels: years,
      datasets: [{
        label: 'Total ($M)',
        data: totals,
        backgroundColor: CHART_PURPLE,
        borderRadius: 6,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, grid: { color: '#f3f4f6' } } }
    }
  });

  new Chart(document.getElementById('chart-deals-year'), {
    type: 'bar',
    data: {
      labels: years,
      datasets: [{
        label: 'Deal Count',
        data: counts,
        backgroundColor: '#0EA5E9',
        borderRadius: 6,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, grid: { color: '#f3f4f6' } } }
    }
  });
}

// ── B: Sector charts ────────────────────────────────────────────────────────

function buildSectorCharts() {
  const entries = Object.entries(SECTOR_BREAKDOWN)
    .sort((a, b) => b[1].total_raised - a[1].total_raised);
  const labels = entries.map(([s]) => s);
  const capitals = entries.map(([, v]) => Math.round(v.total_raised));
  const colors = entries.map(([s]) => SECTOR_COLORS_MAP[s] || '#6366F1');

  new Chart(document.getElementById('chart-sector-capital'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{ data: capitals, backgroundColor: colors, borderRadius: 4 }]
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { x: { beginAtZero: true, grid: { color: '#f3f4f6' } } }
    }
  });

  const countEntries = Object.entries(SECTOR_BREAKDOWN)
    .sort((a, b) => b[1].count - a[1].count);
  new Chart(document.getElementById('chart-sector-count'), {
    type: 'doughnut',
    data: {
      labels: countEntries.map(([s]) => s),
      datasets: [{
        data: countEntries.map(([, v]) => v.count),
        backgroundColor: countEntries.map(([s]) => SECTOR_COLORS_MAP[s] || '#6366F1'),
        borderWidth: 2,
        borderColor: '#fff',
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'right', labels: { font: { size: 11 }, boxWidth: 12 } } }
    }
  });
}

// ── C: 8200 sector chart ────────────────────────────────────────────────────

function build8200Chart(companies) {
  const sectorMap = {};
  const sectorTotal = {};
  companies.forEach(c => {
    const s = c.sector;
    sectorTotal[s] = (sectorTotal[s] || 0) + 1;
    if (c.is_8200) sectorMap[s] = (sectorMap[s] || 0) + 1;
  });

  // 8200 pct by sector
  const entries = Object.entries(sectorMap)
    .map(([s, n]) => [s, Math.round(n / sectorTotal[s] * 100)])
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8);

  new Chart(document.getElementById('chart-8200-sector'), {
    type: 'bar',
    data: {
      labels: entries.map(([s]) => s),
      datasets: [{
        data: entries.map(([, p]) => p),
        backgroundColor: entries.map(([s]) => SECTOR_COLORS_MAP[s] || '#6366F1'),
        borderRadius: 4,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => ctx.parsed.y + '% 8200-founded' } }
      },
      scales: {
        y: { beginAtZero: true, max: 100, ticks: { callback: v => v + '%' }, grid: { color: '#f3f4f6' } }
      }
    }
  });
}

// ── Hot tables ──────────────────────────────────────────────────────────────

function buildHotTables(companies) {
  // Most seed rounds in last 18mo (2025-01 onwards)
  const recentSeeds = {};
  companies.forEach(c => {
    c.deals && c.deals.forEach(d => {
      const rt = (d.round_type || '').toLowerCase();
      const date = d.round_date || '';
      const year = parseInt((date.match(/(20\d\d)/) || [])[1]);
      if ((rt === 'seed' || rt === 'accelerator') && year >= 2025) {
        recentSeeds[c.sector] = (recentSeeds[c.sector] || 0) + 1;
      }
    });
  });
  const seedEntries = Object.entries(recentSeeds).sort((a,b) => b[1]-a[1]).slice(0,6);
  renderHotTable('hot-seed', seedEntries, 'deals');

  // Median round size by sector
  const sectorRounds = {};
  companies.forEach(c => {
    c.deals && c.deals.forEach(d => {
      if (d.round_size) {
        (sectorRounds[c.sector] = sectorRounds[c.sector] || []).push(d.round_size);
      }
    });
  });
  const medianEntries = Object.entries(sectorRounds)
    .map(([s, arr]) => [s, median(arr)])
    .sort((a,b) => b[1]-a[1]).slice(0,6);
  renderHotTable('hot-median', medianEntries.map(([s,m]) => [s, '$'+m.toFixed(1)+'M']), '');

  // Fastest growing (founded 2023-2026)
  const recentCount = {};
  companies.forEach(c => {
    if (c.founding_year >= 2023) {
      recentCount[c.sector] = (recentCount[c.sector] || 0) + 1;
    }
  });
  const growthEntries = Object.entries(recentCount).sort((a,b) => b[1]-a[1]).slice(0,6);
  renderHotTable('hot-growth', growthEntries, 'new cos (2023+)');
}

function renderHotTable(id, entries, unit) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = `<tbody>${entries.map(([label, val]) =>
    `<tr><td>${escHtml(label)}</td><td>${escHtml(String(val))} ${unit}</td></tr>`
  ).join('')}</tbody>`;
}

// ── Exit tables ─────────────────────────────────────────────────────────────

function buildExitTables(companies) {
  const acquired = companies.filter(c => c.acquired);

  // Acquirers
  const acqMap = {};
  acquired.forEach(c => {
    const a = c.acquirer || 'Unknown';
    if (a && a !== 'nan') acqMap[a] = (acqMap[a] || 0) + 1;
  });
  const acqEntries = Object.entries(acqMap).sort((a,b) => b[1]-a[1]).slice(0,8);
  renderHotTable('exit-acquirers', acqEntries, 'acquisitions');

  // Recent notable (sort by exit size desc)
  const notable = acquired
    .filter(c => c.exit_size || c.total_raised)
    .sort((a, b) => (b.exit_size || b.total_raised || 0) - (a.exit_size || a.total_raised || 0))
    .slice(0, 8);
  const el = document.getElementById('exit-recent');
  if (el) {
    el.innerHTML = `<tbody>${notable.map(c =>
      `<tr><td>${escHtml(c.name)}</td><td>${c.exit_size && c.exit_size !== 'nan' ? '$'+c.exit_size+'M' : 'Undisclosed'}</td></tr>`
    ).join('')}</tbody>`;
  }
}

// ── Investor activity ────────────────────────────────────────────────────────

function buildInvestorActivity() {
  fetch('/api/investors')
    .then(r => r.json())
    .then(investors => {
      // Most active leads
      const active = investors
        .filter(i => i.lead_count > 0)
        .sort((a,b) => b.lead_count - a.lead_count)
        .slice(0, 8);
      renderHotTable('active-investors', active.map(i => [i.name, i.lead_count]), 'lead rounds');

      // Top co-investors (by portfolio_count - lead_count)
      const co = investors
        .sort((a,b) => (b.portfolio_count - b.lead_count) - (a.portfolio_count - a.lead_count))
        .slice(0, 8);
      renderHotTable('top-coinvestors', co.map(i => [i.name, i.portfolio_count - i.lead_count]), 'co-investments');
    });
}

// ── 8200 stats ───────────────────────────────────────────────────────────────

function build8200Stats(companies) {
  const cos8200 = companies.filter(c => c.is_8200);
  document.getElementById('stat-8200-count').textContent = cos8200.length;
  document.getElementById('stat-8200-pct').textContent = Math.round(cos8200.length / companies.length * 100) + '%';
  const raised = cos8200.reduce((s, c) => s + (c.total_raised || 0), 0);
  document.getElementById('stat-8200-raised').textContent = '$' + (raised/1000).toFixed(1) + 'B';
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function median(arr) {
  if (!arr.length) return 0;
  const s = [...arr].sort((a,b) => a-b);
  const mid = Math.floor(s.length/2);
  return s.length%2 ? s[mid] : (s[mid-1]+s[mid])/2;
}

function escHtml(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Init ─────────────────────────────────────────────────────────────────────

window.addEventListener('load', () => {
  buildFundingCharts();
  buildSectorCharts();
  buildInvestorActivity();

  fetch('/api/companies')
    .then(r => r.json())
    .then(companies => {
      build8200Chart(companies);
      build8200Stats(companies);
      buildHotTables(companies);
      buildExitTables(companies);
    });
});
