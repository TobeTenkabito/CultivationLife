import copy
from pathlib import Path
import random
from unittest.mock import patch

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState, Player, SectNpc
from cultivation_life.rules import combat_power, max_hp, max_mp, opportunity_required
from cultivation_life.system import asura
from cultivation_life.system.combat.trials import load_battle, dump_battle, run_batch
from cultivation_life.engine.progression import asura_trials

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ready(tmp_path):
    engine = GameEngine(ROOT, tmp_path)
    made = engine.create_game('修罗验收', 'supreme_metal', 'demonic', 420)
    game = engine.store.load(made['id'])
    p = game.player
    p.world, p.realm_index, p.layer = 'asura', 9, 1
    p.location_id = engine.maps.normalize_location('asura', None)
    p.body_training = 100
    p.asura_cultivation.update(conversion=5, souls=100000, body_level=20)
    p.immortal_aperture = dict(capacity=1000, current=1000, imitation_capacity=60, imitation_current=0)
    p.hp, p.mp = max_hp(p), max_mp(p)
    p.opportunity = opportunity_required(p)
    game.pending_event = None
    engine.store.save(game)
    return engine, game


def route(p, name='asura', level=1, rank=1):
    p.asura_cultivation.update(route=name, level=level, domain_rank=rank, domain_name='验收魔域')


def test_creation_requires_species_even_without_bloodlines(tmp_path):
    engine = GameEngine(ROOT, tmp_path)
    with patch('cultivation_life.engine.bloodline_content_available', return_value=False):
        with pytest.raises(ValueError, match='种属'):
            engine.create_game('妖修', 'supreme_metal', 'monster', 1)
        result = engine.create_game('妖修', 'supreme_metal', 'monster', 1, monster_species_id='serpent')
        p = engine.store.load(result['id']).player
        assert p.monster_species_id == 'serpent'
        assert p.monster_evolution_id is None
        assert result['player']['monster_species_name'] == '蛇属'


def test_npc_species_persists_without_bloodline_effects():
    npc = SectNpc('stable', '林玄', '', 4, 1, 103, 500, path='monster')
    assert npc.monster_species_id
    assert SectNpc.from_dict(npc.to_dict()).monster_species_id == npc.monster_species_id


def test_catalog_reproducible_and_distinct():
    games = [GameState(str(i), seed, Player('魔', 'supreme_metal', 'demonic'), '', '') for i, seed in enumerate((42, 42, 43))]
    for game in games:
        asura.ensure(game)
    catalogs = [g.player.asura_cultivation['branches'] for g in games]
    assert catalogs[0] == catalogs[1] != catalogs[2]
    assert len(catalogs[0]) == 8
    assert all(len(rows) == 3 and len({b['name'] for b in rows}) == 3 for rows in catalogs[0].values())


@pytest.mark.parametrize('species,path,expected', [('serpent','monster','mahoraga'),('avian','monster','garuda'),
    ('aquatic','monster','naga'),('flora','monster','gandharva'),('fox','monster','kinnara'),
    (None,'dao','deva'),(None,'demonic','yaksha')])
def test_body_routes(species, path, expected):
    body = dict(body_training=100, path=path, monster_species_id=species)
    assert asura.eligible_routes([body]) == [expected]
    assert asura.eligible_routes([body, body.copy()]) == ['asura']
    body['body_training'] = 1
    assert not asura.eligible_routes([body])


def test_body_power_ignores_equipment_and_original_total():
    base = dict(body_training=100, immortal_body_level=20)
    assert asura.body_power(base) == asura.body_power(dict(base, combat_power=1e15, main_technique_id='anything'))
    assert asura.body_power(dict(base, immortal_body_level=40)) > asura.body_power(base)


def test_refined_soul_consumed_once(ready):
    engine, game = ready
    game.player.foreign_souls = [dict(id='soul', name='旧魂', refined=True, realm_index=9)]
    engine.store.save(game)
    result = engine.asura_action(game.id, 'purify', 'soul')
    assert result['asura']['souls'] == 100090
    assert result['demonic_system']['foreign_souls'] == []
    with pytest.raises(ValueError):
        engine.asura_action(game.id, 'purify', 'soul')


def test_five_real_conversion_events(ready):
    engine, game = ready
    game.player.asura_cultivation['conversion'] = 0
    game.player.immortal_aperture['current'] = 0
    engine.store.save(game)
    for stage in range(1, 6):
        result = engine.asura_action(game.id, 'convert')
        assert result['pending_event']['id'] == f'EVT_ASURA_CONVERSION_{stage}'
        engine.choose(game.id, 'convert')
        saved = engine.store.load(game.id)
        assert saved.player.asura_cultivation['conversion'] == stage
    with pytest.raises(ValueError):
        engine.asura_action(game.id, 'convert')


@pytest.mark.parametrize('realm,ratios,fields', [(9,[1.],[False]),(10,[1.,.8],[True,False]),(11,[1.5,1.],[True,True])])
@pytest.mark.parametrize('rank', [2,8,13])
def test_copies_power_and_actual_domain_capped_at_eight(ready, realm, ratios, fields, rank):
    engine, game = ready
    game.player.realm_index = realm
    route(game.player, level=9, rank=rank)
    power = combat_power(game.player)
    asura_trials.start(engine._dependencies.asura_trials, game, 'asura_breakthrough')
    battle = load_battle(game.active_trial['snapshot'])
    assert battle.escape_forbidden_sides == {'player', 'enemy'}
    for i, (ratio, field) in enumerate(zip(ratios, fields)):
        enemy = battle.units[f'enemy-{i}'].unit
        assert enemy.power == pytest.approx(power * ratio)
        assert bool(enemy.capabilities.voisinages) == field
        if field:
            assert enemy.capabilities.voisinages[0] == asura.field_for(game.player, cap=8)
            assert enemy.capabilities.semantic_rules == asura.source(game.player).semantic_rules
    assert game.player.asura_cultivation['domain_rank'] == rank


def test_condense_fuse_and_permanent_unique_body_power(ready):
    engine, game = ready
    game.player.prisoners = [dict(id=f'b{i}', name=f'肉身{i}', path='dao', body_training=60,
        immortal_body_level=0, divine_sense_rank=60, realm_index=5, layer=1) for i in range(2)]
    engine.store.save(game)
    for i in range(2):
        engine.asura_action(game.id, 'condense', f'b{i}')
    saved = engine.store.load(game.id)
    inherited = sum(b['power'] for b in saved.player.asura_cultivation['bodies'])
    engine.asura_action(game.id, 'fuse', body_ids=['b0','b1'])
    result = engine.choose(game.id, 'fight')
    for _ in range(10):
        if not engine.store.load(game.id).active_trial:
            break
        result = engine.choose(game.id, 'fight')
    saved = engine.store.load(game.id)
    assert saved.player.alive
    assert result['asura']['route'] == 'asura'
    assert result['asura']['inherited_power'] == inherited
    assert result['asura']['bodies'] == []
    with pytest.raises(ValueError):
        engine.asura_action(game.id, 'fuse', body_ids=['b0','b1'])


def test_branch_slots_and_dlc_disabled_projection(ready):
    engine, game = ready
    route(game.player)
    engine.store.save(game)
    engine.asura_action(game.id, 'learn_power')
    with pytest.raises(ValueError):
        engine.asura_action(game.id, 'learn_power')
    saved = engine.store.load(game.id)
    key = saved.player.asura_cultivation['branches']['asura'][0]['id']
    with pytest.raises(ValueError):
        engine.asura_action(game.id, 'choose_branch', key)
    saved.player.realm_index = 10
    saved.player.asura_cultivation['level'] = 5
    engine.store.save(saved)
    engine.asura_action(game.id, 'choose_branch', key)
    with pytest.raises(ValueError):
        engine.asura_action(game.id, 'choose_branch', key)
    saved = engine.store.load(game.id)
    assert asura.source(saved.player).semantic_rules
    with patch.object(asura, 'enabled', return_value=False):
        assert not asura.source(saved.player).semantic_rules
        assert not asura.public(saved)['available']


def test_trial_snapshot_resume_preserves_state(ready):
    engine, game = ready
    route(game.player, level=9)
    asura_trials.start(engine._dependencies.asura_trials, game, 'asura_breakthrough')
    trial = game.active_trial
    battle = load_battle(trial['snapshot'])
    state = trial['battle_state']
    result, _ = run_batch(battle, state, random.Random(4), batch_size=1)
    assert result == 'ongoing'
    snapshot = dump_battle(battle)
    resumed = load_battle(copy.deepcopy(snapshot))
    assert dump_battle(resumed) == snapshot
    assert state['round'] == 1


@pytest.mark.parametrize('realm', [9, 10, 11])
def test_major_breakthrough_requires_veins_and_uses_lethal_trial(ready, realm):
    engine, game = ready
    p = game.player
    p.realm_index, p.layer = realm, 9
    p.opportunity = opportunity_required(p)
    engine.store.save(game)
    with pytest.raises(ValueError):
        engine.breakthrough(game.id)
    p.asura_cultivation['veins'] = {str(realm): 27}
    engine.store.save(game)
    # Major realms use the authored duel, not an earlier probability failure.
    with patch.object(engine, '_breakthrough_chance', return_value={'final': 0}):
        result = engine.breakthrough(game.id)
    assert result['trial']['kind'] == 'asura_breakthrough'
    saved = engine.store.load(game.id)
    assert saved.active_trial['source_realm'] == realm
    assert saved.player.realm_index == realm


def test_conversion_usable_energy_and_native_domain_cannot_bypass_route(ready):
    from cultivation_life.system.immortal_aperture import energy_state
    from cultivation_life.system.combat.contracts import resolve_capabilities
    from cultivation_life.system.upper_voisinage import player_source, public_upper_voisinages
    engine, game = ready
    p = game.player
    p.asura_cultivation['conversion'] = 2
    caps = resolve_capabilities(energy_state(p), {})
    assert caps.usable_capacity == 400
    assert caps.current == 400
    assert not player_source(p).voisinages
    assert not public_upper_voisinages(p)['available']


def test_open_vein_has_pity_and_actual_intrinsic_gain(ready):
    engine, game = ready
    from cultivation_life.system.immortal_cultivation import rules
    p = game.player
    p.asura_cultivation['vein_pity'] = {'9:1': 100}
    before_hp = max_hp(p)
    engine.store.save(game)
    result = engine.asura_action(game.id, 'open_vein')
    saved = engine.store.load(game.id)
    assert result['asura']['opened'] == 1
    assert max_hp(saved.player) - before_hp == rules()['vein_intrinsic']['hp'][0]
    assert saved.player.asura_cultivation['vein_pity'] == {}


def test_long_battle_continues_past_five_and_twenty_four_rounds():
    from cultivation_life.system.combat.contracts import Combatant, CombatCapabilities
    from cultivation_life.system.combat.voisinages import VoisinageBattle
    caps = CombatCapabilities(force_tier=1, ward_tier=2)
    battle = VoisinageBattle([Combatant('player','玩家','player',100,caps), Combatant('enemy-0','劫相','enemy',100,caps)])
    state = dict(mode='asura_breakthrough', round=0, mp_ratio=1,
        stats={side:{k:100 for k in ('might','guard','mobility','sense','sustain','breach')} for side in ('player','enemy')})
    result, rows = run_batch(battle, state, random.Random(1))
    assert result == 'ongoing' and len(rows) == state['round'] == 24
    resumed = load_battle(dump_battle(battle))
    result, rows = run_batch(resumed, state, random.Random(2))
    assert result == 'ongoing' and state['round'] == 48
    assert resumed.escape_forbidden_sides == {'player','enemy'}
    # Fusion also accepts a genuinely suppressed living body.
    resumed.units['enemy-0'].suppressed = True
    state['mode'] = 'asura_fusion'
    result, _ = run_batch(resumed, state, random.Random(3), batch_size=1)
    assert result == 'victory'
    assert resumed.units['enemy-0'].body > 0


def test_vein_quote_cost_pity_and_per_layer_gate(ready):
    engine,g=ready
    p=g.player
    q=asura.public_meridians(p)
    assert len(q['nodes'])==27 and q['required']==3 and q['can_open']
    with patch('cultivation_life.engine.actions.asura.decode_rng') as decoder:
        rng=random.Random(0)
        # A real RNG whose first draw exceeds the initial 85% chance.
        for seed in range(100):
            if random.Random(seed).random()>.85:
                rng=random.Random(seed);break
        decoder.return_value=rng
        engine.asura_action(g.id,'open_vein')
    p=engine.store.load(g.id).player
    failed=asura.public_meridians(p)
    assert failed['opened']==0 and failed['failures']==1
    assert failed['chance']==pytest.approx(q['chance']+q['pity_step'])
    assert p.opportunity==q['opportunity']-q['next_cost']['opportunity']
    assert p.asura_cultivation['souls']==q['souls']-q['next_cost']['souls']
    p.asura_cultivation['veins']={'9':3}
    assert asura.public_meridians(p)['next_cost'] is None
    assert asura.public_meridians(p)['ready']
    p.layer=2
    assert asura.public_meridians(p)['required']==6
    assert asura.public_meridians(p)['failures']==0


def test_material_body_display_is_independent(ready):
    _,g=ready
    b=asura.public_body(dict(id='weak',name='材料',realm_index=11,layer=9,path='demonic',body_training=59,immortal_body_level=0))
    assert not b['eligible'] and b['body_training']==59
    assert b['immortal_body_level']==0 and g.player.asura_cultivation['body_level']==20


@pytest.mark.parametrize('world,path,label', [('asura','demonic','煞元'),('nether','monster','幽元'),('reincarnation','ghost','轮回元力')])
def test_native_energy_projection(ready,world,path,label):
    engine,g=ready
    g.player.world,g.player.path=world,path
    g.player.location_id=engine.maps.normalize_location(world,None)
    shown=engine.present(g)
    assert shown['player']['resource_name']==label
    assert shown['aperture']['name']==label
    assert shown['aperture']['energy_kind']==world
