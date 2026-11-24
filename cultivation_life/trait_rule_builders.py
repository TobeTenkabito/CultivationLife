"""Content helpers for the version-three combat rule vocabulary."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Signature:
    description: str
    rules: tuple = ()


def rule(name, trigger, *actions, **options):
    return dict(id=name, trigger=trigger, actions=list(actions), **options)


def fact(key, op, value):
    return dict(fact=key, op=op, value=value)


def modify(channel, value):
    return dict(op="modify", channel=channel, value=value)


def status(name, channel, value, duration, **options):
    return dict(op="status", key=name, duration=duration, modifiers=[dict(channel=channel, value=value)], **options)


def adjust(stat, value):
    return dict(op="adjust", stat=stat, value=value)


ATTACK = fact("role", "eq", "attacker")
DEFEND = fact("role", "eq", "defender")
HIT = {"all": [ATTACK, fact("event.actual_loss", "gt", 0)]}
ONCE = {"per_battle": 1}
