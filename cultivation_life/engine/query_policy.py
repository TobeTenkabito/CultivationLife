"""Narrow read capabilities; custom storage/account adapters keep serialization."""
from ..storage import supports_committed_summaries
from ..achievements import AchievementSystem, GlobalMetadataStore


def _ports(kind, names):
    # Capture identities once. A class-level replacement is an adapter too.
    return tuple((name, getattr(kind, name)) for name in names)


_ACHIEVEMENT_PORTS = _ports(AchievementSystem, ('public_catalog',))
_METADATA_PORTS = _ports(GlobalMetadataStore, ('read', 'unlock', '_write'))


def _native(value, kind, ports):
    return type(value) is kind and all(
        getattr(getattr(value, name, None), '__func__', None) is original for name, original in ports)


def committed_save_summaries(engine):
    return supports_committed_summaries(engine.store)


def committed_achievements(engine):
    system = engine.achievements
    return (_native(system, AchievementSystem, _ACHIEVEMENT_PORTS)
            and _native(system.metadata, GlobalMetadataStore, _METADATA_PORTS))
