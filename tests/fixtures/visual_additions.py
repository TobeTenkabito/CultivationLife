"""Disposable alpha.3 social scene, using existing public NPC/event definitions."""
import random


def prepare_visual_additions(engine, identity):
    game = engine.store.load(identity)
    # Isolated identity fixture keeps the human-world public event/participants.
    game.player.path = 'demonic'
    game.player.gender = 'female'
    game.pending_event = engine._instantiate_event(engine.events_by_id['EVT_XIANG_NODE_001'], game, random.Random(1))
    engine.store.save(game)


def prepare_domain_battle(engine, identity, kind='control'):
    """Isolated real combat entry; report facts are never hand-authored."""
    from dataclasses import asdict
    from cultivation_life.system.combat.contracts import VoisinageDefinition
    game = engine.store.load(identity)
    game.pending_event = None
    game.settings.update(silent_events=True, combat_popup=True)
    definition = VoisinageDefinition(id='visual_test', name='验收仙域', attainment='visual_test',
        required_level=1, strength=100, opening_cost=10, upkeep_cost=10,
        effect='strike', effect_power=.06, effect_cost=5)
    state = dict(version=1, conversion=1, capacity=1000, current=1000, resource_tier=2,
        force_tier=2, ward_tier=2, voisinage_ids=['visual_test'], attainments={'visual_test': 1},
        plan={'stance': 'press'})
    game.player.transcendence = dict(state)
    power = engine._player_battle_power(game)
    foe = dict(state, plan={'stance': 'press' if kind=='mutual' else 'guard'})
    if kind=='control':
        foe = dict(state, voisinage_ids=[], attainments={}, ward_tier=2)
    if kind=='mixed':
        game.player.transcendence = dict(state, current=28)
        foe = dict(state, voisinage_ids=[], attainments={}, ward_tier=2)
    if kind in {'mutual','group'}:
        definition = VoisinageDefinition(**(asdict(definition) | {'incursion': 180, 'stability': 40}))
    target = dict(target_name='邻域演武', target_power=power, target_realm_index=game.player.realm_index,
        combat_type='cultivator', max_rounds=3, gender='female', path='dao',
        transcendence=foe, voisinages=[asdict(definition)])
    if kind=='group':
        target['player_allies']=[dict(npc_id=f'ally-{i}',name=f'同道{i}',power=power*.4,power_ratio=.4,
            realm_index=game.player.realm_index,kind='cultivator',path='dao',gender='female',
            transcendence=dict(state,current=28 if i==0 else 1000)) for i in range(2)]
        target['members']=[dict(npc_id=f'enemy-{i}',name=f'对手{i}',power=power*.6,
            realm_index=game.player.realm_index,kind='cultivator',path='dao',gender='male',
            transcendence=dict(state)) for i in range(3)]
    engine._combat(game, target, False, random.Random(151))
    assert any(row.get('voisinage', {}).get('animation', {}).get('fields') for row in game.last_combat_report['rounds'])
    engine.store.save(game)
    return game.last_combat_report
