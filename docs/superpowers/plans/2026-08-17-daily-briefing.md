# 每日简报资产与首页 API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将治理后 publishable 证据冻结为每日简报资产，并通过 v16 首页 API 提供下钻与异常统计。

**Architecture:** `reports.py` 负责纯确定性快照构建与 Markdown 渲染；`EvidenceStore` 负责短事务持久化；`SyncDiscoveryWorker` 在同步完成后创建当天资产；首页仅从已持久化快照读取并筛选。质量不合格的事件只计入异常聚合，绝不进入简报事件。

**Tech Stack:** Python 3、SQLite、FastAPI、pytest、PowerShell 启动器。

## Global Constraints

- 每日简报正文和下钻事实只能来自 `content_quality_results.status = 'publishable'` 的证据。
- 产业链位置只能取 `extracted_facts.status = 'audited'`，缺失值固定为 `unknown`。
- `GET /api/dashboard` 必须保持只读，缺少资产时返回稳定空结构。
- 将公开服务契约从 `2026-08-14.v15` 升至 `2026-08-17.v16`，同步 API、启动器、契约测试和用户文档。
- 本任务按用户要求不执行 pytest 或 E2E；仅提供指定测试清单。
- 不改动未跟踪的 `.superpowers/`、`data/`。

---

### Task 1: 每日简报模型与持久化

**Files:**
- Modify: `etf_theme_radar/store.py`
- Modify: `etf_theme_radar/reports.py`
- Create: `tests/test_daily_briefing.py`

**Interfaces:**
- Consumes: `EvidenceStore.publishable_events()`, `EvidenceStore.extracted_fact(event_id)`。
- Produces: `build_daily_briefing(store, as_of_date, generated_at) -> dict`、`EvidenceStore.save_daily_briefing_asset(asset) -> dict`、`EvidenceStore.latest_daily_briefing_asset() -> dict | None`。

- [ ] **Step 1: Write the failing test**

```python
def test_daily_briefing_persists_only_publishable_facts(tmp_path):
    store = EvidenceStore(tmp_path / "briefing.db")
    # Save one publishable and one rejected event, then audited chain data.
    asset = build_daily_briefing(store, "2026-08-17", "2026-08-17T08:00:00+00:00")
    saved = store.save_daily_briefing_asset(asset)
    assert [item["evidence_id"] for item in saved["payload"]["events"]] == ["publishable-event"]
    assert saved["payload"]["events"][0]["industry_chain"] == "upstream"
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_daily_briefing.py -q`

Expected: FAIL because the daily briefing builder and storage methods do not exist.

- [ ] **Step 3: Write minimal implementation**

```python
def build_daily_briefing(store, as_of_date, generated_at):
    events = [_briefing_event(store, event) for event in store.publishable_events()]
    return {"briefing_id": f"daily-briefing:{as_of_date}", "as_of_date": as_of_date,
            "generated_at": generated_at, "payload": {"events": events}}
```

Add `daily_briefing_assets` with a unique `as_of_date`; save the JSON payload and sorted evidence IDs in a single `BEGIN IMMEDIATE` transaction.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_daily_briefing.py -q`

Expected: PASS.

### Task 2: 首页下钻与异常统计

**Files:**
- Modify: `etf_theme_radar/api.py`
- Modify: `tests/test_daily_briefing.py`
- Modify: `tests/test_api_contracts.py`

**Interfaces:**
- Consumes: `EvidenceStore.latest_daily_briefing_asset()` and `EvidenceStore.daily_briefing_exception_stats()`.
- Produces: `GET /api/dashboard?theme=&industry_chain=&source=` with `briefing`, `events`, `facets`, `exceptions`, `metrics`, `runs`, and `generatedAt`.

- [ ] **Step 1: Write the failing tests**

```python
def test_dashboard_intersects_all_three_drilldowns_and_keeps_exceptions_aggregated(...):
    response = client.get("/api/dashboard", params={"theme": "robotics", "industry_chain": "upstream", "source": "sec"})
    assert [item["evidence_id"] for item in response.json()["events"]] == ["e-1"]
    assert response.json()["exceptions"]["quality_statuses"] == {"rejected": 1}

def test_dashboard_without_asset_is_a_read_only_empty_brief(...):
    assert client.get("/api/dashboard").json()["briefing"]["status"] == "not_available"
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_daily_briefing.py tests/test_api_contracts.py -q`

Expected: FAIL because the response has neither asset data nor drilldown fields.

- [ ] **Step 3: Write minimal implementation**

Implement query parameters and a local filter over the frozen asset events. Build themes, industry-chain positions and sources facets from the unfiltered asset; calculate quality exceptions by SQL aggregation and health exceptions from the latest row per connector. Return no event details for non-publishable records.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_daily_briefing.py tests/test_api_contracts.py -q`

Expected: PASS.

### Task 3: 同步生成、v16 契约与文档

**Files:**
- Modify: `etf_theme_radar/sync_worker.py`
- Modify: `etf_theme_radar/api.py`
- Modify: `tools/start_local.ps1`
- Modify: `tests/test_api_contracts.py`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/architecture.md`
- Modify: `docs/data-dictionary.md`
- Modify: `docs/runbook.md`
- Modify: `progress.md`

**Interfaces:**
- Consumes: completed normal sync in `SyncDiscoveryWorker._run_sync` and `build_daily_briefing`.
- Produces: v16 worker-created same-day asset and synchronized public contract documentation.

- [ ] **Step 1: Write the failing tests**

```python
def test_sync_completion_creates_today_daily_briefing_asset(...):
    # Complete a fixture-backed sync and assert latest_daily_briefing_asset exists.
    assert store.latest_daily_briefing_asset()["as_of_date"] == "2026-08-17"

def test_contract_snapshot_exports_v16_daily_briefing_table_and_dashboard_route():
    snapshot = build_snapshot()
    assert snapshot["contract_version"] == "2026-08-17.v16"
    assert "daily_briefing_assets" in snapshot["database_tables"]
    assert ["GET", "/api/dashboard"] in snapshot["api_routes"]
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_daily_briefing.py tests/test_api_contracts.py -q`

Expected: FAIL because v15 is still exported and sync completion does not create an asset.

- [ ] **Step 3: Write minimal implementation and documentation**

Call the deterministic builder only after successful governed sync completion, update API and launcher to v16, then document the new table, generation timing, read-only empty response, parameters and designated regression command.

- [ ] **Step 4: Static review and handoff**

Run only read-only checks: `git diff --check`, `git diff --name-only`, `git status --short`, and inspect the exact changed sections. Do not run pytest/E2E. Report the external regression command and document that it was intentionally not executed.

- [ ] **Step 5: Commit**

```powershell
git add etf_theme_radar tests tools README.md AGENTS.md docs progress.md
git commit -m "feat(briefing): add daily asset dashboard"
```

