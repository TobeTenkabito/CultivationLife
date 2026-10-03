"""Core loading, validation and projections must not import their consumers."""
import copy
from dataclasses import FrozenInstanceError
import importlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools.check_module_dependencies import violations


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('source,target', [
    ('models', 'system.cultivation_ranks'),
    ('models', 'system.monster_identity'),
    ('system.combat.migration', 'rules'),
    ('content_registry', 'event_repository'),
    ('content_registry', 'system.map_system'),
    ('content_registry', 'achievements'),
    ('event_catalog', 'content_registry'),
    ('system.combat.lifecycle_schema', 'system.combat.npc_lifecycle'),
    ('system.ghost_resources', 'system.ghost_system'),
    ('system.crafted_artifact_rules', 'rules'),
    ('system.npc_cultivation', 'system.cultivation_ranks'),
    ('system.cultivation_reserves', 'system.cultivation_policy'),
])
def test_checker_rejects_core_back_references(source, target):
    source, target = (f'cultivation_life.{name}' for name in (source, target))
    assert violations([(source, target, 7)]) == [dict(source=source, target=target, line=7)]


def test_dependency_command_fails_for_any_new_cycle(tmp_path):
    package = tmp_path / 'cultivation_life'
    package.mkdir()
    (package / 'a.py').write_text('from .b import value\nvalue = 1\n')
    (package / 'b.py').write_text('from .a import value\n')
    result = subprocess.run([sys.executable, str(ROOT / 'tools/check_module_dependencies.py'),
                             '--root', str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 1
    assert json.loads(result.stdout)['cycles'] == [2]


@pytest.mark.parametrize('code', [
    # Decode an old save, including ancestry, sense and legacy combat keys,
    # before importing any content loader or gameplay module.
    """
from cultivation_life.models import GameState, SectNpc
game = GameState.from_dict(dict(id='old', seed=17, created_at='', updated_at='',
    player=dict(name='Old save', spirit_root='supreme_metal', path='monster', realm_index=5,
                divine_sense_rank=10),
    last_combat_report={'active_domain': 'old-id'}))
npc = SectNpc('old-npc', 'Monster', '', 5, 1, 30, 100, path='monster')
assert npc.monster_species_id
assert game.player.divine_sense_rank == 13
assert game.last_combat_report == {'active_voisinage': 'old-id'}
assert 'cultivation_life.content_registry' not in sys.modules
assert 'cultivation_life.rules' not in sys.modules
""",
    """
from cultivation_life.event_catalog import EventCatalog
from cultivation_life.achievement_definitions import load_achievement_definitions
from cultivation_life.system.map_definition import MapDefinition
from cultivation_life.system.world_transition_schema import validate_transition_content
from cultivation_life.system.combat.lifecycle_schema import validate_lifecycle
EventCatalog.from_documents([], catalogs={})
load_achievement_definitions({'schema_version': 1, 'achievements': []})
validate_lifecycle({})
assert 'cultivation_life.content_registry' not in sys.modules
assert 'cultivation_life.models' not in sys.modules
""",
    """
from cultivation_life.content_registry import CONTENT
assert CONTENT.realms
assert 'cultivation_life.rules' not in sys.modules
assert 'cultivation_life.event_repository' not in sys.modules
assert 'cultivation_life.system.map_system' not in sys.modules
assert 'cultivation_life.system.combat.npc_lifecycle' not in sys.modules
assert 'cultivation_life.achievements' not in sys.modules
""",
], ids=['legacy-save', 'validators', 'registry'])
def test_foundations_work_in_a_fresh_interpreter(code):
    result = subprocess.run([sys.executable, '-c', 'import sys\n' + code
                             + "\nassert 'cultivation_life.engine' not in sys.modules"],
                            cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('facade,shared,names', [
    ('achievements', 'achievement_definitions', 'load_achievement_definitions'),
    ('content_registry', 'errors', 'ContentError'),
    ('rules', 'combat_benchmarks', 'expected_combat_power standard_combat_power_dlc_bonus'),
    ('rules', 'cultivation_costs', 'opportunity_required'),
    ('system.monster_identity', 'ancestry', 'SPECIES stable_species'),
    ('system.cultivation_ranks', 'cultivation_coordinates', 'rank_for describe body_rank legacy_sense'),
    ('system.cultivation_ranks', 'system.npc_cultivation', 'ensure_npc npc_voisinage_limit npc_golden_light'),
    ('system.cultivation_policy', 'system.cultivation_reserves', 'opportunity_unbounded immortal_reserve'),
    ('system.crafting_system', 'system.crafted_artifact_rules',
     'active_crafted_artifacts crafted_artifact_bonuses effective_artifact_combat_bonus'),
    ('system.ghost_system', 'system.ghost_resources',
     'ensure_ghost_cultivation_state canonical_intrinsic_hp effective_intrinsic_hp ghost_soul_effects'),
    ('system.combat.npc_lifecycle', 'system.combat.lifecycle_schema', 'validate_lifecycle'),
    ('system.combat.npc_lifecycle', 'system.combat.actor_state', 'read _write'),
    ('system.world_transition_system', 'system.world_transition_schema',
     'TransitionDirection TransitionMode classify_transition validate_transition_content'),
    ('system.map_system', 'system.map_definition', 'MapContentError'),
])
def test_original_paths_export_the_shared_implementation(facade, shared, names):
    original = importlib.import_module('cultivation_life.' + facade)
    implementation = importlib.import_module('cultivation_life.' + shared)
    for name in names.split():
        assert getattr(original, name) is getattr(implementation, name)


def test_event_repository_keeps_explicit_catalogs_overrides_and_subclass_dispatch(monkeypatch):
    from cultivation_life import content_registry
    from cultivation_life.errors import ContentError
    from cultivation_life.event_catalog import EventCatalog
    from cultivation_life.event_repository import EventRepository

    catalogs = dict(items={'local': {}}, techniques={}, factions={}, world_npcs={})
    event = dict(id='event', title='Original', choices=[dict(id='take', effects=[
        dict(type='add_item', item_id='local')])])
    documents = [('local.json', dict(schema_version=1, events=[event]))]
    before = copy.deepcopy(documents)
    with pytest.raises(ContentError, match='local'):
        EventRepository.from_documents(documents, catalogs=dict(catalogs, items={}))
    explicit = EventCatalog.from_documents(documents, catalogs=catalogs)

    class CustomRepository(EventRepository):
        validated = []

        @classmethod
        def _validate_event(cls, row, definitions):
            cls.validated.append(row['id'])
            return super()._validate_event(row, definitions)

    monkeypatch.setattr(content_registry, 'ITEM_CATALOG', catalogs['items'])
    default = CustomRepository.from_documents(documents)
    assert isinstance(default, CustomRepository)
    assert default.events == explicit.events
    assert CustomRepository.validated == ['event']
    assert documents == before
    override = [('override.json', dict(schema_version=1, events=[dict(event, title='Replacement')]))]
    with pytest.raises(ContentError):
        EventRepository.from_documents(documents + override, catalogs=catalogs)
    updated = EventRepository.from_documents(documents + override, catalogs=catalogs, allow_overrides=True)
    assert len(updated.events) == 1
    assert updated.by_id['event']['title'] == 'Replacement'
    with pytest.raises(FrozenInstanceError):
        updated.events = ()
    with pytest.raises(FrozenInstanceError):
        updated.extra = 'cannot attach fields to a frozen repository'


def test_asura_quotes_and_resource_switches_follow_the_runtime_gate(monkeypatch):
    from cultivation_life.models import Player
    from cultivation_life.rules import breakthrough_opportunity_required, opportunity_required
    from cultivation_life.system import asura
    from cultivation_life.system.cultivation_reserves import opportunity_unbounded
    from cultivation_life.system.ghost_resources import canonical_intrinsic_hp

    player = Player('Demonic', 'supreme_metal', path='demonic', world='asura', realm_index=9)
    player.asura_cultivation['body_level'] = 2
    monkeypatch.setattr(asura, 'enabled', lambda: True)
    assert asura.public_meridians(player)['breakthrough_cost'] == breakthrough_opportunity_required(player)
    enabled_hp = canonical_intrinsic_hp(player)
    assert opportunity_unbounded(player)
    monkeypatch.setattr(asura, 'enabled', lambda: False)
    assert breakthrough_opportunity_required(player) == opportunity_required(player)
    assert asura.public_meridians(player) == {'available': False}
    assert not opportunity_unbounded(player)
    assert enabled_hp - canonical_intrinsic_hp(player) == 2400
