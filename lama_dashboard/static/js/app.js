// ── Helpers ────────────────────────────────────────────────────────────────

// Returns true if a value is empty, null, undefined, or any nan variant.
function isEmpty(v) {
  if (v === null || v === undefined) return true;
  if (typeof v === 'number' && isNaN(v)) return true;
  const s = String(v).trim().toLowerCase();
  return s === '' || s === 'nan' || s === 'none' || s === 'n/a' || s === 'unknown';
}

// Clean a value: returns the string, or '—' if empty/nan.
function clean(v, fallback = '—') {
  return isEmpty(v) ? fallback : String(v).trim();
}

// Clean a numeric dollar value: returns '$X' or '—'.
function cleanMoney(v, suffix = '') {
  if (isEmpty(v) || v === 0) return '—';
  const n = parseFloat(v);
  if (isNaN(n)) return '—';
  return '$' + fmtM(n) + suffix;
}

function escHtml(str) {
  return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function escAttr(str) {
  return String(str || '').replace(/'/g, "\\'");
}

function fmtM(n) {
  if (n >= 1000) return (n / 1000).toFixed(1) + 'B';
  return n % 1 === 0 ? String(n) : n.toFixed(1);
}

function parseLinkedins(raw) {
  const result = {};
  if (isEmpty(raw)) return result;
  String(raw).split('|').forEach(part => {
    const m = part.match(/^(.+?):\s*(https?:\/\/\S+)/);
    if (m) result[m[1].trim()] = m[2].trim();
  });
  return result;
}

function parseRoles(raw) {
  const result = {};
  if (isEmpty(raw)) return result;
  String(raw).split('|').forEach(part => {
    const idx = part.indexOf(':');
    if (idx > 0) {
      result[part.slice(0, idx).trim()] = part.slice(idx + 1).trim();
    }
  });
  return result;
}

// ── Company Profile Panel ──────────────────────────────────────────────────

function openCompanyPanel(name) {
  fetch(`/api/companies/${encodeURIComponent(name)}`)
    .then(r => r.json())
    .then(c => {
      renderCompanyPanel(c);
      document.getElementById('company-panel').classList.add('open');
      document.getElementById('panel-overlay').classList.add('open');
    });
}

function closePanel() {
  document.getElementById('company-panel').classList.remove('open');
  document.getElementById('panel-overlay').classList.remove('open');
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { closePanel(); if (typeof closeInvestorPanel === 'function') closeInvestorPanel(); }
});

function renderCompanyPanel(c) {
  // ── Header ──
  const websiteVal = clean(c.website, '');
  const websiteHtml = websiteVal
    ? ` <a href="https://${websiteVal}" target="_blank" rel="noopener" style="font-size:14px;color:var(--purple)">↗</a>`
    : '';
  document.getElementById('panel-name').innerHTML = escHtml(c.name) + websiteHtml;

  const metaParts = [];
  if (!isEmpty(c.sector)) metaParts.push(`<span class="badge badge-sector" style="background:${c.sector_color || '#6366F1'}">${escHtml(c.sector)}</span>`);
  if (!isEmpty(c.founding_year)) metaParts.push(`Founded ${c.founding_year}`);
  if (!isEmpty(c.hq_city)) metaParts.push(escHtml(c.hq_city));
  if (!isEmpty(c.employees)) metaParts.push(`👥 ${escHtml(c.employees)}`);
  document.getElementById('panel-meta').innerHTML = metaParts.join(' · ');

  let badgeHtml = '';
  if (c.is_portfolio) badgeHtml += `<span class="badge badge-portfolio">🟣 LAMA PORTFOLIO</span>`;
  if (c.acquired) {
    const acqBy = !isEmpty(c.acquirer) ? ` by ${escHtml(c.acquirer)}` : '';
    const exitStr = !isEmpty(c.exit_size) && c.exit_size !== 0 ? ` · $${c.exit_size}M` : '';
    badgeHtml += `<span class="badge badge-acquired">🟠 ACQUIRED${acqBy}${exitStr}</span>`;
  }
  if (c.is_8200) badgeHtml += `<span class="badge badge-8200">🎖 Unit 8200</span>`;
  document.getElementById('panel-badges').innerHTML = badgeHtml;

  // ── Body ──
  const body = document.getElementById('panel-body');
  let html = '';

  // About
  const desc = clean(c.description, '');
  if (desc) {
    html += `<div class="panel-section">
      <div class="panel-section-title">About</div>
      <div class="panel-description">${escHtml(desc)}</div>`;
    const notes = clean(c.notes, '');
    if (notes) html += `<div class="panel-notes">${escHtml(notes)}</div>`;
    html += `</div>`;
  }

  // Key stats
  const militaryDisplay = (() => {
    const m = clean(c.military_unit, '');
    if (!m || m.toLowerCase() === 'unknown' || m.toLowerCase() === 'none') return '—';
    return escHtml(m);
  })();

  html += `<div class="panel-section">
    <div class="panel-section-title">Key Stats</div>
    <div class="stats-mini">
      <div class="stats-mini-item"><div class="val">${cleanMoney(c.total_raised, 'M')}</div><div class="lbl">Total Raised</div></div>
      <div class="stats-mini-item"><div class="val">${cleanMoney(c.valuation, 'M')}</div><div class="lbl">Valuation</div></div>
      <div class="stats-mini-item"><div class="val">${isEmpty(c.employees) ? '—' : escHtml(c.employees)}</div><div class="lbl">Employees</div></div>
      <div class="stats-mini-item"><div class="val">${militaryDisplay}</div><div class="lbl">Military Unit</div></div>
    </div>
  </div>`;

  // Founders
  const foundersRaw = clean(c.founders, '');
  if (foundersRaw) {
    const founders = foundersRaw.split(',').map(f => f.trim()).filter(Boolean);
    const linkedins = parseLinkedins(c.founder_linkedin);
    const roles = parseRoles(c.last_role);
    html += `<div class="panel-section">
      <div class="panel-section-title">Founders</div>
      <div class="founder-list">`;
    founders.forEach(name => {
      const li = linkedins[name] || '';
      const role = clean(roles[name], '');
      html += `<div class="founder-item">
        <span class="founder-name">${escHtml(name)}${li ? ` <a href="${li}" target="_blank" rel="noopener">LinkedIn ↗</a>` : ''}</span>
        ${role ? `<span class="founder-role">${escHtml(role)}</span>` : ''}
      </div>`;
    });
    html += `</div></div>`;
  }

  // Customer Intelligence (from testimonials data)
  const hasTestimonials = c.total_testimonials && c.total_testimonials > 0;
  if (hasTestimonials) {
    const score = c.thesis_alignment_score || 0;
    const scoreColor = score >= 7 ? '#10B981' : score >= 4 ? '#F59E0B' : '#6B7280';
    const scoreDots = Array.from({length: 10}, (_, i) =>
      `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;margin:1px;background:${i < score ? scoreColor : '#E5E7EB'}"></span>`
    ).join('');

    const industries = (c.top_industries || []).slice(0, 4);
    const roles = (c.top_buyer_roles || []).slice(0, 4);
    const quote = clean(c.thesis_quote, '');
    const orgs = clean(c.key_customer_orgs, '');
    const legacy = clean(c.customers, '');

    html += `<div class="panel-section">
      <div class="panel-section-title">Customer Intelligence</div>
      <div style="display:flex;gap:12px;margin-bottom:10px;flex-wrap:wrap">
        <div style="background:var(--bg-light);border-radius:8px;padding:8px 12px;text-align:center;min-width:70px">
          <div style="font-size:20px;font-weight:700;color:var(--text)">${c.total_testimonials}</div>
          <div style="font-size:11px;color:var(--text-muted)">Testimonials</div>
        </div>
        <div style="background:var(--bg-light);border-radius:8px;padding:8px 12px;text-align:center;min-width:70px">
          <div style="font-size:20px;font-weight:700;color:#0EA5E9">${c.ciso_count || 0}</div>
          <div style="font-size:11px;color:var(--text-muted)">CISO Quotes</div>
        </div>
        <div style="background:var(--bg-light);border-radius:8px;padding:8px 14px">
          <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px">Thesis Alignment</div>
          <div>${scoreDots}</div>
          <div style="font-size:11px;color:${scoreColor};font-weight:600">${score}/10</div>
        </div>
      </div>`;

    if (industries.length) {
      html += `<div style="margin-bottom:8px">
        <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Top Customer Industries</div>
        <div style="display:flex;flex-wrap:wrap;gap:4px">
          ${industries.map(i => `<span style="background:#EDE9FE;color:#6D28D9;border-radius:4px;padding:2px 7px;font-size:12px">${escHtml(i)}</span>`).join('')}
        </div>
      </div>`;
    }

    if (roles.length) {
      html += `<div style="margin-bottom:8px">
        <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Top Buyer Roles</div>
        <div style="display:flex;flex-wrap:wrap;gap:4px">
          ${roles.map(r => `<span style="background:#E0F2FE;color:#0369A1;border-radius:4px;padding:2px 7px;font-size:12px">${escHtml(r)}</span>`).join('')}
        </div>
      </div>`;
    }

    if (orgs) {
      html += `<div style="margin-bottom:8px">
        <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Key Customer Orgs</div>
        <div style="font-size:12px;color:var(--text)">${escHtml(orgs)}</div>
      </div>`;
    } else if (legacy) {
      html += `<div style="margin-bottom:8px">
        <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Known Customers</div>
        <div style="font-size:12px;color:var(--text)">${escHtml(legacy)}</div>
      </div>`;
    }

    if (quote) {
      html += `<div style="border-left:3px solid ${scoreColor};padding:8px 10px;background:var(--bg-light);border-radius:0 6px 6px 0;margin-top:6px">
        <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px">Best thesis-aligned quote</div>
        <div style="font-size:12px;color:var(--text);font-style:italic">"${escHtml(quote.slice(0, 240))}${quote.length > 240 ? '…' : ''}"</div>
      </div>`;
    }

    html += `</div>`;
  } else {
    // Fall back to plain customers field if no testimonial data
    const customers = clean(c.customers, '');
    if (customers) {
      html += `<div class="panel-section">
        <div class="panel-section-title">Customers</div>
        <div style="font-size:13px;color:var(--text-muted)">${escHtml(customers)}</div>
      </div>`;
    }
  }

  // Angels
  const angels = clean(c.angels, '');
  if (angels) {
    html += `<div class="panel-section">
      <div class="panel-section-title">Angel Investors</div>
      <div style="font-size:13px;color:var(--text-muted)">${escHtml(angels)}</div>
    </div>`;
  }

  // Funding history
  const deals = (c.deals || []).filter(d => !isEmpty(d.round_type));
  if (deals.length) {
    html += `<div class="panel-section">
      <div class="panel-section-title">Funding History</div>
      <div style="overflow-x:auto">
      <table class="funding-table">
        <thead><tr>
          <th>Round</th><th>Date</th><th>Size</th><th>Lead Investor</th><th>Co-Investors</th><th>Valuation</th>
        </tr></thead>
        <tbody>`;
    deals.forEach((d, i) => {
      const isLatest = i === deals.length - 1;

      // Clean all deal fields
      const roundType   = clean(d.round_type);
      const roundDate   = clean(d.round_date);
      const roundSize   = cleanMoney(d.round_size, 'M');
      const leadInv     = clean(d.lead_investor);
      const coInv       = clean(d.co_investors);
      const roundVal    = cleanMoney(d.round_valuation, 'M');

      html += `<tr class="${isLatest ? 'latest' : ''}">
        <td>${escHtml(roundType)}</td>
        <td>${escHtml(roundDate)}</td>
        <td>${escHtml(roundSize)}</td>
        <td>${escHtml(leadInv)}</td>
        <td style="max-width:160px;font-size:11px">${escHtml(coInv)}</td>
        <td>${escHtml(roundVal)}</td>
      </tr>`;
    });
    html += `</tbody></table></div></div>`;
  }

  // Related companies
  if (c.related && c.related.length) {
    html += `<div class="panel-section">
      <div class="panel-section-title">Related Companies (${escHtml(c.sector || '')})</div>
      <div class="related-companies">`;
    c.related.slice(0, 5).forEach(r => {
      const raised = !isEmpty(r.total_raised) ? '$' + fmtM(r.total_raised) + 'M' : clean(r.stage, '—');
      html += `<div class="related-item" onclick="openCompanyPanel('${escAttr(r.name)}')">
        <span>${escHtml(r.name)}</span>
        <span style="font-size:12px;color:var(--text-muted)">${escHtml(raised)}</span>
      </div>`;
    });
    html += `</div></div>`;
  }

  body.innerHTML = html;
}

// Global search: delegate to page-specific handler
document.getElementById('global-search').addEventListener('input', function() {
  if (typeof handleGlobalSearch === 'function') handleGlobalSearch(this.value.trim());
});
