from __future__ import annotations
import argparse, json
from datetime import date, timedelta
from pathlib import Path
from .connector_factory import configured_connectors
from .connectors import FixtureConnector
from .pipeline import ingest
from .store import EvidenceStore
from .models import ThemeMetrics
from .scoring import opportunity_score
from .reports import build_daily_brief
from .governance import reclassify_store
from .comparisons import build_comparisons
from .theme_research import run_theme_research
from .evidence_summary_backfill import backfill_evidence_summaries
from .agent_runtime import analysis_llm_config

def run_configured(db: str, days: int, sources: set[str] | None = None) -> dict:
    """运行已配置的数据源；可按源隔离重试。"""
    store = EvidenceStore(db)
    until = date.today(); since = until - timedelta(days=days)
    connectors = configured_connectors(Path("data/cache"))
    if sources:
        connectors = [connector for connector in connectors if connector.source_name in sources]
    try:
        return {connector.source_name: ingest(connector, store, since, until) for connector in connectors}
    finally:
        store.close()
def main() -> None:
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="command",required=True)
    demo=sub.add_parser("demo"); demo.add_argument("--db",default="data/radar.db"); demo.add_argument("--output",default="data/demo-output.json")
    run=sub.add_parser("run"); run.add_argument("--db",default="data/radar.db"); run.add_argument("--days",type=int,default=7); run.add_argument("--sources", help="以逗号分隔的连接器名称；例如 sec_edgar_etf,openalex")
    report=sub.add_parser("report"); report.add_argument("--db",default="data/radar.db"); report.add_argument("--output",default="data/reports/daily-brief.md")
    govern=sub.add_parser("govern"); govern.add_argument("--db",default="data/radar.db")
    compare=sub.add_parser("compare"); compare.add_argument("--db",default="data/radar.db"); compare.add_argument("--output",default="data/reports/classification-comparisons.md")
    research=sub.add_parser("research"); research.add_argument("--db",default="data/radar.db"); research.add_argument("--theme",default="ai-infrastructure"); research.add_argument("--output",default="data/reports/theme-research")
    backfill=sub.add_parser("backfill-evidence-summaries"); backfill.add_argument("--db",default="data/radar.db"); backfill.add_argument("--report-id"); backfill.add_argument("--apply",action="store_true")
    args=p.parse_args()
    if args.command == "run":
        selected = {name.strip() for name in (args.sources or "").split(",") if name.strip()}
        print(json.dumps(run_configured(args.db, max(1, min(args.days, 31)), selected or None), ensure_ascii=False, indent=2)); return
    if args.command == "report": print(build_daily_brief(EvidenceStore(args.db), args.output)); return
    if args.command == "govern":
        store = EvidenceStore(args.db)
        try: print(json.dumps(reclassify_store(store), ensure_ascii=False, indent=2))
        finally: store.close()
        return
    if args.command == "compare": print(build_comparisons(EvidenceStore(args.db), args.output)); return
    if args.command == "research":
        result = run_theme_research(EvidenceStore(args.db), args.theme, args.output)
        print(json.dumps({"run_id": result["run_id"], "status": result["status"], "selected": result["selected"], "audit": result["audit"]}, ensure_ascii=True, indent=2)); return
    if args.command == "backfill-evidence-summaries":
        store = EvidenceStore(args.db)
        try: result = backfill_evidence_summaries(store, analysis_llm_config(), apply=args.apply, report_id=args.report_id)
        finally: store.close()
        print(json.dumps(result, ensure_ascii=False, indent=2)); return
    store=EvidenceStore(args.db); result=ingest(FixtureConnector(Path("tests/fixtures/events.json")),store,date(2025,1,1),date.today())
    metrics=ThemeMetrics("edge-ai-infrastructure", {"research_momentum":82,"patent_momentum":68,"hiring_momentum":74,"corporate_adoption":79,"capital_market_momentum":61,"investable_universe_quality":70,"product_white_space":64,"evidence_diversity":80,"hype":20,"crowding":15,"concentration":25,"data_quality":10}, ("official","academic","patent","jobs"),1,18,tuple(x["event_id"] for x in store.events()))
    payload={"as_of_date":date.today().isoformat(),"pipeline":result,"top_themes":[opportunity_score(metrics)],"disclaimer":"Research simulation; not real-time investment advice or a filing."}
    Path(args.output).parent.mkdir(parents=True,exist_ok=True); Path(args.output).write_text(json.dumps(payload,indent=2),encoding="utf-8"); print(json.dumps(payload,indent=2))
if __name__ == "__main__": main()
