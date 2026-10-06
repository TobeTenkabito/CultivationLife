"""Finite M3 reconnaissance mandate; military lift needs a separate permit."""
from dataclasses import dataclass

FRONTIER_ID = 'lanjiang_frontier'
FRONTIER_ACTIONS = frozenset({'frontier_inquire', 'frontier_scout', 'frontier_report', 'frontier_parley', 'frontier_wait'})
LABELS = {'frontier_inquire': '递送阵眼问讯', 'frontier_scout': '查明先遣身份',
          'frontier_report': '递交当地警讯', 'frontier_parley': '出示修复凭据', 'frontier_wait': '等候一年'}
DURATIONS = {'frontier_inquire': 2, 'frontier_scout': 2, 'frontier_report': 2, 'frontier_parley': 2, 'frontier_wait': 1}
PHASES = frozenset({'inquiry', 'review', 'gathering', 'outbound', 'scouting', 'returning', 'homeward', 'reply', 'closed'})


@dataclass(frozen=True, slots=True)
class ReconRoute:
    id: str = 'recon:demon:human:lanjiang'
    source_world: str = 'demon'
    source_location: str = 'red_marrow_city'
    destination_world: str = 'human'
    destination_location: str = 'lanjiang_steppe'
    capacity: int = 1
    maximum_realm: int = 5
    crossing_years: int = 8


ROUTE = ReconRoute()
SOURCE_FACTION = 'blood_prison'
INITIAL_RESERVE = 18000
ANNUAL_COST = 100
SCOUT_YEARS = 12
MANDATE_YEARS = 200
