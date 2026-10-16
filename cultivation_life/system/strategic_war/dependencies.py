from dataclasses import dataclass
from typing import Callable, Any


@dataclass(frozen=True, slots=True)
class StrategicWarDependencies:
    maps: Any
    start_campaign: Callable
    advance_campaigns: Callable
    find_person: Callable
    members: Callable
    has_sect_voice: Callable
    has_family_voice: Callable
    has_race_voice: Callable
    imprisoned: Callable
    power: Callable
    recruit: Callable
    peace_preview: Callable
    vote_probability: Callable
    prepare_formations: Callable
