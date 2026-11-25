"""Finite local incidents in the eleven ordinary worlds; no content imports."""
from ...definition_data import definition as _content_definition
from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class Response:
    label: str
    years: int
    stones: int
    mana: float
    effect: str
    allowance: int
    finding: str


@dataclass(frozen=True, slots=True)
class Incident:
    id: str
    world: str
    world_name: str
    name: str
    location: str
    location_name: str
    field: str
    field_name: str
    rank: int
    survey_years: int
    glimpse: str
    evidence: str
    responses: tuple[Response, Response]
    category: str = 'local'


INCIDENTS = _content_definition(__name__, "INCIDENTS", Incident, Response)
# Field anomalies and conflict relief have their own records, separate from the
# original local dossiers. They share the transactional fieldwork lifecycle.
def regional_cases():
    local_cases = {case.id: case for case in INCIDENTS}
    rows = []
    for row in _content_definition(__name__, "REGIONAL_CASES", Response):
        local = local_cases[row.pop('source')]
        rows.append(replace(local, **row))
    return tuple(rows)


REGIONAL_CASES = regional_cases()
ALL_INCIDENTS = INCIDENTS + REGIONAL_CASES
BY_ID = {row.id: row for row in ALL_INCIDENTS}
INCIDENT_IDS = frozenset(BY_ID)
INCIDENT_ACTIONS = frozenset({'incident_survey', 'incident_preserve', 'incident_seal', 'incident_review'})
LABELS = {'incident_survey': '核对本地旧记', 'incident_preserve': '保留并修复',
          'incident_seal': '隔离并收束', 'incident_review': '复核处理结果'}


def response(desc, action):
    return desc.responses[0 if action == 'incident_preserve' else 1]


def terms(desc, action):
    if action == 'incident_survey':
        return desc.survey_years, 0, 0
    if action == 'incident_review':
        return 2, 0, 0
    row = response(desc, action)
    return row.years, row.stones, row.mana
