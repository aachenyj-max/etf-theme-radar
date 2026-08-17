# 信息 Agent v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让每日、事件和既有后台信息 Goal 通过持久 Worker 执行受限规划、反方检查和缺口汇总。

**Architecture:** 新模块负责 Goal 载荷校验、稳定幂等创建、可审计的规划循环和安全结果。同步 Worker 只领取 `information_collection` Goal，并在阶段边界持久化状态、心跳、取消和失败；不改变公开 API 或数据库表。

**Tech Stack:** Python 3、SQLite、PydanticAI、pytest。

## Global Constraints

- 不新增公开 API、SQLite 应用表或服务契约；契约保持 `2026-08-14.v15`、45 表。
- 只实施阶段 3 / 任务 3.1，不提前实施阶段 3.2+ 或阶段 4。
- 支持性采集依据治理后 `publishable` 有效增量停止；结束前必须有一次反方检查和缺口汇总。
- 用户要求本对话不运行测试；测试先写入，但仅交付命令清单。
- 不修改未跟踪的 `.superpowers/` 或 `data/`。

---

### Task 1: Information Agent runtime

**Files:**

- Create: `tests/test_info_agent.py`
- Create: `etf_theme_radar/info_agent.py`
- Create: `etf_theme_radar/prompts/info_agent.md`

**Interfaces:**

- Consumes: `EvidenceStore.create_agent_goal`, `EvidenceStore.events`, `content_quality_results` 和 `agent_runtime` 的审计约束。
- Produces: `create_information_goal(...) -> dict`、`run_information_goal(store, goal, owner) -> dict`、`information_agent_prompt() -> str`。

- [ ] Write failing tests for prompt versioning, Goal idempotency, effective-delta stopping, counter search and cancellation.
- [ ] Do not run RED tests; record `python -m pytest tests/test_info_agent.py -q` for external verification.
- [ ] Implement the minimal deterministic runtime and formal prompt.
- [ ] Do not run GREEN tests; leave them for external verification.

### Task 2: Persistent Worker dispatch

**Files:**

- Modify: `etf_theme_radar/sync_worker.py`
- Modify: `tests/test_info_agent.py`

**Interfaces:**

- Consumes: `AgentGoalRuntime.claim("background", ...)` and `run_information_goal`.
- Produces: `SyncDiscoveryWorker.run_once()` handling one claimed information Goal before source sync/discovery work.

- [ ] Write failing worker-dispatch and cancellation tests.
- [ ] Do not run RED tests; record `python -m pytest tests/test_info_agent.py tests/test_agent_runtime.py -q`.
- [ ] Implement Goal claim, heartbeat, cancellation and terminal dispatch.
- [ ] Do not run GREEN tests; leave them for external verification.

### Task 3: Documentation and handoff

**Files:**

- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/architecture.md`
- Modify: `docs/runbook.md`
- Modify: `progress.md`

- [ ] Document the information Goal boundary, prompt versioning, governed effective increments, mandatory counter check and durable Worker ownership.
- [ ] Keep Task 3.1 unchecked and do not append a verified completion row until external tests provide evidence.
- [ ] Review changed files and commit `feat(info): add bounded information agent`.
