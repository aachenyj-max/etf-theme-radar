# 阶段 5导航迁移与生产验收 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成旧入口迁移、受权全局搜索、单实例生产部署与阶段 5 验收，不开始阶段 6。

**Architecture:** 前端删除旧入口而不删除底层证据 API，个人旧保存内容通过可审计迁移进入版本化知识库，正式主题报告继续只读地存在规范版本链。v19 搜索先运行 ACL 再对各受权域排序；生产把 API 和持久 Worker 拆为单实例服务，由 Caddy 唯一对外暴露。

**Tech Stack:** Python、SQLite、FastAPI、pytest、Next.js、TypeScript、Playwright、Docker Compose、Caddy。

**Spec:** `docs/superpowers/specs/2026-08-18-phase5-navigation-production-design.md`

## Global Constraints

- 保留底层证据 API、主题详情时间线和报告来源按钮；不恢复证据浏览器页面。
- 正式主题报告只能保留在主题详情的规范版本链；旧个人保存内容迁移必须按用户和旧 ID 幂等、可审计。
- 知识库 ACL 必须早于搜索、排序、计数、标题投影和结果截断，拒绝项不得泄漏。
- API/Worker 一律单实例，SQLite 和知识文件只能在本地磁盘；默认仅 `127.0.0.1:8080`，绝不暴露 8001、3000 或数据库。
- 所有公开 API/schema 变更同时更新 `api.py`、`tools/start_local.ps1`、契约测试、README、AGENTS、架构、数据字典、运行手册和 `progress.md`；本阶段为 v19。
- 写操作不自动重放；保留未跟踪的 `.superpowers/` 与 `data/`，不纳入提交。

### Task 1: Retire evidence and product-studio entry points

**Files:**
- Modify: `frontend/src/components/app-shell.tsx`, `frontend/src/app/evidence/page.tsx`, `frontend/src/app/product-studio/page.tsx`
- Delete: `frontend/src/components/evidence-explorer-workspace.tsx`, `frontend/src/services/evidence-explorer-gateway.ts`, `frontend/src/lib/evidence-explorer.ts`
- Test: `frontend/e2e/navigation-migration.spec.ts`

- [x] Write an E2E test that asserts the navigation contains neither old entry, `/evidence` returns a migration-safe 404, `/product-studio` is explicitly read-only, and a theme-detail evidence timeline remains visible.
- [x] Run `cd frontend; npm.cmd run test:e2e -- navigation-migration.spec.ts` and observe the old navigation test fail.
- [x] Remove the old UI and replace only the stale routes with the defined compatibility responses.
- [x] Re-run the E2E test and `npm.cmd run lint`.

### Task 2: Migrate personal saves and constrain formal reports

**Files:**
- Modify: `etf_theme_radar/store.py`, `etf_theme_radar/knowledge_base.py`, `etf_theme_radar/api.py`
- Test: `tests/test_report_library.py`, `tests/test_api_contracts.py`

- [x] Write tests that migrate a legacy personal save twice for one owner, assert one knowledge item plus one audit record, and assert a `theme_report` is never migrated and remains readable through its canonical report detail route.
- [x] Run `python -m pytest tests/test_report_library.py tests/test_api_contracts.py -q` and observe the migration test fail.
- [x] Add append-only migration audit storage and owner-scoped migration service; make `/reports` a canonical read-only report listing without personal-save actions.
- [x] Re-run the focused tests.

### Task 3: Add permission-first v19 cross-domain search

**Files:**
- Modify: `etf_theme_radar/api.py`, `frontend/src/components/app-shell.tsx`, `tools/start_local.ps1`
- Test: `tests/test_api_contracts.py`, `tests/test_knowledge_permissions.py`, `frontend/e2e/navigation-migration.spec.ts`

- [x] Write tests that seed matching theme, briefing, ETF, conversation and two knowledge entries, then assert only the authorized knowledge title is returned and there are no evidence/report-library URLs.
- [x] Run the targeted pytest command and observe the v18 search schema test fail.
- [x] Implement user-aware aggregation that calls `KnowledgePermissions` before matching or rendering knowledge metadata; update v19 in API, launcher and contract export expectations.
- [x] Re-run focused pytest/E2E tests and lint.

### Task 4: Production Compose single-worker design and recovery

**Files:**
- Modify: `compose.production.yml`, `compose.public.yml`, `Dockerfile`, `etf_theme_radar/api.py`, `tools/backup_sqlite.py`, `tools/restore_sqlite.py`
- Test: `tests/test_production_deployment.py`

- [x] Write tests that require a distinct single Worker service, prohibit host mappings for API/Worker/Next.js, require loopback-only default Caddy, and prove a database-plus-knowledge restore drill preserves content hashes.
- [x] Run `python -m pytest tests/test_production_deployment.py -q` and observe the deployment expectations fail.
- [x] Make Compose run API without embedded workers and add the separate singleton worker command; preserve health checks, authentication/CORS/CSRF configuration, immutable audit logs, backup manifest and exact-target recovery guards.
- [x] Re-run the deployment test.

### Task 5: Documentation, operational acceptance and release

**Files:**
- Modify: `AGENTS.md`, `README.md`, `frontend/README.md`, `docs/architecture.md`, `docs/data-dictionary.md`, `docs/deployment.md`, `docs/runbook.md`, `progress.md`
- Test: all pytest, frontend lint/E2E/build, backup/restore command drill

- [x] Add the final failing or contract tests for source degradation, empty ETF writes, SSE fallback, worker recovery, lock retry, cancellation and summary rebuild to their existing suites.
- [x] Run each focused failure test before minimal implementation where behavior is absent; run every affected focused suite green.
- [x] Update the documents with v19, navigation migration, read-only compatibility, production topology, five-user HTTPS controls, backup/restore drill and known external-source gaps.
- [x] Run `python -m pytest -q`, `cd frontend; npm.cmd run lint`, `npm.cmd run test:e2e`, `npm.cmd run build`, and the independent backup/restore drill; record exact results in `progress.md`.
- [x] Inspect `git diff`, ensure `.superpowers/` and `data/` are unstaged, then create one `chore: complete agent radar migration` commit.
