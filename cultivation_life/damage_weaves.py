"""Validated operations that redistribute elemental shares of one attack."""

FIVE = ("metal", "wood", "earth", "water", "fire")
LABELS = dict(physical="物理", metal="金", wood="木", water="水", fire="火", earth="土",
              yin="阴", yang="阳", wind="风", thunder="雷")


def validate_weave(row):
    """Validate an elemental recipe once at content load time."""
    elements = LABELS.keys() - {"physical"}
    selectors = elements | {"own_ward", "target_ward", "sole_five", "other_required", "reverse_five", "counter_five"}
    operations = {
        "transfer": ({"source", "target"}, {"fraction", "excess_over", "require_target_share"}),
        "consolidate": ({"target"}, set()),
        "equalize": ({"source", "target"}, set()),
        "larger_to_target": ({"source", "target"}, set()),
        "spread": ({"source", "among"}, set()),
        "equalize_extremes": ({"among", "minimum"}, set()),
    }
    if not isinstance(row, dict) or row.get("op") not in operations:
        raise ValueError("未知配气运算")
    required, optional = operations[row["op"]]
    conditions = {"requires", "own_wards", "target_wards", "require_own_share", "pure"}
    if not required <= row.keys() or row.keys() - required - optional - conditions - {"op"}:
        raise ValueError("配气字段缺失或无效")
    for field in ("requires", "own_wards", "target_wards", "among"):
        if field in row:
            values = row[field]
            if not isinstance(values, list) or not values or len(values) != len(set(values)) or set(values) - elements:
                raise ValueError(f"配气元素列表无效：{field}")
    for field in ("source", "target"):
        if field in row and row[field] not in selectors:
            raise ValueError(f"配气选择器无效：{field}")
    for field in ("require_own_share", "require_target_share", "pure"):
        if field in row and type(row[field]) is not bool:
            raise ValueError(f"配气条件须为布尔值：{field}")
    if "other_required" in (row.get("source"), row.get("target")) and not row.get("requires"):
        raise ValueError("配气选择器须指定所需元素")
    if row["op"] == "transfer":
        if ("fraction" in row) == ("excess_over" in row):
            raise ValueError("配气转移须指定比例或差额")
        if "fraction" in row and (type(row["fraction"]) not in (int, float) or not 0 < row["fraction"] <= 1):
            raise ValueError("配气转移比例须在 (0, 1] 范围内")
        if "excess_over" in row and row["excess_over"] not in elements:
            raise ValueError("配气差额比较元素无效")
    if "minimum" in row and (type(row["minimum"]) is not int or not 2 <= row["minimum"] <= len(row["among"])):
        raise ValueError("配气最少元素数无效")
    return row


def woven_profile(profile, recipe, ward, own_ward):
    if (recipe.get("pure") and len(profile) != 1
            or "own_wards" in recipe and own_ward not in recipe["own_wards"]
            or "target_wards" in recipe and ward not in recipe["target_wards"]
            or recipe.get("require_own_share") and own_ward not in profile
            or any(e not in profile for e in recipe.get("requires", ()))):
        return profile

    def element(selector):
        if selector == "own_ward":
            return own_ward
        if selector == "target_ward":
            return ward
        if selector == "other_required":
            return next((e for e in recipe["requires"] if e != own_ward), None)
        if selector == "sole_five":
            only = next(iter(profile))
            return only if len(profile) == 1 and only in FIVE else None
        if selector in {"reverse_five", "counter_five"}:
            if ward in FIVE:
                step = 1 if selector == "reverse_five" else -1
                return FIVE[(FIVE.index(ward) + step) % len(FIVE)]
            return None
        return selector

    shares = dict(profile)
    op = recipe["op"]
    if op == "equalize_extremes":
        present = sorted((e for e in recipe["among"] if e in shares), key=shares.get)
        if len(present) >= recipe["minimum"]:
            lo, hi = present[0], present[-1]
            shares[lo] = shares[hi] = (shares[lo] + shares[hi]) / 2
        return shares
    if op == "consolidate":
        target = element(recipe["target"])
        if target not in shares:
            return shares
        weights = {target: sum(value for key, value in shares.items() if key != "physical")}
        if "physical" in shares:
            weights["physical"] = shares["physical"]
        return weights
    source = element(recipe["source"])
    if source not in shares or source == "physical":
        return shares
    if op == "spread":
        others = [e for e in recipe["among"] if e in shares and e != source]
        if others:
            portion = shares.pop(source) / len(others)
            for e in others:
                shares[e] += portion
        return shares
    target = element(recipe["target"])
    if target is None or target in {source, "physical"}:
        return shares
    if op == "transfer":
        if recipe.get("require_target_share") and target not in shares:
            return shares
        if "fraction" in recipe:
            amount = shares[source] * recipe["fraction"]
        else:
            baseline = shares.get(recipe["excess_over"])
            if baseline is None or baseline >= shares[source]:
                return shares
            amount = shares[source] - baseline
        shares[source] -= amount
        if not shares[source]:
            del shares[source]
        shares[target] = shares.get(target, 0.) + amount
    elif target in shares:
        if op == "equalize":
            shares[source] = shares[target] = (shares[source] + shares[target]) / 2
        elif shares[source] > shares[target]:
            shares[source], shares[target] = shares[target], shares[source]
    return shares
