"""Automatic birth manuals respect conversion; carried books retain normal gates."""
from pathlib import Path
import pytest
from cultivation_life.engine import GameEngine

ROOT = Path(__file__).resolve().parents[1]
WORLDS = {
    'dao': ('human', 'spirit', 'celestial'),
    'demonic': ('demon', 'true_demon', 'asura'),
    'ghost': ('human', 'hell', 'reincarnation'),
    'monster': ('human', 'monster_realm', 'nether'),
    'confucian': ('human', 'spirit', 'celestial'),
    'buddhist': ('human', 'spirit', 'celestial'),
}

@pytest.mark.parametrize('path', WORLDS)
@pytest.mark.parametrize('realm', range(13))
def test_custom_birth_equips_usable_manuals_in_all_realms(tmp_path, path, realm):
    engine = GameEngine(ROOT, tmp_path)
    world = WORLDS[path][0 if realm <= 5 else 1 if realm <= 8 else 2]
    result = engine.create_game('前尘资粮', 'otherworld', path, 271,
        monster_species_id='serpent' if path == 'monster' else None,
        custom_start=dict(world=world, realm_index=realm, layer=1))
    game = engine.store.load(result['id'])
    player = game.player
    assert player.realm_index == realm and player.world == world
    assert player.immortal_power_converted == (realm >= 9)
    for art in (player.technique, player.support_technique, player.body_technique, player.divine_sense_technique):
        assert art is None or not art.requires_immortal_power or player.immortal_power_converted
        assert art is None or art.required_body_training <= player.body_training
    before = (player.immortal_power_converted, player.immortal_conversion_stage, player.body_training)
    engine.get_game(game.id)
    player = engine.store.load(game.id).player
    assert (player.immortal_power_converted, player.immortal_conversion_stage, player.body_training) == before

def test_mahayana_carried_immortal_book_keeps_equip_gate(tmp_path):
    engine = GameEngine(ROOT, tmp_path)
    result = engine.create_game('大乘前尘', 'otherworld', 'dao', 271,
        custom_start=dict(world='spirit', realm_index=8, techniques=['TECH_IMMORTAL_BODY_FORGING']))
    game = engine.store.load(result['id'])
    assert not game.player.immortal_power_converted
    assert game.player.immortal_conversion_stage == 0
    assert game.player.body_technique.id != 'TECH_IMMORTAL_BODY_FORGING'
    assert any(t.id == 'TECH_IMMORTAL_BODY_FORGING' for t in game.player.known_techniques)
    engine.get_game(game.id)
    before = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='尚未完成仙灵力转化'):
        engine.equip_known_technique(game.id, 'TECH_IMMORTAL_BODY_FORGING', 'body')
    assert engine.store._path(game.id).read_bytes() == before
