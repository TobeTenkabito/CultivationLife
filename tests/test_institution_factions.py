import copy
import random
from pathlib import Path

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import Player
from cultivation_life.system.institutions import migrate_institutions
from cultivation_life.system.faction_geography import local_authorities

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def institution_game(tmp_path):
    engine = GameEngine(ROOT, tmp_path)
    game = engine.store.load(engine.create_game('机构验收', 'supreme_metal', 'dao', 1513,
                                               preset_id='true_immortal')['id'])
    game.pending_event = None
    game.heavenly_court['open_election'] = None
    return engine, game


def test_institutions_are_visible_as_institutions_not_joinable_sects(institution_game):
    engine, game = institution_game
    view = engine.present(game)
    ids = {'heavenly_court', 'yaochi'}
    assert all(game.sects[k].kind == 'institution' for k in ids)
    assert not ids.intersection(row['id'] for row in view['faction']['available'])
    mapped = {f['id']: f for place in view['map']['locations'] for f in place['factions']}
    assert all(mapped[k]['kind'] == 'institution' for k in ids)
    people = [n for n in view['world_npcs'] if n['contact_source'] == 'institution']
    assert len(people) == 6
    assert {n['institution_name'] for n in people} == {'天庭', '瑶池'}
    assert all(n['title'] in {'天庭天官', '瑶池执事'} for n in people)
    assert len(game.heavenly_court['seats']) == 49
    assert not ids.intersection(s['sect_id'] for s in game.heavenly_court['seats'])
    assert {'heavenly_court_official_0', 'yaochi_official_0'} <= game.heavenly_court['officials'].keys()


@pytest.mark.parametrize('key', ['heavenly_court', 'yaochi'])
def test_institution_cannot_be_joined_or_managed_as_a_sect(institution_game, key):
    engine, game = institution_game
    with pytest.raises(ValueError, match='非宗门'):
        engine._effect({'type':'join_faction', 'faction_id':key}, game, {}, random.Random(0))
    with pytest.raises(ValueError, match='机构'):
        engine._ensure_intrigue_faction(game, 'sect', key)
    game.player.faction_id = key
    assert not engine._has_sect_voice(game)
    assert not engine._player_court_representative(game)
    assert not engine.present(game)['faction']['member']


@pytest.mark.parametrize('key', ['heavenly_court', 'yaochi'])
def test_legacy_affiliation_and_institution_progress_survive_load(institution_game, key):
    engine, game = institution_game
    institution = game.sects[key]
    institution.kind = 'sect'
    game.player.faction_id = key
    game.player.faction_contribution = 231
    game.player.faction_join_age = game.player.age - 100
    game.player.faction_reward_preference = 'mana'
    game.yaochi_state['merit'] = 456
    game.heavenly_court['player_merit'] = 789
    seats = copy.deepcopy(game.heavenly_court['seats'])
    names = [npc.name for npc in institution.npcs]
    engine.store.save(game)
    loaded = engine._load(game.id)
    assert loaded.sects[key].kind == 'institution'
    assert loaded.player.faction_id is None and loaded.player.faction_contribution == 0
    legacy = loaded.player.institution_affiliations[key]
    assert legacy == {'joined_age':game.player.faction_join_age, 'legacy_contribution':231,
                      'legacy_reward_preference':'mana'}
    assert Player.from_dict(loaded.player.to_dict()).institution_affiliations[key] == legacy
    assert [npc.name for npc in loaded.sects[key].npcs] == names
    assert loaded.yaochi_state['merit'] == 456
    assert loaded.heavenly_court['player_merit'] == 789
    assert loaded.heavenly_court['seats'] == seats
    assert not migrate_institutions(loaded)
    assert engine.store.load(game.id).player.institution_affiliations == loaded.player.institution_affiliations


def test_institution_officials_keep_titles_and_do_not_trigger_sect_extinction(institution_game):
    engine, game = institution_game
    for key in ('heavenly_court', 'yaochi'):
        institution = game.sects[key]
        assert engine._dynamic_sect_title(institution.npcs[0], institution) == institution.npcs[0].title
        assert institution in local_authorities(game, institution.world, institution.location_id)
        institution.npcs = []
        assert not engine._check_sect_extinction(game, institution)
        assert not institution.extinct


def test_institution_annual_updates_do_not_recruit_sect_disciples(institution_game, monkeypatch):
    engine, game = institution_game
    original = engine._recruit_sect_npc
    def recruit(entity, *args):
        assert entity.kind != 'institution'
        return original(entity, *args)
    monkeypatch.setattr(engine, '_recruit_sect_npc', recruit)
    before = {key: len(game.sects[key].npcs) for key in ('heavenly_court', 'yaochi')}
    game.player.age = 10000
    engine._annual_sect_update(game, random.Random(42))
    assert {key: len(game.sects[key].npcs) for key in before} == before
