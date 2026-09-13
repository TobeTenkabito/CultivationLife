from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]

# Specific names and signature terms from external fiction that previously
# appeared in player-visible content.  Legacy ASCII record IDs are deliberately
# outside this list: keeping them is required for existing save compatibility.
BANNED_VISIBLE_TERMS = (
    "虚天殿", "虚天鼎", "乾蓝冰焰", "补天丹", "乱星海", "玄骨上人", "极阴祖师",
    "万天明", "天悟子", "青易居士", "蛮胡子", "风雷翅", "风希", "昆吾山",
    "玲珑残魂", "向之礼", "八灵尺", "北夜小极宫", "小极宫", "北极元山",
    "星宫双圣", "元磁神山", "元磁神光", "广寒界", "广寒令", "太乙青山",
    "元合五极山", "宝花", "六极", "苦灵岛", "洗灵池", "净灵莲", "元魇",
    "螟虫之母", "母螟", "何康", "刑罚神雷", "土皇钉", "落星旗", "小幻天镜",
    "蟹道人", "马良", "五色小瓶", "赫连商盟", "明尊", "鸣煞", "两仪微尘",
    "阳鹿", "火须子", "魔光圣祖", "轩九灵", "禁元灯", "九真伏仙",
    "蓝瀑圣祖", "血光上尊", "泣灵秘藏", "幻啸沙海", "金蟹守卫", "始印之地",
    "炼神术", "银蝌古文", "青元剑诀", "大庚剑阵", "青蟠剑阵", "春黎剑阵",
    "青元子", "青竹蜂云剑", "玄天仙藤", "玄天斩灵剑", "掌天瓶", "金雷竹",
    "辟邪神雷", "九曲灵参", "金阙玉书", "金阙残书", "雷鸣大陆", "角蚩族",
    "海王族", "夜叉族", "阴罗宗", "化仙宗", "天渊城", "巫行云", "曾沧海",
    "玄天血髓", "虚天炼界篇", "玄天万劫体",
)

# Names from the discarded first rewrite. They are kept out of player-visible
# fields so save-compatible legacy IDs cannot accidentally pull the weak
# bureaucracy/debt version of these stories back into a later build.
RETIRED_REWRITE_TERMS = (
    "潮墓天仓", "潮界衡印", "逐潮梭", "沉星古城", "七曜界标", "回光墟",
    "倒悬书海", "白潮母律", "阙无咎", "镜花君", "灰印王", "赤律天君",
    "天籍追偿", "驮碑玄兽", "无名城", "雨藏灯", "名律残印",
)

VISIBLE_KEYS = {
    "name", "title", "body", "text", "description", "failure", "failure_reason",
    "success_text", "disabled_reason", "reason", "target_name", "story_beats", "abilities",
    "trait_descriptions",
}


def iter_visible_strings(value: object, active: bool = False):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from iter_visible_strings(child, active=key in VISIBLE_KEYS)
    elif isinstance(value, list):
        for child in value:
            yield from iter_visible_strings(child, active=active)
    elif active and isinstance(value, str):
        yield value


class OriginalContentAuditTests(unittest.TestCase):
    def test_external_fiction_terms_do_not_appear_in_visible_content(self) -> None:
        roots = [ROOT / "content", ROOT / "dlc"]
        failures: list[str] = []
        for base in roots:
            for path in base.rglob("*.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                for text in iter_visible_strings(payload):
                    for term in BANNED_VISIBLE_TERMS:
                        if term in text:
                            failures.append(f"{path.relative_to(ROOT)}: {term!r} in {text!r}")
        for path in [ROOT / "README.md", *(ROOT / "docs").glob("*.md")]:
            text = path.read_text(encoding="utf-8")
            for term in BANNED_VISIBLE_TERMS:
                if term in text:
                    failures.append(f"{path.relative_to(ROOT)}: {term!r}")
        self.assertEqual([], failures, "\n".join(failures))

    def test_discarded_rewrite_terms_do_not_return_to_visible_content(self) -> None:
        failures: list[str] = []
        for base in (ROOT / "content", ROOT / "dlc"):
            for path in base.rglob("*.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                for visible_text in iter_visible_strings(payload):
                    for term in RETIRED_REWRITE_TERMS:
                        if term in visible_text:
                            failures.append(f"{path.relative_to(ROOT)}: {term!r} in {visible_text!r}")
        for path in [ROOT / "README.md", *(ROOT / "docs").glob("*.md")]:
            text = path.read_text(encoding="utf-8")
            for term in RETIRED_REWRITE_TERMS:
                if term in text:
                    failures.append(f"{path.relative_to(ROOT)}: {term!r}")
        self.assertEqual([], failures, "\n".join(failures))

    def test_legacy_story_ids_resolve_to_new_visible_names(self) -> None:
        items = {
            row["id"]: row["name"]
            for row in json.loads((ROOT / "content" / "items.json").read_text(encoding="utf-8"))["items"]
        }
        techniques = {
            row["id"]: row["name"]
            for row in json.loads((ROOT / "content" / "techniques.json").read_text(encoding="utf-8"))["techniques"]
        }
        self.assertEqual("沧海玄鼎", items["virtual_heaven_cauldron"])
        self.assertEqual("惊霄羽", items["wind_thunder_wings"])
        self.assertEqual("三元镇劫山", items["yuanhe_five_poles_mountain"])
        self.assertEqual("枯荣天剑", items["mystic_heaven_sword"])
        self.assertEqual("青木归元剑", techniques["TECH_QINGYUAN_SWORD"])
        self.assertEqual("万木生灭阵", techniques["TECH_DAGENG_SWORD_ARRAY"])


if __name__ == "__main__":
    unittest.main()
