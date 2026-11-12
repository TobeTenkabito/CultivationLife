"""Finite personal selection; IDs refer to original equipped/learned books."""
LIMIT = 7


def validate_ids(value, *, uninitialized=False):
    if value is None and uninitialized:
        return None
    if (not isinstance(value, list) or len(value) > LIMIT
            or any(not isinstance(key, str) or not key or len(key) > 200 for key in value)
            or len(set(value)) != len(value)):
        raise ValueError('斗法功法须为至多7部不重复的功法')
    return list(value)
