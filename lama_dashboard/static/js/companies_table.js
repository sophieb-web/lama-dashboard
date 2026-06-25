let allCompanies = [];
let filteredCompanies = [];
let sortCol = 'total_raised';
let sortDir = -1;  // -1 = desc
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
  fetch('/api/companies')
    .then(r => r.json())
    .then(data => {
      allCompanies = data;
      applyTableFilters();
    });
});

function applyTableFilters() {
  const sector = document.getElementById('filter-sector').value;
  const stage = document.getElementById('filter-stage').value;
  const year = parseInt(document.getElementById('filter-year').value) || 0;
  const military = document.getElementById('filter-military').value;
  const portfolioOnly = document.getElementById('filter-portfolio').checked;
  const thesisAligned = document.getElementById('filter-thesis-aligned').checked;
  const search = (document.getElementById('global-search').value || '').toLowerCase();

  filteredCompanies = allCompanies.filter(c => {
    if (portfolioOnly && !c.is_portfolio) return false;
    if (thesisAligned && !(c.thesis_alignment_score > 0)) return false;
    if (sector && c.sector !== sector) return false;
    if (stage && c.stage !== stage) return false;
    if (year && c.founding_year && c.founding_year < year) return false;
    if (military && !(c.military_unit || '').includes(military)) return false;
    if (search && !c.name.toLowerCase().includes(search) &&
        !(c.founders || '').toLowerCase().includes(search) &&
        !(c.description || '').toLowerCase().includes(search)) return false;
    return true;
  });

  sortData();
  page = 1;
  renderTable();
}

function sortTable(col) {
  if (sortCol === col) sortDir *= -1;
  else { sortCol = col; sortDir = -1; }
  document.querySelectorAll('.data-table th').forEach(th => th.classList.remove('sorted'));
  const th = document.querySelector(`th[data-col="${col}"]`);
  if (th) {
    th.classList.add('sorted');
    th.querySelector('.sort-arrow').textContent = sortDir === -1 ? '↓' : '↑';
  }
  sortData();
  renderTable();
}

function sortData() {
  filteredCompanies.sort((a, b) => {
    let av = a[sortCol], bv = b[sortCol];
    if (av == null) av = sortDir === -1 ? -Infinity : Infinity;
    if (bv == null) bv = sortDir === -1 ? -Infinity : Infinity;
    if (typeof av === 'string') av = av.toLowerCase();
    if (typeof bv === 'string') bv = bv.toLowerCase();
    return av < bv ? -sortDir : av > bv ? sortDir : 0;
  });
}

function renderTable() {
  const tbody = document.getElementById('companies-tbody');
  const start = (page - 1) * PAGE_SIZE;
  const pageData = filteredCompanies.slice(start, start + PAGE_SIZE);

  if (!pageData.length) {
    tbody.innerHTML = `<tr><td colspan="10" style="text-align:center;padding:40px;color:var(--text-muted)">No companies match the current filters.</td></tr>`;
    renderPagination();
    return;
  }

  tbody.innerHTML = pageData.map(c => {
    const rowClass = c.is_portfolio ? 'portfolio' : c.acquired ? 'acquired' : '';
    const sectorColor = SECTOR_COLORS[c.sector] || '#6366F1';
    const investors = (c.lead_investors || []).slice(0, 2).join(', ') +
      (c.lead_investors && c.lead_investors.length > 2 ? '…' : '');
    const founders = (c.founders || '').split(',').slice(0, 2).map(f => f.trim()).join(', ') +
      ((c.founders || '').split(',').length > 2 ? '…' : '');

    return `<tr class="${rowClass}" onclick="openCompanyPanel('${escAttr(c.name)}')">
      <td>
        <strong>${escHtml(c.name)}</strong>
        ${c.is_portfolio ? ' <span class="badge badge-portfolio" style="font-size:9px">LP</span>' : ''}
        <div style="font-size:11px;color:var(--text-muted);margin-top:2px">${escHtml((c.description || '').slice(0, 60))}${(c.description || '').length > 60 ? '…' : ''}</div>
      </td>
      <td><span class="badge badge-sector" style="background:${sectorColor}">${escHtml(c.sector)}</span></td>
      <td>${c.founding_year || '—'}</td>
      <td>${c.total_raised ? '$' + fmtM(c.total_raised) : '—'}</td>
      <td><span class="badge badge-stage">${escHtml(c.stage || '—')}</span></td>
      <td style="font-size:12px">${escHtml(investors || '—')}</td>
      <td style="font-size:12px">${escHtml(founders || '—')}</td>
      <td style="font-size:12px">${c.is_8200 ? '<span class="badge badge-8200">8200</span>' : (c.military_unit && c.military_unit !== 'Unknown' && c.military_unit !== 'nan' ? escHtml(c.military_unit) : '—')}</td>
      <td>${c.acquired ? '<span class="badge badge-acquired">' + escHtml(c.acquirer || 'Yes') + '</span>' : '—'}</td>
      <td>${c.is_portfolio ? '<span class="badge badge-portfolio">✓</span>' : '—'}</td>
    </tr>`;
  }).join('');

  renderPagination();
}

function renderPagination() {
  const total = filteredCompanies.length;
  const pages = Math.ceil(total / PAGE_SIZE);
  const pag = document.getElementById('table-pagination');

  if (pages <= 1) { pag.innerHTML = `<span class="page-info">${total} companies</span>`; return; }

  let html = `<span class="page-info">${total} companies · Page ${page} of ${pages}</span>`;
  html += `<button onclick="goPage(${page - 1})" ${page === 1 ? 'disabled' : ''}>← Prev</button>`;

  const range = getPaginationRange(page, pages);
  range.forEach(p => {
    if (p === '…') html += `<span style="padding:0 4px">…</span>`;
    else html += `<button class="${p === page ? 'active' : ''}" onclick="goPage(${p})">${p}</button>`;
  });
  html += `<button onclick="goPage(${page + 1})" ${page === pages ? 'disabled' : ''}>Next →</button>`;
  pag.innerHTML = html;
}

function getPaginationRange(cur, total) {
  if (total <= 7) return Array.from({length: total}, (_, i) => i + 1);
  if (cur <= 4) return [1, 2, 3, 4, 5, '…', total];
  if (cur >= total - 3) return [1, '…', total-4, total-3, total-2, total-1, total];
  return [1, '…', cur-1, cur, cur+1, '…', total];
}

function goPage(p) {
  const pages = Math.ceil(filteredCompanies.length / PAGE_SIZE);
  if (p < 1 || p > pages) return;
  page = p;
  renderTable();
  document.querySelector('.data-table').scrollIntoView({behavior: 'smooth', block: 'start'});
}

function exportCSV() {
  const cols = ['name','sector','founding_year','total_raised','stage','founders','military_unit','acquired','acquirer','is_portfolio'];
  const header = 'Company,Sector,Founded,Raised ($M),Stage,Founders,Military,Acquired,Acquirer,Portfolio\n';
  const rows = filteredCompanies.map(c =>
    cols.map(k => JSON.stringify(c[k] ?? '')).join(',')
  ).join('\n');
  const blob = new Blob([header + rows], {type: 'text/csv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'lama_cyber_companies.csv';
  a.click();
}

function resetTableFilters() {
  document.getElementById('filter-sector').value = '';
  document.getElementById('filter-stage').value = '';
  document.getElementById('filter-year').value = '';
  document.getElementById('filter-military').value = '';
  document.getElementById('filter-portfolio').checked = false;
  document.getElementById('filter-thesis-aligned').checked = false;
  document.getElementById('global-search').value = '';
  applyTableFilters();
}

function handleGlobalSearch(q) { applyTableFilters(); }

function escHtml(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function escAttr(s) { return String(s||'').replace(/'/g,"\\'"); }
function fmtM(n) {
  if (n >= 1000) return (n/1000).toFixed(1)+'B';
  return n%1===0 ? String(n) : n.toFixed(1);
}
