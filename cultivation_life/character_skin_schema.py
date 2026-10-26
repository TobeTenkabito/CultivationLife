"""Pure validation of cosmetic unlock references."""
def validate(state):
    if not isinstance(state, dict) or set(state) - {'unlocked', 'selected'}:
        raise ValueError('皮肤记录无效')
    rows, selected = state.get('unlocked', []), state.get('selected')
    if (not isinstance(rows, list) or len(rows) > 512 or any(not isinstance(s, str) or len(s) > 150 for s in rows)
            or selected is not None and (not isinstance(selected, str) or selected not in rows)):
        raise ValueError('皮肤解锁记录无效')
    return dict(unlocked=list(dict.fromkeys(rows)), selected=selected)
