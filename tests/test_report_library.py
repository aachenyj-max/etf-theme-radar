from etf_theme_radar.store import EvidenceStore
from etf_theme_radar.api import _register_theme_report


def test_report_asset_lifecycle(tmp_path):
    store = EvidenceStore(tmp_path / "reports.db")
    store.save_report_asset({
        "report_id": "report-1",
        "run_id": "run-1",
        "title": "AI 基础设施主题研究",
        "kind": "theme_report",
        "theme_id": "ai-infrastructure",
        "folder_id": "ai",
        "status": "deep_research",
        "tags": ["AI", "ETF"],
        "summary": "治理后研究简报",
        "updated_at": "2026-07-24T10:00:00Z",
        "created_at": "2026-07-24T10:00:00Z",
        "source_count": 6,
        "evidence_count": 32,
        "audit_passed": True,
    })

    saved = store.report_asset("report-1")
    assert saved["title"] == "AI 基础设施主题研究"
    assert saved["deleted_at"] is None

    renamed = store.update_report_asset(
        "report-1",
        title="AI 基础设施研究｜更新版",
        updated_at="2026-07-24T11:00:00Z",
    )
    assert renamed["title"].endswith("更新版")
    assert renamed["version"] == 1

    archived = store.update_report_asset(
        "report-1",
        status="archived",
        updated_at="2026-07-24T12:00:00Z",
    )
    assert archived["status"] == "archived"
    assert archived["archived_at"] == "2026-07-24T12:00:00Z"

    assert store.soft_delete_report_asset("report-1", "2026-07-24T13:00:00Z")
    assert store.report_asset("report-1") is None
    assert store.report_assets() == []
    assert store.report_assets(include_deleted=True)[0]["deleted_at"] == "2026-07-24T13:00:00Z"
    store.close()


def test_verified_research_appends_one_canonical_theme_report_version_chain(tmp_path):
    store = EvidenceStore(tmp_path / "versions.db")
    def result(statement: str) -> dict:
        return {
            "status":"WATCH","output_type":"theme_report","theme_definition":{"theme_id":"semiconductors","name":"半导体"},
            "brief":{"source_types":3},"selected":4,"conclusion":{"statement":statement},"report_markdown":statement,
            "audit":{"passed":True,"publication_gate":{"passed":True,"failed_checks":[]}},
            "claims":[{"text":statement,"type":"thesis","evidence_ids":["e-1"]}],
        }
    _register_theme_report(store,"run-one","semiconductors",result("第一版结论"))
    _register_theme_report(store,"run-two","semiconductors",result("第二版结论"))
    asset=store.report_asset("theme-report:semiconductors")
    assert asset and asset["version"] == 2 and asset["run_id"] == "run-two"
    assert asset["summary"] == "第二版结论"
    assert [item["version"] for item in store.report_versions(asset["report_id"])] == [2,1]
    assert len(store.report_assets()) == 1
    store.close()
