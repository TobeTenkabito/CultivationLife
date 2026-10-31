"""Detached plain-data snapshots with standard deepcopy semantics for extensions.

Only exact builtin dictionaries/lists and immutable scalar types take the fast
path. A fresh memo per boundary preserves internal aliases and cycles; other
types retain their registered deepcopy/reduction behavior. No game cache.
"""
import copy

_ATOMIC = frozenset((str, int, float, bool, type(None), bytes))
_MISSING = object()


def copy_plain_data(value):
    # Keep copied source containers alive even if an extension's __deepcopy__
    # mutates the source graph. Memoized IDs must not be recycled mid-copy.
    return _clone(value, {}, [])


def _clone(value, memo, alive):
    kind = type(value)
    if kind in _ATOMIC:
        return value
    previous = memo.get(id(value), _MISSING)
    if previous is not _MISSING:
        return previous
    if kind is dict:
        result = {}
        memo[id(value)] = result
        alive.append(value)
        for key, child in value.items():
            # Assignment in stdlib deepcopy evaluates its value before key.
            # Extension hooks may observe that order or share memo entries.
            copied_child = child if type(child) in _ATOMIC else _clone(child, memo, alive)
            copied_key = key if type(key) in _ATOMIC else copy.deepcopy(key, memo)
            result[copied_key] = copied_child
        return result
    if kind is list:
        result = []
        memo[id(value)] = result
        alive.append(value)
        for child in value:
            result.append(child if type(child) in _ATOMIC else _clone(child, memo, alive))
        return result
    return copy.deepcopy(value, memo)
