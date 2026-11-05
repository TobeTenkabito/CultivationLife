"""Recruit addresses and training share the original local contact authority."""
import copy
import random
from pathlib import Path

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import SectState
from cultivation_life.system.faction_geography import faction_site
from cultivation_life.system.npc_development import presentation, service
from test_npc_development import game


@pytest.fixture
def sect_game(game):
    person = game.world_npcs.pop('student')
    person.location_id = person.faction_id = None
    sect = SectState('training-sect', '培养宗门', 'human', [person])
    game.sects[sect.id] = sect
    game.player.location_id = faction_site(sect)['id']
    return game, sect, person


def test_existing_roster_address_is_read_only_and_training_keeps_original_person(sect_game):
    game, sect, person = sect_game
    before = copy.deepcopy(game.to_dict())
    row = presentation.public(game)['targets'][0]
    assert row['name'] == person.name and not row['reason'] and row['portrait']
    plan = service.quote(game, 'npc', person.id, 'body')
    assert plan['can_train']
    assert game.to_dict() == before
    service.apply(game, 'npc', person.id, 'body')
    assert person.body_training == 20
    assert sect.npcs[0] is game.player.disciples[0].person is person
    assert person.location_id is None and person.faction_id is None
    assert game.player.location_id == before['player']['location_id']


@pytest.mark.parametrize('blocked', ['remote_player', 'explicit_remote', 'foreign_world',
    'no_membership', 'extinct', 'dead', 'prison', 'assignment', 'other_instance'])
def test_faction_address_does_not_bypass_training_boundaries(sect_game, blocked):
    game, sect, person = sect_game
    if blocked == 'remote_player': game.player.location_id = 'elsewhere'
    elif blocked == 'explicit_remote': person.location_id = 'elsewhere'
    elif blocked == 'foreign_world': person.world = 'spirit'
    elif blocked == 'no_membership':
        sect.npcs.clear()
        game.world_npcs[person.id] = person
    elif blocked == 'extinct': sect.extinct = True
    elif blocked == 'dead': person.alive = False
    elif blocked == 'prison': game.intrigue_state['npc_prisons'] = {person.id: {}}
    elif blocked == 'assignment':
        game.wars = [dict(id='war', strategic_war_id='deployment', status='active',
                         journeys={'army': [dict(person_id=person.id, phase='outbound')]})]
    else:
        game.player.world = person.world = 'lost'
        game.spatial_state = dict(current='a', instances={'a': dict(npc_ids=[]), 'b': dict(npc_ids=[person.id])})
    before = copy.deepcopy(game.to_dict())
    row = presentation.public(game)['targets'][0]
    assert row['reason'] and not row['quotes']
    with pytest.raises(ValueError): service.apply(game, 'npc', person.id, 'body')
    assert game.to_dict() == before


@pytest.mark.parametrize('world,realm', [('human', 3), ('spirit', 8), ('celestial', 9)])
def test_recruitment_records_actual_faction_site(tmp_path, world, realm):
    engine = GameEngine(Path(__file__).resolve().parents[1], tmp_path)
    result = engine.create_game('招募地址', 'supreme_metal', 'dao', 371,
        custom_start=dict(world=world, realm_index=realm, sect='new'))
    game = engine.store.load(result['id'])
    sect = game.sects[game.player.faction_id]
    site = faction_site(sect)['id']
    game.player.location_id = 'player-elsewhere'
    person = engine._recruit_sect_npc(sect, game.player.age, random.Random(1))
    assert person is not None and person in sect.npcs
    assert person.faction_id == sect.id and person.location_id == site
    assert person.world == sect.world and game.player.location_id == 'player-elsewhere'
