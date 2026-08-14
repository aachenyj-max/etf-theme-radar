"""Persistent Agent Goal coordination and bounded local concurrency policy."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .store import EvidenceStore


def _concurrency_defaults() -> dict[str, int]:
    values: dict[str, int] = {}
    section = ""
    path = Path(__file__).parents[1] / "config" / "defaults.yaml"
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw.startswith(" ") and raw.rstrip().endswith(":"):
            section = raw.strip()[:-1]
            continue
        if section == "agent_concurrency" and ":" in raw:
            key, value = raw.strip().split(":", 1)
            values[key] = int(value.strip())
    return values


@dataclass
class GoalConcurrencyPolicy:
    total_limit: int
    interactive_reserved: int
    background_reserved: int
    minimum_total: int
    cooldown_seconds: int
    effective_total: int = field(init=False)
    _cooldown_until: float = field(init=False, default=0)

    def __post_init__(self) -> None:
        if self.total_limit < 2:
            raise ValueError("Agent concurrency total_limit must be at least 2")
        if self.interactive_reserved < 1 or self.background_reserved < 1:
            raise ValueError("Both Agent concurrency lanes need at least one reserved slot")
        if self.interactive_reserved + self.background_reserved != self.total_limit:
            raise ValueError("Reserved Agent concurrency slots must equal total_limit")
        if not 2 <= self.minimum_total <= self.total_limit:
            raise ValueError("minimum_total must be between 2 and total_limit")
        if self.cooldown_seconds < 1:
            raise ValueError("cooldown_seconds must be positive")
        self.effective_total = self.total_limit

    @classmethod
    def from_defaults(cls) -> "GoalConcurrencyPolicy":
        values = _concurrency_defaults()
        return cls(
            total_limit=values["total_limit"],
            interactive_reserved=values["interactive_reserved"],
            background_reserved=values["background_reserved"],
            minimum_total=values["minimum_total"],
            cooldown_seconds=values["cooldown_seconds"],
        )

    @property
    def lane_limits(self) -> dict[str, int]:
        background = max(
            1,
            round(self.effective_total * self.background_reserved / self.total_limit),
        )
        background = min(background, self.effective_total - 1)
        return {
            "interactive": self.effective_total - background,
            "background": background,
        }

    def record_pressure(self, status_code: int, *, observed_at: float) -> bool:
        if status_code not in {429, 503}:
            return False
        reduced = max(self.minimum_total, self.effective_total // 2)
        changed = reduced != self.effective_total
        self.effective_total = reduced
        self._cooldown_until = observed_at + self.cooldown_seconds
        return changed

    def record_success(self, *, observed_at: float) -> bool:
        if observed_at < self._cooldown_until or self.effective_total >= self.total_limit:
            return False
        self.effective_total += 1
        self._cooldown_until = observed_at + self.cooldown_seconds
        return True


class AgentGoalRuntime:
    """Owner-bound interface used by the single persistent Worker."""

    def __init__(
        self, store: EvidenceStore, owner: str, *,
        policy: GoalConcurrencyPolicy | None = None,
    ) -> None:
        self.store = store
        self.owner = owner
        self.policy = policy or GoalConcurrencyPolicy.from_defaults()

    def claim(self, lane: str, now: str, lease_expires_at: str) -> dict | None:
        return self.store.claim_next_agent_goal(
            self.owner, lane, now, lease_expires_at, self.policy.lane_limits[lane]
        )

    def heartbeat(self, goal_id: str, now: str, lease_expires_at: str) -> bool:
        return self.store.heartbeat_agent_goal(goal_id, self.owner, now, lease_expires_at)

    def transition(
        self, goal_id: str, to_status: str, now: str, *, safe_summary: str = "",
        result: dict | None = None, error: str = "",
    ) -> dict:
        return self.store.transition_agent_goal(
            goal_id, self.owner, to_status, now, safe_summary=safe_summary,
            result=result, error=error,
        )

