"""World route classification and content validation without transition side effects."""
from enum import Enum


class TransitionDirection(str, Enum):
    ASCEND = "ascend"
    LATERAL = "lateral"
    DESCEND = "descend"


class TransitionMode(str, Enum):
    PROGRESSION = "progression"
    SEALED_DESCENT = "sealed_descent"
    SEALED_RETURN = "sealed_return"
    PASSAGE = "passage"
    STORY = "story"
    STUDY = "study"
    RIFT = "rift"
    EXPULSION = "expulsion"


def classify_transition(profiles, source, destination):
    if source not in profiles or destination not in profiles or source == destination:
        raise ValueError("目标界面无效")
    difference = profiles[destination]["tier"] - profiles[source]["tier"]
    return TransitionDirection.ASCEND if difference > 0 else TransitionDirection.DESCEND if difference < 0 else TransitionDirection.LATERAL


def validate_transition_content(profiles, routes, realms):
    for world, profile in profiles.items():
        if (profile.get("kind") not in {"world", "spatial"} or type(profile.get("tier")) is not int
                or profile["tier"] < (-1 if profile.get('kind') == 'spatial' else 0)
                or type(profile.get("enabled")) is not bool):
            raise ValueError(f"界面 {world} 的类型、等级或开关不合法")
        for field in ("cultivation_ceiling", "passage_ceiling"):
            ceiling = profile.get(field)
            if ceiling is not None:
                rank, layer = ceiling.get("realm_index"), ceiling.get("layer")
                if (type(rank) is not int or type(layer) is not int or not 0 <= rank < len(realms)
                        or not 1 <= layer <= realms[rank].layers):
                    raise ValueError(f"界面 {world} 的修为上限不合法")
    seen = set()
    for route in routes:
        if not route.get("id") or route["id"] in seen:
            raise ValueError("跨界路线编号缺失或重复")
        seen.add(route["id"])
        direction = classify_transition(profiles, route["source"], route["destination"])
        mode = TransitionMode(route["mode"])
        if type(route.get("enabled")) is not bool:
            raise ValueError("跨界路线必须声明开关")
        if mode == TransitionMode.SEALED_RETURN:
            raise ValueError("返界授权仅能来自当前封印")
        if mode == TransitionMode.STUDY and (direction != TransitionDirection.LATERAL
                or profiles[route['source']]['tier'] != 3 or route.get('capacity') != 1
                or route.get('purpose') != 'personal_study'):
            raise ValueError('访学路线仅支持最高界面之间的单人访学')
        if 'research_visitors' in route and (mode != TransitionMode.STUDY or type(route['research_visitors']) is not bool):
            raise ValueError('研究人员许可只能用于明确的个人访学路线')
        if mode == TransitionMode.SEALED_DESCENT and direction != TransitionDirection.DESCEND:
            raise ValueError("封印下界路线必须通往低阶界面")
        if route.get("generic_cross_world") and mode != TransitionMode.SEALED_DESCENT:
            raise ValueError("普通跨界入口只能公开既有下界路线")
