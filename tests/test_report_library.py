from etf_theme_radar.store import EvidenceStore
from etf_theme_radar.api import _register_theme_report
from etf_theme_radar.knowledge_base import KnowledgeBase


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


def test_legacy_personal_reports_migrate_once_to_local_and_exclude_theme_reports(tmp_path):
    store = EvidenceStore(tmp_path / "legacy-reports.db")
    store.save_report_asset({
        "report_id": "legacy-note", "run_id": "", "title": "机器人旧资料",
        "kind": "evidence_brief", "theme_id": "robotics", "folder_id": "robotics",
        "status": "completed", "tags": ["机器人"], "summary": "旧个人保存内容",
        "updated_at": "2026-08-18T00:00:00Z", "created_at": "2026-08-18T00:00:00Z",
    })
    store.save_report_asset({
        "report_id": "theme-report:robotics", "run_id": "run-robotics", "title": "机器人正式主题报告",
        "kind": "theme_report", "theme_id": "robotics", "folder_id": "robotics",
        "status": "completed", "tags": ["机器人"], "summary": "规范版本链",
        "updated_at": "2026-08-18T00:00:00Z", "created_at": "2026-08-18T00:00:00Z",
    })
    library = KnowledgeBase(store, files_root=tmp_path / "knowledge-files")

    first = library.migrate_legacy_personal_reports(owner_user_id="local", migrated_at="2026-08-18T01:00:00Z")
    second = library.migrate_legacy_personal_reports(owner_user_id="local", migrated_at="2026-08-18T01:01:00Z")

    assert first == {"migrated": ["legacy-note"], "skipped_formal": ["theme-report:robotics"]}
    assert second == {"migrated": [], "skipped_formal": ["theme-report:robotics"]}
    migrated = store.conn.execute(
        "SELECT owner_user_id,legacy_report_id,knowledge_item_id FROM legacy_report_migrations"
    ).fetchone()
    assert migrated is not None and migrated[0:2] == ("local", "legacy-note")
    item = library.item(migrated[2], "local")
    assert item is not None and item["title"] == "机器人旧资料"
    assert "旧个人保存内容".encode() in (library.read_content(migrated[2], "local") or b"")
    assert store.conn.execute(
        "SELECT COUNT(*) FROM legacy_report_migrations WHERE legacy_report_id='theme-report:robotics'"
    ).fetchone()[0] == 0
    store.close()
