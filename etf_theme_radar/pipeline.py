from __future__ import annotations
from datetime import date
from .connectors import SourceConnector
from .store import EvidenceStore
from .governance import classify
from .content_quality import evaluate_content_quality
from .fact_extraction import extract_facts
def ingest(connector: SourceConnector, store: EvidenceStore, since: date, until: date) -> dict:
    health=connector.healthcheck(); store.save_health(health); store.commit()
    result={"source":connector.source_name,"status":health.status,"items":0,"events":0,"errors":[]}
    if health.status != "healthy":
        store.commit()
        return result
    try:
        for item_id in connector.discover(since,until):
            try:
                raw=connector.fetch(item_id); store.save_raw(raw); events=connector.normalize(raw)
                for event in events:
                    governed = classify(event, raw.text)
                    store.save_event(governed)
                    store.save_content_quality_result(
                        evaluate_content_quality(governed.__dict__, raw.text).as_dict()
                    )
                    store.save_extracted_fact(extract_facts(governed.__dict__, raw.text).as_dict())
                store.commit()
                result["items"]+=1; result["events"]+=len(events)
            except Exception as exc:
                store.rollback()
                result["errors"].append(str(exc))
        result["errors"].extend(getattr(connector, "discovery_errors", []))
    except Exception as exc: result["errors"].append(str(exc))
    hits = int(getattr(connector, "cache_hits", 0))
    misses = int(getattr(connector, "cache_misses", 0))
    result["cache_status"] = "hit" if hits and not misses else "mixed" if hits and misses else "miss" if misses else "not_used"
    result["cache_hits"] = hits
    result["cache_misses"] = misses
    store.commit()
    return result
