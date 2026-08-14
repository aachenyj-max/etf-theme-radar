from __future__ import annotations
import ast, asyncio, json, os
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Literal
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from .connector_factory import configured_connectors
from .models import utcnow
from .pipeline import ingest
from .reports import build_daily_brief
from .store import EvidenceStore, RESEARCH_EXECUTION_STATUSES
from .workflow import recover_interrupted_runs
from .worker import stop_all_workers, worker_for, worker_status
from .sync_worker import stop_all_sync_workers, sync_worker_for, sync_worker_status
from .governance import reclassify_store
from .agent_runtime import capability_status
from .ontology import refresh_research_assets
from . import internal_auth

@asynccontextmanager
async def lifespan(_app: FastAPI):
    internal_auth.validate_configuration()
    recovered = recover_interrupted_runs(_db())
    worker = worker_for(_db())
    if recovered:
        worker.wake()
    sync_worker = sync_worker_for(_db())
    if os.getenv("STARTUP_SYNC_ENABLED","true").lower() in {"1","true","yes","on"}:
        store = _store()
        try:
            today = date.today().isoformat()
            store.create_sync_run(str(uuid4()), utcnow(), days=int(os.getenv("STARTUP_SYNC_DAYS","7")), idempotency_key=f"daily:{today}")
            iso_year, iso_week, _ = date.today().isocalendar()
            store.create_discovery_run({
                "discovery_run_id": str(uuid4()), "idempotency_key": f"weekly:{iso_year}-W{iso_week:02d}",
                "run_kind": "weekly", "status": "queued", "stage": "queued", "created_at": utcnow(),
                "window_start": (date.today() - timedelta(days=29)).isoformat(), "window_end": today,
            })
        finally: store.close()
        sync_worker.wake()
    try:
        yield
    finally:
        stop_all_sync_workers()
        stop_all_workers()

app=FastAPI(title="ETF Theme Radar",version="0.5.0",description="分析 ETF 格局、跟踪产业动量的主题研究工具；不提供个性化投资或交易建议。",lifespan=lifespan)
SERVICE_ID = "etf-theme-radar"
CONTRACT_VERSION = "2026-08-14.v10"
CORE_RESEARCH_OBJECTIVE = "analyze_etf_landscape_and_track_industry_momentum"
AUTO_RESEARCH_SOURCES = [
    "sec", "arxiv", "company_careers", "etf_holdings", "etf_news",
    "patents", "sp_global", "x", "forums",
]
SOURCE_METADATA = {
    "sec_edgar_etf": {"display_name":"SEC ETF 文件","short_name":"SEC","category":"监管文件","logo_url":"https://www.sec.gov/files/sec-logo.png","evidence_role":"primary","authority":"official"},
    "openalex": {"display_name":"OpenAlex 论文","short_name":"OpenAlex","category":"学术论文","logo_url":"https://cdn.simpleicons.org/openaccess/10273D","evidence_role":"primary","authority":"academic"},
    "google_patents": {"display_name":"Google Patents","short_name":"Patents","category":"专利公开发现","logo_url":"https://cdn.simpleicons.org/google/4285F4","evidence_role":"discovery","authority":"secondary"},
    "public_job_boards": {"display_name":"公司公开招聘","short_name":"招聘","category":"公司招聘","logo_url":"https://cdn.simpleicons.org/greenhouse/357E63","evidence_role":"supporting","authority":"first_party"},
    "official_etf_holdings": {"display_name":"ETF 官方持仓","short_name":"ETF","category":"发行人官方持仓","logo_url":None,"evidence_role":"primary","authority":"official","cache_ttl_seconds":21600},
    "yahoo_etf_news": {"display_name":"Yahoo Finance ETF 公开资讯","short_name":"Yahoo","category":"ETF 资讯发现","logo_url":"https://cdn.simpleicons.org/yahoo/6001D2","evidence_role":"discovery","authority":"secondary","cache_ttl_seconds":1800},
    "sp_global_dji": {"display_name":"S&P DJI 公开资讯","short_name":"S&P DJI","category":"指数公告（待授权）","logo_url":None,"evidence_role":"primary","authority":"official"},
    "anysearch_discovery": {"display_name":"公开讨论发现","short_name":"Web","category":"X / 公开论坛","logo_url":None,"evidence_role":"discovery","authority":"secondary"},
}
def _db(path: str | None=None) -> str: return path or os.getenv("DATABASE_PATH","data/radar.db")
def _public_url(name: str, fallback: str) -> str: return os.getenv(name, fallback).strip().rstrip("/") or fallback
def _store(path: str | None=None) -> EvidenceStore: return EvidenceStore(_db(path))
def _run_database_path(run_id: str) -> str:
    registry = _store()
    try: return registry.registered_run_path(run_id) or _db()
    finally: registry.close()
def _run_store(run_id: str) -> EvidenceStore: return EvidenceStore(_run_database_path(run_id))
def _report_store(report_id: str) -> EvidenceStore:
    run_id = report_id.removeprefix("report:") if report_id.startswith("report:") else ""
    return _run_store(run_id) if run_id else _store()
class ResearchRequest(BaseModel):
    topic:str|None=Field(default=None,min_length=2,max_length=200)
    theme:str|None=None
    objective:str=CORE_RESEARCH_OBJECTIVE
    sources:list[str]=Field(default_factory=list)
    time_range:str="multi_horizon"
    custom_date_range:dict|None=None
    output_type:str="theme_report"
    database_path:str|None=None
class EventResearchRequest(BaseModel): evidence_id:str; database_path:str|None=None
class ReviewRequest(BaseModel): decision:Literal["approve","return"]; note:str=""
class ReportUpdateRequest(BaseModel):
    title:str|None=Field(default=None,min_length=1,max_length=200)
    status:Literal["deep_research","watch","completed","draft","archived"]|None=None
class ReportAssistantRequest(BaseModel): command:str=Field(min_length=1,max_length=500)
class EntityReviewRequest(BaseModel): decision:Literal["confirmed","rejected"]
class ThemeCandidateReviewRequest(BaseModel):
    decision:Literal["confirm","merge","reject"]
    target_theme_id:str=""
    note:str=Field(default="",max_length=500)
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)

def _is_public_auth_path(path: str) -> bool:
    return path in {"/health", "/api/auth/session", "/api/auth/login", "/api/auth/logout"}

@app.middleware("http")
async def require_internal_login(request: Request, call_next):
    if not internal_auth.enabled() or _is_public_auth_path(request.url.path):
        return await call_next(request)
    username = internal_auth.session_user(request.cookies.get(internal_auth.COOKIE_NAME))
    if not username:
        return JSONResponse({"detail": "请先登录内部账号"}, status_code=401)
    request.state.internal_username = username
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        expected_origin = _public_url("PUBLIC_FRONTEND_URL", "").rstrip("/")
        if origin and expected_origin and origin.rstrip("/") != expected_origin:
            return JSONResponse({"detail": "跨站写操作被拒绝"}, status_code=403)
    return await call_next(request)

@app.get("/api/auth/session")
def auth_session(request: Request):
    if not internal_auth.enabled():
        return {"enabled": False, "authenticated": True, "username": "local"}
    username = internal_auth.session_user(request.cookies.get(internal_auth.COOKIE_NAME))
    return {"enabled": True, "authenticated": bool(username), "username": username or ""}

@app.post("/api/auth/login")
def auth_login(request: LoginRequest, response: Response):
    if not internal_auth.enabled():
        raise HTTPException(404, "内部账号登录未启用")
    user = internal_auth.authenticate(request.username, request.password)
    if not user:
        raise HTTPException(401, "账号或密码错误")
    secure = os.getenv("INTERNAL_AUTH_COOKIE_SECURE", "true").strip().lower() in {"1", "true", "yes", "on"}
    ttl = max(300, int(os.getenv("INTERNAL_AUTH_TTL_SECONDS", str(internal_auth.DEFAULT_TTL_SECONDS))))
    response.set_cookie(
        internal_auth.COOKIE_NAME, internal_auth.issue_session(user.username),
        max_age=ttl, httponly=True, secure=secure, samesite="lax", path="/",
    )
    return {"authenticated": True, "username": user.username}

@app.post("/api/auth/logout")
def auth_logout(response: Response):
    response.delete_cookie(internal_auth.COOKIE_NAME, path="/")
    return {"authenticated": False}

@app.get("/health")
def health(): return {"status":"ok","trading":"disabled","service_id":SERVICE_ID,"contract_version":CONTRACT_VERSION}
@app.get("/api/connectors/health")
def connector_health(): return [h.__dict__ for h in (c.healthcheck() for c in configured_connectors(Path("data/cache")))]
@app.get("/api/capabilities")
def capabilities():
    raw_health = connector_health()
    connectors = [{**item, **SOURCE_METADATA.get(item["source_name"], {"display_name":item["source_name"],"short_name":item["source_name"],"category":"公开来源","logo_url":None,"evidence_role":"supporting","authority":"unknown"})} for item in raw_health]
    ready = sum(item["enabled"] and item["status"] == "healthy" for item in connectors)
    store = _store()
    try:
        preview = store.latest_etf_preview_snapshot()
        preview_run = store.active_etf_preview_sync_run()
    finally:
        store.close()
    return {
        "service":{"id":SERVICE_ID,"name":"ETF Theme Radar","version":app.version,"contract_version":CONTRACT_VERSION,"canonical_api":_public_url("PUBLIC_API_URL", "http://127.0.0.1:8001"),"canonical_frontend":_public_url("PUBLIC_FRONTEND_URL", "http://127.0.0.1:3000")},
        "worker":worker_status(_db()),
        "sync_discovery_worker":sync_worker_status(_db()),
        "connectors":connectors,
        "sources":connectors,
        "source_coverage":{"ready":ready,"total":len(connectors),"label":f"{ready}/{len(connectors)}","excluded":["patentsview"]},
        "llm":capability_status(),
        "playwright_mcp":{"configured":bool(os.getenv("PLAYWRIGHT_MCP_COMMAND"))},
        "core_capability":{"id":CORE_RESEARCH_OBJECTIVE,"name":"分析 ETF 格局、跟踪产业动量","output_type":"theme_report"},
        "output_types":{"theme_report":True},
        "runtime_profiles":{"theme_report":{"name":"统一主题研究","max_seconds":480,"max_tool_calls":12,"max_model_requests":6,"time_windows":["30d","90d","1y","5-10y_scenarios"],"source_selection":"automatic"}},
        "etf_preview": {
            "source": "天天基金网", "enabled": True,
            "status": (preview or {}).get("status", "not_synced"),
            "last_collected_at": (preview or {}).get("collected_at", ""),
            "market_as_of": (preview or {}).get("market_as_of", ""),
            "total": int((preview or {}).get("total", 0)),
            "refresh_status": (preview_run or {}).get("status", "idle"),
        },
    }

@app.get("/api/etf-preview")
def get_etf_preview(
    category: Literal["sp500", "exchange", "active"] | None = None,
    q: str = Query(default="", max_length=100),
    sort_by: Literal[
        "code", "name", "operating_fee", "scale_billion", "return_2025",
        "rolling_1y", "yesterday_return", "tracking_error", "premium_rate",
        "average_turnover_billion_20d",
    ] = "scale_billion",
    order: Literal["asc", "desc"] = "desc",
):
    store = _store()
    try:
        snapshot = store.latest_etf_preview_snapshot()
        active_run = store.active_etf_preview_sync_run()
    finally:
        store.close()
    if not snapshot:
        return {
            "state": "empty", "source": "天天基金网", "items": [],
            "counts": {"sp500": 0, "exchange": 0, "active": 0},
            "filtered_count": 0, "total_before_filters": 0,
            "refresh": active_run,
        }
    categories = snapshot.get("categories") or {}
    items = list(categories.get(category, [])) if category else [item for values in categories.values() for item in values]
    query = q.strip().casefold()
    if query:
        items = [
            item for item in items
            if query in str(item.get("code") or "").casefold()
            or query in str(item.get("c_code") or "").casefold()
            or query in str(item.get("name") or "").casefold()
        ]
    present = [item for item in items if item.get(sort_by) is not None]
    missing = [item for item in items if item.get(sort_by) is None]

    def sort_value(item: dict):
        value = item.get(sort_by)
        return value.casefold() if isinstance(value, str) else value

    present.sort(key=sort_value, reverse=order == "desc")
    items = present + missing
    return {
        **{key: value for key, value in snapshot.items() if key != "categories"},
        "state": "ready" if snapshot.get("status") == "available" else "degraded",
        "items": items,
        "filtered_count": len(items),
        "total_before_filters": len(categories.get(category, [])) if category else int(snapshot.get("total", 0)),
        "refresh": active_run,
    }

@app.post("/api/etf-preview/refresh", status_code=202)
def refresh_etf_preview():
    store = _store()
    try:
        existing = store.active_etf_preview_sync_run()
        if existing:
            return {
                "sync_run_id": existing["sync_run_id"], "status": existing["status"],
                "poll_url": f"/api/sync-runs/{existing['sync_run_id']}", "idempotent": True,
            }
        sync_run_id = str(uuid4())
        store.create_sync_run(
            sync_run_id, utcnow(), days=0,
            idempotency_key=f"etf-preview:manual:{sync_run_id}",
        )
    finally:
        store.close()
    sync_worker_for(_db()).wake()
    return {
        "sync_run_id": sync_run_id, "status": "queued",
        "poll_url": f"/api/sync-runs/{sync_run_id}", "idempotent": False,
    }
@app.post("/api/pipeline/run")
def run_pipeline(days:int=Query(default=7,ge=1,le=31)):
    store=_store(); until=date.today()
    try: return {c.source_name:ingest(c,store,until-timedelta(days=days),until) for c in configured_connectors(Path("data/cache"))}
    finally: store.close()

@app.post("/api/sync",status_code=202)
def sync_sources(days:int=Query(default=7,ge=1,le=31)):
    return create_sync_run(days)

@app.post("/api/sync-runs",status_code=202)
def create_sync_run(days:int=Query(default=7,ge=1,le=31)):
    sync_run_id=str(uuid4()); store=_store()
    try: store.create_sync_run(sync_run_id,utcnow(),days=days)
    finally: store.close()
    sync_worker_for(_db()).wake()
    return {"sync_run_id":sync_run_id,"status":"queued"}

@app.get("/api/sync-runs")
def list_sync_runs():
    store=_store()
    try: items=store.sync_runs()
    finally: store.close()
    return {"runs":items}

@app.get("/api/sync-runs/{sync_run_id}")
def get_sync_run(sync_run_id:str):
    store=_store()
    try: item=store.sync_run(sync_run_id)
    finally: store.close()
    if not item: raise HTTPException(404,"同步任务不存在")
    return item

@app.post("/api/sync-runs/{sync_run_id}/cancel")
def cancel_sync_run(sync_run_id:str):
    store=_store()
    try: changed=store.request_sync_cancel(sync_run_id)
    finally: store.close()
    if not changed: raise HTTPException(409,"同步任务不可取消")
    return {"sync_run_id":sync_run_id,"status":"cancelling"}
def _event_list(value: object) -> list[str]:
    if isinstance(value, list): return [str(item) for item in value]
    if not isinstance(value, str) or not value: return []
    try:
        parsed = json.loads(value)
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []

def _matches_source_type(event: dict, requested: str) -> bool:
    raw = f"{event.get('origin_source_type','')} {event.get('source_type','')} {event.get('source','')}".lower()
    aliases = {
        "sec": ("sec", "regulatory", "filing", "government"),
        "paper": ("academic", "paper", "arxiv", "research"),
        "patent": ("patent",),
        "job": ("job", "career", "greenhouse"),
        "company_update": ("official", "company", "press_release", "newsroom"),
        "social_discussion": ("social", "forum", "twitter", "x.com"),
    }
    return any(token in raw for token in aliases.get(requested, (requested.lower(),)))

@app.get("/api/evidence")
def evidence(
    limit:int=Query(default=100,ge=1,le=500),
    theme:str|None=None,
    source_type:str|None=None,
    company:str|None=None,
    date_from:str|None=None,
    date_to:str|None=None,
    include_unreviewed:bool=False,
):
    store = _store()
    try:
        events = store.events()
    finally:
        store.close()
    if not include_unreviewed:
        events = [item for item in events if item.get("relevance_status") == "relevant" and item.get("theme_assignment_status") == "assigned"]
    if theme:
        events = [
            item for item in events
            if theme in {item.get("primary_theme"), *_event_list(item.get("secondary_themes")), *_event_list(item.get("themes"))}
        ]
    if source_type: events = [item for item in events if _matches_source_type(item, source_type)]
    if company:
        company_key = company.casefold()
        events = [
            item for item in events
            if company_key in f"{item.get('publisher','')} {item.get('company_id','')} {' '.join(_event_list(item.get('companies')))}".casefold()
        ]
    if date_from: events = [item for item in events if (item.get("published_at") or "") >= date_from]
    if date_to: events = [item for item in events if (item.get("published_at") or "") <= date_to]
    return {"evidence":events[:limit],"total":len(events),"note":"只读、治理后证据接口"}

@app.get("/api/evidence/facets")
def evidence_facets():
    store=_store()
    try: events=[item for item in store.events() if item.get("relevance_status")=="relevant" and item.get("theme_assignment_status")=="assigned"]
    finally: store.close()
    themes=sorted({item.get("primary_theme") for item in events if item.get("primary_theme")})
    companies=sorted({item.get("company_id") or item.get("publisher") for item in events if item.get("company_id") or item.get("publisher")})
    sources=sorted({item.get("origin_source_type") or item.get("source_type") for item in events})
    return {"themes":[{"id":item,"label":THEME_LABELS.get(item,item)} for item in themes],"companies":companies,"source_types":sources,"generated_at":utcnow()}

@app.get("/api/evidence/{evidence_id}")
def evidence_detail(evidence_id:str):
    store = _store()
    try:
        event = next((item for item in store.events() if item["event_id"] == evidence_id), None)
    finally:
        store.close()
    if not event: raise HTTPException(404, "证据不存在")
    return event

THEME_LABELS = {"ai-infrastructure":"AI 基础设施","edge-ai-infrastructure":"边缘 AI 基础设施","robotics":"智能机器人","semiconductors":"半导体"}

def _theme_payloads() -> list[dict]:
    store = _store()
    try:
        events = [item for item in store.events() if item.get("relevance_status")=="relevant" and item.get("theme_assignment_status")=="assigned"]
        definitions={item["theme_id"]:item for item in store.theme_definitions()}
        snapshots=store.theme_snapshots()
        reports={item["theme_id"]:item for item in store.report_assets() if item.get("kind") == "theme_report"}
    finally: store.close()
    grouped:dict[str,list[dict]] = {}
    for event in events: grouped.setdefault(event.get("primary_theme") or "unknown",[]).append(event)
    payload=[]
    latest_snapshots={}
    for snapshot in snapshots: latest_snapshots.setdefault(snapshot["theme_id"],snapshot)
    for theme in sorted(set(grouped)|set(definitions)):
        items=grouped.get(theme,[])
        if theme in {"unknown","irrelevant","no_theme_match","needs_review"}: continue
        source_types={item.get("origin_source_type") or item.get("source_type") for item in items}
        companies={item.get("company_id") or item.get("publisher") for item in items if item.get("company_id") or item.get("publisher")}
        primary=sum(item.get("primary_or_secondary")=="primary" for item in items)
        snapshot=latest_snapshots.get(theme)
        score=float(snapshot["score"]) if snapshot else min(100,round(35+len(source_types)*8+min(len(companies),20)*1.5+min(primary,10),1))
        definition=definitions.get(theme,{})
        latest=items[0] if items else {}
        metrics=(snapshot or {}).get("metrics",{})
        report=reports.get(theme,{})
        payload.append({
            "id":f"theme_{theme}","slug":theme,"title":definition.get("name") or THEME_LABELS.get(theme,theme.replace("-"," ").title()),"englishTitle":theme.replace("-"," ").title(),
            "description":definition.get("description") or "由治理后的公开证据形成的主题观察。","sector":"semiconductors" if "semiconductor" in theme else "industrials" if "robot" in theme else "technology",
            "sources":sorted({"sec" if "sec" in str(x) else "research" if str(x)=="academic" else "patents" if str(x)=="patent" else "careers" if "company" in str(x) else "market_discussion" for x in source_types}),
            "stage":"deep_research" if len(source_types)>=3 and primary>=2 else "validating","trend":snapshot.get("trend","unknown") if snapshot else "unknown",
            "trendReason":snapshot.get("trend_reason","尚未生成历史快照。") if snapshot else "尚未生成历史快照。",
            "metrics":{"themeScore":score,"researchMomentum":metrics.get("research_momentum",min(100,len(items)*2)),"commercialAdoption":metrics.get("corporate_adoption",min(100,len(companies)*5)),"etfWhiteSpace":metrics.get("product_white_space",0),"companies":len(companies),"components":metrics.get("components",{}),"penalties":metrics.get("penalties",0),"evidenceGatePassed":metrics.get("evidence_gate_passed",False)},
            "latestCatalyst":latest.get("title") or "暂无最新催化剂","latestEvidence":latest.get("summary") or "暂无摘要","mainRisk":"反方证据、可投资性和集中度仍需持续复核。",
            "evidenceCount":len(items),"sourceTypeCount":len(source_types),"updatedAt":latest.get("observed_at") or definition.get("updated_at","") ,
            "currentConclusion":report.get("summary") or "尚未发布正式主题结论。","reportVersion":int(report.get("version") or 0),"lastVerifiedAt":report.get("updated_at") or "","reportId":report.get("report_id") or "",
            "coverage":{"evidence":len(items),"sourceTypes":len(source_types),"official":primary,"confidence":snapshot.get("confidence","low") if snapshot else "low"},
        })
    return sorted(payload,key=lambda item:item["metrics"]["themeScore"],reverse=True)

@app.get("/api/themes")
def themes(sector:str="all",source:str="all",period:str="90d",stage:str="all"):
    items=_theme_payloads()
    if sector!="all": items=[item for item in items if item["sector"]==sector]
    if source!="all": items=[item for item in items if source in item["sources"]]
    if stage!="all": items=[item for item in items if item["stage"]==stage]
    store=_store()
    try: candidates=store.theme_candidates(limit=50)
    finally: store.close()
    return {"themes":items,"candidates":candidates,"totalBeforeFilters":len(_theme_payloads()),"generatedAt":utcnow(),"coverageNote":f"{period} 观察窗口 · 候选先过可信度门槛再排序 · 历史不足时不推断趋势"}

@app.get("/api/theme-candidates")
def theme_candidates(status:str|None=None,limit:int=Query(default=50,ge=1,le=200)):
    store=_store()
    try: items=store.theme_candidates(status=status,limit=limit)
    finally: store.close()
    return {"candidates":items,"count":len(items),"generatedAt":utcnow(),"reviewRequired":True}

@app.get("/api/discovery-runs")
def discovery_runs(limit:int=Query(default=20,ge=1,le=100)):
    store=_store()
    try: items=store.discovery_runs(limit)
    finally: store.close()
    return {"runs":items,"count":len(items)}

@app.get("/api/theme-candidates/{candidate_id}")
def theme_candidate(candidate_id:str):
    store=_store()
    try: item=store.theme_candidate(candidate_id)
    finally: store.close()
    if not item: raise HTTPException(404,"候选主题不存在")
    return item

@app.post("/api/theme-candidates/{candidate_id}/review")
def review_theme_candidate(candidate_id:str,request:ThemeCandidateReviewRequest):
    store=_store(); result=None
    try:
        try: result=store.review_theme_candidate(candidate_id,request.decision,utcnow(),target_theme_id=request.target_theme_id,note=request.note)
        except ValueError as exc: raise HTTPException(409,str(exc)) from exc
        if result and result.get("theme_id"):
            refresh_research_assets(store)
    finally: store.close()
    if not result: raise HTTPException(409,"候选不存在或已经完成复核")
    return result

@app.get("/api/entities/review")
def entity_review_queue():
    store=_store()
    try: items=store.entities("needs_review")
    finally: store.close()
    return {"entities":items,"count":len(items),"generatedAt":utcnow()}

@app.post("/api/entities/{entity_id}/review")
def review_entity(entity_id:str, request:EntityReviewRequest):
    store=_store()
    try: changed=store.review_entity(entity_id,request.decision,utcnow())
    finally: store.close()
    if not changed: raise HTTPException(404,"实体不存在")
    return {"entity_id":entity_id,"review_status":request.decision}

@app.get("/api/dashboard")
def dashboard():
    store=_store()
    try:
        events=store.events(); runs=store.research_runs(); reports=store.report_assets()
    finally: store.close()
    governed=[item for item in events if item.get("relevance_status")=="relevant" and item.get("theme_assignment_status")=="assigned"]
    theme_items=_theme_payloads()
    return {"metrics":{"themes":len(theme_items),"evidence":len(governed),"runs":len(runs),"reports":len(reports)},"themes":theme_items[:3],"runs":runs[:6],"generatedAt":utcnow()}

@app.get("/api/search")
def global_search(q:str=Query(min_length=2,max_length=120),limit:int=Query(default=12,ge=1,le=30)):
    needle=q.casefold().strip(); store=_store()
    try:
        evidence_items=[item for item in store.events() if needle in f"{item.get('title','')} {item.get('summary','')} {item.get('publisher','')}".casefold()][:limit]
        report_items=[item for item in store.report_assets() if needle in f"{item.get('title','')} {item.get('summary','')} {' '.join(_event_list(item.get('tags')))}".casefold()][:limit]
        definitions=[item for item in store.theme_definitions() if needle in f"{item.get('name','')} {item.get('description','')} {' '.join(item.get('aliases',[]))}".casefold()][:limit]
    finally: store.close()
    results=[{"id":item["theme_id"],"kind":"theme","title":item["name"],"summary":item["description"],"href":f"/theme-radar?theme={item['theme_id']}"} for item in definitions]
    results += [{"id":item["event_id"],"kind":"evidence","title":item["title"],"summary":item.get("summary","")[:180],"href":f"/evidence?evidence={item['event_id']}"} for item in evidence_items]
    results += [{"id":item["report_id"],"kind":"report","title":item["title"],"summary":item.get("summary","")[:180],"href":f"/reports/{item['report_id']}"} for item in report_items]
    return {"query":q,"results":results[:limit],"count":min(len(results),limit)}
@app.post("/api/reports/daily")
def daily_report():
    raise HTTPException(410,"日报输出已停止创建；当前仅生成主题研究报告")

@app.get("/api/reports")
def report_library(
    query:str="",
    folder:str="all",
    status:str="all",
    date_range:Literal["30d","90d","1y","all"]="all",
):
    store = _store()
    try:
        reports = store.report_assets()
    finally:
        store.close()
    all_reports = reports
    folders = [
        {
            "id": folder_id,
            "report_count": len([item for item in all_reports if item["folder_id"] == folder_id and item["status"] != "archived"]),
            "latest_update": max((item["updated_at"] for item in all_reports if item["folder_id"] == folder_id and item["status"] != "archived"), default=None),
        }
        for folder_id in ("ai","energy","robotics","healthcare")
    ]
    if folder != "all": reports = [item for item in reports if item["folder_id"] == folder]
    if status == "all": reports = [item for item in reports if item["status"] != "archived"]
    else: reports = [item for item in reports if item["status"] == status]
    if date_range != "all":
        days = 30 if date_range == "30d" else 90 if date_range == "90d" else 365
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        reports = [item for item in reports if (item["updated_at"] or "") >= cutoff]
    if query.strip():
        key = query.strip().casefold()
        reports = [item for item in reports if key in f"{item['title']} {item['theme_id']} {item['tags']} {item['summary']}".casefold()]
    return {
        "reports":reports,
        "total":len(reports),
        "total_before_filters":len(all_reports),
        "active_count":len([item for item in all_reports if item["status"] != "archived"]),
        "archived_count":len([item for item in all_reports if item["status"] == "archived"]),
        "folders":folders,
        "note":"研究资产只读列表；正文与证据附件按 run_id 关联",
    }

@app.post("/api/reports/assistant")
def report_library_assistant(request:ReportAssistantRequest):
    store = _store()
    try:
        reports = store.report_assets()
    finally:
        store.close()
    command = request.command.casefold()
    if "机器人" in command or "robotics" in command:
        matched = [item for item in reports if item["folder_id"] == "robotics" and item["status"] != "archived"]
        return {"title":"机器人研究","summary":f"找到 {len(matched)} 份机器人研究。","matchedReportIds":[item["report_id"] for item in matched],"suggestedFilters":{"folder":"robotics","query":""}}
    if ("比较" in command or "compare" in command) and "ai" in command:
        matched = [item for item in reports if item["folder_id"] == "ai" and "ETF" in item["tags"] and item["status"] != "archived"]
        return {"title":"AI ETF 报告对比","summary":f"找到 {len(matched)} 份可用于对比的 AI ETF 研究。","matchedReportIds":[item["report_id"] for item in matched],"suggestedFilters":{"folder":"ai","query":"ETF"}}
    if "变化" in command or "changes" in command or "更新" in command:
        matched = [item for item in reports if item["status"] != "archived"][:3]
        return {"title":"最近研究变化","summary":f"找到最近更新的 {len(matched)} 份研究文件。","matchedReportIds":[item["report_id"] for item in matched],"suggestedFilters":{"dateRange":"30d","query":""}}
    matched = [item for item in reports if command in f"{item['title']} {item['theme_id']} {item['tags']}".casefold()]
    return {"title":"资料库搜索结果","summary":f"找到 {len(matched)} 份相关研究。" if matched else "没有找到直接匹配项。","matchedReportIds":[item["report_id"] for item in matched],"suggestedFilters":{"query":request.command} if matched else None}

@app.get("/api/reports/{report_id}")
def get_report_asset(report_id:str):
    store = _store()
    try:
        report = store.report_asset(report_id)
    finally:
        store.close()
    if not report: raise HTTPException(404,"报告不存在或已经删除")
    return report

REPORT_THEME_LABELS = {
    "ai-infrastructure": "AI 基础设施",
    "edge-ai-infrastructure": "边缘 AI 基础设施",
    "robotics": "智能机器人",
    "semiconductors": "半导体",
}

def _memo_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item.get("name") or item.get("title") or item) if isinstance(item, dict) else str(item) for item in value]
    return [str(value)] if value not in (None, "", "unknown") else []

def _counter_arguments(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    normalized = []
    for item in value:
        if isinstance(item, str) and item.strip().startswith(("{", "[")):
            try:
                parsed = json.loads(item)
            except json.JSONDecodeError:
                try:
                    parsed = ast.literal_eval(item)
                except (ValueError, SyntaxError):
                    parsed = None
            if isinstance(parsed, dict):
                item = parsed
        if isinstance(item, dict):
            normalized.append(item)
        elif str(item).strip():
            normalized.append({"claim": str(item)})
    return [
        {
            "claim": str(item.get("claim") or item.get("title") or "待核验反方观点"),
            "reason": str(item.get("reason") or item.get("limitation") or "需要人工复核语境。"),
            "sourceUrl": str(item.get("source_url") or item.get("url") or ""),
            "publisher": str(item.get("publisher") or item.get("publisher_domain") or "公开来源"),
        }
        for item in normalized
    ]

def _citation_payload(item: dict, index: int, side: str) -> dict:
    from .theme_research import LEGACY_EVIDENCE_SUMMARY, _fallback_chinese_evidence
    source_type = str(item.get("source_type") or item.get("origin_source_type") or "公开来源")
    logo_domains = {
        "regulatory": "sec.gov",
        "sec": "sec.gov",
        "academic": "arxiv.org",
        "patent": "patents.google.com",
        "social": "x.com",
        "forum": "seekingalpha.com",
    }
    domain = logo_domains.get(source_type.casefold()) or item.get("publisher_domain") or ""
    publisher = str(item.get("publisher") or domain or "公开来源")
    evidence = str(item.get("zh_fact_summary") or item.get("fact_summary") or item.get("research_implication") or "该证据的中文事实摘要尚待补充。")
    if LEGACY_EVIDENCE_SUMMARY in evidence:
        evidence = _fallback_chinese_evidence(item)["zh_fact_summary"]
    return {
        "id": f"citation-{index:02d}",
        "evidenceId": str(item.get("evidence_id") or item.get("event_id") or f"source-{index:02d}"),
        "side": side,
        "sourceType": source_type,
        "publisher": publisher,
        "logoUrl": f"https://www.google.com/s2/favicons?domain={domain}&sz=128" if domain else "",
        "claim": str(item.get("zh_title") or item.get("claim") or item.get("title") or "待核验证据"),
        "evidence": evidence,
        "limitation": str(item.get("limitation") or "该来源需要与其他独立证据交叉验证。"),
        "confidence": float(item.get("classification_confidence") or item.get("extraction_confidence") or 0),
        "url": str(item.get("source_url") or item.get("url") or ""),
    }

def _research_sources(citations: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for citation in citations:
        url = str(citation.get("url") or "")
        domain = str(citation.get("publisher_domain") or "")
        if not domain and "://" in url:
            domain = url.split("://", 1)[1].split("/", 1)[0].casefold().removeprefix("www.")
        publisher = str(citation.get("publisher") or domain or "公开来源")
        key = domain or publisher.casefold()
        item = grouped.setdefault(key, {
            "id": key, "name": publisher, "type": str(citation.get("source_type") or "公开来源"),
            "citationCount": 0, "url": url,
            "logoUrl": f"https://www.google.com/s2/favicons?domain={domain}&sz=128" if domain else "",
            "fallback": publisher[:1].upper(),
        })
        item["citationCount"] += 1
    return sorted(grouped.values(), key=lambda item: (-item["citationCount"], item["name"].casefold()))

def _report_detail_payload(asset: dict, run: dict | None, latest_market_snapshot: dict | None = None) -> dict:
    result = (run or {}).get("result") or {}
    detail = result.get("detail") or {}
    brief = result.get("brief") or {}
    hypothesis = detail.get("hypothesis") or {}
    counter = detail.get("counter") or {}
    investability = detail.get("investability") or {}
    landscape = detail.get("landscape") or {}
    audit = result.get("audit") or {}
    bull = [_citation_payload(item, index, "bull") for index, item in enumerate(brief.get("key_evidence") or [], 1)]
    bear_raw = counter.get("counter_evidence") or []
    bear = [_citation_payload(item, len(bull) + index, "bear") for index, item in enumerate(bear_raw, 1)]
    source_types = int(brief.get("source_types") or asset.get("source_count") or 0)
    first_party = int(brief.get("first_party") or 0)
    audit_passed = bool(audit.get("passed", asset.get("audit_passed")))
    confidence = "high" if audit_passed and source_types >= 3 and first_party >= 2 else "medium" if audit_passed else "low"
    raw_status = str(result.get("status") or asset.get("status") or "WATCH").upper()
    status = {"DEEP_RESEARCH": "DEEP_RESEARCH", "DEEP RESEARCH": "DEEP_RESEARCH", "WATCH": "WATCH", "REJECT": "REJECT"}.get(raw_status)
    if not status:
        status = "DEEP_RESEARCH" if asset.get("status") == "deep_research" else "WATCH"
    missing = _memo_list(counter.get("missing_evidence")) or ["结构化反方证据、历史基线与产品重叠数据仍待补充。"]
    similar_etfs = landscape.get("similar_etfs") or []
    theme_etf_snapshot = landscape.get("theme_etf_snapshot") or {}
    existing_etfs = [
        f"{item.get('ticker')} · {item.get('issuer')} · {item.get('category')}"
        if isinstance(item, dict) else str(item)
        for item in similar_etfs
    ]
    existing_etfs.extend(
        f"{item.get('code')} · {item.get('name')} · ETF 预览冻结快照"
        for item in (theme_etf_snapshot.get("products") or [])
        if isinstance(item, dict)
    )
    market_snapshot = landscape.get("market_snapshot") or {}
    if latest_market_snapshot:
        independent_market = {
            **(latest_market_snapshot.get("payload") or {}),
            "snapshot_id": latest_market_snapshot["snapshot_id"],
            "collected_at": latest_market_snapshot["collected_at"],
            "market_as_of": latest_market_snapshot.get("market_as_of") or "",
            "status": latest_market_snapshot.get("status") or "unknown",
            "products": latest_market_snapshot.get("products") or [],
            "errors": latest_market_snapshot.get("errors") or [],
            "origin": "independent_snapshot",
        }
    else:
        independent_market = {
            **market_snapshot,
            "snapshot_id": "legacy-report-snapshot" if market_snapshot else "",
            "origin": "legacy_report_snapshot" if market_snapshot else "unavailable",
        }
    overlap = str(landscape.get("overlap_status") or "unknown")
    white_space = str(landscape.get("product_white_space") or "unknown")
    landscape_status = "unknown" if not existing_etfs and overlap == "unknown" and white_space == "unknown" else "partial"
    companies = _memo_list(investability.get("identified_public_companies"))
    beneficiaries = _memo_list(hypothesis.get("potential_beneficiaries"))
    company_status = "partial" if companies or beneficiaries else "unknown"
    thesis = str(hypothesis.get("hypothesis") or asset.get("summary") or "当前报告尚未形成可审计的结构化主题假设。")
    conclusion = result.get("conclusion") or {}
    report_sections = result.get("report_sections") or {}
    evidence_gaps = report_sections.get("evidence_gaps") or conclusion.get("evidence_gaps") or []
    detailed_missing = [
        f"{item.get('area')}：{item.get('gap')}。影响：{item.get('impact')}"
        for item in evidence_gaps if isinstance(item, dict)
    ]
    if detailed_missing:
        missing = detailed_missing
    fallback_verdict = "supported" if status == "DEEP_RESEARCH" else "insufficient" if status == "REJECT" else "mixed"
    conclusion_payload = {
        "verdict": str(conclusion.get("verdict") or fallback_verdict),
        "confidence": str(conclusion.get("confidence") or confidence),
        "statement": str(
            conclusion.get("statement")
            or ("现有证据支持继续深度研究，但仍需关闭关键数据缺口。" if status == "DEEP_RESEARCH"
                else "当前证据存在支持与限制，尚不足以形成买卖或产品决策。")
        ),
        "keyEvidenceIds": [str(item) for item in conclusion.get("key_evidence_ids") or []],
        "limitations": _memo_list(conclusion.get("limitations")) or missing[:4],
        "evidenceGaps": evidence_gaps,
        "modelUsed": bool(conclusion.get("model_used")),
    }
    return {
        "reportId": asset["report_id"],
        "runId": asset.get("run_id") or None,
        "title": asset["title"],
        "themeId": asset.get("theme_id") or "unknown",
        "themeLabel": REPORT_THEME_LABELS.get(asset.get("theme_id"), asset.get("theme_id") or "未分类主题"),
        "status": status,
        "confidence": confidence,
        "lastUpdated": asset.get("updated_at") or "",
        "version": int(asset.get("version") or 1),
        "auditPassed": audit_passed,
        "conclusion": conclusion_payload,
        "executiveSummary": str(asset.get("summary") or thesis),
        "investmentThesis": thesis,
        "whyNow": _memo_list(hypothesis.get("key_catalysts")) or ["等待独立一级来源形成连续新增证据。"],
        "keyDrivers": _memo_list(hypothesis.get("economic_mechanism")) or ["尚未形成可审计的经济传导机制。"],
        "mainRisks": _memo_list(hypothesis.get("disconfirming_conditions")) or ["当前证据不足以支持投资或 ETF 产品结论。"],
        "bullCase": bull,
        "bearCase": {
            "citations": bear,
            "counterArguments": _counter_arguments(counter.get("conflicting_evidence")),
            "risks": _memo_list(hypothesis.get("disconfirming_conditions")),
            "missingData": missing,
        },
        "etfLandscape": {
            "existingEtfs": existing_etfs,
            "overlap": overlap,
            "whiteSpace": white_space,
            "dataStatus": landscape_status,
            "products": market_snapshot.get("products") or [],
            "marketAsOf": str(market_snapshot.get("market_as_of") or ""),
            "marketSnapshotStatus": str(market_snapshot.get("status") or "unknown"),
            "limitations": _memo_list(market_snapshot.get("limitations")),
            "themeRelatedFunds": theme_etf_snapshot.get("products") or [],
            "previewSnapshotId": str(theme_etf_snapshot.get("snapshot_id") or ""),
            "previewMarketAsOf": str(theme_etf_snapshot.get("market_as_of") or ""),
            "previewStatus": str(theme_etf_snapshot.get("status") or "not_assessed"),
            "previewLimitations": _memo_list(theme_etf_snapshot.get("limitations")),
        },
        "latestMarketSnapshot": independent_market,
        "researchSources": _research_sources([*(brief.get("key_evidence") or []), *bear_raw]),
        "companyMap": {
            "purePlays": [],
            "enablers": companies,
            "beneficiaries": beneficiaries,
            "dataStatus": company_status,
        },
        "decision": {
            "currentStatus": status,
            "rationale": "证据质量与来源覆盖支持继续研究。" if status == "DEEP_RESEARCH" else "关键证据缺口尚未关闭，当前维持观察。",
            "nextActions": missing[:4],
        },
        "structuredAnalysis": {
            "whyTheme": report_sections.get("why_theme") or {},
            "industryChain": report_sections.get("industry_chain") or {},
            "growthDrivers": report_sections.get("growth_drivers") or [],
            "etfInvestmentAngle": report_sections.get("etf_investment_angle") or {},
            "risks": report_sections.get("risks") or [],
            "scenarios": report_sections.get("scenarios") or [],
            "scorecard": report_sections.get("scorecard") or [],
            "evidenceGaps": evidence_gaps,
        },
    }

@app.get("/api/reports/{report_id}/detail")
def get_report_detail(report_id:str, version:int|None=Query(default=None,ge=1)):
    store = _report_store(report_id)
    try:
        report = store.report_asset(report_id)
        versions = store.report_versions(report_id) if report else []
        latest_market_snapshot = store.latest_etf_market_snapshot(report_id) if report else None
        selected_version = next((item for item in versions if item["version"] == version), None) if version else (versions[0] if versions else None)
        if version and not selected_version:
            raise HTTPException(404,"报告版本不存在")
        if selected_version:
            payload = selected_version.get("payload") or {}
            run = {"result": payload.get("result") or {}}
            frozen_asset = payload.get("asset") or {}
            report = {
                **report,
                **frozen_asset,
                "version": selected_version["version"],
                "updated_at": selected_version.get("created_at") or report.get("updated_at"),
            }
        else:
            run = store.research_run(report["run_id"]) if report and report.get("run_id") else None
    finally:
        store.close()
    if not report: raise HTTPException(404,"报告不存在或已经删除")
    return _report_detail_payload(report, run, latest_market_snapshot)

@app.post("/api/reports/{report_id}/market-snapshot", status_code=202)
def refresh_report_market_snapshot(report_id: str):
    store = _report_store(report_id)
    try:
        report = store.report_asset(report_id)
        if not report:
            raise HTTPException(404, "报告不存在或已经删除")
        existing = next(
            (
                run for run in store.research_runs(200)
                if run["theme_id"] == f"report-refresh:{report_id}"
                and run["status"] in {"queued", "collecting", "analyzing"}
            ),
            None,
        )
        if existing:
            return {
                "run_id": existing["run_id"], "status": existing["status"],
                "poll_url": f"/api/research-runs/{existing['run_id']}", "idempotent": True,
            }
        run_id = str(uuid4())
        created_at = utcnow()
        store.create_research_run(
            run_id, f"report-refresh:{report_id}", created_at,
            {"report_id": report_id, "sources": ["tiantian", "etf_news"], "refresh_workflow":"dual_source_deterministic", "database_path": _run_database_path(report.get("run_id") or "")},
            status="queued", stage="market_refresh", database_path=_run_database_path(report.get("run_id") or ""),
        )
    finally:
        store.close()
    registry = _store()
    try:
        path = _run_database_path(report.get("run_id") or "")
        registry.register_run(run_id, path, created_at)
    finally:
        registry.close()
    worker_for(path)
    return {"run_id": run_id, "status": "queued", "poll_url": f"/api/research-runs/{run_id}"}

@app.get("/api/reports/{report_id}/versions")
def get_report_versions(report_id:str):
    store=_report_store(report_id)
    try:
        if not store.report_asset(report_id): raise HTTPException(404,"报告不存在或已经删除")
        versions=store.report_versions(report_id)
        claims=store.report_claims(report_id)
    finally: store.close()
    return {"report_id":report_id,"versions":versions,"claims":claims}


def _version_change_payload(left:dict,right:dict) -> dict:
    left_result=(left.get("payload") or {}).get("result") or {}
    right_result=(right.get("payload") or {}).get("result") or {}
    left_sections=left_result.get("report_sections") or {}
    right_sections=right_result.get("report_sections") or {}
    left_scores={item.get("id"):item for item in left_sections.get("scorecard") or []}
    right_scores={item.get("id"):item for item in right_sections.get("scorecard") or []}
    score_changes=[]
    for key in sorted(set(left_scores)|set(right_scores)):
        before=left_scores.get(key) or {}; after=right_scores.get(key) or {}
        if before.get("stars") != after.get("stars") or before.get("status") != after.get("status"):
            score_changes.append({"id":key,"label":after.get("label") or before.get("label") or key,"before":before.get("stars"),"after":after.get("stars"),"before_status":before.get("status"),"after_status":after.get("status"),"reason":after.get("reason","")})
    def etf_ids(sections:dict) -> set[str]:
        return {str(item.get("ticker") or item.get("code") or "") for item in ((sections.get("etf_investment_angle") or {}).get("products") or []) if item.get("ticker") or item.get("code")}
    left_etfs,right_etfs=etf_ids(left_sections),etf_ids(right_sections)
    left_gaps={str(item.get("area") or "") for item in left_sections.get("evidence_gaps") or []}
    right_gaps={str(item.get("area") or "") for item in right_sections.get("evidence_gaps") or []}
    left_conclusion=left_result.get("conclusion") or {}; right_conclusion=right_result.get("conclusion") or {}
    return {
        "conclusion":{"before":left_conclusion.get("statement", ""),"after":right_conclusion.get("statement", ""),"verdict_before":left_conclusion.get("verdict"),"verdict_after":right_conclusion.get("verdict"),"changed":left_conclusion.get("statement") != right_conclusion.get("statement") or left_conclusion.get("verdict") != right_conclusion.get("verdict")},
        "score_changes":score_changes,
        "etfs_added":sorted(right_etfs-left_etfs),"etfs_removed":sorted(left_etfs-right_etfs),
        "evidence_gaps_added":sorted(right_gaps-left_gaps),"evidence_gaps_closed":sorted(left_gaps-right_gaps),
        "evidence_count_before":int(left_result.get("selected") or 0),"evidence_count_after":int(right_result.get("selected") or 0),
    }


@app.get("/api/reports/{report_id}/timeline")
def report_version_timeline(report_id:str):
    store=_report_store(report_id)
    try:
        if not store.report_asset(report_id): raise HTTPException(404,"报告不存在或已经删除")
        versions=sorted(store.report_versions(report_id),key=lambda item:item["version"])
    finally: store.close()
    items=[]
    for index,item in enumerate(versions):
        result=(item.get("payload") or {}).get("result") or {}; conclusion=result.get("conclusion") or {}; sections=result.get("report_sections") or {}
        change=_version_change_payload(versions[index-1],item) if index else None
        tags=[]
        if change:
            if change["conclusion"]["changed"]: tags.append("结论变化")
            if change["score_changes"]: tags.append("评分变化")
            if change["etfs_added"] or change["etfs_removed"]: tags.append("ETF 格局变化")
            if change["evidence_gaps_added"] or change["evidence_gaps_closed"]: tags.append("证据缺口变化")
        items.append({"version":item["version"],"created_at":item["created_at"],"content_hash":item["content_hash"],"verdict":conclusion.get("verdict","insufficient"),"confidence":conclusion.get("confidence","low"),"conclusion":conclusion.get("statement",""),"scorecard":sections.get("scorecard") or [],"change_tags":tags,"change":change})
    return {"report_id":report_id,"versions":list(reversed(items))}

@app.get("/api/reports/{report_id}/compare")
def compare_report_versions(report_id:str, left:int=Query(ge=1), right:int=Query(ge=1)):
    store=_report_store(report_id)
    try: versions={item["version"]:item for item in store.report_versions(report_id)}
    finally: store.close()
    if left not in versions or right not in versions: raise HTTPException(404,"报告版本不存在")
    left_lines=set(versions[left]["markdown"].splitlines()); right_lines=set(versions[right]["markdown"].splitlines())
    return {"report_id":report_id,"left":left,"right":right,"structured":_version_change_payload(versions[left],versions[right]),"added":sorted(right_lines-left_lines),"removed":sorted(left_lines-right_lines),"unchanged_count":len(left_lines&right_lines)}

@app.patch("/api/reports/{report_id}")
def update_report_asset(report_id:str, request:ReportUpdateRequest):
    if request.title is None and request.status is None: raise HTTPException(422,"没有可更新字段")
    store = _report_store(report_id)
    try:
        report = store.update_report_asset(report_id,title=request.title,status=request.status,updated_at=utcnow())
    finally:
        store.close()
    if not report: raise HTTPException(404,"报告不存在或已经删除")
    return report

@app.delete("/api/reports/{report_id}")
def delete_report_asset(report_id:str):
    store = _report_store(report_id)
    try:
        deleted = store.soft_delete_report_asset(report_id,utcnow())
    finally:
        store.close()
    if not deleted: raise HTTPException(404,"报告不存在或已经删除")
    return {"report_id":report_id,"status":"deleted","recoverable":True}

THEME_LIBRARY_META = {
    "ai-infrastructure": ("AI 基础设施主题研究", "ai", ["AI", "数据中心", "ETF"]),
    "edge-ai-infrastructure": ("边缘 AI 基础设施主题研究", "ai", ["AI", "半导体", "边缘计算"]),
    "robotics": ("智能机器人主题研究", "robotics", ["机器人", "自动化"]),
    "semiconductors": ("半导体主题研究", "ai", ["半导体", "ETF"]),
}

def _register_theme_report(store:EvidenceStore, run_id:str, theme:str, result:dict) -> None:
    publication_gate = ((result.get("audit") or {}).get("publication_gate") or {})
    if not (result.get("audit") or {}).get("passed") or not publication_gate.get("passed"):
        failed = publication_gate.get("failed_checks") or (result.get("audit") or {}).get("errors") or ["unknown"]
        raise ValueError(f"报告未通过发布质量门槛：{', '.join(str(item) for item in failed)}")
    display_name=((result.get("theme_definition") or {}).get("name") or theme)
    title, folder, tags = THEME_LIBRARY_META.get(theme,(f"{display_name} 主题研究","ai",[display_name]))
    status = {"DEEP_RESEARCH":"deep_research","WATCH":"watch","REJECT":"completed"}.get(result.get("status"),"completed")
    brief = result.get("brief") or {}
    now = utcnow()
    report_id=f"theme-report:{theme}"
    existing = store.report_asset(report_id)
    version = int((existing or {}).get("version") or 0) + 1
    created_at = (existing or {}).get("created_at") or now
    summary = str((result.get("conclusion") or {}).get("statement") or "当前报告尚未形成可审计结论。")
    asset={
        "report_id":report_id,"run_id":run_id,"title":title,"kind":"theme_report","theme_id":theme,
        "folder_id":folder,"status":status,"tags":tags,"summary":summary,
        "updated_at":now,"created_at":created_at,"version":version,"source_count":brief.get("source_types",0),
        "evidence_count":result.get("selected",0),"audit_passed":bool((result.get("audit") or {}).get("passed")),
    }
    payload = {"asset":asset,"result":result,"change_reason":"用户核实后发布的主题研究版本"}
    claims = list(result.get("claims") or [])
    if existing:
        if not store.save_and_promote_report_version(
            report_id, version, payload, str(result.get("report_markdown") or ""), now, claims,
        ):
            raise ValueError("报告版本已存在，请刷新后重试")
    else:
        store.save_report_asset(asset)
        store.save_report_version(report_id,version,payload,str(result.get("report_markdown") or ""),now)
        for index, claim in enumerate(claims):
            store.save_report_claim(f"{report_id}:v{version}:c{index+1}",report_id,version,str(claim.get("text") or ""),str(claim.get("type") or "support"),[str(item) for item in claim.get("evidence_ids") or []],now)

@app.post("/api/research-runs",status_code=202)
def create_research_run(request:ResearchRequest):
    topic=(request.topic or request.theme or "").strip()
    if len(topic)<2: raise HTTPException(422,"研究主题至少需要两个字符")
    if request.output_type != "theme_report":
        raise HTTPException(422,"当前仅支持主题研究；快速扫描和 ETF 机会分析已停止创建")
    run_id=str(uuid4()); path=_db(request.database_path); store=EvidenceStore(path); created_at=utcnow()
    payload=request.model_dump()
    payload.update({
        "topic":topic,
        "objective":CORE_RESEARCH_OBJECTIVE,
        "sources":list(AUTO_RESEARCH_SOURCES),
        "time_range":"multi_horizon",
        "output_type":"theme_report",
        "source_selection":"automatic",
    })
    queue_status = store.enqueue_theme_research_run(
        run_id, request.theme or "pending", created_at, payload, database_path=path,
    )
    queued_run = store.research_run(run_id)
    store.close()
    registry=_store()
    try: registry.register_run(run_id,path,created_at)
    finally: registry.close()
    if queue_status == "planning":
        worker_for(path)
    return {"run_id":run_id,"status":queue_status,"queue_position":(queued_run or {}).get("queue_position"),"poll_url":f"/api/research-runs/{run_id}"}

@app.get("/api/research-runs")
def list_research_runs(limit:int=Query(default=20,ge=1,le=100), offset:int=Query(default=0,ge=0)):
    store = _store()
    try:
        runs, total = store.paginated_research_runs(limit=limit, offset=offset)
    finally:
        store.close()
    items = []
    attention = {"awaiting_theme_review", "awaiting_report_review", "returned", "blocked_configuration"}
    for run in runs:
        items.append({
            "run_id": run["run_id"], "topic": (run.get("request") or {}).get("topic") or run["theme_id"],
            "status": run["status"], "stage": run["stage"], "progress": run["progress"],
            "created_at": run["created_at"], "updated_at": run["updated_at"],
            "queue_position": run.get("queue_position"),
            "needs_attention": run["status"] in attention,
            "output_type": (run.get("request") or {}).get("output_type", "theme_report"),
        })
    return {"runs": items, "total": total, "limit": limit, "offset": offset, "has_more": offset + len(items) < total}
@app.get("/api/research-runs/{run_id}")
def get_research_run(run_id:str):
    item=_research_run_snapshot(run_id)
    if not item: raise HTTPException(404,"研究任务不存在")
    return item

def _research_run_snapshot(run_id:str) -> dict | None:
    store=_run_store(run_id)
    try:
        item=store.research_run(run_id)
        if not item: return None
        item["steps"]=store.run_steps(run_id); item["approvals"]=store.approvals(run_id)
        item["agent_runs"]=store.agent_runs(run_id); item["tool_calls"]=store.tool_calls(run_id)
        if item["stage"] == "collecting" and item["status"] in {"queued", "collecting"}:
            completed_calls = sum(call.get("status") != "running" for call in item["tool_calls"])
            item["progress"] = max(int(item.get("progress") or 0), min(44, 30 + completed_calls * 2))
        coverages = []
        for call in item["tool_calls"]:
            for value in (
                call.get("coverage_before"), call.get("coverage_after"),
                (call.get("result") or {}).get("coverage"),
            ):
                if isinstance(value, dict) and "evidence" in value:
                    coverages.append(value)
        baseline = int(coverages[0].get("evidence", 0)) if coverages else 0
        current = int(coverages[-1].get("evidence", baseline)) if coverages else baseline
        item["evidence_progress"] = {
            "baseline": baseline,
            "current": current,
            "raw_added": sum(int(call.get("evidence_delta") or 0) for call in item["tool_calls"]),
            "relevant_added": max(0, current - baseline),
        }
        item["queue_position"] = item.get("queue_position")
        item["needs_attention"] = item["status"] in {
            "awaiting_theme_review", "awaiting_report_review", "returned", "blocked_configuration",
        }
        agent = item["agent_runs"][-1] if item["agent_runs"] else {}
        finish_calls = [call for call in item["tool_calls"] if call.get("tool_name") == "finish_research"]
        finish_result = (finish_calls[-1].get("result") or {}) if finish_calls else {}
        item["audit_summary"] = {
            "researchObjective": (item.get("request") or {}).get("objective", "build_investment_thesis"),
            "coverage": item["evidence_progress"],
            "counterCheck": any(
                bool((call.get("arguments") or {}).get("counter_evidence"))
                or (call.get("arguments") or {}).get("purpose") == "counter"
                for call in item["tool_calls"]
            ),
            "remainingGaps": [
                str(value) for value in (
                    finish_result.get("remaining_gaps")
                    or (item.get("result") or {}).get("remaining_gaps")
                    or ((item.get("result") or {}).get("detail") or {}).get("counter", {}).get("missing_evidence")
                    or []
                )[:8]
            ],
            "stopReason": str(agent.get("stop_reason") or finish_result.get("stop_reason") or ""),
            "usage": {
                "modelRequests": sum(int(value.get("model_requests") or 0) for value in item["agent_runs"]),
                "toolCalls": len(item["tool_calls"]),
            },
        }
        item["stream_events"] = [
            {
                "id": int(call["tool_call_id"]),
                "kind": "tool_call",
                "name": str(call.get("tool_name") or ""),
                "status": str(call.get("status") or ""),
                "started_at": str(call.get("started_at") or ""),
                "finished_at": str(call.get("finished_at") or ""),
                "source": str((call.get("arguments") or {}).get("source") or ""),
                "evidence_delta": int(call.get("evidence_delta") or 0),
                "relevant_evidence_delta": int(call.get("relevant_evidence_delta") or 0),
                "latency_ms": int(call.get("latency_ms") or 0),
            }
            for call in item["tool_calls"][-20:]
        ]
        # Persisted snapshots expose structured outputs and audit records only.
        # Remove any accidental provider debug fields before SSE serialization.
        forbidden = {"chain_of_thought", "reasoning", "thought", "hidden_reasoning", "model_thoughts"}
        def scrub(value):
            if isinstance(value, dict):
                return {key: scrub(child) for key, child in value.items() if key.casefold() not in forbidden}
            if isinstance(value, list):
                return [scrub(child) for child in value]
            return value
        item = scrub(item)
        return item
    finally:
        store.close()

STREAM_PAUSE_STATES={"waiting","awaiting_theme_review","awaiting_report_review","completed","returned","cancelled","failed","blocked_configuration"}

async def research_run_events(run_id:str, poll_interval:float=.5, heartbeat_seconds:float=15):
    """Stream durable audit snapshots; never emits model chain-of-thought."""
    previous=""; last_sent=0.0; sequence=0
    loop=asyncio.get_running_loop()
    while True:
        item=_research_run_snapshot(run_id)
        if not item: return
        serialized=json.dumps(item,ensure_ascii=False,sort_keys=True,separators=(",",":"))
        now=loop.time()
        if serialized!=previous:
            sequence+=1; previous=serialized; last_sent=now
            yield f"id: {sequence}\nevent: run_snapshot\ndata: {serialized}\n\n"
            if item["status"] in STREAM_PAUSE_STATES: return
        elif now-last_sent>=heartbeat_seconds:
            last_sent=now
            yield ": keep-alive\n\n"
        await asyncio.sleep(poll_interval)

@app.get("/api/research-runs/{run_id}/stream")
def stream_research_run(run_id:str):
    if not _research_run_snapshot(run_id): raise HTTPException(404,"研究任务不存在")
    return StreamingResponse(
        research_run_events(run_id),media_type="text/event-stream",
        headers={"Cache-Control":"no-cache, no-transform","Connection":"keep-alive","X-Accel-Buffering":"no"},
    )

@app.post("/api/research-runs/{run_id}/theme-review")
def review_theme(run_id:str, request:ReviewRequest):
    path=_run_database_path(run_id); store=EvidenceStore(path); run=store.research_run(run_id)
    if not run or run["status"]!="awaiting_theme_review": store.close(); raise HTTPException(409,"当前不在主题复核阶段")
    if request.decision=="return":
        changed=store.transition_research_run(run_id,{"awaiting_theme_review"},status="returned",stage="theme_review",updated_at=utcnow(),result={**run["result"],"available_actions":["rerun"]},progress=12,review_gate="")
        promoted = None
    else:
        changed, promoted = store.requeue_research_run(
            run_id, {"awaiting_theme_review"}, stage_after_promotion="queued",
            updated_at=utcnow(), result={**run["result"],"available_actions":["cancel"]},
            progress=15, review_gate="", lease_owner="", lease_expires_at="", heartbeat_at="",
        )
    if not changed: store.close(); raise HTTPException(409,"主题复核状态已被其他操作更新")
    store.save_approval(run_id,"theme_definition",request.decision,request.note,utcnow())
    if request.decision=="approve": store.save_theme_definition(run["result"]["theme_definition"],utcnow(),confirmed=True)
    store.close()
    if request.decision=="approve" and promoted: worker_for(path)
    return get_research_run(run_id)

@app.post("/api/research-runs/{run_id}/report-review")
def review_report(run_id:str, request:ReviewRequest):
    store=_run_store(run_id); run=store.research_run(run_id)
    if not run or run["status"]!="awaiting_report_review": store.close(); raise HTTPException(409,"当前不在报告复核阶段")
    result={**run["result"]}
    if request.decision == "approve":
        gate = ((result.get("audit") or {}).get("publication_gate") or {})
        if not (result.get("audit") or {}).get("passed") or not gate.get("passed"):
            failed = gate.get("failed_checks") or (result.get("audit") or {}).get("errors") or ["报告结构或引用审计未通过"]
            store.close()
            raise HTTPException(409, {"message":"报告未通过发布质量门槛，只能要求补充研究","failed_checks":failed})
    if request.decision=="return":
        result["available_actions"]=["rerun"]
        changed=store.transition_research_run(run_id,{"awaiting_report_review"},status="returned",stage="report_review",updated_at=utcnow(),result=result,progress=92,review_gate="")
    else:
        result["available_actions"]=["archive"]
        changed, promoted = store.transition_and_promote(
            run_id, {"awaiting_report_review"}, promote=True,
            status="completed", stage="completed", updated_at=utcnow(),
            result=result, progress=100, review_gate="",
        )
    if not changed: store.close(); raise HTTPException(409,"报告复核状态已被其他操作更新")
    store.save_approval(run_id,"final_report",request.decision,request.note,utcnow())
    if request.decision=="approve":
        definition=result.get("theme_definition") or {}; _register_theme_report(store,run_id,definition.get("theme_id",run["theme_id"]),result)
    store.close()
    if request.decision=="approve" and promoted:
        worker_for(_run_database_path(promoted))
    return get_research_run(run_id)

@app.post("/api/research-runs/{run_id}/rerun")
def rerun_research(run_id:str):
    path=_run_database_path(run_id); store=EvidenceStore(path); run=store.research_run(run_id)
    if not run or run["status"]!="returned": store.close(); raise HTTPException(409,"只有已退回任务可以重跑")
    next_attempt=int(run["attempt"])+1
    if run["stage"]=="theme_review":
        resume_stage, result, progress = "planning", {}, 0
    else:
        resume_stage, result, progress = "queued", run["result"], 15
    changed, promoted = store.requeue_research_run(
        run_id, {"returned"}, stage_after_promotion=resume_stage,
        updated_at=utcnow(), result=result, progress=progress, review_gate="",
        attempt=next_attempt, lease_owner="", lease_expires_at="", heartbeat_at="",
    )
    store.close()
    if not changed: raise HTTPException(409,"任务已被其他操作更新")
    if promoted: worker_for(path)
    current = get_research_run(run_id)
    return {"run_id":run_id,"status":current["status"],"queue_position":current.get("queue_position")}

@app.post("/api/research-runs/{run_id}/cancel")
def cancel_research(run_id:str):
    store=_run_store(run_id); run=store.research_run(run_id)
    if not run or run["status"] in {"completed","failed","cancelled"}: store.close(); raise HTTPException(409,"任务不可取消")
    releases_slot = run["status"] in RESEARCH_EXECUTION_STATUSES
    changed, promoted = store.transition_and_promote(
        run_id, {run["status"]}, promote=releases_slot,
        status="cancelled", stage="cancelled", updated_at=utcnow(), result=run["result"],
        error="用户取消任务", review_gate="", lease_owner="", lease_expires_at="",
        heartbeat_at="", queue_position=None,
    )
    store.close()
    if not changed: raise HTTPException(409,"任务已被其他操作更新")
    if promoted:
        worker_for(_run_database_path(promoted))
    return {"run_id":run_id,"status":"cancelled"}

@app.post("/api/research-runs/{run_id}/finish")
def finish_returned_research(run_id: str):
    """Explicitly close a returned run so the waiting slot can advance."""
    store = _run_store(run_id)
    run = store.research_run(run_id)
    if not run or run["status"] != "returned":
        store.close()
        raise HTTPException(409, "只有已退回任务可以结束")
    result = {**run["result"], "available_actions": []}
    changed, promoted = store.transition_and_promote(
        run_id, {"returned"}, promote=True, status="cancelled", stage="closed",
        updated_at=utcnow(), result=result, error="用户结束已退回任务",
        review_gate="", lease_owner="", lease_expires_at="", heartbeat_at="",
    )
    store.close()
    if not changed:
        raise HTTPException(409, "任务已被其他操作更新")
    if promoted:
        worker_for(_run_database_path(promoted))
    return {"run_id": run_id, "status": "cancelled", "promoted_run_id": promoted}
@app.get("/api/research-runs/{run_id}/report")
def get_research_report(run_id:str):
    store=_run_store(run_id)
    try: item=store.research_run(run_id)
    finally: store.close()
    if not item: raise HTTPException(404,"研究任务不存在")
    if item["status"]!="completed": raise HTTPException(409,"报告尚未生成")
    return {"run_id":run_id,"markdown":item["result"].get("report_markdown"),"brief":item["result"].get("brief"),"audit":item["result"].get("audit")}

@app.post("/api/event-research-runs", status_code=202)
def create_event_research_run(request: EventResearchRequest):
    raise HTTPException(410,"事件研究输出已停止创建；资讯证据仅作为主题研究的辅助输入")
    # Legacy implementation is intentionally retained below for read compatibility
    # and migration reference, but cannot be reached by new API requests.
    evidence_store = _store(request.database_path)
    try:
        if not any(item["event_id"] == request.evidence_id for item in evidence_store.events()):
            raise HTTPException(404, "证据不存在")
    finally: evidence_store.close()
    run_id=str(uuid4()); path=_db(request.database_path); created_at=utcnow(); store=EvidenceStore(path)
    store.create_event_research_run(run_id,request.evidence_id,created_at,database_path=path); store.close()
    registry=_store()
    try: registry.register_run(run_id,path,created_at)
    finally: registry.close()
    worker_for(path)
    return {"run_id": run_id, "status": "queued", "poll_url": f"/api/event-research-runs/{run_id}"}

@app.get("/api/event-research-runs/{run_id}")
def get_event_research_run(run_id: str):
    store=_run_store(run_id)
    try: item=store.research_run(run_id)
    finally: store.close()
    if not item or not item["theme_id"].startswith("event:"): raise HTTPException(404, "事件研究任务不存在")
    return item

@app.get("/api/event-research-runs/{run_id}/report")
def get_event_research_report(run_id: str):
    item = get_event_research_run(run_id)
    if item["status"] != "completed": raise HTTPException(409, "报告尚未生成")
    return {"run_id": run_id, "markdown": item["result"].get("markdown"), "fact_pack": item["result"].get("fact_pack"), "audit": item["result"].get("audit")}
