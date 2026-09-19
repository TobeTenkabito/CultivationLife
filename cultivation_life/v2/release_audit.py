from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .server import V2HTTPCommandRegistry


@dataclass(frozen=True, slots=True)
class V2ReleaseSurfaceReport:
    frozen_operations: tuple[str, ...]
    http_operations: tuple[str, ...]
    client_operations: tuple[str, ...]
    missing_from_http: tuple[str, ...]
    missing_from_client: tuple[str, ...]
    v2_only_http_operations: tuple[str, ...]
    v2_only_client_operations: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not (
            self.missing_from_http
            or self.missing_from_client
        )

    def to_dict(self) -> dict[str, object]:
        return {"ready": self.ready, **asdict(self)}


def assess_release_surface(project_root: Path) -> V2ReleaseSurfaceReport:
    """Verify that migrated commands are reachable from both HTTP and the client.

    Domain tests alone cannot prove that a packaged player can invoke a feature.
    This check deliberately treats every frozen V1 public operation as part of
    the release contract until it is explicitly retired from the inventory.
    """
    root = Path(project_root)
    inventory = json.loads(
        (root / "docs" / "v2" / "v1_behavior_inventory.json").read_text(
            encoding="utf-8"
        )
    )
    frozen = set(map(str, inventory["public_operations"]))
    registry = V2HTTPCommandRegistry(object())  # handlers are lazy closures
    http = set(registry.operations)
    # One V2 destination-based command intentionally replaces three V1 route
    # names.  Extras such as explicit fight/refresh are valid V2 additions,
    # not release failures.
    http_coverage = http & frozen
    if "ascend-world" in http:
        http_coverage.update({
            "spirit-crossing", "celestial-ascension", "asura-ascension",
        })
    script = (root / "web" / "v2.js").read_text(encoding="utf-8")
    # The client has two legitimate entry styles: direct commands for the
    # always-visible time/event controls, and declarative ``op(...)`` records
    # for typed, data-driven system forms.  Both flow through the same command
    # executor at runtime; keeping the route name literal makes omissions and
    # accidental renames statically auditable.
    client = set(re.findall(r"\bcommand\(\s*['\"]([^'\"]+)['\"]", script))
    client.update(re.findall(r"\bop\(\s*['\"]([^'\"]+)['\"]", script))
    return V2ReleaseSurfaceReport(
        frozen_operations=tuple(sorted(frozen)),
        http_operations=tuple(sorted(http)),
        client_operations=tuple(sorted(client)),
        missing_from_http=tuple(sorted(frozen - http_coverage)),
        missing_from_client=tuple(sorted(frozen - client)),
        v2_only_http_operations=tuple(sorted(http - frozen)),
        v2_only_client_operations=tuple(sorted(client - frozen)),
    )
