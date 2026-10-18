"""Real command regressions for natal ownership and lawful organization custody."""
import copy

import pytest

from test_other_systems_audit_fixes import api, new_game, snapshot
from test_crafting_field_audit_fixes import basic_recipe, blocking_state
from test_family_expansion import family_game
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.models import SectNpc, SectState
from cultivation_life.rules import add_item, remove_item
from cultivation_life.system.ghost.progression import apply_soul_erosion
from cultivation_life.system.ghost_resources import ghost_opportunity_multiplier


def organization_game(engine, kind='sect', world='human'):
    tier = int(WORLD_SYSTEMS['world_profiles'][world]['tier'])
    shown = engine.create_game('监禁验收', 'supreme_metal', 'dao', 888,
        custom_start=dict(world=world, realm_index={1:4, 2:7, 3:10}[tier], layer=1))
    game = engine._load(shown['id'])
    game.pending_event = None
    game.settings['silent_events'] = True
    member = SectNpc('audit_member', '在册成员', '弟子', 1, 1, 20, 100,
                     world=world, spirit_root='supreme_water', affinity=80)
    org = SectState('audit_org', '验收宗' if kind == 'sect' else '验收家族', world, [member],
                    kind=kind, founded_by_player=True, founder_player_id=game.id)
    if kind == 'sect':
        game.sects[org.id] = org
        game.player.faction_id = org.id
        member.faction_id = org.id
    else:
        game.family = org
        member.family_traits['kin'] = True
    engine.store.save(game)
    engine.get_game(game.id)
    return engine._load(game.id), member.id


def forged_game(engine, act, realm=3):
    game = new_game(engine, realm=realm)
    payload = basic_recipe(engine, game)
    payload['name'] = '照魂灯'
    engine.store.save(game)
    act(game.id, 'crafting-forge', **payload)
    game = engine._load(game.id)
    artifact = game.player.crafted_artifacts[-1]
    return game, artifact['id']


@pytest.mark.parametrize('mode', ['realm', 'event', 'imprisonment'])
@pytest.mark.parametrize('action', ['natal', 'unbind_natal'])
def test_crafted_natal_commands_share_main_boundary_and_refuse_atomically(api, mode, action):
    engine, act = api
    game, identity = forged_game(engine, act)
    if action == 'unbind_natal':
        act(game.id, 'crafted-artifact', action='natal', artifact_id=identity)
        game = engine._load(game.id)
    if mode == 'realm':
        game.player.realm_index = 1
        engine.store.save(game)
    else:
        game = blocking_state(engine, game, mode, followup=mode == 'event')
    frozen = snapshot(engine, game.id)
    act(game.id, 'crafted-artifact', status=400, action=action, artifact_id=identity)
    assert engine.store._path(game.id).read_bytes() == frozen
    assert not engine.get_game(game.id)['natal_artifact']['operation_available']


def test_crafted_natal_recovers_after_real_followup_and_preserves_unbind_penalty(api):
    engine, act = api
    game, identity = forged_game(engine, act)
    game = blocking_state(engine, game, followup=True)
    reward = copy.deepcopy(game.pending_event['_followup_event'])
    act(game.id, 'choice', event_id=game.pending_event['id'], choice_id='acknowledge')
    act(game.id, 'choice', event_id=reward['id'], choice_id='pill')
    act(game.id, 'crafted-artifact', action='natal', artifact_id=identity)
    assert engine._load(game.id).natal_artifact['crafted_artifact_id'] == identity
    act(game.id, 'crafted-artifact', action='unbind_natal', artifact_id=identity)
    saved = engine._load(game.id)
    assert not saved.natal_artifact and saved.player.natal_origin_penalty == pytest.approx(.1)
    assert len(saved.player.crafted_artifacts) == 1


def test_sale_of_last_ghost_vessel_detaches_but_partial_stack_remains(api):
    engine, act = api
    game = new_game(engine, 'ghost')
    add_item(game.player, 'starfall_blade', 2)
    game.auction_state = dict(id='vessel-sale', status='black_market', world=game.player.world,
                              location_id=game.player.location_id)
    engine.store.save(game)
    act(game.id, 'ghost-attachment', action='attach', item_id='starfall_blade')
    act(game.id, 'black-market-sell', kind='item', asset_id='starfall_blade')
    assert engine._load(game.id).player.ghost_attachment
    frozen = snapshot(engine, game.id)
    act(game.id, 'black-market-sell', status=400, kind='item', asset_id='not-owned')
    assert engine.store._path(game.id).read_bytes() == frozen
    act(game.id, 'black-market-sell', kind='item', asset_id='starfall_blade')
    saved = engine._load(game.id)
    assert saved.player.ghost_attachment is None
    assert not any(i.id == 'starfall_blade' for i in saved.player.inventory)
    assert ghost_opportunity_multiplier(saved.player) == pytest.approx(1)
    act(game.id, 'black-market-leave')
    act(game.id, 'advance', action='rest', years=1)
    saved = engine._load(game.id)
    assert saved.player.ghost_soul_erosion_rate_pp == pytest.approx(.0002)


def test_missing_vessel_schema10_load_reconciles_once_without_resources_or_rng(api):
    engine, _ = api
    game = new_game(engine, 'ghost')
    snapshot(engine, game.id)
    game = engine._load(game.id)
    game.player.ghost_attachment = dict(item_id='gone', name='旧魂灯', erosion_growth_multiplier=.45)
    engine.store.save(game)
    before = copy.deepcopy(game.player.inventory)
    rng = game.rng_state
    loaded = engine._load(game.id)
    assert loaded.player.ghost_attachment is None
    assert loaded.player.inventory == before and loaded.rng_state == rng
    assert engine._load(game.id).player.ghost_attachment is None


def test_crafted_vessel_sale_detaches_same_instance(api):
    engine, act = api
    game, identity = forged_game(engine, act)
    # This fixture changes only path, never creates a second crafted instance.
    game.player.path = 'ghost'
    engine.store.save(game)
    act(game.id, 'ghost-attachment', action='attach', item_id=identity)
    act(game.id, 'crafted-artifact', action='sell', artifact_id=identity)
    saved = engine._load(game.id)
    assert saved.player.ghost_attachment is None and not saved.player.crafted_artifacts


def test_jailed_heir_cannot_invite_teach_gift_or_infuse_and_release_recovers(api):
    engine, act = api
    game = family_game(engine)
    act(game.id, 'family-action', action='invite', npc_id='family_heir')
    act(game.id, 'intrigue-personnel', kind='family', action='imprison', npc_id='family_heir', years=100)
    frozen = snapshot(engine, game.id)
    for action, extra in [('invite', {}), ('teach', {'technique_id':game.player.known_techniques[0].id}),
                          ('gift_equipment', {'item_id':'spirit_sword'}), ('infuse', {})]:
        act(game.id, 'family-action', status=400, action=action, npc_id='family_heir', **extra)
        assert engine.store._path(game.id).read_bytes() == frozen
    saved = engine._load(game.id)
    assert not saved.player.party
    saved.player.party.append({'id':'family_heir'})  # An already-saved stale reference must not fight.
    assert not any(unit.id == 'family_heir' for unit in engine._player_combat_units(saved))
    act(game.id, 'intrigue-personnel', kind='family', action='release', npc_id='family_heir')
    shown = act(game.id, 'family-action', action='invite', npc_id='family_heir')
    assert any(member['id']=='family_heir' for member in shown['party'])


WORLDS = tuple(world for world, profile in WORLD_SYSTEMS['world_profiles'].items()
               if profile.get('enabled', True) and profile.get('tier') in {1, 2, 3})


@pytest.mark.parametrize('kind', ['sect', 'family'])
@pytest.mark.parametrize('world', WORLDS)
def test_imprisonment_resolution_works_in_each_ordinary_world_and_releases(api, kind, world):
    engine, act = api
    game, identity = organization_game(engine, kind, world)
    section = next(s for s in engine.get_game(game.id)['intrigue_system']['sections'] if s['kind']==kind)
    assert identity in {n['id'] for n in section['imprisonment_targets']}
    shown = act(game.id, 'intrigue-resolution', kind=kind, resolution_type='imprison_member',
                target_id=identity, years=7, reason='侵占组织资材', player_vote=True)
    saved = engine._load(game.id)
    record = saved.intrigue_state['factions'][f'{kind}:audit_org']
    assert record['prison'][0]['sentence_remaining'] == 7
    assert record['prison'][0]['reason'] == '侵占组织资材'
    assert engine._intrigue_is_imprisoned(saved, identity)
    assert shown['intrigue_system']['resolutions'][0]['result']=='passed'
    frozen = snapshot(engine, game.id)
    act(game.id, 'intrigue-resolution', status=400, kind=kind, resolution_type='imprison_member', target_id=identity)
    assert engine.store._path(game.id).read_bytes() == frozen
    act(game.id, 'intrigue-personnel', kind=kind, action='release', npc_id=identity)
    assert not engine._intrigue_is_imprisoned(engine._load(game.id), identity)


@pytest.mark.parametrize('invalid', ['outsider', 'dead', 'other_world', 'instance', 'controller', 'ruling_member', 'years', 'busy'])
def test_invalid_imprisonment_resolution_refuses_without_votes_rng_or_prison_changes(api, invalid):
    engine, act = api
    game, identity = organization_game(engine)
    npc = game.sects['audit_org'].npcs[0]
    target, years = identity, 10
    if invalid == 'outsider':
        npc = copy.deepcopy(npc); npc.id = 'outsider'; npc.faction_id = None
        game.world_npcs[npc.id] = npc; target = npc.id
    elif invalid == 'dead': npc.alive = False
    elif invalid == 'other_world': npc.world = 'spirit'
    elif invalid == 'instance':
        from cultivation_life.system.combat.npc_lifecycle import move_world
        from cultivation_life.content_registry import WORLD_SYSTEMS
        move_world(npc, 'lost', game.player.age, WORLD_SYSTEMS.get('transcendent_combat', {}))
        game.spatial_state.setdefault('instances', {})['elsewhere'] = {
            'id':'elsewhere', 'kind':'lost', 'name':'隔绝实例', 'npc_ids':[npc.id], 'location_id':None}
    elif invalid == 'controller': target = 'player'
    elif invalid == 'ruling_member':
        npc.realm_index = 5
        game.sects['audit_org'].founded_by_player = False
        game.sects['audit_org'].founder_player_id = None
    elif invalid == 'years': years = 0
    elif invalid == 'busy':
        game = blocking_state(engine, game)
    engine.store.save(game)
    frozen = snapshot(engine, game.id)
    refused = act(game.id, 'intrigue-resolution', status=400, kind='sect', resolution_type='imprison_member',
        target_id=target, years=years)
    if invalid == 'ruling_member':
        assert '控制者' in refused['error']
    assert engine.store._path(game.id).read_bytes() == frozen


def test_no_votes_does_not_imprison_and_outsider_uses_existing_bounty(api):
    engine, act = api
    game, identity = organization_game(engine)
    act(game.id, 'intrigue-resolution', kind='sect', resolution_type='imprison_member',
        target_id=identity, player_vote=False)
    saved = engine._load(game.id)
    assert not engine._intrigue_is_imprisoned(saved, identity)
    outsider = copy.deepcopy(saved.sects['audit_org'].npcs[0])
    outsider.id = 'outsider_bounty'; outsider.faction_id = None
    saved.world_npcs[outsider.id] = outsider
    engine.store.save(saved)
    act(game.id, 'issue-bounty', npc_id=outsider.id)
    assert any(b['target_id']==outsider.id for b in engine._load(game.id).player_bounties)


@pytest.mark.parametrize('years', [True, 1.5, '7', None, -1, 1001])
def test_sentence_input_validation_is_atomic(api, years):
    engine, act = api
    game, identity = organization_game(engine)
    frozen = snapshot(engine, game.id)
    act(game.id, 'intrigue-resolution', status=400, kind='sect', resolution_type='imprison_member',
        target_id=identity, years=years)
    assert engine.store._path(game.id).read_bytes() == frozen


@pytest.mark.parametrize('blocked', ['dlc', 'authority'])
def test_imprisonment_resolution_keeps_dlc_and_authority_gates(api, monkeypatch, blocked):
    engine, act = api
    game, identity = organization_game(engine)
    if blocked == 'authority':
        game.player.realm_index = 1
        engine.store.save(game)
    else:
        monkeypatch.setattr(engine, '_intrigue_enabled', lambda: False)
    frozen = snapshot(engine, game.id)
    act(game.id, 'intrigue-resolution', status=400, kind='sect', resolution_type='imprison_member', target_id=identity)
    assert engine.store._path(game.id).read_bytes() == frozen
