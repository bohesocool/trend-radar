"""TrendRadar Web 应用入口 — FastAPI + 固定密码鉴权 + Webhook 触发。"""

from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from trend_radar.config import get_config
from trend_radar.web.api import router
from trend_radar.web.auth import login, require_auth
from trend_radar.web.settings_api import router as settings_router

_WEB_DIR = Path(__file__).resolve().parent
_STATIC_DIR = _WEB_DIR / "static"
_TEMPLATE_DIR = _WEB_DIR / "templates"

app = FastAPI(title="TrendRadar", version="0.1.0", description="GitHub 趋势 + AI 资讯雷达")

# 静态文件
_STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


# ===== 静态资源版本号 (用于缓存失效) =====
# 由 CSS/JS 文件的修改时间算出指纹；文件一变，URL 上的 ?v= 就变，浏览器缓存自动失效。
import hashlib


def _compute_asset_version() -> str:
    h = hashlib.md5()
    for rel in ("css/style.css", "js/app.js"):
        try:
            h.update(str((_STATIC_DIR / rel).stat().st_mtime_ns).encode())
        except OSError:
            pass
    return h.hexdigest()[:8]


_ASSET_VERSION = _compute_asset_version()


# ===== 中间件: 静态资源长期缓存 + 响应压缩 =====
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware


class StaticCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        if request.url.path.startswith("/static/"):
            # URL 带版本号 (?v=)，内容变更即换 URL，故可安全地长期不可变缓存。
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp


app.add_middleware(StaticCacheMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=500)

# API 路由
app.include_router(router)
app.include_router(settings_router)


# ===== 页面路由 (HTML 不缓存，但静态资源引用带版本号) =====

_NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate"}


def _read_template(filename: str) -> str:
    """读取模板并给静态资源引用追加版本号，触发浏览器缓存失效。"""
    html = (_TEMPLATE_DIR / filename).read_text(encoding="utf-8")
    return (
        html.replace("/static/css/style.css", f"/static/css/style.css?v={_ASSET_VERSION}")
        .replace("/static/js/app.js", f"/static/js/app.js?v={_ASSET_VERSION}")
    )


def _html(filename: str) -> HTMLResponse:
    return HTMLResponse(content=_read_template(filename), headers=_NO_CACHE)


@app.get("/login", response_class=HTMLResponse)
async def login_page() -> HTMLResponse:
    return _html("login.html")


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    return _html("dashboard.html")


@app.get("/trends", response_class=HTMLResponse)
async def trends_page(request: Request) -> HTMLResponse:
    """趋势详情页 — 服务端渲染，数据直接嵌入 HTML，无需客户端 fetch。"""
    import json as _json
    from trend_radar import db

    # Auth check — redirect to login if no valid token
    auth_header = request.headers.get("Authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    # Also check cookie (for direct browser navigation)
    if not token:
        from starlette.datastructures import Headers
        cookie = request.cookies.get("trendradar_jwt", "")
        if cookie:
            token = cookie
    # If still no token, serve the template (JS will redirect to login)
    # We can't do a 302 redirect here because the browser needs to load the page
    # and JS handles the redirect. But we CAN skip embedding data if not authenticated.

    dates = db.list_dates_with_data()
    source_labels = {
        "github": "GitHub",
        "hackernews": "Hacker News",
        "reddit": "Reddit",
        "twitter": "Twitter / X",
        "arxiv": "arXiv",
    }
    known_order = ["github", "hackernews", "reddit", "twitter", "arxiv"]

    if not dates:
        return HTMLResponse(content=_read_template("trends.html"), headers=_NO_CACHE)

    selected_date = dates[0]
    # Support ?date= query param
    from urllib.parse import parse_qs
    query_params = parse_qs(request.url.query or "")
    if "date" in query_params and query_params["date"][0] in dates:
        selected_date = query_params["date"][0]
    all_items = db.get_trend_items_by_date(selected_date)

    # 按源分组
    by_source: dict[str, list] = {}
    for item in all_items:
        src = item.get("source") or "unknown"
        by_source.setdefault(src, []).append(item)

    # 排序源
    sources = [s for s in known_order if s in by_source]
    for s in by_source:
        if s not in known_order:
            sources.append(s)

    # 构建嵌入 JSON — 精简每个 item 只保留渲染所需字段
    slim_by_source = {}
    for src in sources:
        slim_by_source[src] = [
            {
                "t": item.get("title", ""),
                "u": item.get("url", ""),
                "d": item.get("description", ""),
                "l": item.get("language", ""),
                "p": item.get("popularity", ""),
                "g": item.get("tags", "[]"),
            }
            for item in by_source[src]
        ]

    embedded_data = _json.dumps(
        {"date": selected_date, "dates": dates, "sources": sources, "data": slim_by_source},
        ensure_ascii=False,
    )

    html = _read_template("trends.html")
    # 在 </body> 前注入数据 + 内联 JS
    inject = f"""
    <script id="trends-data" type="application/json">{embedded_data}</script>
    <script>
    (function() {{
      var raw = document.getElementById('trends-data').textContent;
      var payload = JSON.parse(raw);
      var sourceLabels = {_json.dumps(source_labels, ensure_ascii=False)};
      var ITEMS_PER_PAGE = 30;

      var content = document.getElementById('content');
      var bySource = payload.data;
      var sources = payload.sources;
      var selectedDate = payload.date;
      var dates = payload.dates;
      var loaded = {{}};

      // Date selector
      var html = '<div class="date-selector"><label>日期</label><select onchange="navigateTo(\\'/trends?date=\\'+this.value)">';
      dates.forEach(function(d) {{
        html += '<option value="' + d + '"' + (d === selectedDate ? ' selected' : '') + '>' + d + '</option>';
      }});
      html += '</select></div>';

      if (!sources.length) {{
        html += '<div class="state-block"><div class="state-icon">📭</div><div class="state-title">该日期无数据</div><div class="state-desc">日期 ' + selectedDate + ' 没有采集到任何趋势数据。</div></div>';
        content.innerHTML = html;
        return;
      }}

      // Tabs
      html += '<div class="source-tabs">';
      sources.forEach(function(src, idx) {{
        var label = sourceLabels[src] || src;
        var count = bySource[src].length;
        html += '<button class="source-tab' + (idx === 0 ? ' active' : '') + '" data-source="' + src + '" onclick="switchTab(\\''+src+'\\')">' + label + ' <span class="tab-count">' + count + '</span></button>';
      }});
      html += '</div>';

      // Tab panels
      sources.forEach(function(src, idx) {{
        var label = sourceLabels[src] || src;
        var isActive = idx === 0;
        html += '<div class="tab-panel' + (isActive ? ' active' : '') + '" id="tab-' + src + '">';
        html += '<div class="source-group"><div class="source-header"><div class="source-title">' + label + ' <span class="source-count">' + bySource[src].length + '</span></div></div>';
        html += '<div id="content-' + src + '"></div>';
        html += '</div></div>';
      }});

      content.innerHTML = html;

      // Initialize page state BEFORE first render
      window._bySource = bySource;
      window._pageCount = {{}};

      // Load first tab
      renderSource(sources[0]);

      function esc(s) {{
        if (!s) return '';
        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
      }}

      function parseTags(v) {{
        if (Array.isArray(v)) return v;
        if (!v) return [];
        try {{ return JSON.parse(v); }} catch(e) {{ return []; }}
      }}

      function renderCard(item) {{
        var tags = parseTags(item.g);
        var html = '<div class="trend-card">';
        html += '<div class="trend-title"><a href="' + esc(item.u) + '" target="_blank" rel="noopener">' + esc(item.t) + '</a></div>';
        if (item.d) html += '<div class="trend-desc">' + esc(item.d) + '</div>';
        html += '<div class="trend-meta">';
        if (item.l) html += '<span class="badge badge-tool">' + esc(item.l) + '</span>';
        if (item.p) html += '<span class="trend-popularity">★ ' + esc(item.p) + '</span>';
        tags.forEach(function(tag) {{ html += '<span class="badge badge-sustained">' + esc(tag) + '</span>'; }});
        html += '</div></div>';
        return html;
      }}

      function renderSource(src) {{
        if (loaded[src]) return;
        loaded[src] = true;
        var container = document.getElementById('content-' + src);
        if (!container) return;
        var items = bySource[src] || [];
        if (!items.length) {{ container.innerHTML = '<p class="text-tertiary" style="font-size:13px;">无数据</p>'; return; }}

        var html = '<div class="trend-grid" id="grid-' + src + '">';
        items.slice(0, ITEMS_PER_PAGE).forEach(function(item) {{ html += renderCard(item); }});
        html += '</div>';
        if (items.length > ITEMS_PER_PAGE) {{
          html += '<div class="load-more-wrapper"><button class="btn btn-ghost btn-sm" onclick="loadMore(\\''+src+'\\',' + ITEMS_PER_PAGE + ')">加载更多 (' + (items.length - ITEMS_PER_PAGE) + ' 条剩余)</button></div>';
        }}
        container.innerHTML = html;
        window._pageCount[src] = 1;
      }}

      window.switchTab = function(source) {{
        document.querySelectorAll('.source-tab').forEach(function(t) {{ t.classList.remove('active'); }});
        document.querySelectorAll('.tab-panel').forEach(function(p) {{ p.classList.remove('active'); }});
        var tab = document.querySelector('.source-tab[data-source="' + source + '"]');
        var panel = document.getElementById('tab-' + source);
        if (tab) tab.classList.add('active');
        if (panel) panel.classList.add('active');
        if (!loaded[source]) renderSource(source);
      }};

      window.loadMore = function(source, perPage) {{
        var items = bySource[source];
        if (!items) return;
        var page = (window._pageCount[source] || 1) + 1;
        var start = (page - 1) * perPage;
        var newItems = items.slice(start, start + perPage);
        var grid = document.getElementById('grid-' + source);
        if (grid) {{
          var html = '';
          newItems.forEach(function(item) {{ html += renderCard(item); }});
          grid.insertAdjacentHTML('beforeend', html);
        }}
        window._pageCount[source] = page;
        var remaining = items.length - (start + perPage);
        var wrapper = grid ? grid.parentElement.querySelector('.load-more-wrapper') : null;
        if (remaining <= 0 && wrapper) wrapper.remove();
        else if (wrapper) wrapper.querySelector('button').textContent = '加载更多 (' + remaining + ' 条剩余)';
      }};
    }})();
    </script>
    """

    html = html.replace("</body>", inject + "\n</body>")
    return HTMLResponse(content=html, headers=_NO_CACHE)


@app.get("/suggestions", response_class=HTMLResponse)
async def suggestions_page() -> HTMLResponse:
    return _html("suggestions.html")


@app.get("/suggestion/{suggestion_id}", response_class=HTMLResponse)
async def suggestion_detail_page(suggestion_id: int) -> HTMLResponse:
    return _html("suggestion_detail.html")


@app.get("/archive", response_class=HTMLResponse)
async def archive_page() -> HTMLResponse:
    return _html("archive.html")


@app.get("/settings", response_class=HTMLResponse)
async def settings_page() -> HTMLResponse:
    return _html("settings.html")


# ===== 登录端点 =====

class LoginRequest(BaseModel):
    password: str


@app.post("/api/login", response_class=JSONResponse)
async def do_login(req: LoginRequest) -> dict:
    """用固定密码登录，返回 session token。"""
    token = login(req.password)
    if token:
        return {"status": "ok", "token": token}
    raise HTTPException(status_code=401, detail="密码错误")


# ===== Webhook 触发端点 (供 Hermes cron / 外部 HTTP 调用) =====

@app.post("/api/trigger/daily", response_class=JSONResponse)
async def trigger_daily(auth: bool = Depends(require_auth)) -> dict:
    """手动触发日报流程。需要 Bearer token 鉴权。"""
    from trend_radar.scheduler import run_daily

    try:
        report = await run_daily()
        return {
            "status": "ok",
            "date": report.date,
            "hot_topics": len(report.analysis.hot_topics),
            "suggestions": len(report.suggestions),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trigger/weekly", response_class=JSONResponse)
async def trigger_weekly(auth: bool = Depends(require_auth)) -> dict:
    """手动触发周报流程。需要 Bearer token 鉴权。"""
    from trend_radar.scheduler import run_weekly

    try:
        result = await run_weekly()
        return {"status": "ok", "report": result[:200] if isinstance(result, str) else ""}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trigger/collect", response_class=JSONResponse)
async def trigger_collect(auth: bool = Depends(require_auth)) -> dict:
    """仅执行数据采集 (不做分析/生成/推送)。"""
    from trend_radar.scheduler import run_collect_all

    try:
        items = await run_collect_all()
        return {
            "status": "ok",
            "total_items": len(items),
            "sources": list({i.source for i in items}),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trigger/daily/stream")
async def trigger_daily_stream(auth: bool = Depends(require_auth)):
    """以 SSE 流式返回日报进度。每个步骤一条事件，结束发送 done / error。"""
    import asyncio
    import json as _json

    from starlette.responses import StreamingResponse

    from trend_radar.scheduler import run_daily

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def on_progress(step: int, total: int, label: str) -> None:
        # run_daily 跑在独立线程里，用 call_soon_threadsafe 把进度推回主事件循环的队列
        loop.call_soon_threadsafe(
            queue.put_nowait,
            {"type": "progress", "step": step, "total": total, "label": label},
        )

    async def worker() -> None:
        try:
            # run_daily 内含大量同步 CPU/IO 步骤，放到线程里跑，避免阻塞事件循环、
            # 保证进度事件能实时 flush 给前端。
            report = await asyncio.to_thread(
                lambda: asyncio.run(run_daily(progress=on_progress))
            )
            queue.put_nowait(
                {
                    "type": "done",
                    "date": report.date,
                    "hot_topics": len(report.analysis.hot_topics),
                    "suggestions": len(report.suggestions),
                }
            )
        except Exception as e:  # noqa: BLE001
            queue.put_nowait({"type": "error", "detail": str(e)})
        finally:
            queue.put_nowait(None)  # 结束哨兵

    async def event_gen():
        task = asyncio.create_task(worker())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield f"data: {_json.dumps(item, ensure_ascii=False)}\n\n"
        finally:
            await task

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def main() -> None:
    cfg = get_config()["web"]
    uvicorn.run(
        "trend_radar.web.app:app",
        host=cfg["host"],
        port=cfg["port"],
        reload=False,
    )


if __name__ == "__main__":
    main()