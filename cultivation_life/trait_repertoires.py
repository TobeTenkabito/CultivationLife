"""Load personal technique definitions in catalog order for stable seeded births."""
from dataclasses import dataclass

from .combat_semantics import parse_rules
from .content_io import read_json
from .content_paths import default_content_root
from .damage_weaves import validate_weave
from .errors import ContentError
from .trait_rule_builders import Signature


@dataclass(frozen=True)
class Repertoire:
    name: str
    family: str
    books: tuple[str, ...]
    signature: Signature
    level: int
    innate: bool
    bodily: bool
    artifacts: tuple[str, ...]
    weave: dict | None

    @property
    def book(self):
        return self.books[0]

    @property
    def artifact(self):
        return self.artifacts[0] if self.artifacts else ""


def load_repertoires(path):
    data = read_json(path)
    if (type(data.get("schema_version")) is not int or data["schema_version"] != 1
            or not isinstance(data.get("traits"), list)):
        raise ContentError(f"{path}: invalid repertoire catalog")
    groups = {rarity: {} for rarity in ("绿", "蓝", "紫", "橙")}
    seen = set()
    assigned_books = set()
    assigned_artifacts = set()
    required = {"id", "name", "rarity", "family", "level", "innate", "bodily", "books", "description"}
    for index, row in enumerate(data["traits"]):
        try:
            if not isinstance(row, dict) or required - row.keys() or row.keys() - required - {"artifacts", "rules", "weave"}:
                raise ValueError("invalid repertoire fields")
            if not all(isinstance(row[k], str) and row[k].strip() for k in ("id", "name", "family", "description")):
                raise ValueError("missing repertoire identifier, description or source")
            key = row["id"]
            if key in seen or row["rarity"] not in groups:
                raise ValueError("duplicate ID or invalid rarity")
            if (type(row["level"]) is not int or row["level"] < 1 or type(row["innate"]) is not bool
                    or type(row["bodily"]) is not bool):
                raise ValueError("invalid level or ownership")
            if not row["books"]:
                raise ValueError("missing mastery source")
            for sources, assigned in ((row["books"], assigned_books), (row.get("artifacts", []), assigned_artifacts)):
                if (not isinstance(sources, list) or any(not isinstance(s, str) or not s.strip() for s in sources)
                        or len(set(sources)) != len(sources) or assigned.intersection(sources)):
                    raise ValueError("invalid or duplicate mastery source")
                assigned.update(sources)
            rules = row.get("rules", [])
            if not isinstance(rules, list) or any(not isinstance(step, dict) or "schema_version" in step or "source_id" in step for step in rules):
                raise ValueError("invalid battle rules")
            parse_rules([dict(step, schema_version=3, source_id=row["name"]) for step in rules])
            weave = validate_weave(row["weave"]) if "weave" in row else None
            if not rules and not weave:
                raise ValueError("missing effect")
            groups[row["rarity"]][key] = Repertoire(
                row["name"], row["family"], tuple(row["books"]), Signature(row["description"], tuple(rules)),
                row["level"], row["innate"], row["bodily"], tuple(row.get("artifacts", [])), weave)
            seen.add(key)
        except (ValueError, KeyError, TypeError) as exc:
            raise ContentError(f"{path.name}: trait {index + 1}: {exc}") from exc
    return groups


BY_RARITY = load_repertoires(default_content_root() / "trait_repertoires.json")
REPERTOIRES = {key: entry for group in BY_RARITY.values() for key, entry in group.items()}
WEAVES = {key: entry.weave for key, entry in REPERTOIRES.items() if entry.weave}
