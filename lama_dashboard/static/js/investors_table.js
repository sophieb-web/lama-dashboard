let allInvestors = [];
let filteredInvestors = [];
let sortCol = 'portfolio_count';
let sortDir = -1;
let page = 1;
const PAGE_SIZE = 50;

const SECTOR_COLORS = {
  "AI Security": "#8B5CF6", "Cloud Security": "#0EA5E9", "Data Security": "#10B981",
  "Identity & Access": "#F59E0B", "Application Security": "#EF4444",
  "Supply Chain Security": "#06B6D4", "Security Operations": "#6366F1",
  "Network Security": "#84CC16", "Endpoint & XDR": "#F97316",
  "OT / ICS / IoT": "#EC4899", "GRC & Compliance": "#14B8A6",
  "Threat Intelligence": "#A78BFA"
};

window.addEventListener('load', () => {
  fetch('/api/investors')
    .then(r => r.json())
    .then(data => {
      allInvestors = data;
      applyInvestorFilters();
    });
});

function applyInvestorFilters() {
  const stage = document.getElementById('filter-stage').value;
  const sector = document.getElementById('filter-sector').value;
  const lpOnly = document.getElementById('filter-lp').checked;
  const search = (document.getElementById('global-search').value || '').toLowerCase();

  filteredInvestors = allInvestors.filter(inv => {
    if (lpOnly && !inv.is_lama_lp) return false;
    if (stage && inv.stage_focus !== stage) return false;
    if (sector && !inv.sectors[sector]) return false;
    if (search && !inv.name.toLowerCase().includes(search)) return false;
    return true;
  });

  sortInvestorData();
  page = 1;
  renderInvestorTable();
}

function sortInvestors(col) {
  if (sortCol === col) sortDir *= -1;
  else { sortCol = col; sortDir = -1; }
  document.querySelectorAll('#investors-table th').forEach(th => th.classList.remove('sorted'));
  const th = document.querySelector(`th[data-col="${col}"]`);
  if (th) {
    th.classList.add('sorted');
    th.querySelector('.sort-arrow').textContent = sortDir === -1 ? '↓' : '↑';
  }
  sortInvestorData();
  renderInvestorTable();
}

function sortInvestorData() {
  filteredInvestors.sort((a, b) => {
    let av = a[sortCol], bv = b[sortCol];
    if (av == null) av = sortDir === -1 ? -Infinity : Infinity;
    if (bv == null) bv = sortDir === -1 ? -Infinity : Infinity;
    if (typeof av === 'string') av = av.toLowerCase();
    if (typeof bv === 'string') bv = bv.toLowerCase();
    return av < bv ? -sortDir : av > bv ? sortDir : 0;
  });
}

function renderInvestorTable() {
  const tbody = document.getElementById('investors-tbody');
  const start = (page - 1) * PAGE_SIZE;
  const pageData = filteredInvestors.slice(start, start + PAGE_SIZE);

  if (!pageData.length) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;padding:40px;color:var(--text-muted)">No investors match filters.</td></tr>`;
    renderInvPagination();
    return;
  }

  tbody.innerHTML = pageData.map((inv, idx) => {
    const rank = start + idx + 1;
    const topSectors = Object.entries(inv.sectors).slice(0, 2)
      .map(([s, n]) => `<span class="badge badge-sector" style="background:${SECTOR_COLORS[s]||'#6366F1'};font-size:10px">${s}</span>`)
      .join(' ');

    return `<tr onclick="openInvestorPanel('${escAttr(inv.name)}')" style="cursor:pointer">
      <td style="color:var(--text-muted);font-size:12px">${rank}</td>
      <td>
        <strong>${escHtml(inv.name)}</strong>
        ${inv.is_lama_lp ? ' <span class="badge badge-lp">Lama LP</span>' : ''}
      </td>
      <td><strong>${inv.portfolio_count}</strong></td>
      <td>${inv.lead_count}</td>
      <td>${inv.total_deployed > 0 ? '$' + fmtM(inv.total_deployed) : '—'}</td>
      <td><span class="badge badge-stage">${escHtml(inv.stage_focus)}</span></td>
      <td>${topSectors || '—'}</td>
      <td style="font-size:12px;color:var(--text-muted)">${escHtml(inv.most_recent_deal || '—')}</td>
      <td>${inv.is_lama_lp ? '✓' : '—'}</td>
    </tr>`;
  }).join('');

  renderInvPagination();
}

function renderInvPagination() {
  const total = filteredInvestors.length;
  const pages = Math.ceil(total / PAGE_SIZE);
  const pag = document.getElementById('investor-pagination');
  if (pages <= 1) { pag.innerHTML = `<span class="page-info">${total} investors</span>`; return; }
  let html = `<span class="page-info">${total} investors · Page ${page} of ${pages}</span>`;
  html += `<button onclick="goInvPage(${page-1})" ${page===1?'disabled':''}>← Prev</button>`;
  html += `<button onclick="goInvPage(${page+1})" ${page===pages?'disabled':''}>Next →</button>`;
  pag.innerHTML = html;
}

function goInvPage(p) {
  const pages = Math.ceil(filteredInvestors.length / PAGE_SIZE);
  if (p < 1 || p > pages) return;
  page = p;
  renderInvestorTable();
}

// ── Investor Profile Panel ───────────────────────────────────────────────────

function openInvestorPanel(name) {
  const inv = allInvestors.find(i => i.name === name);
  if (!inv) return;

  document.getElementById('inv-panel-name').textContent = inv.name;
  document.getElementById('inv-panel-meta').innerHTML =
    `<span>${inv.portfolio_count} portfolio companies</span> · ` +
    `<span>${inv.total_deployed > 0 ? '$' + fmtM(inv.total_deployed) + 'M deployed' : ''}</span> · ` +
    `<span class="badge badge-stage">${inv.stage_focus}</span>`;
  document.getElementById('inv-panel-badges').innerHTML =
    inv.is_lama_lp ? '<span class="badge badge-lp">Lama LP Connected</span>' : '';

  const body = document.getElementById('inv-panel-body');
  const topSectors = Object.entries(inv.sectors).slice(0, 5);
  const sectorBars = topSectors.map(([s, n]) =>
    `<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
      <div style="width:100px;font-size:12px;color:var(--text-muted)">${escHtml(s)}</div>
      <div style="flex:1;background:var(--border);border-radius:4px;height:8px">
        <div style="width:${Math.min(100, n/topSectors[0][1]*100)}%;background:${SECTOR_COLORS[s]||'#6366F1'};height:8px;border-radius:4px"></div>
      </div>
      <div style="font-size:12px;font-weight:600;width:24px">${n}</div>
    </div>`
  ).join('');

  const companyTags = inv.companies.sort().map(c =>
    `<div class="company-tag" onclick="openCompanyPanel('${escAttr(c)}')">${escHtml(c)}</div>`
  ).join('');

  body.innerHTML = `
    <h2>${escHtml(inv.name)}</h2>
    <div class="sub">${inv.portfolio_count} investments · ${inv.stage_focus} focus</div>

    <div class="panel-section-title" style="margin-top:16px">Sector Breakdown</div>
    <div style="margin-bottom:16px">${sectorBars}</div>

    <div class="panel-section-title">Portfolio Companies (${inv.companies.length})</div>
    <div class="company-tags">${companyTags}</div>
  `;

  document.getElementById('investor-panel').classList.add('open');
  document.getElementById('investor-overlay').classList.add('open');
}

function closeInvestorPanel() {
  document.getElementById('investor-panel').classList.remove('open');
  document.getElementById('investor-overlay').classList.remove('open');
}

function resetInvestorFilters() {
  document.getElementById('filter-stage').value = '';
  document.getElementById('filter-sector').value = '';
  document.getElementById('filter-lp').checked = false;
  document.getElementById('global-search').value = '';
  applyInvestorFilters();
}

function handleGlobalSearch(q) { applyInvestorFilters(); }

function escHtml(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function escAttr(s) { return String(s||'').replace(/'/g,"\\'"); }
function fmtM(n) {
  if (n >= 1000) return (n/1000).toFixed(1)+'B';
  return n%1===0 ? String(n) : n.toFixed(1);
}
