from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ActionUnitLedger:
    """Tracks one click/action unit while the world still advances year by year.

    Benefits are annual, but an action's resource cost and active encounter are
    paid/resolved only once. Keeping that distinction here prevents every new
    long-duration action from having to reinvent the same bookkeeping.
    """

    action: str
    planned_years: int
    elapsed_years: int = 0
    resource_cost_paid: bool = False
    combat_resolved: bool = False
    results: dict[str, list[str]] = field(default_factory=dict)

    def begin_year(self) -> None:
        self.elapsed_years += 1

    def claim_resource_cost(self) -> bool:
        if self.resource_cost_paid:
            return False
        self.resource_cost_paid = True
        return True

    def claim_combat(self) -> bool:
        if self.combat_resolved:
            return False
        self.combat_resolved = True
        return True

