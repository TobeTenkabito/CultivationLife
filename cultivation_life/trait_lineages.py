"""Curated personal lineages. Books and artifacts refer to canonical content IDs."""
from .definition_data import definition as _content_definition
from dataclasses import dataclass
from .errors import ContentError
from .trait_repertoires import BY_RARITY, REPERTOIRES


@dataclass(frozen=True)
class Lineage:
    name: str
    rarity: str
    family: str
    level: int
    rule: str
    percent: int = 0
    element: str = ""
    other: str = ""
    innate: bool = False
    books: tuple[str, ...] = ()
    artifacts: tuple[str, ...] = ()

    def description(self, labels):
        a = labels.get(self.element, "")
        b = labels.get(self.other, "")
        damage = "物理伤害" if self.element == "physical" else f"{a}属性伤害"
        n = self.percent
        return {
            "damage": f"{damage}提高 {n}%",
            "resist": f"{a}抗提高 {n} 个百分点",
            "own": f"自身以{b}护身时，{damage}提高 {n}%",
            "pure": f"纯{a}攻击伤害提高 {n}%",
            "pair": f"同一击兼具{a}和{b}时，这两项伤害各提高 {n}%",
            "pierce": f"{damage}穿透至多 {n} 个百分点{a}抗",
            "guard": f"以{b}护身承受{a}伤时，克制倍率由 1.20 降至 {1 + n / 100:.2f}",
            "foundation_practice": f"练气期和筑基期的日常修炼所得进度提高 {n}%",
            "practice": f"日常修炼所得进度提高 {n}%",
            "balanced": f"身在肉身且炼体和神识均达三级时，日常修炼所得进度提高 {n}%",
        }[self.rule]


LINEAGES = _content_definition(__name__, "LINEAGES", Lineage)

for rarity, group in BY_RARITY.items():
    for key, entry in group.items():
        if key in LINEAGES:
            raise ContentError(f"特质 ID 重复：{key}")
        LINEAGES[key] = Lineage(entry.name, rarity, entry.family, entry.level, "signature",
                                innate=entry.innate, books=entry.books, artifacts=entry.artifacts)

# Selected old traits also have an artifact lineage. All other items retain their ordinary use.
ARTIFACT_TRAITS = _content_definition(__name__, "ARTIFACT_TRAITS")
for _trait, _entry in LINEAGES.items():
    for _item in _entry.artifacts:
        if ARTIFACT_TRAITS.setdefault(_item, _trait) != _trait:
            raise ContentError(f"法宝传承特质重复配置：{_item}")

# These abilities follow the physical body during wandering and possession.
LINEAGE_BODY_TRAITS = _content_definition(__name__, "LINEAGE_BODY_TRAITS")
LINEAGE_BODY_TRAITS.update(key for key, entry in REPERTOIRES.items() if entry.bodily)
