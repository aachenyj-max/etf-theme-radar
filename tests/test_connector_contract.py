from datetime import date
from pathlib import Path
from etf_theme_radar.connectors import FixtureConnector
def test_fixture_connector_contract():
    c=FixtureConnector(Path("tests/fixtures/events.json")); ids=c.discover(date(2025,1,1),date(2025,2,1)); raw=c.fetch(ids[0]); events=c.normalize(raw)
    assert ids and raw.content_hash and events[0].raw_content_hash == raw.content_hash

