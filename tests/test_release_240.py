"""Opportunity, local organizations, bounded businesses and authored initial lives."""
import copy
from pathlib import Path
from unittest.mock import patch
import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.rules import opportunity_multiplier, expected_combat_power
from cultivation_life.system.economy import organizations
from cultivation_life.system.economy.ledger import transfer_value, balance
from cultivation_life.system.economy.estate_management import recruitment_ready, invest_surplus
from cultivation_life.system.economy.fleet_network import guard_required
from test_economy_network import economy, act, cash
from test_economy_enterprises import buy, estate_act

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def engine(tmp_path):
    return GameEngine(ROOT, tmp_path)


def custom(engine, **changes):
    path = changes.pop('path', 'dao')
    return engine.create_game('前尘', 'supreme_metal', path, 421,
        monster_species_id='fox' if path == 'monster' else None,
        custom_start=dict(world='human', realm_index=3, layer=1, divine_sense_rank=23, **changes))


def test_opportunity_efficiency_once_and_costs_unscaled(engine):
    game = engine._load(engine.create_game('杀戮', 'supreme_metal', 'demonic', 5, preset_id='demonic_core')['id'])
    p = game.player
    before = p.opportunity
    cfg = WORLD_SYSTEMS['demonic_cultivation']
    base = cfg['kill_opportunity_base'] + 3 * cfg['kill_opportunity_per_realm']
    gain = engine._grant_demonic_kill_opportunity(p, 3)
    assert gain == pytest.approx(base * opportunity_multiplier(p))
    assert p.opportunity - before == pytest.approx(gain)
    assert engine._add_opportunity(p, 7) == pytest.approx(7 * opportunity_multiplier(p))
    assert engine._add_opportunity(p, 7, apply_efficiency=False) == pytest.approx(7)
    assert engine._add_opportunity(p, -7) == pytest.approx(-7)


def test_custom_independent_sense_and_unique_natal_survive_reload(engine):
    result = custom(engine, inventory=[dict(id='spirit_sword', quantity=1)], natal_artifact='spirit_sword',
                    additional_roots=['water'], sect='new', family='new')
    game = engine._load(result['id'])
    assert game.player.divine_sense_rank == 23
    assert result['player']['cultivation_ranks']['sense']['name'] == '筑基中期'
    assert game.player.additional_roots == ['water']
    assert game.natal_artifact['item_id'] == 'spirit_sword'
    assert not any(i.id == 'spirit_sword' for i in game.player.inventory)
    assert game.player.age > 100
    assert game.player.faction_join_age == game.player.age
    for org in (game.family, game.sects[game.player.faction_id]):
        assert org.npcs and org.location_id == game.player.location_id
    assert engine.get_game(game.id)['player']['divine_sense']['level'] == 23


def test_untrained_rewards_use_efficiency_without_unlocking_cultivation(engine):
    game = engine._load(engine.create_game('初见机缘', 'supreme_wood', 'dao', 240)['id'])
    assert game.player.technique is None
    assert opportunity_multiplier(game.player) == 0
    expected = 10 * opportunity_multiplier(game.player, allow_untrained=True)
    assert expected > 0
    assert engine._add_opportunity(game.player, 10) == pytest.approx(expected)


@pytest.mark.parametrize('world,path,realm,rank,warming', [
    ('celestial', 'dao', 9, 4, 3), ('asura', 'demonic', 9, 4, 3),
    ('nether', 'monster', 9, 2, 0), ('reincarnation', 'ghost', 9, 2, 0), ('spirit', 'dao', 6, 4, 0)])
def test_path_domains_are_real_sources(engine, world, path, realm, rank, warming):
    result = engine.create_game('领域前尘', 'supreme_metal', path, 91,
        monster_species_id='fox' if path == 'monster' else None,
        custom_start=dict(world=world, realm_index=realm, layer=1, domain_rank=rank, warming=warming,
                          tendency='restore_hp', divine_sense_rank=30))
    game = engine._load(result['id'])
    if world == 'celestial':
        from cultivation_life.system.doctrine.progression import source
        value = source(game.doctrine_state['player'], game.doctrine_state['definitions'], world)
    elif world == 'spirit':
        from cultivation_life.system.spirit_voisinage import player_source
        value = player_source(game)
    else:
        from cultivation_life.system.upper_voisinage_rules import player_source
        value = player_source(game.player)
    assert len(value.voisinages) == 1
    assert game.player.world == world


def test_existing_family_keeps_identity_and_custody_once(engine):
    result = custom(engine, family='birth-family-human-0')
    game = engine._load(result['id'])
    assert game.family.id == 'birth-family-human-0' and not game.family.founded_by_player
    assert game.family.id not in game.sects
    ids = [n.id for s in game.sects.values() for n in s.npcs] + [n.id for n in game.family.npcs]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize('change', [dict(world='invalid'), dict(realm_index=True), dict(layer=99),
    dict(inventory=[dict(id='invalid', quantity=1)]), dict(natal_artifact='spirit_sword'),
    dict(sect='taixuan'), dict(additional_roots=['bad']), dict(domain_rank=4), dict(tianji_bracket=99)])
def test_invalid_custom_creates_no_partial_save(engine, change):
    before = engine.list_games()
    payload = dict(world='human', realm_index=3, layer=1)
    payload.update(change)
    with pytest.raises(ValueError):
        engine.create_game('invalid', 'supreme_metal', 'dao', 1, custom_start=payload)
    assert engine.list_games() == before


def test_tianji_start_is_unique_and_dlc_gated(engine):
    result = custom(engine, tianji_bracket=3)
    game = engine._load(result['id'])
    item = next(i for i in game.player.crafted_artifacts if i['tianji']['kind'] == 'true_body')
    key = item['tianji']['definition_id']
    definition = next(r for r in game.tianji_state['artifacts'] if r['id'] == key)
    assert 41 <= definition['rank'] <= 60
    assert key not in game.tianji_state['holders']
    assert game.tianji_state['true_body_states'][key]['holder_ref'] == item['id']
    with patch('cultivation_life.system.tianji_system.tianji_content_available', return_value=False):
        with pytest.raises(ValueError, match='DLC'):
            custom(engine, tianji_bracket=1)


def test_organization_funding_and_entrust_conserve_cash(economy):
    engine, game = economy
    entity = game.sects['tianjian']
    game.player.faction_id = entity.id
    game.player.location_id = entity.location_id
    game.player.realm_index = 4
    before = cash(game)
    treasury = f'organization:sect:{entity.id}'
    initial = balance(game, treasury)
    game = act(engine, game, 'organization_fund', owner_kind='sect', amount=100000)
    assert balance(game, treasury) == initial + 100000
    assert cash(game) == before
    from cultivation_life.system.economy.enterprise_view import public_estates
    offer = next(o for o in public_estates(game, engine.maps)['offers'] if o['kind'] == 'farm')
    game = act(engine, game, 'estate_buy', owner_kind='sect', kind='farm', cost=offer['cost'])
    identity = f'human:{entity.location_id}:farm'
    game = estate_act(engine, game, identity, 'entrust', enabled=True)
    assert game.economy_v2['estates'][identity]['entrusted']
    assert cash(game) == before
    original = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='变化'):
        engine.fleet_action(game.id, dict(action='estate_entrust', estate_id=identity, revision=-1, enabled=False))
    assert engine.store._path(game.id).read_bytes() == original


def test_npc_budget_gates_recruitment_and_real_purchase(economy):
    engine, game = economy
    entity = game.sects['wanmo']
    finance = organizations.register(game, 'sect', entity.id, entity.world)
    source = f'organization:sect:{entity.id}'
    transfer_value(game, source, 'background:human', balance(game, source), '清空测试预算')
    assert not recruitment_ready(game, entity)
    transfer_value(game, 'background:human', source, 1000000, '测试预算')
    assert recruitment_ready(game, entity)
    before = cash(game)
    invest_surplus(game, engine.maps, entity, finance)
    row = next(r for r in game.economy_v2['estates'].values() if r['owner_id'] == entity.id)
    assert row['entrusted'] and row['location'] == entity.location_id
    assert balance(game, source) < 1000000 and cash(game) == before


def test_raid_uses_actual_wallet_and_backing_alliance_wanted(economy):
    engine, game = economy
    fleet = next(f for f in game.economy_v2['transport']['worlds']['human']['fleets'].values() if f['owner_kind'] == 'alliance')
    game.player.location_id = fleet['location']
    transfer_value(game, 'background:human', f'caravan:{fleet["id"]}', 10000, '测试载资')
    original = balance(game, 'player')
    with patch.object(engine, '_combat', return_value=('victory', '获胜')):
        game = act(engine, game, 'raid', fleet_id=fleet['id'])
    assert balance(game, 'player') == original + 4000
    assert balance(game, f'caravan:{fleet["id"]}') == 6000
    key = f'alliance:human:{fleet["owner_id"]}'
    assert game.player.hostility[key] > WORLD_SYSTEMS['faction_conflict']['wanted_threshold']
    assert engine._hostility_entity_state(game, key)['status'] == 'active'
    snapshot = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):
        engine.fleet_action(game.id, dict(action='raid', fleet_id=fleet['id']))
    assert engine.store._path(game.id).read_bytes() == snapshot
    for world, realm in [('human', 2), ('spirit', 3), ('celestial', 4)]:
        assert guard_required(world) == round(expected_combat_power(realm, 1) * 2)
