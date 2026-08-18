from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_launcher_uses_only_canonical_ports_and_build_directory() -> None:
    launcher = (PROJECT_ROOT / "tools" / "start_local.ps1").read_text(encoding="utf-8")
    next_config = (PROJECT_ROOT / "frontend" / "next.config.mjs").read_text(encoding="utf-8")

    assert "$apiPort = 8001" in launcher
    assert "$webPort = 3000" in launcher
    assert '$env:RADAR_NEXT_DIST_DIR = ".next"' in launcher
    assert "Find-AvailablePort" not in launcher
    assert 'distDir: process.env.RADAR_NEXT_DIST_DIR || ".next"' in next_config
    assert 'allowedDevOrigins: ["127.0.0.1"]' in next_config
    assert 'process.env.RADAR_BACKEND_URL || "http://127.0.0.1:8001"' in next_config


def test_launcher_restores_next_build_directory_environment() -> None:
    launcher = (PROJECT_ROOT / "tools" / "start_local.ps1").read_text(encoding="utf-8")

    assert 'GetEnvironmentVariable("RADAR_NEXT_DIST_DIR", "Process")' in launcher
    assert 'Remove-Item Env:RADAR_NEXT_DIST_DIR' in launcher
    assert '$env:RADAR_NEXT_DIST_DIR = $previousNextDistDir' in launcher


def test_e2e_server_disables_next_lock_only_for_its_own_process() -> None:
    next_config = (PROJECT_ROOT / "frontend" / "next.config.mjs").read_text(encoding="utf-8")
    playwright_config = (PROJECT_ROOT / "frontend" / "playwright.config.ts").read_text(encoding="utf-8")

    assert 'lockDistDir: process.env.RADAR_E2E !== "1"' in next_config
    assert 'set "RADAR_E2E=1" && npm run dev' in playwright_config


def test_launcher_reuses_only_matching_contract_with_worker_heartbeat() -> None:
    launcher = (PROJECT_ROOT / "tools" / "start_local.ps1").read_text(encoding="utf-8")
    assert '$contractVersion = "2026-08-18.v19"' in launcher
    assert "api/capabilities" in launcher
    assert 'service.id -eq $serviceId' in launcher
    assert 'service.contract_version -eq $contractVersion' in launcher
    assert 'worker.heartbeat_at' in launcher
    assert 'launcher.lock' in launcher
    assert '$attempt -lt 180' in launcher


def test_batch_launcher_stays_visible_and_reuse_opens_frontend() -> None:
    batch = (PROJECT_ROOT / "启动ETF主题雷达.bat").read_text(encoding="utf-8")
    launcher = (PROJECT_ROOT / "tools" / "start_local.ps1").read_text(encoding="utf-8")

    assert "pause >nul" in batch
    assert "if not \"%EXIT_CODE%\"==\"0\" pause" not in batch
    reuse_block = launcher.split("if (Wait-ExistingCanonicalServices)", 1)[1].split("throw", 1)[0]
    assert "Start-Process $webUri" in reuse_block
