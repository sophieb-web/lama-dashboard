// D3 force-directed bubble map

let allCompanies = [];
let simulation = null;
let svg, g;
let currentFilters = { sector: '', stage: '', year: '', military: '', portfolio: false, search: '' };
let sectorToggle = {};  // sector -> visible

const WIDTH = () => document.getElementById('bubble-map').clientWidth;
const HEIGHT = 620;

function initBubbleMap() {
  svg = d3.select('#bubble-map')
    .attr('height', HEIGHT)
    .style('background', '#fafafa');

  // Zoom
  const zoom = d3.zoom().scaleExtent([0.3, 4]).on('zoom', e => {
    g.attr('transform', e.transform);
  });
  svg.call(zoom);
  g = svg.append('g');

  // Load data
  fetch('/api/companies')
    .then(r => r.json())
    .then(data => {
      allCompanies = data;
      buildLegend();
      renderMap(allCompanies);
    });
}

function buildLegend() {
  const legend = document.getElementById('bubble-legend');
  const sectors = Object.keys(SECTOR_COLORS);
  legend.innerHTML = sectors.map(s => `
    <div class="legend-item" onclick="toggleSector('${s.replace(/'/g,"\\'")}')">
      <div class="legend-dot" style="background:${SECTOR_COLORS[s]}"></div>
      <span>${s}</span>
    </div>
  `).join('');
  sectors.forEach(s => sectorToggle[s] = true);
}

function toggleSector(sector) {
  sectorToggle[sector] = !sectorToggle[sector];
  // Update legend item style
  document.querySelectorAll('.legend-item').forEach(el => {
    const s = el.querySelector('span').textContent;
    el.style.opacity = sectorToggle[s] ? '1' : '0.35';
  });
  applyMapFilters();
}

function renderMap(companies) {
  g.selectAll('*').remove();

  const w = WIDTH();
  const radius = d3.scaleSqrt()
    .domain([0, d3.max(companies, d => d.total_raised || 0)])
    .range([5, 48]);

  // Group companies by sector for cluster positions
  const sectors = [...new Set(companies.map(d => d.sector))];
  const sectorCount = sectors.length;
  const clusterCenters = {};
  sectors.forEach((s, i) => {
    const angle = (i / sectorCount) * 2 * Math.PI - Math.PI / 2;
    const cx = w / 2 + Math.cos(angle) * (w * 0.28);
    const cy = HEIGHT / 2 + Math.sin(angle) * (HEIGHT * 0.32);
    clusterCenters[s] = { x: cx, y: cy };
  });

  const nodes = companies.map(d => ({
    ...d,
    r: radius(d.total_raised || 1),
    x: (clusterCenters[d.sector]?.x || w / 2) + (Math.random() - 0.5) * 80,
    y: (clusterCenters[d.sector]?.y || HEIGHT / 2) + (Math.random() - 0.5) * 80,
  }));

  // Cluster force
  const clusterForce = alpha => {
    nodes.forEach(d => {
      const center = clusterCenters[d.sector];
      if (!center) return;
      d.vx = (d.vx || 0) + (center.x - d.x) * alpha * 0.04;
      d.vy = (d.vy || 0) + (center.y - d.y) * alpha * 0.04;
    });
  };

  if (simulation) simulation.stop();
  simulation = d3.forceSimulation(nodes)
    .force('collide', d3.forceCollide(d => d.r + 2).strength(0.85))
    .force('x', d3.forceX(d => clusterCenters[d.sector]?.x || w / 2).strength(0.06))
    .force('y', d3.forceY(d => clusterCenters[d.sector]?.y || HEIGHT / 2).strength(0.06))
    .force('cluster', clusterForce)
    .alpha(0.9)
    .alphaDecay(0.025)
    .on('tick', ticked);

  // Sector label groups
  const labelG = g.append('g').attr('class', 'sector-labels');
  Object.entries(clusterCenters).forEach(([sector, pos]) => {
    labelG.append('text')
      .attr('x', pos.x).attr('y', pos.y - 60)
      .attr('text-anchor', 'middle')
      .attr('fill', SECTOR_COLORS[sector] || '#666')
      .attr('font-size', '11px')
      .attr('font-weight', '600')
      .attr('font-family', 'Inter, sans-serif')
      .attr('opacity', 0.6)
      .text(sector);
  });

  const tooltip = document.getElementById('bubble-tooltip');

  const node = g.selectAll('g.bubble-node')
    .data(nodes, d => d.name)
    .join('g')
    .attr('class', 'bubble-node')
    .style('cursor', 'pointer')
    .on('mouseover', function(event, d) {
      tooltip.style.display = 'block';
      tooltip.innerHTML = `<strong>${d.name}</strong>
        <span style="color:#a78bfa">${d.sector}</span><br>
        ${d.total_raised ? '<b>Raised:</b> $' + fmtM(d.total_raised) + 'M · ' : ''}
        <b>Stage:</b> ${d.stage || '—'}<br>
        ${d.founding_year ? '<b>Founded:</b> ' + d.founding_year + ' · ' : ''}
        ${d.hq_city && d.hq_city !== 'nan' ? d.hq_city : ''}
        ${d.is_portfolio ? '<br><span style="color:#c4b5fd">🟣 Lama Portfolio</span>' : ''}
        ${d.acquired ? '<br><span style="color:#fbbf24">🟠 Acquired' + (d.acquirer && d.acquirer !== 'nan' ? ' by ' + d.acquirer : '') + '</span>' : ''}`;
    })
    .on('mousemove', function(event) {
      tooltip.style.left = (event.clientX + 14) + 'px';
      tooltip.style.top = (event.clientY - 10) + 'px';
    })
    .on('mouseout', function() {
      tooltip.style.display = 'none';
    })
    .on('click', function(event, d) {
      event.stopPropagation();
      tooltip.style.display = 'none';
      openCompanyPanel(d.name);
    });

  // Circle
  node.append('circle')
    .attr('r', d => d.r)
    .attr('fill', d => {
      if (d.acquired) return '#d1d5db';
      return SECTOR_COLORS[d.sector] || '#6366F1';
    })
    .attr('fill-opacity', d => d.acquired ? 0.55 : 0.82)
    .attr('stroke', d => {
      if (d.is_portfolio) return '#F59E0B';
      return 'rgba(255,255,255,0.3)';
    })
    .attr('stroke-width', d => d.is_portfolio ? 2.5 : 1);

  // Portfolio ring
  node.filter(d => d.is_portfolio)
    .append('circle')
    .attr('r', d => d.r + 4)
    .attr('fill', 'none')
    .attr('stroke', '#F59E0B')
    .attr('stroke-width', 1.5)
    .attr('stroke-dasharray', '3,2');

  // Labels for larger bubbles
  node.filter(d => d.r > 18)
    .append('text')
    .attr('text-anchor', 'middle')
    .attr('dy', '0.35em')
    .attr('fill', '#fff')
    .attr('font-size', d => Math.min(d.r * 0.38, 11) + 'px')
    .attr('font-family', 'Inter, sans-serif')
    .attr('font-weight', '600')
    .attr('pointer-events', 'none')
    .text(d => d.name.length > 12 ? d.name.slice(0, 11) + '…' : d.name);

  // ACQ / LP badges
  node.filter(d => d.acquired)
    .append('text')
    .attr('text-anchor', 'middle')
    .attr('dy', d => d.r * 0.55 + 'px')
    .attr('fill', '#92400e')
    .attr('font-size', '8px')
    .attr('font-weight', '700')
    .attr('pointer-events', 'none')
    .text('ACQ');

  function ticked() {
    node.attr('transform', d => `translate(${d.x},${d.y})`);
  }
}

function applyMapFilters() {
  const sector = document.getElementById('filter-sector').value;
  const stage = document.getElementById('filter-stage').value;
  const year = parseInt(document.getElementById('filter-year').value) || 0;
  const military = document.getElementById('filter-military').value;
  const portfolioOnly = document.getElementById('filter-portfolio').checked;
  const search = document.getElementById('global-search').value.toLowerCase();

  currentFilters = { sector, stage, year, military, portfolio: portfolioOnly, search };

  let filtered = allCompanies.filter(c => {
    if (c.is_portfolio) return true;  // Never hide portfolio
    if (portfolioOnly) return false;
    if (sector && c.sector !== sector) return false;
    if (!sectorToggle[c.sector]) return false;
    if (stage && c.stage !== stage) return false;
    if (year && c.founding_year && c.founding_year < year) return false;
    if (military && !(c.military_unit || '').includes(military)) return false;
    if (search && !c.name.toLowerCase().includes(search)) return false;
    return true;
  });

  // Dim non-matching when search active
  if (search) {
    g.selectAll('g.bubble-node').each(function(d) {
      const matches = d.name.toLowerCase().includes(search) || d.is_portfolio;
      d3.select(this).attr('opacity', matches ? 1 : 0.15);
    });
    return;
  }

  renderMap(filtered);
}

function resetMapFilters() {
  document.getElementById('filter-sector').value = '';
  document.getElementById('filter-stage').value = '';
  document.getElementById('filter-year').value = '';
  document.getElementById('filter-military').value = '';
  document.getElementById('filter-portfolio').checked = false;
  document.getElementById('global-search').value = '';
  Object.keys(sectorToggle).forEach(s => sectorToggle[s] = true);
  document.querySelectorAll('.legend-item').forEach(el => el.style.opacity = '1');
  renderMap(allCompanies);
}

function handleGlobalSearch(q) {
  applyMapFilters();
}

function fmtM(n) {
  if (!n) return '0';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'B';
  return n % 1 === 0 ? String(n) : n.toFixed(1);
}

// Init on load
window.addEventListener('load', initBubbleMap);
window.addEventListener('resize', () => {
  if (allCompanies.length) renderMap(allCompanies);
});
