/* ============================================================
   TrendRadar — Frontend Application Logic
   Linear Design System · Auth · Routing · Pages · Chart.js
   ============================================================ */

'use strict';

const API = '/api';
const TOKEN_KEY = 'trendradar_jwt';
const CHART_JS_CDN = 'https://cdn.jsdelivr.net/npm/chart.js';

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
      <button class="btn btn-ghost btn-sm" onclick="Auth.logout()">登出</button>
    </div>
  </div><div class="page-enter" id="page-body">${loadingHTML('正在加载最新报告…')}</div>`;

  try {
    const [report, stats] = await Promise.all([
      getJSON('/latest'),
      getJSON('/stats'),
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
    const dates = await getJSON('/dates').catch(() => []);

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
      hotTopics.forEach((t) => {
        const evidence = t.evidence || [];
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
            </div>
            ${evidence.length ? `<div class="topic-evidence"><span class="evidence-label">证据:</span>${evidence.map((e) => esc(e)).join(' · ')}</div>` : ''}
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
  const gradient = ctx.createLinearGradient(0, 0, 0, 240);
  gradient.addColorStop(0, 'rgba(94, 106, 210, 0.25)');
  gradient.addColorStop(1, 'rgba(94, 106, 210, 0)');

  new Chart(ctx, {
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

    const trends = await getJSON(`/trends/${selectedDate}`);

    const bySource = {};
    trends.forEach((t) => {
      const src = t.source || 'unknown';
      (bySource[src] = bySource[src] || []).push(t);
    });

    const sourceLabels = {
      github: 'GitHub',
      hackernews: 'Hacker News',
      reddit: 'Reddit',
      twitter: 'Twitter / X',
      arxiv: 'arXiv',
    };

    let dateSelector = `<div class="date-selector"><label>日期</label><select onchange="window.location.href='/trends?date='+this.value">`;
    dates.forEach((d) => {
      dateSelector += `<option value="${esc(d)}" ${d === selectedDate ? 'selected' : ''}>${esc(d)}</option>`;
    });
    dateSelector += `</select></div>`;

    let html = dateSelector;

    let totalShown = 0;
    for (const [source, label] of Object.entries(sourceLabels)) {
      const items = bySource[source] || [];
      if (!items.length) continue;

      html += `<div class="source-group">
        <div class="source-header">
          <div class="source-title">${esc(label)}</div>
          <span class="source-count">${items.length}</span>
        </div>
        <div class="trend-grid">`;

      items.slice(0, 12).forEach((t) => {
        const tags = parseJSONField(t.tags, []);
        html += `
          <div class="trend-card">
            <div class="trend-title">
              <a href="${esc(t.url || '#')}" target="_blank" rel="noopener">${esc(t.title || '')}</a>
            </div>
            ${t.description ? `<div class="trend-desc">${esc(t.description)}</div>` : ''}
            <div class="trend-meta">
              ${t.language ? `<span class="badge badge-tool">${esc(t.language)}</span>` : ''}
              ${t.popularity ? `<span class="trend-popularity">★ ${esc(t.popularity)}</span>` : ''}
              ${tags.map((tag) => `<span class="badge badge-sustained">${esc(tag)}</span>`).join('')}
            </div>
          </div>`;
        totalShown++;
      });

      html += `</div></div>`;
    }

    /* Unknown sources */
    for (const [source, items] of Object.entries(bySource)) {
      if (sourceLabels[source]) continue;
      html += `<div class="source-group">
        <div class="source-header">
          <div class="source-title">${esc(source)}</div>
          <span class="source-count">${items.length}</span>
        </div>
        <div class="trend-grid">`;
      items.slice(0, 12).forEach((t) => {
        const tags = parseJSONField(t.tags, []);
        html += `
          <div class="trend-card">
            <div class="trend-title"><a href="${esc(t.url || '#')}" target="_blank" rel="noopener">${esc(t.title || '')}</a></div>
            ${t.description ? `<div class="trend-desc">${esc(t.description)}</div>` : ''}
            <div class="trend-meta">
              ${t.popularity ? `<span class="trend-popularity">★ ${esc(t.popularity)}</span>` : ''}
              ${tags.map((tag) => `<span class="badge badge-sustained">${esc(tag)}</span>`).join('')}
            </div>
          </div>`;
      });
      html += `</div></div>`;
    }

    if (totalShown === 0) {
      html += emptyHTML('📭', '该日期无数据', `日期 ${esc(selectedDate)} 没有采集到任何趋势数据。`);
    }

    setBody(html);
  } catch (e) {
    setBody(errorHTML(e.message));
  }
}

/* ============================================================
   7. Suggestions Page
   ============================================================ */

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

    let dateSelector = `<div class="date-selector"><label>日期</label><select onchange="window.location.href='/suggestions?date='+this.value">`;
    dates.forEach((d) => {
      dateSelector += `<option value="${esc(d)}" ${d === selectedDate ? 'selected' : ''}>${esc(d)}</option>`;
    });
    dateSelector += `</select></div>`;

    let html = dateSelector;
    html += `<div class="section-title">项目建议 <span class="section-count">${suggestions.length}</span></div>`;

    if (!suggestions.length) {
      html += `<div class="card"><p class="text-tertiary" style="font-size:13px;">此日期无建议</p></div>`;
      setBody(html);
      return;
    }

    html += `<div class="suggestions-grid">`;

    for (const s of suggestions) {
      const techStack = s.tech_stack || [];
      const keyFeatures = s.key_features || [];
      const similarProjects = s.similar_projects || [];
      const viralHooks = s.viral_hooks || [];

      html += `
        <div class="suggestion-card">
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

      if (keyFeatures.length) {
        html += `<div class="suggestion-section">
          <div class="section-label">核心功能</div>
          <ul class="key-features">
            ${keyFeatures.map((f) => `<li>${esc(f)}</li>`).join('')}
          </ul>
        </div>`;
      }

      if (techStack.length) {
        html += `<div class="suggestion-section">
          <div class="section-label">技术栈</div>
          <div style="display:flex; flex-wrap:wrap; gap:6px;">
            ${techStack.map((t) => `<span class="tag">${esc(t)}</span>`).join('')}
          </div>
        </div>`;
      }

      if (similarProjects.length) {
        html += `<div class="suggestion-section">
          <div class="section-label">类似项目对比</div>
          <table class="compare-table">
            <thead><tr><th>项目</th><th>Star</th><th>我们的优势</th></tr></thead>
            <tbody>`;
        similarProjects.forEach((p) => {
          html += `<tr>
            <td>${esc(p.name || '')}</td>
            <td style="color:var(--text-tertiary);">${esc(p.stars || '')}</td>
            <td class="col-advantage">${esc(p.our_advantage || '')}</td>
          </tr>`;
        });
        html += `</tbody></table></div>`;
      }

      if (viralHooks.length) {
        html += `<div class="suggestion-section">
          <div class="section-label">病毒传播因素</div>
          <div style="font-size:13px; color:var(--text-secondary); line-height:1.7;">
            ${viralHooks.map((h) => `<span class="badge badge-rising" style="margin:2px;">${esc(h)}</span>`).join(' ')}
          </div>
        </div>`;
      }

      /* Scaffold files */
      if (s.has_scaffold) {
        try {
          const files = await getJSON(`/scaffold-files/${encodeURIComponent(selectedDate)}/${encodeURIComponent(s.name)}`);
          if (files.length) {
            html += `<div class="scaffold-section">
              <div class="scaffold-label">脚手架文件</div>
              <div class="scaffold-files">
                ${files.map((f) => {
                  const href = `${API}/scaffold/${encodeURIComponent(selectedDate)}/${encodeURIComponent(s.name)}/${encodeURIComponent(f)}`;
                  return `<a href="${href}" target="_blank" class="scaffold-link">↓ ${esc(f)}</a>`;
                }).join('')}
              </div>
            </div>`;
          }
        } catch (e) {
          /* scaffold fetch failed — skip silently */
        }
      }

      html += `</div>`;
    }

    html += `</div>`;
    setBody(html);
  } catch (e) {
    setBody(errorHTML(e.message));
  }
}

/* ============================================================
   8. Archive Page
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
        <div class="login-subtitle">输入 JWT Token 以登录</div>
        <form class="login-form" id="login-form" onsubmit="handleLogin(event)">
          <div class="form-field">
            <label for="jwt-input">JWT Token</label>
            <input
              type="password"
              id="jwt-input"
              placeholder="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
              autocomplete="off"
              required
            />
          </div>
          <div class="login-error" id="login-error"></div>
          <button type="submit" class="btn btn-primary login-btn">登录</button>
        </form>
        <div class="login-hint">
          Token 存储于浏览器 localStorage，仅在本地使用。<br/>
          登出后将清除本地凭证。
        </div>
      </div>
    </div>`;
}

async function handleLogin(event) {
  event.preventDefault();
  const input = document.getElementById('jwt-input');
  const errorEl = document.getElementById('login-error');
  const token = input.value.trim();

  errorEl.textContent = '';

  if (!token) {
    errorEl.textContent = '请输入 JWT Token';
    return;
  }

  /* Quick validation against /health (or any endpoint) to verify token */
  try {
    const resp = await fetch(`${API}/health`, {
      headers: { 'Authorization': `Bearer ${token}` },
    });
    /* /health may not require auth, but a 401 here means bad token */
    if (resp.status === 401) {
      errorEl.textContent = 'Token 无效或已过期';
      return;
    }
  } catch (e) {
    /* Network error — still store token and try; user can retry later */
  }

  Auth.setToken(token);
  window.location.href = '/';
}

/* ============================================================
   10. Router — auto-init based on pathname
   ============================================================ */

(async function init() {
  const path = window.location.pathname.replace(/\/+$/, '') || '/';

  /* Add Google Fonts (Inter + JetBrains Mono) if not already present */
  if (!document.querySelector('link[href*="fonts.googleapis.com/css2?family=Inter"]')) {
    const preconnect1 = document.createElement('link');
    preconnect1.rel = 'preconnect';
    preconnect1.href = 'https://fonts.googleapis.com';
    document.head.appendChild(preconnect1);

    const preconnect2 = document.createElement('link');
    preconnect2.rel = 'preconnect';
    preconnect2.href = 'https://fonts.gstatic.com';
    preconnect2.crossOrigin = '';
    document.head.appendChild(preconnect2);

    const fontLink = document.createElement('link');
    fontLink.rel = 'stylesheet';
    fontLink.href = 'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap';
    document.head.appendChild(fontLink);
  }

  const routes = {
    '/': loadDashboard,
    '/trends': loadTrends,
    '/suggestions': loadSuggestions,
    '/archive': loadArchive,
    '/login': loadLogin,
  };

  const handler = routes[path];
  if (handler) {
    try {
      await handler();
    } catch (e) {
      console.error('Page init error:', e);
      const content = document.getElementById('content');
      if (content) {
        content.innerHTML = errorHTML(e.message);
      }
    }
  }
})();
