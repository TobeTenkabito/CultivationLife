from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "dlc" / "guixu-tide"
CONTENT = TARGET / "content"


HUMAN = {
    "prefix": "canghai",
    "techniques": [
        "潮生归元经", "沧溟剑典", "九曲玄河经", "叠浪护心法", "归潮炼体篇",
        "照海观神术", "五岳镇流诀", "镜月遁法", "水火济鼎经", "观澜阵解",
    ],
    "equipment": [
        "定海玄珠", "归流古鼎", "潮音剑", "伏流甲", "断浪尺", "蜃光镜",
        "玄龟盾", "听潮铃", "泊舟靴", "量海斗", "沧波旗", "雨师环",
    ],
    "consumable": [
        "海眼定神丹", "九转回潮丹", "避水天符", "蜃景遁符",
        "覆海阵盘", "锁潮阵旗", "月汐护脉散", "玄浪破禁梭",
    ],
    "plant": [
        "月汐莲", "沧海芝", "玄潮参", "龙涎藻", "七星水玉花",
        "寒髓珊瑚", "蜃气果", "还阳海棠", "碧浪藤", "凝露贝母",
    ],
    "material": [
        "海心玄铁", "太阴潮晶", "沉渊铜母", "玄龟背甲", "蜃楼砂",
        "寒泉玉髓", "风蚀星铜", "水府梁木", "归墟磁石", "万年蚌珠",
    ],
    "currency_names": [
        "潮纹石匣·甲", "潮纹石匣·乙", "潮纹石匣·丙", "水府遗藏·一", "水府遗藏·二",
        "海眼灵藏·一", "海眼灵藏·二", "祖庭库藏·一", "祖庭库藏·二", "月库总匣",
    ],
    "currency": [800, 1200, 1800, 2500, 3600, 5000, 7200, 10000, 14000, 20000],
}

SPIRIT = {
    "prefix": "weir",
    "techniques": [
        "万流归虚经", "星潮界剑录", "太虚鲸息法", "无岸法身篇", "照界观神术",
        "天河折空遁", "五行界轮经", "雾海藏形书", "星槎阵枢解", "虚实两仪丹经",
    ],
    "equipment": [
        "尾闾界轮", "万流星槎", "断界天戈", "虚鲸法衣", "无岸神镜", "星潮镇尺",
        "雾海天幕", "界骸骨盾", "折空履", "归孔法环", "天河定盘", "太虚鸣钟",
    ],
    "consumable": [
        "两仪化虚丹", "星潮养神露", "断界遁符", "无岸定身符",
        "万流归孔阵盘", "界骸锁空旗", "虚实护劫散", "星槎破界梭",
    ],
    "plant": [
        "无岸道莲", "虚鲸髓芝", "星潮神参", "界隙空灵花", "天河九叶草",
        "雾海魂藻", "两仪合生果", "太虚银竹", "归孔法则藤", "界骸还元苔",
    ],
    "material": [
        "尾闾界心", "虚空母银", "星髓神晶", "界鲸脊骨", "法则琉璃",
        "天河重水", "无岸神木", "雾海幻砂", "断界罡髓", "星槎古铜",
    ],
    "currency_names": [
        "星纹石匣·甲", "星纹石匣·乙", "星纹石匣·丙", "残港遗藏·一", "残港遗藏·二",
        "界骸灵藏·一", "界骸灵藏·二", "归孔库藏·一", "归孔库藏·二", "无岸总匣",
    ],
    "currency": [50000, 80000, 120000, 180000, 260000, 360000, 500000, 700000, 900000, 1200000],
}


def dump(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def technique_rows(spec: dict, spirit: bool) -> list[dict]:
    result = []
    categories = ["spiritual"] * 10
    elements = ["water", "water", "water", "neutral", "neutral", "water", "earth", "wind", "fire", "neutral"]
    for index, name in enumerate(spec["techniques"], 1):
        grade = (5 + (index >= 8)) if spirit else (3 + (index >= 4) + (index >= 9))
        combat = (14000 + index * 5200) if spirit else (900 + index * 520)
        row = {
            "id": f"TECH_GUIXU_{spec['prefix'].upper()}_{index:02d}",
            "name": name, "path": "dao", "element": elements[index - 1],
            "grade": grade, "level": 1,
            "opportunity_bonus": round((0.40 if spirit else 0.22) + index * (0.018 if spirit else 0.012), 3),
            "hp_bonus": round((0.36 if spirit else 0.18) + index * 0.012, 3),
            "mp_bonus": round((0.42 if spirit else 0.20) + index * 0.014, 3),
            "combat_bonus": combat, "karma_multiplier": 1.0,
        }
        if categories[index - 1] != "spiritual":
            row["category"] = categories[index - 1]
            if categories[index - 1] == "body":
                row["body_breakthrough_bonus"] = 0.08 if spirit else 0.05
                row["body_bonus_max_layer"] = 80 if spirit else 45
            else:
                row["divine_sense_bonus"] = 0.24 if spirit else 0.14
        result.append(row)
    return result


def item_rows(spec: dict, spirit: bool) -> list[dict]:
    rows: list[dict] = []
    scale = 20 if spirit else 1
    for index, name in enumerate(spec["equipment"], 1):
        power = (18000 + index * 19000) if spirit else (600 + index * 1150)
        rows.append({
            "id": f"guixu_{spec['prefix']}_equipment_{index:02d}", "name": name,
            "combat_bonus": power, "hp_bonus": index * 18 * scale, "mp_bonus": index * 20 * scale,
            "description": f"归墟潮汐中保存下来的{name}；战斗力 +{power:,}。",
            "tags": ["guixu_tide", spec["prefix"], "equipment", "treasure"],
        })
    for index, name in enumerate(spec["consumable"], 1):
        row = {
            "id": f"guixu_{spec['prefix']}_consumable_{index:02d}", "name": name,
            "description": f"封存在归墟中的{name}，服用后恢复状态并补益当前境界机缘。",
            "tags": ["guixu_tide", "guixu_consumable", spec["prefix"], "consumable", "pill" if index <= 2 else "talisman"],
        }
        rows.append(row)
    for index, name in enumerate(spec["plant"], 1):
        rows.append({
            "id": f"guixu_{spec['prefix']}_plant_{index:02d}", "name": name,
            "hp_bonus": index * 12 * scale, "mp_bonus": index * 14 * scale,
            "opportunity_bonus": round(0.01 + index * 0.004, 3),
            "plant_id": f"guixu_{spec['prefix']}_plant_{index:02d}",
            "plant_years": (2000 + index * 500) if spirit else (100 + index * 40),
            "plant_kind": "guixu", "plant_value": spec["currency"][min(index - 1, 9)],
            "description": f"{name}随归墟潮汐沉浮，可入药、炼器或直接温养肉身元神。",
            "tags": ["guixu_tide", spec["prefix"], "spirit_plant", "treasure"],
        })
    for index, name in enumerate(spec["material"], 1):
        rows.append({
            "id": f"guixu_{spec['prefix']}_material_{index:02d}", "name": name,
            "combat_bonus": (index * 2500) if spirit else (index * 120),
            "description": f"{name}是归墟中罕见的炼器、阵法与本命法宝材料。",
            "tags": ["guixu_tide", spec["prefix"], "crafting_material", "treasure"],
        })
    return rows


def layer_weights(category: str, index: int) -> dict[str, int]:
    if category == "currency" and index <= 3:
        return {"outer": 6, "middle": 3, "inner": 1, "final": 0}
    if index <= 3:
        return {"outer": 3, "middle": 4, "inner": 2, "final": 1}
    if index <= 7:
        return {"outer": 1, "middle": 3, "inner": 4, "final": 2}
    return {"outer": 0, "middle": 1, "inner": 3, "final": 6}


def pool_rows(spec: dict) -> list[dict]:
    rows = []
    for index, name in enumerate(spec["techniques"], 1):
        rows.append({
            "id": f"{spec['prefix']}_technique_{index:02d}", "name": name,
            "category": "technique", "kind": "technique",
            "content_id": f"TECH_GUIXU_{spec['prefix'].upper()}_{index:02d}",
            "tier": "major" if index <= 2 else "normal", "value": spec["currency"][min(index, 9)],
            "layer_weights": layer_weights("technique", index),
        })
    for category in ("equipment", "consumable", "plant", "material"):
        for index, name in enumerate(spec[category], 1):
            rows.append({
                "id": f"{spec['prefix']}_{category}_{index:02d}", "name": name,
                "category": category, "kind": "item",
                "content_id": f"guixu_{spec['prefix']}_{category}_{index:02d}",
                "tier": "major" if (category in {"equipment", "plant", "material"} and index <= (2 if category == "equipment" else 1)) else "normal",
                "value": spec["currency"][min(index - 1, 9)],
                "layer_weights": layer_weights(category, index),
            })
    for index, (name, quantity) in enumerate(zip(spec["currency_names"], spec["currency"]), 1):
        rows.append({
            "id": f"{spec['prefix']}_currency_{index:02d}", "name": name,
            "category": "currency", "kind": "item_bundle", "content_id": "spirit_stone",
            "quantity": quantity, "tier": "major" if index == 10 else "normal", "value": quantity,
            "layer_weights": layer_weights("currency", index),
        })
    return rows


def layers(names: list[str], efficiencies: list[list[float]]) -> list[dict]:
    ids = ["outer", "middle", "inner", "final", "secret"]
    travel = [1, 3, 4, 5, 2]
    roster = [12, 8, 5, 3, 0]
    return [{
        "id": layer_id, "name": name, "travel_days": travel[index], "roster_size": roster[index],
        "qi_gain_efficiencies": dict(zip(["spirit", "demon", "monster", "yin"], efficiencies[index])),
    } for index, (layer_id, name) in enumerate(zip(ids, names))]


def main() -> None:
    CONTENT.mkdir(parents=True, exist_ok=True)
    dump(TARGET / "manifest.json", {
        "schema_version": 1, "api_version": 1, "id": "official.guixu-tide",
        "name": "归墟之潮：九死一生", "version": "0.1.0", "kind": "dlc",
        "enabled": True, "load_order": 140, "requires": [],
        "description": "人界与灵界各一座周期归墟，含限时夺宝、修士争夺、被困与苦修破关。",
    })
    dump(CONTENT / "items.json", {"schema_version": 1, "items": [
        *item_rows(HUMAN, False), *item_rows(SPIRIT, True),
    ]})
    dump(CONTENT / "techniques.json", {"schema_version": 1, "techniques": [
        *technique_rows(HUMAN, False), *technique_rows(SPIRIT, True),
    ]})
    dump(CONTENT / "guixu_tide.json", {
        "schema_version": 1,
        "settings": {
            "draw_per_cycle": 6,
            "action_days": {"search": 2, "combat": 1, "negotiate": 1, "event": 1},
            "recruit_cap": 2, "secret_clue_threshold": 3,
            "secret_unlock_probability_per_year": 0.05, "enmity_kappa": 0.5,
        },
        "dungeons": [
            {
                "id": "guixu_human_canghai", "name": "沧海归墟", "world": "human",
                "entry_location_id": "lancang_sea", "max_entry_rank": [4, 9], "eject_rank": [5, 1],
                "period_years": 100, "first_open_year": 100, "announce_lead_years": 10, "window_days": 90,
                "layers": layers(
                    ["破碎泊港", "倒悬水府", "无光海眼", "沉没祖庭", "月下潮库"],
                    [[1.35, .55, .75, .90], [1.55, .60, .82, 1.05], [1.75, .70, .95, 1.20], [2.0, .75, 1.05, 1.30], [2.15, .80, 1.10, 1.45]],
                ),
                "treasure_pool": pool_rows(HUMAN),
            },
            {
                "id": "guixu_spirit_weir", "name": "虚天尾闾", "world": "spirit",
                "entry_location_id": "mist_sea_isles", "max_entry_rank": [6, 9], "eject_rank": [7, 1],
                "period_years": 200, "first_open_year": 200, "announce_lead_years": 20, "window_days": 120,
                "layers": layers(
                    ["雾海残港", "界骸回廊", "星潮断层", "万流归孔", "无岸法藏"],
                    [[1.85, .75, 1.10, 1.10], [2.10, .85, 1.20, 1.25], [2.40, .95, 1.35, 1.40], [2.75, 1.05, 1.50, 1.60], [3.0, 1.15, 1.65, 1.80]],
                ),
                "treasure_pool": pool_rows(SPIRIT),
            },
        ],
    })
    dump(CONTENT / "guixu_events.json", {"schema_version": 1, "events": [
        {"id": "EVT_GUIXU_ANNOUNCE", "version": 1, "title": "归墟潮讯", "body": "{dungeon_name}将在{lead_years}年后开启。本届潮眼显露的重宝为：{major_treasures}。", "category": "guixu", "tags": ["manual_only", "guixu", "announcement"], "weight": 0, "conditions": {}, "choices": [{"id": "acknowledge", "text": "记下潮讯", "effects": []}]},
        {"id": "EVT_GUIXU_OPEN", "version": 1, "title": "归墟门开", "body": "{dungeon_name}已经开启，潮门只会稳定{window_days}天。入口位于{entry_name}。", "category": "guixu", "tags": ["manual_only", "guixu", "open"], "weight": 0, "conditions": {}, "choices": [{"id": "acknowledge", "text": "查看归墟面板", "effects": []}]},
    ]})
    achievements = [
        ("guixu_first_entry", "初入归墟", "首次进入任一归墟副本", "SYS_GUIXU_ENTER", "entered"),
        ("guixu_full_return", "满载而归", "携至少三条本届宝物成功返程", "SYS_GUIXU_RETURN", "full_return"),
        ("guixu_narrow_escape", "九死一生", "剩余不足三天时成功返程", "SYS_GUIXU_RETURN", "narrow_escape"),
        ("guixu_break_free", "破关而出", "被困后突破归墟修为边界", "SYS_GUIXU_EJECT", "breakthrough"),
        ("guixu_secret", "别有洞天", "首次进入归墟秘层", "SYS_GUIXU_MOVE", "secret"),
        ("guixu_negotiate", "虎口夺食", "首次通过宝物交涉取得宝物", "SYS_GUIXU_NEGOTIATE", "traded"),
        ("guixu_recruit", "同舟共济", "首次拉拢归墟修士", "SYS_GUIXU_RECRUIT", "joined"),
        ("guixu_last_treasure", "掘地三尺", "亲手取得一座归墟主池最后的宝物", "SYS_GUIXU_TREASURE", "last_treasure"),
        ("guixu_die_trapped", "坐化归墟", "被困期间寿尽坐化", "SYS_GUIXU_TRAPPED_DEATH", "dead"),
    ]
    dump(CONTENT / "achievements.json", {"schema_version": 1, "achievements": [{
        "id": row[0], "name": row[1], "description": row[2], "category": "cultivation",
        "condition": {"history": {"event_id": row[3], "result": row[4]}},
    } for row in achievements]})


if __name__ == "__main__":
    main()
