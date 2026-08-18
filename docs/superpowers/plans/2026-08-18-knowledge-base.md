# Personal Knowledge Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提供默认私有、可确认共享且能安全进入研究上下文的个人知识库。

**Architecture:** SQLite 保存版本化元数据、授权和分块，受控本地目录保存带哈希的原文件。单一权限服务在查询、检索和上下文组装前过滤；FastAPI 将写入拆为预览和单次确认，Next.js 仅通过授权资源渲染方案 C。

**Tech Stack:** Python 3.11、SQLite、FastAPI/Pydantic、pytest、Next.js/TypeScript、Playwright。

**Spec:** `docs/superpowers/specs/2026-08-18-knowledge-base-design.md`

## Global Constraints

- API 仍是单实例，数据库和知识文件目录只可位于本地磁盘；不暴露 8001、3000 或 SQLite。
- 受控文件根为 `KNOWLEDGE_FILES_DIR` 或 `data/knowledge-files`，永不接受客户端路径。
- 权限先于检索、排序、计数、标题投影和 token 预算；拒绝项不泄漏任何元数据。
- 正式报告、三个独立评分和结论不得读取个人知识库作为写入输入。
- 所有写 API 使用幂等键和 pending-confirmation，前端不自动重放。
- 新公开 API 将契约提升为 `2026-08-18.v18`，同步 `api.py`、`tools/start_local.ps1`、契约测试和运行手册。
- 保留未跟踪的 `.superpowers/`、`data/`，不纳入提交。

---

### Task 1: Versioned storage and safe files

**Files:**

- Create: `tests/test_knowledge_base.py`
- Create: `etf_theme_radar/knowledge_base.py`
- Modify: `etf_theme_radar/store.py`

**Interfaces:**

- Produces `KnowledgeBase.create_item(*, item_id, owner_user_id, kind, title, content, filename, mime_type, theme_id, folder_id, created_at) -> dict`.
- Produces `KnowledgeBase.replace_content(*, item_id, owner_user_id, content, filename, mime_type, created_at) -> dict` and `KnowledgeBase.soft_delete(...) -> dict`, `restore(...) -> dict`.
- Produces store records from `knowledge_item`, `knowledge_item_versions` and `knowledge_folders`.

- [ ] **Step 1: Write failing storage tests.** Add tests that create a note and upload, assert the version hash and controlled relative file path, replace it into version 2, reject `../escape.txt`, soft-delete and restore, and report a missing physical file without returning content.
- [ ] **Step 2: Run the storage tests red.** Run `python -m pytest tests/test_knowledge_base.py -q`; expect import/API failure because `KnowledgeBase` does not exist.
- [ ] **Step 3: Add storage schema and minimal implementation.** Add immutable item-version and folder tables; implement SHA-256 write/read, version allocation, owner-scoped folder entry, soft delete and restore without changing old versions.
- [ ] **Step 4: Run storage tests green.** Run `python -m pytest tests/test_knowledge_base.py -q`; expect PASS.
- [ ] **Step 5: Commit.** `git add etf_theme_radar/store.py etf_theme_radar/knowledge_base.py tests/test_knowledge_base.py && git commit -m "feat(knowledge): add versioned private storage"`.

### Task 2: ACL, pending confirmation and authorized retrieval

**Files:**

- Create: `tests/test_knowledge_permissions.py`
- Create: `tests/test_knowledge_retrieval.py`
- Create: `etf_theme_radar/knowledge_permissions.py`
- Create: `etf_theme_radar/knowledge_retrieval.py`
- Modify: `etf_theme_radar/store.py`

**Interfaces:**

- Produces `KnowledgePermissions.visible_items(user_id, *, query, theme_id, collection) -> list[dict]` and `can_read(item_id, user_id) -> bool`.
- Produces `KnowledgeRetrieval.search(*, user_id, query, theme_id, token_budget) -> list[dict]`.
- Produces `create_knowledge_confirmation(...) -> dict`, `confirm_knowledge_operation(...) -> dict` for share, revoke, move, delete and restore.

- [ ] **Step 1: Write failing permission tests.** Cover private owner visibility, member share, team share, revoke immediate denial, foreign direct read denial, and verify an excluded title/ID never appears in search output or token accounting.
- [ ] **Step 2: Run permission tests red.** Run `python -m pytest tests/test_knowledge_permissions.py tests/test_knowledge_retrieval.py -q`; expect missing ACL/retrieval APIs.
- [ ] **Step 3: Implement a shared ACL SQL predicate.** Add `knowledge_shares` and `pending_operations`; use the predicate in list, get, search and chunks before projection; bind confirmation to owner, action, current version and expiration.
- [ ] **Step 4: Add deterministic chunk retrieval.** Persist chunks containing current-version text, source kind, page number and character range; rank only authorized active chunks by theme, recency, kind and text match.
- [ ] **Step 5: Run ACL/retrieval tests green.** Run the same pytest command; expect PASS.
- [ ] **Step 6: Commit.** `git add etf_theme_radar/store.py etf_theme_radar/knowledge_permissions.py etf_theme_radar/knowledge_retrieval.py tests/test_knowledge_permissions.py tests/test_knowledge_retrieval.py && git commit -m "feat(knowledge): enforce permission-first retrieval"`.

### Task 3: Parse frozen documents and connect research context

**Files:**

- Modify: `tests/test_knowledge_base.py`
- Modify: `tests/test_context_builder.py`
- Modify: `etf_theme_radar/knowledge_base.py`
- Modify: `etf_theme_radar/context_builder.py`

**Interfaces:**

- Produces `parse_version(*, item_id, version) -> list[dict]` with `page_number`, `char_start`, `char_end`, `source_type` and text.
- Produces `research_knowledge_context(*, user_id, theme_id, query, token_budget) -> list[dict]` consumed by `build_research_context(..., knowledge=...)`.

- [ ] **Step 1: Write failing parser/context tests.** Exercise note, meeting material, ETF profile, conversation excerpt and saved reference; assert page or character positions survive chunking and a privately sourced snippet is labelled internal and is downstream of evidence/ETF layers.
- [ ] **Step 2: Run parser/context tests red.** Run `python -m pytest tests/test_knowledge_base.py tests/test_context_builder.py -q`; expect parsing/context integration failure.
- [ ] **Step 3: Implement bounded parsers and adapters.** Support text, Markdown, JSON, HTML, PDF and DOCX where available; reject unsupported MIME types into a visible parse-failed state; chunk only frozen version text and retrieve it through the ACL service.
- [ ] **Step 4: Preserve the trust boundary.** Ensure `build_research_context` accepts only authorised retrieval output, adds `internal_material=True`, and does not alter score/summary/report persistence paths.
- [ ] **Step 5: Run parser/context tests green.** Run the same pytest command; expect PASS.
- [ ] **Step 6: Commit.** `git add etf_theme_radar/knowledge_base.py etf_theme_radar/context_builder.py tests/test_knowledge_base.py tests/test_context_builder.py && git commit -m "feat(knowledge): add parsed research context"`.

### Task 4: API contract and confirmation flow

**Files:**

- Modify: `tests/test_api_contracts.py`
- Modify: `tests/test_knowledge_base.py`
- Modify: `etf_theme_radar/api.py`
- Modify: `tools/start_local.ps1`
- Modify: `README.md`
- Modify: `docs/runbook.md`

**Interfaces:**

- Adds `GET/POST /api/knowledge`, `GET /api/knowledge/{item_id}`, `POST /api/knowledge/{item_id}/operations/preview`, and `POST /api/knowledge/operations/{operation_id}/confirm`.
- Request models require `idempotency_key`; list/get/search responses are already permission-filtered.

- [ ] **Step 1: Write failing API contract tests.** Assert v18 from health, capabilities and launcher-export paths; assert a foreign user receives 404; assert share/move/delete do not change state until a matching confirmation token is confirmed and cannot be replayed.
- [ ] **Step 2: Run API tests red.** Run `python -m pytest tests/test_api_contracts.py tests/test_knowledge_base.py -q`; expect 404/missing v18 fields.
- [ ] **Step 3: Implement request models and routes.** Derive owner from `_request_user_id`, enforce idempotency and confirmation, convert access denial to 404, and bump API/launcher contract versions together.
- [ ] **Step 4: Run API tests green.** Run the same pytest command; expect PASS.
- [ ] **Step 5: Commit.** `git add etf_theme_radar/api.py tools/start_local.ps1 tests/test_api_contracts.py tests/test_knowledge_base.py README.md docs/runbook.md && git commit -m "feat(knowledge): expose confirmed knowledge APIs"`.

### Task 5: Scheme-C knowledge library UI

**Files:**

- Create: `frontend/src/app/knowledge/page.tsx`
- Create: `frontend/src/lib/knowledge-base.ts`
- Create: `frontend/src/services/knowledge-base-gateway.ts`
- Create: `frontend/src/components/knowledge-base-workspace.tsx`
- Create: `frontend/e2e/knowledge-base.spec.ts`
- Modify: `frontend/src/components/app-shell.tsx`
- Modify: `frontend/src/components/research-workspace.tsx`
- Modify: `frontend/README.md`

**Interfaces:**

- Produces `KnowledgeBaseGateway.list`, `get`, `previewOperation`, and `confirmOperation`.
- The workspace has folders and smart collections: recent, theme-related, shared and deleted.

- [ ] **Step 1: Write failing Playwright tests.** Mock the knowledge API and assert the default privacy badge, only authorised results, and that share/move/delete produce a preview dialog before a single confirmation request; assert a failed write never triggers a retry.
- [ ] **Step 2: Run UI test red.** Run `cd frontend; npm.cmd run test:e2e -- knowledge-base.spec.ts`; expect route/component missing.
- [ ] **Step 3: Implement typed gateway and workspace.** Add `/knowledge`, navigation, folders, smart collections, search and the confirmation dialog; keep `/reports` for formal reports and change research completion link to `/knowledge` only for personal saved material.
- [ ] **Step 4: Run UI test green and lint.** Run `cd frontend; npm.cmd run test:e2e -- knowledge-base.spec.ts` and `npm.cmd run lint`; expect PASS and no TypeScript errors.
- [ ] **Step 5: Commit.** `git add frontend && git commit -m "feat(knowledge): add private library workspace"`.

### Task 6: Backup/restore, documentation and full verification

**Files:**

- Modify: `tests/test_production_deployment.py`
- Modify: `tools/backup_sqlite.py`
- Modify: `tools/restore_sqlite.py`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/architecture.md`
- Modify: `docs/data-dictionary.md`
- Modify: `docs/runbook.md`
- Modify: `progress.md`

**Interfaces:**

- `create_backup(source, destination_dir, knowledge_dir=...) -> Path` creates SQLite backup, files snapshot and manifest.
- `restore_backup(backup, target, confirmation, knowledge_backup_dir=..., knowledge_target_dir=...) -> None` requires exact target confirmation and validates manifest hashes.

- [ ] **Step 1: Write failing backup tests.** Create a database and versioned knowledge file, back both up, restore into an independent target, then assert content hash, version, ACL row and chunk count match; assert a bad manifest or unmatched confirmation fails without overwriting target.
- [ ] **Step 2: Run backup tests red.** Run `python -m pytest tests/test_production_deployment.py -q`; expect missing knowledge snapshot support.
- [ ] **Step 3: Implement manifest-backed file snapshot and restore.** Copy only files addressed by active/soft-deleted versions to a temporary sibling, hash every entry, atomically publish it, and verify the restored set before replacing the explicit target.
- [ ] **Step 4: Update operational documents.** Document local-only paths, API-stop recovery, independent restore drill, v18 contract and personal-material research boundary; mark phase 4 only after fresh evidence.
- [ ] **Step 5: Run final verification.** Run `python -m pytest -q`, `cd frontend; npm.cmd run lint`, `cd frontend; npm.cmd run test:e2e`, and the independent backup/restore test; record actual results and any environment-only warnings.
- [ ] **Step 6: Commit.** `git add AGENTS.md README.md docs progress.md tools tests && git commit -m "feat(knowledge): verify private library backup recovery"`.
