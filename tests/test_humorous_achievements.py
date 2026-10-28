"""Humorous achievements use original diplomacy, inventory and progression facts."""
import copy
from pathlib import Path

import pytest

from cultivation_life.achievement_definitions import load_achievement_definitions
from cultivation_life.achievement_facts import world_sects_submit
from cultivation_life.achievements import AchievementSystem
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState, Player, SectState
from cultivation_life.rules import add_item
from cultivation_life.world_state import race_pair


ROOT = Path(__file__).resolve().parents[1]


def unified_state():
    game = GameState('humor-test', 1, Player('沈砚', 'supreme_fire'), '', '')
    game.sects = {key: SectState(key, key) for key in ('own', 'first', 'second')}
    game.player.faction_id = 'own'
    for target in ('first', 'second'):
        game.sect_relations[race_pair('own', target)] = {
            'status': 'vassal', 'overlord': 'own', 'subject': target,
        }
    return game


def test_unification_is_read_only_and_local():
    game = unified_state()
    game.sects['remote'] = SectState('remote', '远宗', world='spirit')
    game.sects['gone'] = SectState('gone', '旧宗', extinct=True)
    game.sects['court'] = SectState('court', '机构', kind='institution')
    game.sects['clan'] = SectState('clan', '外族', kind='family')
    before = copy.deepcopy(game.to_dict())
    assert world_sects_submit(game)
    assert world_sects_submit(game)
    assert game.to_dict() == before


@pytest.mark.parametrize('invalid', [
    'alliance', 'war', 'neutral', 'truce', 'reversed', 'missing_subject',
    'missing_overlord', 'missing_relation', 'indirect', 'independent',
    'owner_extinct', 'owner_remote', 'no_membership', 'institution',
])
def test_unification_rejects_incomplete_or_wrong_direction(invalid):
    game = unified_state()
    relation = game.sect_relations[race_pair('own', 'second')]
    if invalid in {'alliance', 'war', 'neutral', 'truce'}:
        relation['status'] = invalid
    elif invalid == 'reversed':
        relation.update(overlord='second', subject='own')
    elif invalid == 'missing_subject':
        relation.pop('subject')
    elif invalid == 'missing_overlord':
        relation.pop('overlord')
    elif invalid == 'missing_relation':
        game.sect_relations.pop(race_pair('own', 'second'))
    elif invalid == 'indirect':
        relation['overlord'] = 'first'
        game.sect_relations[race_pair('first', 'second')] = relation
    elif invalid == 'independent':
        game.sects['third'] = SectState('third', '独立宗')
    elif invalid == 'owner_extinct':
        game.sects['own'].extinct = True
    elif invalid == 'owner_remote':
        game.player.world = 'spirit'
    elif invalid == 'no_membership':
        game.player.faction_id = None
    elif invalid == 'institution':
        game.sects['own'].kind = 'institution'
    before = copy.deepcopy(game.to_dict())
    assert not world_sects_submit(game)
    assert game.to_dict() == before


def test_unification_requires_another_surviving_sect():
    game = unified_state()
    game.sects['first'].extinct = game.sects['second'].extinct = True
    assert not world_sects_submit(game)
    game.sects.pop('own')
    game.player.faction_id = None
    assert not world_sects_submit(game)


def test_family_can_be_the_single_overlord_but_split_ownership_does_not_count():
    game = unified_state()
    game.player.faction_id = None
    game.family = SectState('family', '沈氏', kind='family')
    for target in game.sects:
        game.sect_relations[race_pair('family', target)] = {
            'status': 'vassal', 'overlord': 'family', 'subject': target,
        }
    assert world_sects_submit(game)
    game.sect_relations.pop(race_pair('family', 'second'))
    game.player.faction_id = 'own'
    game.sect_relations.pop(race_pair('own', 'first'))
    assert not world_sects_submit(game)
    game.family.extinct = True
    assert not world_sects_submit(game)


@pytest.fixture
def system(tmp_path):
    import json
    catalog = json.loads((ROOT / 'content' / 'achievements.json').read_text(encoding='utf-8'))
    return AchievementSystem(load_achievement_definitions(catalog), tmp_path)


def matches(system, identity, game, rank=None):
    definition = next(row for row in system.definitions if row['id'] == identity)
    return system._matches(definition['condition'], game, player_rank=rank)


def test_wealth_uses_personal_current_inventory_and_exact_threshold(system):
    game = unified_state()
    add_item(game.player, 'spirit_stone', 999999)
    assert not matches(system, 'wealth_million_stones', game)
    add_item(game.player, 'spirit_stone', 1)
    assert matches(system, 'wealth_million_stones', game)
    game.player.inventory.clear()
    assert not matches(system, 'wealth_million_stones', game)


def test_ranking_needs_actual_first_place(system):
    game = unified_state()
    assert not matches(system, 'cultivation_rank_one', game)
    assert not matches(system, 'cultivation_rank_one', game, rank=2)
    assert matches(system, 'cultivation_rank_one', game, rank=1)


def test_disciple_must_be_alive_and_at_least_mahayana(system):
    game = unified_state()
    game.player.disciples = [{'id': 'disciple', 'alive': True, 'realm_index': 7}]
    assert not matches(system, 'cultivation_mahayana_disciple', game)
    game.player.disciples[0]['realm_index'] = 8
    assert matches(system, 'cultivation_mahayana_disciple', game)
    game.player.disciples[0]['alive'] = False
    assert not matches(system, 'cultivation_mahayana_disciple', game)


def test_substitutes_count_only_surviving_mechanical_puppets(system):
    game = unified_state()
    game.player.puppets = [{'id': str(i), 'type': 'mechanical', 'alive': True} for i in range(2)]
    game.player.puppets.extend([
        {'id': 'corpse', 'type': 'corpse', 'alive': True},
        {'id': 'broken', 'type': 'mechanical', 'alive': False},
        {'id': 'worn', 'type': 'mechanical', 'alive': True, 'durability': 0},
    ])
    assert not matches(system, 'crafting_three_mechanical_puppets', game)
    game.player.puppets.append({'id': 'third', 'type': 'mechanical', 'alive': True})
    assert matches(system, 'crafting_three_mechanical_puppets', game)


def test_final_diplomacy_submission_unlocks_once_and_survives_reload(tmp_path, monkeypatch):
    engine = GameEngine(ROOT, tmp_path)
    identity = engine.create_game('天下布武验收', 'supreme_fire', 'dao', 355, preset_id='core')['id']
    game = engine._load(identity)
    sects = [sect for sect in game.sects.values()
             if sect.kind == 'sect' and not sect.extinct and sect.world == game.player.world]
    assert len(sects) >= 3
    own, final = sects[:2]
    game.player.faction_id = own.id
    own.founded_by_player = True
    own.founder_player_id = game.id
    game.player.realm_index = 4
    record = engine._ensure_intrigue_faction(game, 'sect', own.id)
    record['controller_id'] = 'player'
    record['positions']['leader'] = 'player'
    game.pending_event = game.active_trial = None
    for target in sects[2:]:
        game.sect_relations[race_pair(own.id, target.id)] = {
            'status': 'vassal', 'overlord': own.id, 'subject': target.id,
        }
    game.sect_relations[race_pair(own.id, final.id)] = {'status': 'neutral', 'affinity': 0}
    engine.store.save(game)
    assert not world_sects_submit(game)
    monkeypatch.setattr(engine, '_vote_probability', lambda *args: 1.0)
    monkeypatch.setattr(engine, '_sect_power', lambda game, key: 10000 if key == own.id else 1)
    shown = engine.propose_sect_diplomacy(identity, final.id, 'vassal')
    assert '天下布武' in {row['name'] for row in shown['new_achievements']}
    saved = engine.store.load(identity)
    assert world_sects_submit(saved)
    reloaded = GameEngine(ROOT, tmp_path)
    assert '天下布武' not in {row['name'] for row in reloaded.get_game(identity)['new_achievements']}
    catalog = reloaded.list_achievements()['achievements']
    assert next(row for row in catalog if row['name'] == '天下布武')['unlocked']
