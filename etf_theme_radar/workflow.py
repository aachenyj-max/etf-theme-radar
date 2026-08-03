from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from .agent_runtime import analysis_llm_config, generate_theme_definition, run_research_agent
from .models import utcnow
from .ontology import refresh_research_assets
from .store import EvidenceStore
from .output_modes import run_research_output
from .event_research import run_event_deep_dive
from .etf_market import collect_market_snapshot, minimum_verified_etfs
from .etf_discovery import discover_global_etfs
from .theme_research import _llm_conclusion

THEME_ALIASES = {
    "AI 基础设施": ["ai infrastructure", "data center", "gpu cluster", "compute cluster"],
    "机器人": ["robotics", "robotic", "humanoid", "industrial robot"],
    "核能": ["nuclear energy", "nuclear power", "small modular reactor", "smr"],
    "半导体": ["semiconductor", "chip", "wafer", "foundry"],
}


def slugify(value: str) -> str:
    ascii_words = re.findall(r"[a-z0-9]+", value.casefold())
    if ascii_words:
        return "-".join(ascii_words)[:80]
    return "theme-" + __import__("hashlib").sha256(value.encode("utf-8")).hexdigest()[:12]


def _model_theme_definition(topic: str, objective: str) -> dict | None:
    return generate_theme_definition(topic, objective)


def build_theme_definition(topic: str, objective: str) -> dict:
    topic = topic.strip()
    generated = _model_theme_definition(topic, objective)
    aliases = THEME_ALIASES.get(topic, [])
    definition = generated or {
        "name": topic,
        "description": f"围绕“{topic}”的技术、产业采用和可投资证据进行可审计研究。",
        "aliases": aliases,
        "include_terms": aliases or [topic],
        "exclude_terms": [],
        "research_questions": ["是否存在跨来源的持续活动？", "商业采用和可投资公司证据是否充分？", "哪些证据会否定当前主题假设？"],
    }
    definition["theme_id"] = slugify(str(definition.get("name") or topic))
    definition["model_used"] = bool(generated)
    return definition


def _audit_call(store: EvidenceStore, run: dict, tool_name: str, arguments: dict, action):
    """Audit non-agent model work with the same durable tool-call contract."""
    call_uid = f"{run['run_id']}:{run['attempt']}:{tool_name}"
    existing = store.tool_call_by_uid(run["run_id"], call_uid)
    if existing and existing["status"] == "succeeded" and "value" in existing["result"]:
        return existing["result"]["value"]
    started = utcnow()
    call_id = store.start_tool_call(
        run_id=run["run_id"], attempt=run["attempt"], call_uid=call_uid,
        agent_run_id="", round_number=0, tool_name=tool_name,
        started_at=started, arguments=arguments,
    )
    began = time.monotonic()
    try:
        value = action()
        store.finish_tool_call(
            call_id, status="succeeded", finished_at=utcnow(),
            result={"completed": True, "model_used": bool(value.get("model_used")) if isinstance(value, dict) else bool(value), "value": value},
            latency_ms=int((time.monotonic() - began) * 1000),
        )
        return value
    except Exception as exc:
        store.finish_tool_call(
            call_id, status="failed", finished_at=utcnow(), error=str(exc),
            result={"failure_category": "model_or_parser_error"},
            latency_ms=int((time.monotonic() - began) * 1000),
        )
        raise


def plan_run(database_path: str, run_id: str, lease_owner: str = "") -> None:
    store = EvidenceStore(database_path)
    try:
        run = store.research_run(run_id)
        if not run:
            return
        now = utcnow()
        store.save_step(run_id, run["attempt"], "planning", "running", started_at=now)
        topic_key = str(run["request"]["topic"]).strip().casefold()
        known = next((item for item in store.theme_definitions() if item.get("status") == "confirmed" and topic_key in {str(item.get("theme_id", "")).casefold(), str(item.get("name", "")).casefold(), *(str(alias).casefold() for alias in item.get("aliases", []))}), None)
        if known and run["request"].get("output_type") == "etf_opportunity_analysis":
            definition = {
                **known,
                "include_terms": known.get("aliases", []),
                "exclude_terms": [],
                "research_questions": ["ETF 官方持仓覆盖是否充分？", "可投资公司池与产品空白是否可核验？", "哪些证据会否定当前 ETF 机会假设？"],
                "model_used": False,
            }
        else:
            definition = _audit_call(
                store, run, "llm_theme_definition",
                {"topic": run["request"]["topic"], "objective": run["request"].get("objective", "build_investment_thesis")},
                lambda: build_theme_definition(run["request"]["topic"], run["request"].get("objective", "build_investment_thesis")),
            )
        result = {"theme_definition": definition, "coverage": {}, "available_actions": ["approve_theme", "return_theme"]}
        auto_continue = bool(known and run["request"].get("output_type") == "etf_opportunity_analysis")
        store.save_step(run_id, run["attempt"], "planning", "succeeded", started_at=now, finished_at=utcnow(), details={"model_used": definition["model_used"], "known_theme": bool(known), "auto_continue": auto_continue})
        if auto_continue:
            result["available_actions"] = ["cancel"]
            store.update_research_run(run_id, status="queued", stage="collecting", updated_at=utcnow(), result=result, progress=15, review_gate="")
        else:
            store.update_research_run(run_id, status="awaiting_theme_review", stage="theme_review", updated_at=utcnow(), result=result, progress=12, review_gate="theme_definition")
    except Exception as exc:
        store.update_research_run(run_id, status="failed", stage="planning", updated_at=utcnow(), error=str(exc), progress=0)
        store.promote_waiting_run(utcnow())
    finally:
        if lease_owner:
            store.release_run(run_id, lease_owner)
        store.close()


def execute_run(database_path: str, run_id: str, lease_owner: str = "") -> None:
    """Execute only the persisted current phase, allowing phase-level recovery."""
    store = EvidenceStore(database_path)
    try:
        run = store.research_run(run_id)
        if not run:
            return
        attempt = run["attempt"]
        result = dict(run["result"])
        current = store.research_run(run_id)
        if not current or current["status"] == "cancelled":
            return
        phase = current["stage"]
        if current["status"] == "queued" or phase == "collecting":
            step, progress = "collecting", 30
            started = utcnow()
            store.save_step(run_id, attempt, step, "running", started_at=started)
            store.update_research_run(run_id, status=step, stage=step, updated_at=started, result=result, progress=progress, review_gate="")
            details = {"agent": run_research_agent(store, store.research_run(run_id) or run, result["theme_definition"])}
            result["agent"] = details["agent"]
            if details["agent"].get("status") == "blocked_configuration":
                store.save_step(run_id, attempt, step, "failed", started_at=started, finished_at=utcnow(), error=details["agent"].get("error", "模型配置错误"), details=details)
                store.update_research_run(run_id, status="blocked_configuration", stage="collecting", updated_at=utcnow(), result=result, error=details["agent"].get("error", "模型配置错误"), progress=30)
                store.promote_waiting_run(utcnow())
                return
            store.save_step(run_id, attempt, step, "succeeded", started_at=started, finished_at=utcnow(), details=details)
            store.update_research_run(run_id, status="governing", stage="governing", updated_at=utcnow(), result=result, progress=45)
            return
        if phase == "governing":
            started = utcnow()
            store.save_step(run_id, attempt, "governing", "running", started_at=started)
            store.update_research_run(run_id, status="governing", stage="governing", updated_at=started, result=result, progress=52)
            # Ingestion deterministically classifies each new event before it
            # commits. Reclassifying the entire evidence database on every
            # cached research attempt duplicates minutes of work. Startup and
            # explicit source syncs retain full reclassification so changed
            # governance configuration is still applied centrally.
            details = {
                "classification": "incremental_at_ingest",
                "research_assets": refresh_research_assets(store),
            }
            store.save_step(run_id, attempt, "governing", "succeeded", started_at=started, finished_at=utcnow(), details=details)
            store.update_research_run(run_id, status="analyzing", stage="analyzing", updated_at=utcnow(), result=result, progress=65)
            return
        if phase == "analyzing":
            definition = result["theme_definition"]
            started = utcnow()
            store.save_step(run_id, attempt, "analyzing", "running", started_at=started)
            store.update_research_run(run_id, status="analyzing", stage="analyzing", updated_at=started, result=result, progress=72)
            research = _audit_call(
                store, run, "llm_evidence_synthesis", {"theme_id": definition["theme_id"]},
                lambda: run_research_output(
                    store, definition["theme_id"],
                    Path("data/reports/research-runs") / run_id / f"attempt-{attempt}",
                    run_id, analysis_llm_config(), output_type=run["request"].get("output_type", "theme_report"), theme_name=definition["name"],
                    aliases=[*definition.get("aliases", []), *definition.get("include_terms", [])],
                    approved_sources=run["request"].get("sources", []),
                ),
            )
            result.update(research)
            result["theme_definition"] = definition
            result["available_actions"] = ["approve_report", "return_report"]
            store.save_step(run_id, attempt, "analyzing", "succeeded", started_at=started, finished_at=utcnow(), details={"selected": research["selected"]})
            store.update_research_run(run_id, status="auditing", stage="auditing", updated_at=utcnow(), result=result, progress=86)
            return
        if phase == "auditing":
            audit = result.get("audit") or {"passed": False, "issues": ["缺少审计结果"]}
            audit_status = "succeeded" if audit.get("passed") else "failed"
            store.save_step(run_id, attempt, "auditing", audit_status, started_at=utcnow(), finished_at=utcnow(), details=audit)
            store.update_research_run(run_id, status="awaiting_report_review", stage="report_review", updated_at=utcnow(), result=result, progress=92, review_gate="final_report")
    except Exception as exc:
        current = store.research_run(run_id)
        if current and current["status"] != "cancelled":
            retry_count = next((int(item.get("retry_count") or 0) for item in store.run_steps(run_id) if item["attempt"] == current["attempt"] and item["step_name"] == current["stage"]), 0)
            if retry_count < 1:
                store.save_step(run_id, current["attempt"], current["stage"], "retrying", finished_at=utcnow(), error=str(exc), retry_count=retry_count + 1)
                store.update_research_run(run_id, status=current["stage"], stage=current["stage"], updated_at=utcnow(), result=current["result"], error=str(exc))
            else:
                store.update_research_run(run_id, status="failed", stage=current["stage"], updated_at=utcnow(), result=current["result"], error=str(exc))
                store.promote_waiting_run(utcnow())
    finally:
        if lease_owner:
            store.release_run(run_id, lease_owner)
        store.close()


def execute_event_run(database_path: str, run_id: str, lease_owner: str = "") -> None:
    store=EvidenceStore(database_path)
    try:
        run=store.research_run(run_id)
        if not run or run["status"]=="cancelled": return
        evidence_id=str(run["request"].get("evidence_id") or run["theme_id"].removeprefix("event:"))
        started=utcnow(); store.save_step(run_id,run["attempt"],"source_verification","running",started_at=started)
        store.update_research_run(run_id,status="analyzing",stage="source_verification",updated_at=started,progress=45)
        result=_audit_call(store,run,"llm_event_fact_analysis",{"evidence_id":evidence_id},lambda:run_event_deep_dive(store,evidence_id,Path("data/reports/event-research-runs")/run_id,run_id,analysis_llm_config()))
        current=store.research_run(run_id)
        if not current or current["status"]=="cancelled": return
        store.save_step(run_id,run["attempt"],"source_verification","succeeded",started_at=started,finished_at=utcnow(),details={"verified_fact_count":(result.get("audit") or {}).get("verified_fact_count",0)})
        store.update_research_run(run_id,status="completed",stage="completed",updated_at=utcnow(),result=result,progress=100)
        fact_pack=result.get("fact_pack") or {}; now=utcnow(); report_id=f"report:{run_id}"
        asset={"report_id":report_id,"run_id":run_id,"title":fact_pack.get("event_title") or f"{evidence_id} 事件研究","kind":"event_report","theme_id":str((fact_pack.get("theme_id") or "unknown")),"folder_id":"ai","status":"watch","tags":["事件研究","证据核验"],"summary":"基于通用事件事实包、交叉核验与待验证事项生成的深度研究。","updated_at":now,"created_at":now,"version":1,"source_count":len(fact_pack.get("sources") or []),"evidence_count":len(fact_pack.get("facts") or []),"audit_passed":bool((result.get("audit") or {}).get("passed"))}
        store.save_report_asset(asset); store.save_report_version(report_id,1,{"asset":asset,"result":result},str(result.get("markdown") or ""),now)
    except Exception as exc:
        current=store.research_run(run_id)
        if current and current["status"]!="cancelled": store.update_research_run(run_id,status="failed",stage="source_verification",updated_at=utcnow(),result=current["result"],error=str(exc))
    finally:
        if lease_owner: store.release_run(run_id,lease_owner)
        store.close()


def execute_market_refresh(database_path: str, run_id: str, lease_owner: str = "") -> None:
    """Create an independent ETF market snapshot without mutating the report."""
    store = EvidenceStore(database_path)
    try:
        run = store.research_run(run_id)
        if not run or run["status"] == "cancelled":
            return
        report_id = str(run["request"].get("report_id") or "")
        report = store.report_asset(report_id)
        versions = store.report_versions(report_id)
        if not report or not versions:
            raise ValueError("报告或报告版本不存在")
        started = utcnow()
        store.save_step(run_id, run["attempt"], "market_refresh", "running", started_at=started)
        store.update_research_run(
            run_id, status="collecting", stage="market_refresh", updated_at=started,
            result={"report_id": report_id}, progress=35,
        )
        payload = versions[0]["payload"]
        result = dict(payload.get("result") or {})
        detail = dict(result.get("detail") or {})
        landscape = dict(detail.get("landscape") or {})
        competitors = landscape.get("similar_etfs") or []
        market_snapshot = collect_market_snapshot(
            competitors, Path("data/cache/yahoo-etf-market")
        )
        now = utcnow()
        snapshot_id = str(uuid4())
        errors = [
            {"ticker": item.get("ticker"), "error": item.get("error")}
            for item in market_snapshot.get("products") or [] if item.get("error")
        ]
        store.save_etf_market_snapshot({
            "snapshot_id": snapshot_id, "report_id": report_id,
            "collected_at": now, "market_as_of": market_snapshot.get("market_as_of", ""),
            "status": market_snapshot.get("status", "unknown"),
            "products": market_snapshot.get("products") or [], "errors": errors,
            "payload": market_snapshot,
        })
        outcome = {
            "report_id": report_id, "report_version": int(report["version"]),
            "snapshot_id": snapshot_id, "market_snapshot": market_snapshot,
        }
        store.save_step(
            run_id, run["attempt"], "market_refresh", "succeeded",
            started_at=started, finished_at=now,
            details={"report_id": report_id, "report_version": int(report["version"]), "snapshot_id": snapshot_id},
        )
        store.update_research_run(
            run_id, status="completed", stage="completed", updated_at=now,
            result=outcome, progress=100,
        )
    except Exception as exc:
        current = store.research_run(run_id)
        if current and current["status"] != "cancelled":
            store.update_research_run(
                run_id, status="failed", stage="market_refresh", updated_at=utcnow(),
                result=current["result"], error=str(exc),
            )
    finally:
        if lease_owner:
            store.release_run(run_id, lease_owner)
        store.close()


def recover_interrupted_runs(database_path: str) -> list[str]:
    """Return durable runnable jobs; the Worker claims them instead of spawning threads."""
    store = EvidenceStore(database_path)
    try: runs = store.research_runs(200)
    finally: store.close()
    return [run["run_id"] for run in runs if run["status"] in {"planning", "queued", "collecting", "governing", "analyzing", "auditing"}]
