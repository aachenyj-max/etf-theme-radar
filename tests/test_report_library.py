from etf_theme_radar.store import EvidenceStore


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
    assert renamed["version"] == 2

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
