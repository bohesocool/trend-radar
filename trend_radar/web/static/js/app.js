/* ============================================================
   TrendRadar — Frontend Application Logic
   Linear Design System · Auth · Routing · Pages · Chart.js
   ============================================================ */

'use strict';

const API = '/api';
const TOKEN_KEY = 'trendradar_jwt';
const CHART_JS_CDN = '/static/js/chart.umd.min.js';

/* ============================================================
   1. Auth Module
   ============================================================ */

const Auth = {
  getToken() {
    return localStorage.getItem(TOKEN_KEY);
  },

  setToken(token) {
    localStorage.setItem(TOKEN_KEY, token.trim());
  },

  clearToken() {
    localStorage.removeItem(TOKEN_KEY);
  },

  isLoggedIn() {
    return !!this.getToken();
  },

  logout() {
    this.clearToken();
    window.location.href = '/login';
  },

  /** Redirect to /login if not authenticated. Returns true if redirected. */
  requireAuth() {
    if (!this.isLoggedIn()) {
      window.location.href = '/login';
      return true;
    }
    return false;
  },
};

/* Expose to window so inline onclick/onsubmit handlers can reach them
   (top-level const/function-decls in a classic script are NOT auto-attached
   to window in modern browsers). */
window.Auth = Auth;
window.handleLogin = handleLogin;
window.handleRunDaily = handleRunDaily;

/* Topic detail toggle (used by dashboard hot-topic expandable cards) */
window.toggleTopicDetail = function(id, btn) {
  var el = document.getElementById(id);
  if (!el) return;
  if (el.style.display === 'none') {
    el.style.display = 'block';
    if (btn) btn.textContent = '收起 ▴';
  } else {
    el.style.display = 'none';
    if (btn) btn.textContent = '展开详情 ▾';
  }
};

/* ============================================================
   2. HTTP Wrapper
   ============================================================ */

/**
 * fetch with Authorization header + unified error handling.
 * On 401, clears token and redirects to /login.
 */
async function fetchWithAuth(url, options = {}) {
  const token = Auth.getToken();
  const headers = {
    ...(options.headers || {}),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  let resp;
  try {
    resp = await fetch(url, { ...options, headers });
  } catch (networkErr) {
    throw new Error(`网络错误: ${networkErr.message}`);
  }

  if (resp.status === 401) {
    Auth.clearToken();
    window.location.href = '/login';
    throw new Error('认证已过期，请重新登录');
  }

  if (!resp.ok) {
    let detail = '';
    try {
      const body = await resp.json();
      detail = body.detail || body.message || '';
    } catch (_) { /* non-JSON body */ }
    throw new Error(`HTTP ${resp.status}${detail ? ` — ${detail}` : ''}`);
  }

  const contentType = resp.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return resp.json();
  }
  return resp.text();
}

/** Shorthand for GET JSON. */
async function getJSON(path) {
  return fetchWithAuth(`${API}${path}`);
}

/** Shorthand for POST JSON. Optional body is sent as JSON. */
async function postJSON(path, body) {
  const opts = { method: 'POST' };
  if (body !== undefined) {
    opts.headers = { 'Content-Type': 'application/json' };
    opts.body = JSON.stringify(body);
  }
  return fetchWithAuth(`${API}${path}`, opts);
}

/** Shorthand for DELETE JSON with an optional JSON body. */
async function delJSON(path, body) {
  const opts = { method: 'DELETE' };
  if (body !== undefined) {
    opts.headers = { 'Content-Type': 'application/json' };
    opts.body = JSON.stringify(body);
  }
  return fetchWithAuth(`${API}${path}`, opts);
}

/* ============================================================
   3. Helpers
   ============================================================ */

function esc(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** Safely parse a JSON string field (tags are stored as JSON strings). */
function parseJSONField(value, fallback) {
  if (Array.isArray(value)) return value;
  if (!value) return fallback;
  if (typeof value === 'string') {
    try { return JSON.parse(value); } catch (_) { return fallback; }
  }
  return fallback;
}

function heatColor(score) {
  if (score >= 75) return 'var(--danger)';
  if (score >= 50) return 'var(--brand-hover)';
  if (score >= 25) return 'var(--success)';
  return 'var(--text-tertiary)';
}

function trendBadge(trend) {
  const map = {
    rising: '↗ Rising',
    peak: '↑ Peak',
    sustained: '→ Sustained',
    cooling: '↓ Cooling',
  };
  const key = trend || 'sustained';
  return `<span class="badge badge-${key}">${map[key] || esc(trend)}</span>`;
}

function categoryBadge(cat) {
  const map = {
    cli: 'CLI',
    web: 'Web',
    library: 'Library',
    bot: 'Bot',
    tool: 'Tool',
  };
  const key = cat || 'tool';
  return `<span class="badge badge-${key}">${map[key] || esc(cat)}</span>`;
}

function difficultyClass(d) {
  return d === 'easy' ? 'difficulty-easy'
    : d === 'hard' ? 'difficulty-hard'
    : 'difficulty-medium';
}

function loadingHTML(text = '加载中…') {
  return `<div class="loading-inline"><span class="spinner"></span>${esc(text)}</div>`;
}

function emptyHTML(icon, title, desc) {
  return `<div class="state-block">
    <div class="state-icon">${icon}</div>
    <div class="state-title">${esc(title)}</div>
    <div class="state-desc">${desc || ''}</div>
  </div>`;
}

function errorHTML(message) {
  return `<div class="error-block">
    <div class="error-title">加载失败</div>
    <div>${esc(message)}</div>
  </div>`;
}

function setPageTitle(title, subtitle) {
  const content = document.getElementById('content');
  if (!content) return;
  const header = `<div class="page-header">
    <div>
      <div class="page-title">${esc(title)}</div>
      ${subtitle ? `<div class="page-subtitle">${esc(subtitle)}</div>` : ''}
    </div>
    <div class="page-header-actions">
      <button class="btn btn-ghost btn-sm" onclick="Auth.logout()">登出</button>
    </div>
  </div>`;
  content.innerHTML = header + `<div class="page-enter" id="page-body"></div>`;
}

function setBody(html) {
  const body = document.getElementById('page-body');
  if (body) {
    body.innerHTML = html;
    body.classList.remove('page-enter');
    void body.offsetWidth; /* reflow to restart animation */
    body.classList.add('page-enter');
  }
}

/* ============================================================
   4. Chart.js Loader
   ============================================================ */

let _chartJsPromise = null;

function loadChartJS() {
  if (window.Chart) return Promise.resolve(window.Chart);
  if (_chartJsPromise) return _chartJsPromise;
  _chartJsPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = CHART_JS_CDN;
    script.onload = () => resolve(window.Chart);
    script.onerror = () => reject(new Error('Chart.js CDN 加载失败'));
    document.head.appendChild(script);
  });
  return _chartJsPromise;
}

/* ============================================================
   5. Dashboard Page
   ============================================================ */

async function loadDashboard() {
  if (Auth.requireAuth()) return;

  const content = document.getElementById('content');
  content.innerHTML = `<div class="page-header">
    <div>
      <div class="page-title">仪表盘</div>
      <div class="page-subtitle">今日趋势概览与项目推荐</div>
    </div>
    <div class="page-header-actions">
      <button class="btn btn-primary btn-sm" id="run-daily-btn" onclick="handleRunDaily(event)">▶ 立即运行日报</button>
      <button class="btn btn-ghost btn-sm" onclick="Auth.logout()">登出</button>
    </div>
  </div><div class="page-enter" id="page-body">${loadingHTML('正在加载最新报告…')}</div>`;

  try {
    const [report, stats, dates] = await Promise.all([
      getJSON('/latest'),
      getJSON('/stats'),
      getJSON('/dates').catch(() => []),
    ]);

    if (!report.date) {
      setBody(emptyHTML(
        '🔭',
        '暂无报告数据',
        '请先运行 <code>python scripts/run_daily.py</code> 采集数据并生成报告。',
      ));
      return;
    }

    const hotTopics = report.hot_topics || [];
    const suggestions = report.suggestions || [];

    let html = `
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">报告日期</div>
          <div class="stat-value text-value">${esc(report.date)}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">采集数据量</div>
          <div class="stat-value">${report.raw_items_count || 0}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">热点主题</div>
          <div class="stat-value">${hotTopics.length}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">项目建议</div>
          <div class="stat-value">${suggestions.length}</div>
        </div>
      </div>

      <div class="chart-card">
        <div class="chart-header">
          <div>
            <div class="chart-title">7 天热度趋势</div>
            <div class="chart-subtitle">每日采集数据量变化</div>
          </div>
        </div>
        <div class="chart-container">
          <canvas id="trendChart"></canvas>
        </div>
      </div>

      <div class="card">
        <div class="card-title">今日趋势概述</div>
        <p style="font-size:14px; color:var(--text-secondary); line-height:1.7;">
          ${esc(report.summary || '暂无概述')}
        </p>
      </div>

      <div class="section-title">
        热点主题
        <span class="section-count">${hotTopics.length}</span>
      </div>`;

    if (hotTopics.length) {
      html += `<div class="topic-list">`;
      hotTopics.forEach((t, idx) => {
        const evidence = t.evidence || [];
        const keyInsights = t.key_insights || [];
        const recommendations = t.recommendations || [];
        const detailedAnalysis = t.detailed_analysis || '';
        const languages = t.languages || [];
        const cardId = `topic-detail-${idx}`;
        html += `
          <div class="topic-card">
            <div class="topic-head">
              <div class="topic-name">${esc(t.topic)}</div>
              ${trendBadge(t.trend)}
            </div>
            <div class="topic-desc">${esc(t.description || '')}</div>
            <div class="heat-bar">
              <div class="heat-bar-fill" style="width:${t.heat_score || 0}%; background:${heatColor(t.heat_score)};"></div>
            </div>
            <div class="topic-meta">
              <span>热度 <span style="color:var(--text-secondary); font-weight:500;">${t.heat_score || 0}</span>/100</span>
              ${languages.length ? `<span class="topic-langs">${languages.map((l) => `<span class="badge badge-tool" style="margin-left:4px;">${esc(l)}</span>`).join('')}</span>` : ''}
            </div>
            ${evidence.length ? `<div class="topic-evidence"><span class="evidence-label">证据:</span>${evidence.map((e) => esc(e)).join(' · ')}</div>` : ''}
            ${(detailedAnalysis || keyInsights.length || recommendations.length) ? `
              <button class="btn btn-ghost btn-sm topic-expand-btn" onclick="toggleTopicDetail('${cardId}', this)">展开详情 ▾</button>
              <div class="topic-detail" id="${cardId}" style="display:none;">
                ${detailedAnalysis ? `<div class="topic-detail-section"><div class="topic-detail-label">📊 深度分析</div><div class="topic-detail-text">${esc(detailedAnalysis)}</div></div>` : ''}
                ${keyInsights.length ? `<div class="topic-detail-section"><div class="topic-detail-label">💡 关键洞察</div><ul class="topic-detail-list">${keyInsights.map((i) => `<li>${esc(i)}</li>`).join('')}</ul></div>` : ''}
                ${recommendations.length ? `<div class="topic-detail-section"><div class="topic-detail-label">🎯 建议</div><ul class="topic-detail-list">${recommendations.map((r) => `<li>${esc(r)}</li>`).join('')}</ul></div>` : ''}
              </div>` : ''}
          </div>`;
      });
      html += `</div>`;
    } else {
      html += `<div class="card"><p class="text-tertiary" style="font-size:13px;">暂无热点</p></div>`;
    }

    html += `<div class="section-title">今日推荐项目<span class="section-count">${suggestions.length}</span></div>`;
    if (suggestions.length) {
      html += `<div class="suggestions-grid">`;
      suggestions.forEach((s) => {
        const techStack = s.tech_stack || [];
        html += `
          <div class="suggestion-card">
            <div class="suggestion-head">
              <div class="suggestion-name">${esc(s.name)}</div>
              ${categoryBadge(s.category)}
            </div>
            <div class="suggestion-tagline">${esc(s.tagline || '')}</div>
            <div class="suggestion-desc">${esc(s.description || '')}</div>
            ${techStack.length ? `<div class="suggestion-section"><div class="section-label">技术栈</div><div style="display:flex; flex-wrap:wrap; gap:6px;">${techStack.map((t) => `<span class="tag">${esc(t)}</span>`).join('')}</div></div>` : ''}
            <div class="suggestion-meta">
              ${s.estimated_stars ? `<span class="meta-item"><span>★</span><span class="meta-value">${esc(s.estimated_stars)}</span></span>` : ''}
              ${s.timeline ? `<span class="meta-item"><span>⏱</span><span class="meta-value">${esc(s.timeline)}</span></span>` : ''}
              ${s.difficulty ? `<span class="meta-item ${difficultyClass(s.difficulty)}">${esc(s.difficulty)}</span>` : ''}
            </div>
            <a href="/suggestions?date=${encodeURIComponent(report.date)}" class="btn btn-ghost btn-sm">查看详情 →</a>
          </div>`;
      });
      html += `</div>`;
    } else {
      html += `<div class="card"><p class="text-tertiary" style="font-size:13px;">暂无建议</p></div>`;
    }

    setBody(html);

    /* Render Chart.js 7-day trend (uses recent_summaries from /stats) */
    renderTrendChart(stats, dates).catch((e) => console.warn('Chart render failed:', e));
  } catch (e) {
    setBody(errorHTML(e.message));
  }
}

/**
 * Render a 7-day line chart of daily collected data volume.
 * @param stats — /api/stats response
 * @param dates — /api/dates array
 */
async function renderTrendChart(stats, dates) {
  const recent = (stats && stats.recent_summaries) || [];
  if (!recent.length) return;

  let chartData = recent.slice(0, 7).reverse(); /* oldest → newest */

  /* If we have fewer than 7 from stats, try to fill from dates */
  if (chartData.length < 7 && dates && dates.length) {
    chartData = chartData.slice();
  }

  const labels = chartData.map((s) => s.date);
  const values = chartData.map((s) => s.raw_items_count || 0);

  let Chart;
  try {
    Chart = await loadChartJS();
  } catch (e) {
    console.warn('Chart.js unavailable:', e.message);
    return;
  }

  const canvas = document.getElementById('trendChart');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  /* SPA 下反复进入仪表盘会重复 new Chart，先销毁上一个实例避免泄漏 */
  if (window._dashChart) {
    try { window._dashChart.destroy(); } catch (_) { /* noop */ }
  }
  const gradient = ctx.createLinearGradient(0, 0, 0, 240);
  gradient.addColorStop(0, 'rgba(94, 106, 210, 0.25)');
  gradient.addColorStop(1, 'rgba(94, 106, 210, 0)');

  window._dashChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: '采集数据量',
        data: values,
        borderColor: '#5e6ad2',
        backgroundColor: gradient,
        borderWidth: 2,
        fill: true,
        tension: 0.35,
        pointRadius: 3,
        pointHoverRadius: 5,
        pointBackgroundColor: '#5e6ad2',
        pointBorderColor: '#0f1011',
        pointBorderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#191a1b',
          borderColor: 'rgba(255,255,255,0.08)',
          borderWidth: 1,
          titleColor: '#f7f8f8',
          bodyColor: '#d0d6e0',
          padding: 10,
          cornerRadius: 6,
          displayColors: false,
        },
      },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.04)', drawBorder: false },
          ticks: { color: '#8a8f98', font: { size: 11, family: 'JetBrains Mono' } },
        },
        y: {
          grid: { color: 'rgba(255,255,255,0.04)', drawBorder: false },
          ticks: { color: '#8a8f98', font: { size: 11 } },
          beginAtZero: true,
        },
      },
    },
  });
}

/* ============================================================
   6. Trends Page
   ============================================================ */

async function loadTrends() {
  /* Check if server-side rendered data is already present */
  if (document.getElementById('trends-data')) {
    /* Server-side rendering — data embedded by backend.
       Auth check only — don't re-render. */
    if (Auth.requireAuth()) return;
    return;
  }
  if (Auth.requireAuth()) return;

  setPageTitle('趋势详情', '按数据源分组的原始采集数据');
  setBody(loadingHTML('正在加载趋势数据…'));

  try {
    const dates = await getJSON('/dates');
    if (!dates.length) {
      setBody(emptyHTML('📭', '暂无数据', '还没有任何采集记录。'));
      return;
    }

    const params = new URLSearchParams(window.location.search);
    let selectedDate = params.get('date') || dates[0];
    if (!dates.includes(selectedDate)) selectedDate = dates[0];

    /* Fetch only summary (counts per source) — tiny payload */
    const summary = await getJSON(`/trends/${selectedDate}/summary`);
    const sourceCounts = summary.sources || {};

    const sourceLabels = {
      github: 'GitHub',
      hackernews: 'Hacker News',
      reddit: 'Reddit',
      twitter: 'Twitter / X',
      arxiv: 'arXiv',
    };

    /* Build sorted source list: known sources first (in defined order), then unknowns */
    const knownOrder = ['github', 'hackernews', 'reddit', 'twitter', 'arxiv'];
    const sources = knownOrder.filter((s) => sourceCounts[s]);
    for (const s of Object.keys(sourceCounts)) {
      if (!knownOrder.includes(s)) sources.push(s);
    }

    let dateSelector = `<div class="date-selector"><label>日期</label><select onchange="navigateTo('/trends?date='+this.value)">`;
    dates.forEach((d) => {
      dateSelector += `<option value="${esc(d)}" ${d === selectedDate ? 'selected' : ''}>${esc(d)}</option>`;
    });
    dateSelector += `</select></div>`;

    if (!sources.length) {
      setBody(dateSelector + emptyHTML('📭', '该日期无数据', `日期 ${esc(selectedDate)} 没有采集到任何趋势数据。`));
      return;
    }

    /* Build tabs */
    let html = dateSelector;
    html += `<div class="source-tabs">`;
    sources.forEach((src, idx) => {
      const label = sourceLabels[src] || esc(src);
      const count = sourceCounts[src];
      html += `<button class="source-tab ${idx === 0 ? 'active' : ''}" data-source="${esc(src)}" onclick="switchTrendTab('${esc(src)}')">${esc(label)} <span class="tab-count">${count}</span></button>`;
    });
    html += `</div>`;

    /* Build empty tab panels — content loaded on demand */
    sources.forEach((src, idx) => {
      const label = sourceLabels[src] || esc(src);
      const isActive = idx === 0;
      html += `<div class="tab-panel ${isActive ? 'active' : ''}" id="tab-${esc(src)}">`;
      html += `<div class="source-group"><div class="source-header"><div class="source-title">${esc(label)} <span class="source-count">${sourceCounts[src]}</span></div></div>`;
      html += `<div id="content-${esc(src)}">${loadingHTML('点击加载 ' + esc(label) + ' 数据…')}</div>`;
      html += `</div></div>`;
    });

    setBody(html);

    /* Lazily load the first tab */
    window._trendsDate = selectedDate;
    window._trendsLoaded = {};
    loadTrendSource(sources[0], sourceCounts[sources[0]]);
  } catch (e) {
    setBody(errorHTML(e.message));
  }
}

async function loadTrendSource(source, expectedCount) {
  if (window._trendsLoaded[source]) return;
  window._trendsLoaded[source] = true;

  const container = document.getElementById(`content-${source}`);
  if (!container) return;
  container.innerHTML = loadingHTML('正在加载 ' + source + ' 数据…');

  const ITEMS_PER_PAGE = 30;

  try {
    const items = await getJSON(`/trends/${window._trendsDate}?source=${encodeURIComponent(source)}`);

    if (!items.length) {
      container.innerHTML = '<p class="text-tertiary" style="font-size:13px;">无数据</p>';
      return;
    }

    let html = `<div class="trend-grid" id="grid-${source}">`;
    html += items.slice(0, ITEMS_PER_PAGE).map((t) => renderTrendCard(t)).join('');
    html += `</div>`;

    const hasMore = items.length > ITEMS_PER_PAGE;
    if (hasMore) {
      html += `<div class="load-more-wrapper"><button class="btn btn-ghost btn-sm" onclick="loadMoreTrends('${source}', ${ITEMS_PER_PAGE})">加载更多 (${items.length - ITEMS_PER_PAGE} 条剩余)</button></div>`;
    }

    container.innerHTML = html;
    window._trendData = window._trendData || {};
    window._trendData[source] = items;
    window._trendPageCount = window._trendPageCount || {};
    window._trendPageCount[source] = 1;
  } catch (e) {
    container.innerHTML = errorHTML(e.message);
    window._trendsLoaded[source] = false;
  }
}

function renderTrendCard(t) {
  const tags = parseJSONField(t.tags, []);
  const stars = (t.total_stars != null) ? t.total_stars : t.popularity;
  return `
    <div class="trend-card">
      <div class="trend-title">
        <a href="${esc(t.url || '#')}" target="_blank" rel="noopener">${esc(t.title || '')}</a>
        ${t.is_new ? `<span class="badge badge-rising">NEW</span>` : ''}
      </div>
      ${t.description ? `<div class="trend-desc">${esc(t.description)}</div>` : ''}
      <div class="trend-meta">
        ${t.language ? `<span class="badge badge-tool">${esc(t.language)}</span>` : ''}
        ${stars ? `<span class="trend-popularity">★ ${esc(stars)}</span>` : ''}
        ${t.daily_rate ? `<span class="trend-popularity">📈 +${esc(t.daily_rate)}/天</span>` : ''}
        ${tags.map((tag) => `<span class="badge badge-sustained">${esc(tag)}</span>`).join('')}
      </div>
    </div>`;
}

function switchTrendTab(source) {
  document.querySelectorAll('.source-tab').forEach((t) => t.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach((p) => p.classList.remove('active'));
  const tab = document.querySelector(`.source-tab[data-source="${source}"]`);
  const panel = document.getElementById(`tab-${source}`);
  if (tab) tab.classList.add('active');
  if (panel) panel.classList.add('active');

  /* Lazy load this tab's data if not yet loaded */
  if (!window._trendsLoaded[source]) {
    const countEl = panel?.querySelector('.source-count');
    const count = countEl ? parseInt(countEl.textContent) : 0;
    loadTrendSource(source, count);
  }
}

function loadMoreTrends(source, perPage) {
  const data = window._trendData;
  if (!data || !data[source]) return;
  const page = (window._trendPageCount[source] || 1) + 1;
  const start = (page - 1) * perPage;
  const newItems = data[source].slice(start, start + perPage);
  const grid = document.getElementById(`grid-${source}`);
  if (grid) {
    grid.insertAdjacentHTML('beforeend', newItems.map((t) => renderTrendCard(t)).join(''));
  }
  window._trendPageCount[source] = page;
  const remaining = data[source].length - (start + perPage);
  const wrapper = grid?.parentElement?.querySelector('.load-more-wrapper');
  if (remaining <= 0 && wrapper) {
    wrapper.remove();
  } else if (wrapper) {
    wrapper.querySelector('button').textContent = `加载更多 (${remaining} 条剩余)`;
  }
}

window.switchTrendTab = switchTrendTab;
window.loadMoreTrends = loadMoreTrends;
window.loadTrendSource = loadTrendSource;

/* ============================================================
   7. Suggestions Page
   ============================================================ */

let _suggManage = false;        // 是否处于管理模式
let _suggSelected = new Set();  // 已选中的建议 id
let _suggDate = '';             // 当前查看的日期
let _suggData = [];             // 当前日期的建议列表（摘要数据，用于导出）

/** 渲染单张建议卡片（div 版，支持选中/置顶）。 */
function suggestionCardHTML(s) {
  const techStack = (s.tech_stack || []).slice(0, 5);
  const pinned = !!s.pinned;
  let html = `
    <div class="suggestion-card sugg-card${pinned ? ' pinned' : ''}" data-id="${s.id}">
      <input type="checkbox" class="sugg-check" aria-label="选择" ${_suggSelected.has(s.id) ? 'checked' : ''}>
      <button class="sugg-pin${pinned ? ' active' : ''}" title="置顶/取消置顶" aria-label="置顶">${pinned ? '★' : '☆'}</button>
      <div class="suggestion-head">
        <div class="suggestion-name">${esc(s.name)}</div>
        ${categoryBadge(s.category)}
      </div>
      <div class="suggestion-tagline">${esc(s.tagline || '')}</div>
      <div class="suggestion-desc">${esc(s.description || '')}</div>
      <div class="suggestion-meta">
        ${s.estimated_stars ? `<span class="meta-item"><span>★</span><span class="meta-value">${esc(s.estimated_stars)}</span></span>` : ''}
        ${s.timeline ? `<span class="meta-item"><span>⏱</span><span class="meta-value">${esc(s.timeline)}</span></span>` : ''}
        ${s.difficulty ? `<span class="meta-item ${difficultyClass(s.difficulty)}">${esc(s.difficulty)}</span>` : ''}
      </div>`;
  if (techStack.length) {
    html += `<div class="suggestion-section">
      <div style="display:flex; flex-wrap:wrap; gap:6px;">
        ${techStack.map((t) => `<span class="tag">${esc(t)}</span>`).join('')}
      </div>
    </div>`;
  }
  html += `<div class="suggestion-cta">查看详情 →</div></div>`;
  return html;
}

async function loadSuggestions() {
  if (Auth.requireAuth()) return;

  setPageTitle('项目建议', 'AI 分析推荐的开源项目创意');
  setBody(loadingHTML('正在加载项目建议…'));

  try {
    const dates = await getJSON('/dates');
    if (!dates.length) {
      setBody(emptyHTML('📭', '暂无建议', '还没有任何报告数据。'));
      return;
    }

    const params = new URLSearchParams(window.location.search);
    let selectedDate = params.get('date') || dates[0];
    if (!dates.includes(selectedDate)) selectedDate = dates[0];

    const report = await getJSON(`/report/${selectedDate}`);
    const suggestions = report.suggestions || [];

    // 重置管理状态
    _suggManage = false;
    _suggSelected = new Set();
    _suggDate = selectedDate;
    _suggData = suggestions;

    let dateSelector = `<div class="date-selector"><label>日期</label><select onchange="navigateTo('/suggestions?date='+this.value)">`;
    dates.forEach((d) => {
      dateSelector += `<option value="${esc(d)}" ${d === selectedDate ? 'selected' : ''}>${esc(d)}</option>`;
    });
    dateSelector += `</select></div>`;

    let html = dateSelector;
    html += `<div class="section-title">项目建议 <span class="section-count">${suggestions.length}</span>`;
    if (suggestions.length) {
      html += `<button class="btn btn-ghost btn-sm sugg-manage-btn" id="sugg-manage-btn">管理</button>`;
    }
    html += `</div>`;

    if (!suggestions.length) {
      html += `<div class="card"><p class="text-tertiary" style="font-size:13px;">此日期无建议</p></div>`;
      setBody(html);
      return;
    }

    html += `<div class="suggestions-grid" id="sugg-grid">`;
    for (const s of suggestions) html += suggestionCardHTML(s);
    html += `</div>`;

    // 底部浮动工具栏（仅管理模式显示）
    html += `<div class="sugg-toolbar" id="sugg-toolbar" hidden>
      <span class="sugg-toolbar-count">已选 <b id="sugg-sel-count">0</b> 项</span>
      <div class="sugg-toolbar-actions">
        <button class="btn btn-ghost btn-sm" id="sugg-selall">全选</button>
        <button class="btn btn-ghost btn-sm" id="sugg-export">导出</button>
        <button class="btn btn-danger btn-sm" id="sugg-delete">删除</button>
        <button class="btn btn-ghost btn-sm" id="sugg-exit">退出管理</button>
      </div>
    </div>`;

    setBody(html);
    _wireSuggestions();
  } catch (e) {
    setBody(errorHTML(e.message));
  }
}

/** 绑定建议页的所有交互（每次渲染后调用）。 */
function _wireSuggestions() {
  const grid = document.getElementById('sugg-grid');
  const manageBtn = document.getElementById('sugg-manage-btn');
  if (!grid) return;

  if (manageBtn) manageBtn.addEventListener('click', () => _setSuggManage(!_suggManage));

  grid.addEventListener('click', (e) => {
    const card = e.target.closest('.sugg-card');
    if (!card) return;
    const id = Number(card.dataset.id);

    if (e.target.closest('.sugg-pin')) {
      e.preventDefault();
      _togglePin(id, card);
      return;
    }
    if (e.target.closest('.sugg-check')) {
      _toggleSelect(id, card);
      return;
    }
    if (_suggManage) {
      _toggleSelect(id, card);
      return;
    }
    navigateTo('/suggestion/' + id);
  });

  const on = (idAttr, fn) => { const el = document.getElementById(idAttr); if (el) el.addEventListener('click', fn); };
  on('sugg-exit', () => _setSuggManage(false));
  on('sugg-selall', _toggleSelectAll);
  on('sugg-delete', _deleteSelected);
  on('sugg-export', _exportSelected);
}

function _setSuggManage(on) {
  _suggManage = on;
  const grid = document.getElementById('sugg-grid');
  const toolbar = document.getElementById('sugg-toolbar');
  const btn = document.getElementById('sugg-manage-btn');
  if (grid) grid.classList.toggle('manage', on);
  if (toolbar) toolbar.hidden = !on;
  if (btn) btn.textContent = on ? '完成' : '管理';
  if (!on) {
    _suggSelected.clear();
    grid?.querySelectorAll('.sugg-card.selected').forEach((c) => c.classList.remove('selected'));
    grid?.querySelectorAll('.sugg-check').forEach((c) => { c.checked = false; });
    const selall = document.getElementById('sugg-selall');
    if (selall) selall.textContent = '全选';
  }
  _updateSuggToolbar();
}

function _toggleSelect(id, card) {
  const sel = _suggSelected.has(id);
  if (sel) _suggSelected.delete(id); else _suggSelected.add(id);
  const now = _suggSelected.has(id);
  card.classList.toggle('selected', now);
  const cb = card.querySelector('.sugg-check');
  if (cb) cb.checked = now;
  _updateSuggToolbar();
}

function _toggleSelectAll() {
  const grid = document.getElementById('sugg-grid');
  if (!grid) return;
  const cards = [...grid.querySelectorAll('.sugg-card')];
  const allSelected = cards.length && cards.every((c) => _suggSelected.has(Number(c.dataset.id)));
  cards.forEach((c) => {
    const id = Number(c.dataset.id);
    if (allSelected) _suggSelected.delete(id); else _suggSelected.add(id);
    const now = _suggSelected.has(id);
    c.classList.toggle('selected', now);
    const cb = c.querySelector('.sugg-check');
    if (cb) cb.checked = now;
  });
  const selall = document.getElementById('sugg-selall');
  if (selall) selall.textContent = allSelected ? '全选' : '取消全选';
  _updateSuggToolbar();
}

function _updateSuggToolbar() {
  const count = document.getElementById('sugg-sel-count');
  if (count) count.textContent = String(_suggSelected.size);
  const del = document.getElementById('sugg-delete');
  const exp = document.getElementById('sugg-export');
  const empty = _suggSelected.size === 0;
  if (del) del.disabled = empty;
  if (exp) exp.disabled = empty;
}

async function _togglePin(id, card) {
  const willPin = !card.classList.contains('pinned');
  const btn = card.querySelector('.sugg-pin');
  try {
    await postJSON(`/suggestion/${id}/pin`, { pinned: willPin });
    // 置顶状态变化会影响排序，重新加载列表
    loadSuggestions();
  } catch (e) {
    if (btn) { btn.classList.add('pin-error'); setTimeout(() => btn.classList.remove('pin-error'), 1200); }
    alert('操作失败：' + e.message);
  }
}

async function _deleteSelected() {
  const ids = [..._suggSelected];
  if (!ids.length) return;
  const ok = await confirmGlass({
    icon: '🗑️',
    title: `删除 ${ids.length} 个项目建议？`,
    desc: '删除后无法恢复。项目建议是可由 AI 重新生成的内容。',
    confirmLabel: '永久删除',
    danger: true,
  });
  if (!ok) return;
  try {
    await delJSON('/suggestions', { ids });
    loadSuggestions();
  } catch (e) {
    alert('删除失败：' + e.message);
  }
}

function _exportSelected() {
  const ids = _suggSelected;
  const items = _suggData.filter((s) => ids.has(s.id));
  if (!items.length) return;
  let md = `# 项目建议导出（${_suggDate}）\n\n`;
  items.forEach((s, i) => {
    md += `## ${i + 1}. ${s.name}\n\n`;
    if (s.tagline) md += `> ${s.tagline}\n\n`;
    if (s.category) md += `- **分类**：${s.category}\n`;
    if (s.estimated_stars) md += `- **预估 Star**：${s.estimated_stars}\n`;
    if (s.timeline) md += `- **时间线**：${s.timeline}\n`;
    if (s.difficulty) md += `- **难度**：${s.difficulty}\n`;
    md += `\n`;
    if (s.description) md += `${s.description}\n\n`;
    if ((s.tech_stack || []).length) md += `**技术栈**：${s.tech_stack.join('、')}\n\n`;
    if ((s.key_features || []).length) md += `**核心功能**：\n${s.key_features.map((f) => `- ${f}`).join('\n')}\n\n`;
    if ((s.viral_hooks || []).length) md += `**病毒传播因素**：${s.viral_hooks.join('、')}\n\n`;
    md += `---\n\n`;
  });
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `项目建议_${_suggDate}.md`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/* ============================================================
   7a. Reusable frosted-glass confirm dialog
   ============================================================ */

/** 通用毛玻璃确认框，返回 Promise<boolean>。 */
function confirmGlass({ icon = '⚠️', title = '确认操作', desc = '', confirmLabel = '确认', danger = false } = {}) {
  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.className = 'rd-overlay';
    overlay.innerHTML = `
      <div class="rd-modal" role="dialog" aria-modal="true">
        <button class="rd-close" aria-label="关闭">✕</button>
        <div class="rd-icon">${icon}</div>
        <h3 class="rd-title">${esc(title)}</h3>
        ${desc ? `<p class="rd-desc">${esc(desc)}</p>` : ''}
        <div class="rd-actions">
          <button class="btn btn-ghost" data-act="cancel">取消</button>
          <button class="btn ${danger ? 'btn-danger' : 'btn-primary'}" data-act="ok">${esc(confirmLabel)}</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add('rd-show'));

    const close = (val) => {
      overlay.classList.remove('rd-show');
      document.removeEventListener('keydown', onKey);
      setTimeout(() => overlay.remove(), 240);
      resolve(val);
    };
    const onKey = (e) => { if (e.key === 'Escape') close(false); };
    document.addEventListener('keydown', onKey);
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) close(false);
      const act = e.target.closest('[data-act]')?.dataset.act;
      if (act === 'ok') close(true);
      if (act === 'cancel') close(false);
    });
    overlay.querySelector('.rd-close').addEventListener('click', () => close(false));
  });
}

/* ============================================================
   8. Archive Page
   ============================================================ */

/* ============================================================
   7b. Suggestion Detail Page
   ============================================================ */

let _detailSuggestionId = null;

/** Render a text block that may contain ```fenced code``` — code → <pre>, text → <br>. */
function renderTextBlock(text) {
  if (!text) return '';
  const parts = String(text).split('```');
  let out = '';
  parts.forEach((part, i) => {
    if (i % 2 === 1) {
      // code block — drop an optional leading language line
      const body = part.replace(/^[a-zA-Z0-9_-]*\n/, '');
      out += `<pre class="code-block">${esc(body.replace(/\n+$/, ''))}</pre>`;
    } else if (part.trim()) {
      out += `<p class="detail-text">${esc(part.trim()).replace(/\n/g, '<br>')}</p>`;
    }
  });
  return out;
}

function genSectionHTML(title, key1, key2, full, btnLabel, handler) {
  const has = (full[key1] && full[key1].length) || (key2 && full[key2] && full[key2].length);
  let inner;
  if (has) {
    inner = renderTextBlock(full[key1]);
    if (key2 && full[key2]) inner += renderTextBlock(full[key2]);
  } else {
    inner = `<button class="btn btn-primary" onclick="${handler}(this)">✨ ${btnLabel}</button>
      <p class="text-tertiary" style="font-size:12px; margin-top:8px;">点击后调用 AI 单独生成，约需 10-30 秒</p>`;
  }
  return `<div class="card detail-section">
    <div class="section-label">${title}</div>
    <div class="detail-section-body">${inner}</div>
  </div>`;
}

async function loadSuggestionDetail() {
  if (Auth.requireAuth()) return;

  const m = window.location.pathname.match(/\/suggestion\/(\d+)/);
  const id = m ? m[1] : null;
  _detailSuggestionId = id;

  setPageTitle('项目建议详情', '');
  setBody(loadingHTML('正在加载详情…'));

  if (!id) {
    setBody(errorHTML('无效的建议 ID'));
    return;
  }

  try {
    const s = await getJSON(`/suggestion/${id}`);
    const keyFeatures = s.key_features || [];
    const mvpFeatures = s.mvp_features || [];
    const techStack = s.tech_stack || [];
    const similarProjects = s.similar_projects || [];
    const viralHooks = s.viral_hooks || [];

    let html = `<div class="detail-topbar">
      <a class="back-link" href="/suggestions?date=${esc(s.date || '')}">← 返回项目建议</a>
      <button class="btn btn-ghost btn-sm" id="regen-btn">🔄 重新生成</button>
    </div>`;

    html += `<div class="detail-header">
      <div class="suggestion-head">
        <div class="suggestion-name" style="font-size:22px;">${esc(s.name)}</div>
        ${categoryBadge(s.category)}
      </div>
      <div class="suggestion-tagline" style="font-size:15px;">${esc(s.tagline || '')}</div>
      <div class="suggestion-meta">
        ${s.estimated_stars ? `<span class="meta-item"><span>★</span><span class="meta-value">${esc(s.estimated_stars)}</span></span>` : ''}
        ${s.timeline ? `<span class="meta-item"><span>⏱</span><span class="meta-value">${esc(s.timeline)}</span></span>` : ''}
        ${s.difficulty ? `<span class="meta-item ${difficultyClass(s.difficulty)}">${esc(s.difficulty)}</span>` : ''}
      </div>
    </div>`;

    if (s.description) {
      html += `<div class="card detail-section"><div class="section-label">项目描述</div>
        <p class="detail-text">${esc(s.description)}</p></div>`;
    }

    if (s.target_audience) {
      html += `<div class="card detail-section"><div class="section-label">目标用户</div>
        <p class="detail-text">${esc(s.target_audience)}</p></div>`;
    }

    if (keyFeatures.length) {
      html += `<div class="card detail-section"><div class="section-label">核心功能</div>
        <ul class="key-features">${keyFeatures.map((f) => `<li>${esc(f)}</li>`).join('')}</ul></div>`;
    }

    if (techStack.length) {
      html += `<div class="card detail-section"><div class="section-label">技术栈</div>
        <div style="display:flex; flex-wrap:wrap; gap:6px;">${techStack.map((t) => `<span class="tag">${esc(t)}</span>`).join('')}</div></div>`;
    }

    if (mvpFeatures.length) {
      html += `<div class="card detail-section"><div class="section-label">MVP 功能</div>
        <ul class="key-features">${mvpFeatures.map((f) => `<li>${esc(f)}</li>`).join('')}</ul></div>`;
    }

    if (similarProjects.length) {
      html += `<div class="card detail-section"><div class="section-label">类似项目对比</div>
        <table class="compare-table"><thead><tr><th>项目</th><th>Star</th><th>我们的优势</th></tr></thead><tbody>`;
      similarProjects.forEach((p) => {
        html += `<tr><td>${esc(p.name || '')}</td><td style="color:var(--text-tertiary);">${esc(p.stars || '')}</td><td class="col-advantage">${esc(p.our_advantage || '')}</td></tr>`;
      });
      html += `</tbody></table></div>`;
    }

    if (viralHooks.length) {
      html += `<div class="card detail-section"><div class="section-label">病毒传播因素</div>
        <div style="line-height:1.9;">${viralHooks.map((h) => `<span class="badge badge-rising" style="margin:2px;">${esc(h)}</span>`).join(' ')}</div></div>`;
    }

    // On-demand sections
    html += genSectionHTML('架构与目录结构', 'architecture', 'repo_structure', s, '生成架构与目录结构', 'genArchitecture');
    html += genSectionHTML('README 营销策略', 'readme_strategy', 'naming_tips', s, '生成 README 营销策略', 'genReadme');

    setBody(html);

    const regenBtn = document.getElementById('regen-btn');
    if (regenBtn) regenBtn.addEventListener('click', () => _regenerateSuggestion(id, regenBtn));
  } catch (e) {
    setBody(errorHTML(e.message));
  }
}

async function _regenerateSuggestion(id, btn) {
  const ok = await confirmGlass({
    icon: '🔄',
    title: '重新生成这个项目建议？',
    desc: '将基于当天的趋势分析重新调用 AI 生成一个新点子，覆盖当前内容（约 10-30 秒）。置顶状态保留。',
    confirmLabel: '重新生成',
  });
  if (!ok) return;
  btn.disabled = true;
  btn.textContent = '生成中…';
  try {
    await postJSON(`/suggestion/${id}/regenerate`);
    loadSuggestionDetail();
  } catch (e) {
    btn.disabled = false;
    btn.textContent = '🔄 重新生成';
    alert('重新生成失败：' + e.message);
  }
}

async function _genSection(btn, endpoint) {
  if (!_detailSuggestionId) return;
  const body = btn.closest('.detail-section-body');
  const original = btn.textContent;
  btn.disabled = true;
  btn.textContent = '生成中…';
  try {
    const result = await postJSON(`/suggestion/${_detailSuggestionId}/${endpoint}`);
    let html = '';
    Object.keys(result).forEach((k) => { html += renderTextBlock(result[k]); });
    body.innerHTML = html || '<p class="text-tertiary">未生成内容</p>';
  } catch (e) {
    btn.disabled = false;
    btn.textContent = original;
    const err = document.createElement('p');
    err.className = 'error-text';
    err.style.cssText = 'color:var(--danger,#e5484d); font-size:13px; margin-top:8px;';
    err.textContent = '生成失败：' + e.message;
    body.appendChild(err);
  }
}

window.genArchitecture = function(btn) { _genSection(btn, 'architecture'); };
window.genReadme = function(btn) { _genSection(btn, 'readme'); };

/* ============================================================
   8b. Settings Page
   ============================================================ */

async function loadSettings() {
  if (Auth.requireAuth()) return;

  setPageTitle('设置', '管理 AI 配置和采集参数');
  setBody(loadingHTML('正在加载配置…'));

  try {
    const settings = await getJSON('/settings');
    const ai = settings.ai || {};
    const collect = settings.collect || {};

    const githubLangs = (collect.github_languages || ['python']).join(', ');
    const arxivCats = (collect.arxiv_categories || ['cs.AI', 'cs.CL', 'cs.LG']).join(', ');
    const redditSubs = (collect.reddit_subreddits || []).join(', ');

    let html = `
      <div class="settings-section">
        <div class="settings-section-title">AI 配置</div>
        <div class="settings-section-desc">LLM API 地址、密钥和模型名称。修改后需重启容器生效。</div>
        <div class="settings-form">
          <div class="form-field">
            <label>API Base URL</label>
            <input type="text" id="setting-api-base" value="${esc(ai.api_base || '')}" placeholder="https://x666.me">
            <div class="form-hint">不含 /v1 后缀，系统会自动补全</div>
          </div>
          <div class="form-field">
            <label>API Key</label>
            <input type="password" id="setting-api-key" value="${esc(ai.api_key || '')}" placeholder="sk-...">
            <div class="form-hint">密码框，不会回显。留空表示不修改</div>
          </div>
          <div class="form-field">
            <label>模型名称</label>
            <input type="text" id="setting-model" value="${esc(ai.model || '')}" placeholder="glm-5.2">
          </div>
        </div>
      </div>

      <div class="settings-section">
        <div class="settings-section-title">采集配置</div>
        <div class="settings-section-desc">数据采集器参数，修改后需重启容器生效。</div>
        <div class="settings-form">
          <div class="form-field">
            <label>日报建议数量</label>
            <input type="number" id="setting-daily-suggestions" value="${collect.daily_suggestions || 3}" min="1" max="10">
          </div>
          <div class="form-field">
            <label>GitHub 采集语言</label>
            <input type="text" id="setting-github-langs" value="${esc(githubLangs)}" placeholder="python, javascript, go">
            <div class="form-hint">逗号分隔</div>
          </div>
          <div class="form-field">
            <label>HN 最低热度分</label>
            <input type="number" id="setting-hn-min-points" value="${collect.hn_min_points || 100}" min="0">
          </div>
          <div class="form-field">
            <label>arXiv 分类</label>
            <input type="text" id="setting-arxiv-cats" value="${esc(arxivCats)}" placeholder="cs.AI, cs.CL, cs.LG">
            <div class="form-hint">逗号分隔</div>
          </div>
          <div class="form-field">
            <label>Reddit 子版列表</label>
            <input type="text" id="setting-reddit-subs" value="${esc(redditSubs)}" placeholder="MachineLearning, artificial, LocalLLaMA">
            <div class="form-hint">逗号分隔</div>
          </div>
          <div class="form-field">
            <label>Twitter 采集开关</label>
            <div style="display:flex; align-items:center; gap:12px;">
              <label class="toggle-switch">
                <input type="checkbox" id="setting-twitter-enabled" ${collect.twitter_enabled ? 'checked' : ''}>
                <span class="toggle-slider"></span>
              </label>
              <span style="font-size:13px; color:var(--text-tertiary);">开启后从 RSSHub 采集 Twitter AI 资讯</span>
            </div>
          </div>
          <div class="form-actions">
            <button class="btn btn-primary" onclick="saveSettings()">保存配置</button>
            <span class="settings-save-msg" id="settings-msg"></span>
          </div>
        </div>
      </div>`;

    setBody(html);
  } catch (e) {
    setBody(errorHTML(e.message));
  }
}

async function saveSettings() {
  const msg = document.getElementById('settings-msg');
  if (!msg) return;
  msg.className = 'settings-save-msg';
  msg.textContent = '保存中...';

  const apiBase = document.getElementById('setting-api-base')?.value?.trim() || '';
  const apiKey = document.getElementById('setting-api-key')?.value?.trim() || '';
  const model = document.getElementById('setting-model')?.value?.trim() || '';
  const dailySuggestions = parseInt(document.getElementById('setting-daily-suggestions')?.value || '3');
  const githubLangs = document.getElementById('setting-github-langs')?.value?.split(',').map((s) => s.trim()).filter(Boolean) || ['python'];
  const hnMinPoints = parseInt(document.getElementById('setting-hn-min-points')?.value || '100');
  const arxivCats = document.getElementById('setting-arxiv-cats')?.value?.split(',').map((s) => s.trim()).filter(Boolean) || ['cs.AI', 'cs.CL', 'cs.LG'];
  const redditSubs = document.getElementById('setting-reddit-subs')?.value?.split(',').map((s) => s.trim()).filter(Boolean) || [];
  const twitterEnabled = document.getElementById('setting-twitter-enabled')?.checked || false;

  const payload = {
    ai: { api_base: apiBase, api_key: apiKey, model: model },
    collect: {
      daily_suggestions: dailySuggestions,
      github_languages: githubLangs,
      hn_min_points: hnMinPoints,
      arxiv_categories: arxivCats,
      reddit_subreddits: redditSubs,
      twitter_enabled: twitterEnabled,
    },
  };

  try {
    const result = await fetchWithAuth(`${API}/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    msg.className = 'settings-save-msg success';
    msg.textContent = '✅ ' + (result.message || '配置已保存');
  } catch (e) {
    msg.className = 'settings-save-msg error';
    msg.textContent = '❌ 保存失败: ' + e.message;
  }
}

window.saveSettings = saveSettings;

/* ============================================================
   8c. Archive Page (actual)
   ============================================================ */

async function loadArchive() {
  if (Auth.requireAuth()) return;

  setPageTitle('历史报告', '所有已生成报告的归档');
  setBody(loadingHTML('正在加载历史报告…'));

  try {
    const stats = await getJSON('/stats');
    const recent = stats.recent_summaries || [];

    let html = `
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">总报告数</div>
          <div class="stat-value">${stats.total_reports || 0}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">最新报告</div>
          <div class="stat-value text-value">${esc(stats.latest_date || '-')}</div>
        </div>
      </div>`;

    if (recent.length) {
      html += `<div class="section-title">最近 7 天 <span class="section-count">${recent.length}</span></div>`;
      html += `<div class="archive-list">`;
      recent.forEach((s) => {
        html += `
          <div class="archive-item">
            <a href="/trends?date=${encodeURIComponent(s.date)}" class="archive-date">${esc(s.date)}</a>
            <div class="archive-summary">${esc(s.summary || '暂无概述')}</div>
            <div class="archive-meta">
              <span>数据量 <span class="meta-value">${s.raw_items_count || 0}</span></span>
              <a href="/suggestions?date=${encodeURIComponent(s.date)}" class="btn btn-ghost btn-sm">建议</a>
            </div>
          </div>`;
      });
      html += `</div>`;
    } else {
      html += emptyHTML('📚', '暂无历史报告', '还没有生成过任何日报。');
    }

    setBody(html);
  } catch (e) {
    setBody(errorHTML(e.message));
  }
}

/* ============================================================
   9. Login Page
   ============================================================ */

function loadLogin() {
  /* If already logged in, redirect to dashboard */
  if (Auth.isLoggedIn()) {
    window.location.href = '/';
    return;
  }

  const content = document.getElementById('content');
  if (!content) return;

  content.innerHTML = `
    <div class="login-wrapper">
      <div class="login-card">
        <div class="login-logo">🔭</div>
        <h1>TrendRadar</h1>
        <div class="login-subtitle">GitHub 趋势 + AI 资讯雷达</div>
        <form class="login-form" id="login-form" onsubmit="handleLogin(event)">
          <div class="form-field">
            <label for="password-input">密码</label>
            <input
              type="password"
              id="password-input"
              placeholder="输入访问密码"
              autocomplete="off"
              required
            />
          </div>
          <div class="login-error" id="login-error"></div>
          <button type="submit" class="btn btn-primary login-btn">登录 →</button>
        </form>
        <div class="login-hint">
          密码存储于服务端 .env，登录后获取 session token。<br/>
          Token 存储于浏览器 localStorage，仅在本地使用。
        </div>
      </div>
    </div>`;
}

async function handleLogin(event) {
  event.preventDefault();
  const input = document.getElementById('password-input');
  const errorEl = document.getElementById('login-error');
  if (!input) return;
  const password = input.value;
  if (!password) {
    if (errorEl) errorEl.textContent = '请输入密码';
    return;
  }

  if (errorEl) errorEl.textContent = '';

  try {
    const resp = await fetch(`${API}/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    });
    const data = await resp.json();
    if (resp.status === 200 && data.token) {
      Auth.setToken(data.token);
      window.location.href = '/';
    } else {
      if (errorEl) errorEl.textContent = data.detail || '密码错误';
    }
  } catch (e) {
    if (errorEl) errorEl.textContent = '网络错误，请重试';
  }
}

/* ============================================================
   10. Router — SPA 局部导航
   拦截站内链接，只替换 #content，不整页刷新（消除切页白屏与重复加载）
   ============================================================ */

const routes = {
  '/': loadDashboard,
  '/trends': loadTrends,
  '/suggestions': loadSuggestions,
  '/archive': loadArchive,
  '/settings': loadSettings,
  '/login': loadLogin,
};

function resolveHandler(path) {
  if (routes[path]) return routes[path];
  if (/^\/suggestion\/\d+$/.test(path)) return loadSuggestionDetail;
  return null;
}

/** 高亮侧边栏当前页 */
function updateActiveNav(path) {
  document.querySelectorAll('.nav-link').forEach((a) => {
    const href = a.getAttribute('href');
    const active = href === path || (href && href !== '/' && path.startsWith(href));
    a.classList.toggle('active', !!active);
  });
}

/** 渲染当前 URL 对应的页面 */
async function runRoute() {
  const path = window.location.pathname.replace(/\/+$/, '') || '/';
  updateActiveNav(path);
  const handler = resolveHandler(path);
  if (!handler) return;
  try {
    await handler();
  } catch (e) {
    console.error('[TrendRadar] Page init error:', e);
    const content = document.getElementById('content');
    if (content) content.innerHTML = errorHTML(e.message);
  }
}

/** SPA 导航：改 URL + 重渲染主内容，不整页刷新 */
async function navigateTo(path, replace) {
  /* 移除服务端注入的 trends 数据残留，回到该页时走客户端渲染，保持一致 */
  const ssr = document.getElementById('trends-data');
  if (ssr) ssr.remove();
  if (replace) history.replaceState({}, '', path);
  else history.pushState({}, '', path);
  window.scrollTo(0, 0);
  await runRoute();
}
window.navigateTo = navigateTo;

/* 拦截站内链接点击，改为局部导航 */
document.addEventListener('click', (e) => {
  if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
  const a = e.target.closest('a');
  if (!a) return;
  const href = a.getAttribute('href');
  if (!href || !href.startsWith('/')) return;        // 外链 / 锚点不拦截
  if (a.target === '_blank' || a.hasAttribute('download')) return;
  e.preventDefault();
  navigateTo(href);
});

/* 浏览器前进 / 后退 */
window.addEventListener('popstate', () => runRoute());

/* 首次加载 */
(function init() {
  runRoute();
  initThemeToggle();
  initLogoutButtons();
})();

/* ============================================================
   11. Theme Toggle
   ============================================================ */

function initThemeToggle() {
  const btn = document.getElementById('theme-toggle');
  if (!btn) return;
  const current = document.documentElement.getAttribute('data-theme') || 'dark';
  btn.textContent = current === 'dark' ? '☀️' : '🌙';
  btn.addEventListener('click', () => {
    const cur = document.documentElement.getAttribute('data-theme') || 'dark';
    const next = cur === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('trendradar_theme', next);
    btn.textContent = next === 'dark' ? '☀️' : '🌙';
  });
}

function initLogoutButtons() {
  document.querySelectorAll('.logout-btn, #logout-btn').forEach((btn) => {
    if (btn.dataset.bound) return;
    btn.dataset.bound = '1';
    btn.addEventListener('click', () => Auth.logout());
  });
}

/* ============================================================
   12. Trigger Daily — frosted-glass modal + SSE live progress
   ============================================================ */

let _runModalRunning = false;

function handleRunDaily(event) {
  if (event) event.preventDefault();
  openRunModal();
}

/** Build and show the centered frosted-glass modal in its confirm state. */
function openRunModal() {
  removeRunModal();

  const overlay = document.createElement('div');
  overlay.className = 'rd-overlay';
  overlay.id = 'rd-overlay';
  overlay.innerHTML = `
    <div class="rd-modal" role="dialog" aria-modal="true" aria-labelledby="rd-title">
      <button class="rd-close" id="rd-close" aria-label="关闭">✕</button>
      <div class="rd-icon">🔭</div>
      <h3 class="rd-title" id="rd-title">立即运行日报</h3>
      <p class="rd-desc" id="rd-desc">将执行完整日报流程：<b>采集 → 分析 → 建议 → 报告 → 推送</b>。<br>整个过程约需数分钟，运行期间请保持页面打开。</p>

      <div class="rd-progress" id="rd-progress" hidden>
        <div class="rd-spinner"><span></span><span></span></div>
        <div class="rd-phase" id="rd-phase">准备中…</div>
        <div class="rd-bar"><div class="rd-bar-fill" id="rd-bar-fill"></div></div>
        <div class="rd-pct" id="rd-pct">0%</div>
        <ol class="rd-steps" id="rd-steps">
          <li data-step="1"><span class="rd-dot"></span><em>采集</em></li>
          <li data-step="2"><span class="rd-dot"></span><em>分析</em></li>
          <li data-step="3"><span class="rd-dot"></span><em>建议</em></li>
          <li data-step="4"><span class="rd-dot"></span><em>报告</em></li>
          <li data-step="5"><span class="rd-dot"></span><em>推送</em></li>
        </ol>
      </div>

      <div class="rd-result" id="rd-result" hidden></div>

      <div class="rd-actions" id="rd-actions">
        <button class="btn btn-ghost" id="rd-cancel">取消</button>
        <button class="btn btn-primary" id="rd-confirm">确认运行</button>
      </div>
    </div>`;

  document.body.appendChild(overlay);
  document.body.classList.add('rd-lock');
  requestAnimationFrame(() => overlay.classList.add('rd-show'));

  _runModalRunning = false;
  document.getElementById('rd-confirm').addEventListener('click', startRunDaily);
  document.getElementById('rd-cancel').addEventListener('click', closeRunModal);
  document.getElementById('rd-close').addEventListener('click', closeRunModal);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) closeRunModal(); });
  document.addEventListener('keydown', _runModalKeydown);
}

function _runModalKeydown(e) {
  if (e.key === 'Escape') closeRunModal();
}

/** Close guarded by running state — the modal must stay open while a run is in flight. */
function closeRunModal() {
  if (_runModalRunning) return;
  removeRunModal();
}

function removeRunModal() {
  const overlay = document.getElementById('rd-overlay');
  if (!overlay) return;
  document.removeEventListener('keydown', _runModalKeydown);
  document.body.classList.remove('rd-lock');
  overlay.classList.remove('rd-show');
  setTimeout(() => overlay.remove(), 240);
}

/** Confirmed — keep the modal open and stream live progress over SSE. */
async function startRunDaily() {
  const $ = (id) => document.getElementById(id);
  const confirmBtn = $('rd-confirm');
  const cancelBtn = $('rd-cancel');
  const closeBtn = $('rd-close');
  const phaseEl = $('rd-phase');
  const fillEl = $('rd-bar-fill');
  const pctEl = $('rd-pct');
  const resultEl = $('rd-result');
  const stepsEl = $('rd-steps');

  _runModalRunning = true;
  $('rd-desc').hidden = true;
  $('rd-progress').hidden = false;
  resultEl.hidden = true;
  confirmBtn.style.display = 'none';
  closeBtn.style.display = 'none';
  cancelBtn.disabled = true;
  cancelBtn.textContent = '运行中…';

  const setStep = (step, total, label) => {
    phaseEl.textContent = `步骤 ${step}/${total} · ${label}`;
    const pct = Math.round(((step - 1) / total) * 100);
    fillEl.style.width = pct + '%';
    pctEl.textContent = pct + '%';
    stepsEl.querySelectorAll('li').forEach((li) => {
      const s = Number(li.dataset.step);
      li.classList.toggle('done', s < step);
      li.classList.toggle('active', s === step);
    });
  };

  const finish = (ok, html) => {
    _runModalRunning = false;
    resultEl.hidden = false;
    resultEl.className = 'rd-result ' + (ok ? 'success' : 'error');
    resultEl.innerHTML = html;
    cancelBtn.style.display = 'none';
    closeBtn.style.display = '';
    // Re-purpose the primary button as a clean "完成/关闭" (strip the old confirm listener).
    const fresh = confirmBtn.cloneNode(true);
    fresh.style.display = '';
    fresh.textContent = ok ? '完成' : '关闭';
    confirmBtn.parentNode.replaceChild(fresh, confirmBtn);
    fresh.addEventListener('click', removeRunModal);
  };

  try {
    const token = Auth.getToken();
    const resp = await fetch(`${API}/trigger/daily/stream`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (resp.status === 401) { Auth.clearToken(); window.location.href = '/login'; return; }
    if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    let settled = false;

    while (!settled) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf('\n\n')) !== -1) {
        const raw = buf.slice(0, idx).trim();
        buf = buf.slice(idx + 2);
        if (!raw.startsWith('data:')) continue;
        let evt;
        try { evt = JSON.parse(raw.slice(5).trim()); } catch (_) { continue; }

        if (evt.type === 'progress') {
          setStep(evt.step, evt.total, evt.label);
        } else if (evt.type === 'done') {
          fillEl.style.width = '100%';
          pctEl.textContent = '100%';
          stepsEl.querySelectorAll('li').forEach((li) => { li.classList.remove('active'); li.classList.add('done'); });
          phaseEl.textContent = '✓ 全部完成';
          finish(true, `✅ 日报生成成功！<br>日期 <strong>${esc(evt.date)}</strong> · 热点 ${esc(evt.hot_topics)} · 建议 ${esc(evt.suggestions)}`);
          settled = true;
          loadDashboard();
        } else if (evt.type === 'error') {
          finish(false, `❌ 运行失败：${esc(evt.detail || '未知错误')}`);
          settled = true;
        }
      }
    }
    if (!settled) finish(false, '❌ 运行中断：与服务器的连接意外结束');
  } catch (e) {
    finish(false, `❌ 运行失败：${esc(e.message)}`);
  }
}
