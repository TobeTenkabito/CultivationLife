"""Validate declarative Dharma content before an extension can be enabled."""
import math


def validate_buddhist_content(document, documents):
    config = document.get("settings", {})
    def require(condition, message):
        if not condition:
            raise ValueError("佛修内容：" + message)
    def numeric(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    positive = ("grace_units", "upkeep_follower_scale", "annual_karma_cap", "follower_income_scale",
                "follower_income_coefficient", "temple_tier_scale", "permission_fee", "permission_years",
                "technique_level_score", "great_threshold", "success_threshold", "normal_threshold")
    require(all(numeric(config.get(key)) and config[key] > 0 for key in positive), "年限、门槛与收益参数须为正数")
    probability = ("negative_combat_cap", "upkeep_floor", "negative_chance_cap", "negative_chance_base",
                   "negative_chance_scale", "unlicensed_risk", "intervention_chance", "intervention_wanted_chance",
                   "intervention_purge_chance", "intervention_dispersion_chance", "intervention_retention")
    require(all(numeric(config.get(key)) and 0 <= config[key] <= 1 for key in probability), "比例须在 0 至 1 之间")
    require(config["great_threshold"] > config["success_threshold"] > config["normal_threshold"], "法会门槛顺序错误")
    temples = config.get("temples", [])
    require(len(temples) == 4, "寺庙须配置零至三级")
    for temple in temples:
        require(all(numeric(temple.get(key)) for key in ("floor", "decay", "cost")), "寺庙参数非法")
        require(0 < temple["decay"] < 1 and temple["floor"] >= 0 and temple["cost"] >= 0, "寺庙须持续衰减且保底非负")
    blessings = config.get("blessings", {})
    require(set(blessings) == {"market", "commission", "natal", "stipend", "karma_decay", "sha_decay"}, "须完整配置六项加持")
    for key, row in blessings.items():
        require(numeric(row.get("upkeep")) and row["upkeep"] > 0, "加持开支须为正数")
        if key in {"market", "commission", "natal"}:
            require(numeric(row.get("multiplier")) and 0 < row["multiplier"] <= 1, "折扣参数非法")
    require(set(config.get("outcomes", {})) == {"great", "success", "normal", "failure"}, "法会须有四档结算")
    ids = {row["id"] for name, doc in documents.items() if name.endswith("_events.json") for row in doc.get("events", [])}
    require(len(config.get("reincarnation_trial_events", [])) == 9, "轮回飞升须配置九重劫关")
    for key in ("positive_events", "negative_events", "reincarnation_trial_events"):
        require(bool(config.get(key)) and set(config[key]) <= ids, "法会引用了不存在的事件")
    for event in documents.get("buddhist_events.json", {}).get("events", []):
        require({"manual_only", "all_realms"} <= set(event.get("tags", [])), "法会事件必须由会话触发")
        for choice in event.get("choices", []):
            for effect in choice.get("effects", []):
                require(effect.get("type") == "buddhist_assembly" and effect.get("action") in {"spar", "debate", "teach", "listen", "withdraw"}, "未知法会效果")
