"""Finite M3 reconnaissance mandate; military lift needs a separate permit."""
from ...definition_data import definition as _content_definition
from dataclasses import dataclass

FRONTIER_ID = _content_definition(__name__, "FRONTIER_ID")
FRONTIER_ACTIONS = frozenset({'frontier_inquire', 'frontier_scout', 'frontier_report', 'frontier_parley', 'frontier_wait'})
LABELS = {'frontier_inquire': '递送阵眼问讯', 'frontier_scout': '查明先遣身份',
          'frontier_report': '递交当地警讯', 'frontier_parley': '出示修复凭据', 'frontier_wait': '等候一年'}
DURATIONS = {'frontier_inquire': 2, 'frontier_scout': 2, 'frontier_report': 2, 'frontier_parley': 2, 'frontier_wait': 1}
PHASES = frozenset({'inquiry', 'review', 'gathering', 'outbound', 'scouting', 'returning', 'homeward', 'reply', 'closed'})


RECON_ROUTE = _content_definition(__name__, "RECON_ROUTE")


@dataclass(frozen=True, slots=True)
class ReconRoute:
    id: str = RECON_ROUTE["id"]
    source_world: str = RECON_ROUTE["source_world"]
    source_location: str = RECON_ROUTE["source_location"]
    destination_world: str = RECON_ROUTE["destination_world"]
    destination_location: str = RECON_ROUTE["destination_location"]
    capacity: int = RECON_ROUTE["capacity"]
    maximum_realm: int = RECON_ROUTE["maximum_realm"]
    crossing_years: int = RECON_ROUTE["crossing_years"]


ROUTE = ReconRoute()
SOURCE_FACTION = _content_definition(__name__, "SOURCE_FACTION")
INITIAL_RESERVE = _content_definition(__name__, "INITIAL_RESERVE")
ANNUAL_COST = _content_definition(__name__, "ANNUAL_COST")
SCOUT_YEARS = _content_definition(__name__, "SCOUT_YEARS")
MANDATE_YEARS = _content_definition(__name__, "MANDATE_YEARS")
