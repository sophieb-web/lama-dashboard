let allDeals = [];
let filteredDeals = [];
let sortCol = 'round_date';
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
  fetch('/api/deals')
    .then(r => r.json())
    .then(data => {
      allDeals = data;
      applyDealFilters();
    });
});

function applyDealFilters() {
  const round   = document.getElementById('filter-round').value;
  const sector  = document.getElementById('filter-sector').value;
  const year    = document.getElementById('filter-year').value;
  const minSize = parseFloat(document.getElementById('filter-minsize').value) || 0;
  const search  = (document.getElementById('global-search').value || '').toLowerCase();

  filteredDeals = allDeals.filter(d => {
    if (round  && !d.round_type.toLowerCase().includes(round.toLowerCase())) return false;
    if (sector && d.sector !== sector) return false;
    if (year   && !String(d.round_date).includes(year)) return false;
    if (minSize && (d.round_size == null || d.round_size < minSize)) return false;
    if (search && !d.company.toLowerCase().includes(search) &&
        !(d.lead_investor || '').toLowerCase().includes(search) &&
        !(d.co_investors  || '').toLowerCase().includes(search)) return false;
    return true;
  });

  sortDealData();
  page = 1;
  renderDealsTable();
}

function sortDeals(col) {
  if (sortCol === col) sortDir *= -1;
  else { sortCol = col; sortDir = -1; }
  document.querySelectorAll('#deals-table th').forEach(th => th.classList.remove('sorted'));
  const th = document.querySelector(`th[data-col="${col}"]`);
  if (th) {
    th.classList.add('sorted');
    th.querySelector('.sort-arrow').textContent = sortDir === -1 ? '↓' : '↑';
  }
  sortDealData();
  renderDealsTable();
}

function sortDealData() {
  filteredDeals.sort((a, b) => {
    let av = a[sortCol], bv = b[sortCol];
    if (av == null) av = sortDir === -1 ? '' : '￿';
    if (bv == null) bv = sortDir === -1 ? '' : '￿';
    if (typeof av === 'string') av = av.toLowerCase();
    if (typeof bv === 'string') bv = bv.toLowerCase();
    return av < bv ? -sortDir : av > bv ? sortDir : 0;
  });
}

function renderDealsTable() {
  const tbody = document.getElementById('deals-tbody');
  const start = (page - 1) * PAGE_SIZE;
  const pageData = filteredDeals.slice(start, start + PAGE_SIZE);

  if (!pageData.length) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;padding:40px;color:var(--text-muted)">No deals match the current filters.</td></tr>`;
    renderDealsPagination();
    return;
  }

  tbody.innerHTML = pageData.map(d => {
    const sectorColor = SECTOR_COLORS[d.sector] || '#6366F1';
    const rowClass = d.is_portfolio ? 'portfolio' : '';
    const coInvShort = d.co_investors
      ? d.co_investors.split(',').slice(0, 2).map(s => s.trim()).join(', ') +
        (d.co_investors.split(',').length > 2 ? '…' : '')
      : '—';

    return `<tr class="${rowClass}" onclick="openCompanyPanel('${escAttr(d.company)}')">
      <td>
        <strong>${escHtml(d.company)}</strong>
        ${d.is_portfolio ? ' <span class="badge badge-portfolio" style="font-size:9px">LP</span>' : ''}
      </td>
      <td><span class="badge badge-sector" style="background:${sectorColor}">${escHtml(d.sector)}</span></td>
      <td><span class="badge badge-stage">${escHtml(d.round_type || '—')}</span></td>
      <td style="white-space:nowrap">${escHtml(d.round_date || '—')}</td>
      <td><strong>${d.round_size != null ? '$' + fmtM(d.round_size) : '—'}</strong></td>
      <td style="font-size:12px">${escHtml(d.lead_investor || '—')}</td>
      <td style="font-size:11px;color:var(--text-muted);max-width:180px">${escHtml(coInvShort)}</td>
      <td style="font-size:12px">${d.round_valuation != null ? '$' + fmtM(d.round_valuation) : '—'}</td>
      <td>${d.is_portfolio ? '<span class="badge badge-portfolio">✓</span>' : '—'}</td>
    </tr>`;
  }).join('');

  renderDealsPagination();
}

function renderDealsPagination() {
  const total = filteredDeals.length;
  const pages = Math.ceil(total / PAGE_SIZE);
  const pag = document.getElementById('deals-pagination');

  if (pages <= 1) { pag.innerHTML = `<span class="page-info">${total} deals</span>`; return; }

  let html = `<span class="page-info">${total} deals · Page ${page} of ${pages}</span>`;
  html += `<button onclick="goDealPage(${page - 1})" ${page === 1 ? 'disabled' : ''}>← Prev</button>`;
  const range = getPaginationRange(page, pages);
  range.forEach(p => {
    if (p === '…') html += `<span style="padding:0 4px">…</span>`;
    else html += `<button class="${p === page ? 'active' : ''}" onclick="goDealPage(${p})">${p}</button>`;
  });
  html += `<button onclick="goDealPage(${page + 1})" ${page === pages ? 'disabled' : ''}>Next →</button>`;
  pag.innerHTML = html;
}

function getPaginationRange(cur, total) {
  if (total <= 7) return Array.from({length: total}, (_, i) => i + 1);
  if (cur <= 4) return [1, 2, 3, 4, 5, '…', total];
  if (cur >= total - 3) return [1, '…', total-4, total-3, total-2, total-1, total];
  return [1, '…', cur-1, cur, cur+1, '…', total];
}

function goDealPage(p) {
  const pages = Math.ceil(filteredDeals.length / PAGE_SIZE);
  if (p < 1 || p > pages) return;
  page = p;
  renderDealsTable();
  document.querySelector('.data-table').scrollIntoView({behavior: 'smooth', block: 'start'});
}

function exportDealsCSV() {
  const cols = ['company','sector','round_type','round_date','round_size','lead_investor','co_investors','round_valuation','is_portfolio'];
  const header = 'Company,Sector,Round,Date,Size ($M),Lead Investor,Co-Investors,Valuation ($M),Portfolio\n';
  const rows = filteredDeals.map(d =>
    cols.map(k => JSON.stringify(d[k] ?? '')).join(',')
  ).join('\n');
  const blob = new Blob([header + rows], {type: 'text/csv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'lama_cyber_deals.csv';
  a.click();
}

function resetDealFilters() {
  document.getElementById('filter-round').value = '';
  document.getElementById('filter-sector').value = '';
  document.getElementById('filter-year').value = '';
  document.getElementById('filter-minsize').value = '';
  document.getElementById('global-search').value = '';
  applyDealFilters();
}

function handleGlobalSearch(q) { applyDealFilters(); }

function escHtml(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function escAttr(s) { return String(s||'').replace(/'/g,"\\'"); }
function fmtM(n) {
  if (n >= 1000) return (n/1000).toFixed(1)+'B';
  return n%1===0 ? String(n) : n.toFixed(1);
}
