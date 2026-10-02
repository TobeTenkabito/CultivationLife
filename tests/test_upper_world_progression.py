"""Base upper worlds share ordinary progression; DLC routes remain opt-in."""
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.content_registry import CONTENT_DOCUMENTS, TECHNIQUE_CATALOG, MARKET_GOODS
from cultivation_life.formation_content import expanded_formation_materials
from cultivation_life.rules import opportunity_required, public_player, add_item
from cultivation_life.models import SectNpc

ROOT = Path(__file__).resolve().parents[1]
WORLDS = [('asura', 'demonic'), ('nether', 'monster'), ('reincarnation', 'ghost')]


@pytest.fixture(autouse=True)
def base_without_asura_dlc():
    # These regressions exercise the base game with optional progression off.
    with patch('cultivation_life.system.asura.enabled', return_value=False):
        yield


@pytest.fixture
def prepared(tmp_path):
    engine = GameEngine(ROOT, tmp_path)
    made = engine.create_game('上境验收', 'supreme_metal', 'dao', 1500)
    game = engine.store.load(made['id'])
    game.pending_event = None
    return engine, game


def upper(engine, game, world, path, rank=9, layer=1):
    p = game.player
    p.world, p.path, p.realm_index, p.layer = world, path, rank, layer
    p.location_id = engine.maps.normalize_location(world, None)
    p.lifespan = None
    p.opportunity = opportunity_required(p) * 3
    engine.store.save(game)


@pytest.mark.parametrize('world,path', WORLDS)
@pytest.mark.parametrize('rank', range(9, 13))
def test_base_old_save_caps_and_restores_manual_progression(prepared, world, path, rank):
    engine, game = prepared
    upper(engine, game, world, path, rank)
    with patch('cultivation_life.engine.bloodline_content_available', return_value=False), patch('cultivation_life.system.monster_bloodline_system.bloodline_content_available', return_value=False):
        loaded = engine._load(game.id)
        p = loaded.player
        assert p.opportunity == opportunity_required(p)
        assert p.awaiting_minor_breakthrough and not p.awaiting_major_breakthrough
        assert not public_player(p)['opportunity_unbounded']
        assert p.next_tribulation_age > p.age
        assert engine._public_major_breakthrough(p)['enabled']
        with patch.object(engine, '_breakthrough_chance', return_value={'final': 1}):
            shown = engine.breakthrough(game.id)
        assert shown['player']['layer'] == 2
        assert shown['player']['realm_index'] == rank
        assert shown['player']['opportunity'] == 0


@pytest.mark.parametrize('world,path', WORLDS)
@pytest.mark.parametrize('rank', [9, 10, 11])
@pytest.mark.parametrize('layer', [3, 6, 9])
def test_base_upper_uses_legacy_trials_not_immortal_trials(prepared, world, path, rank, layer):
    engine, game = prepared
    upper(engine, game, world, path, rank, layer)
    with patch('cultivation_life.engine.bloodline_content_available', return_value=False), patch('cultivation_life.system.monster_bloodline_system.bloodline_content_available', return_value=False), patch.object(engine, '_breakthrough_chance', return_value={'final': 1}):
        engine.breakthrough(game.id)
    saved = engine.store.load(game.id)
    assert saved.active_trial['kind'] == ('traditional' if layer < 9 else 'heavenly_demon' if path == 'demonic' else 'heavenly')
    assert (saved.player.realm_index, saved.player.layer) == (rank, layer)


def test_monster_enabled_keeps_layer_one_evolution_and_blocks_normal_button(prepared):
    engine, game = prepared
    upper(engine, game, 'nether', 'monster')
    loaded = engine._load(game.id)
    assert loaded.player.awaiting_major_breakthrough
    assert not loaded.player.awaiting_minor_breakthrough
    assert engine._manual_minor_layers(loaded.player) == set()
    view = engine._public_major_breakthrough(loaded.player)
    assert view['action_label'] == '选择血脉进化' and view['chance'] is None
    with pytest.raises(ValueError, match='血脉'):
        engine.breakthrough(game.id)


@pytest.mark.parametrize('world,path', WORLDS)
def test_top_realm_cannot_overflow(prepared, world, path):
    engine, game = prepared
    upper(engine, game, world, path, 12, 9)
    engine._resolve_breakthroughs(game, random.Random(1))
    assert engine._manual_breakthrough_kind(game.player) is None
    assert game.player.opportunity == opportunity_required(game.player)
    assert (game.player.realm_index, game.player.layer) == (12, 9)


@pytest.mark.parametrize('world,path', WORLDS)
def test_npc_upper_advancement_and_cap(prepared, world, path):
    engine, _ = prepared
    npc = SectNpc('upper', '上境', '', 9, 9, 5000, None, world=world, path=path, spirit_root='supreme_metal')
    npc.cultivation_progress = 1000
    with patch.object(engine, '_npc_breakthrough_probability', return_value=1):
        assert engine._advance_npc_cultivation(npc, random.Random(1))['type'] == 'breakthrough'
    assert (npc.realm_index, npc.layer) == (10, 1)
    npc.realm_index, npc.layer = 12, 9
    assert engine._advance_npc_cultivation(npc, random.Random(1)) is None


@pytest.mark.parametrize('world,path', WORLDS)
@pytest.mark.parametrize('rank', range(9,13))
def test_complete_crafting_formation_and_technique_market(prepared, world, path, rank):
    engine, game = prepared
    upper(engine, game, world, path, rank)
    materials = [m for m in CONTENT_DOCUMENTS['crafting.json']['materials'] if m['world']==world and m['tier']==rank]
    assert {'primary','secondary','quench'} <= {r for m in materials for r in m['roles']}
    formations = expanded_formation_materials(CONTENT_DOCUMENTS['formations.json'])
    assert set(CONTENT_DOCUMENTS['formations.json']['material_progression']['natures']) <= {m['nature'] for m in formations if m['world']==world and m['tier']==rank}
    manuals = [TECHNIQUE_CATALOG[g['content_id']] for g in MARKET_GOODS if g['world']==world and g['tier']==rank and g['kind']=='technique']
    assert {'main','combat','body','divine_sense'} <= {t.category if t.category!='spiritual' else t.growth_preference for t in manuals}
    assert all(not t.requires_immortal_power for t in manuals)
    assert engine._market_tier(game.player)==rank
    engine._clear_market(game)
    engine._ensure_market(game, random.Random(1))
    assert game.market_offers and all(o['tier'] >= rank for o in game.market_offers)


def test_root_books_satisfy_actual_void_gate_without_changing_root_quality(prepared):
    engine, game = prepared
    p = game.player
    p.world, p.realm_index, p.layer = 'spirit', 5, 9
    p.location_id = engine.maps.normalize_location('spirit', None)
    assert set(engine._major_breakthrough_requirement(p)['missing_affinities']) == {'木','水','火','土'}
    for element in ('wood','water','fire','earth'):
        add_item(p, 'zique_'+element)
    engine.store.save(game)
    for element in ('wood','water','fire','earth'):
        engine.use_item(game.id, 'zique_'+element)
    p = engine.store.load(game.id).player
    assert engine._major_breakthrough_requirement(p)['met']
    assert p.spirit_root == 'supreme_metal'
