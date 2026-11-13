"""Presentation cannot spend resources, reroll, or disclose unused NPC books."""
import copy

import pytest

from cultivation_life.combat_costs import technique_cost
from cultivation_life.system.combat.trials import dump_battle, load_battle
from test_fixed_technique_combat import fight, manual, step
from test_technique_effect_foundation import battle as lineage_battle, manual as lineage_manual, begin


@pytest.mark.parametrize('realm,pricing', [(0, 'mixed'), (1, 'proportional'), (5, 'fixed')])
def test_projection_uses_frozen_hybrid_price_without_mutating_battle(realm, pricing):
    book = manual()
    book['cost_model'] = dict(grade=1, realm=realm, fixed=3.)
    b = fight([book], [manual()])
    step(b, 1)
    before = copy.deepcopy(dump_battle(b))
    events = copy.deepcopy(b.techniques.catalog.events)
    a = b.report()['technique_effects']
    assert a == b.report()['technique_effects']
    assert dump_battle(b) == before and b.techniques.catalog.events == events
    slot = a['player_loadout'][0]
    assert slot['pricing'] == pricing and slot['cost'] == technique_cost(book, 100.)
    assert slot['resource'] == 'mana'
    assert 'enemy_loadout' not in a and len(a['player_loadout']) == 1
    assert all('name' in row for row in a['events'])
    assert load_battle(before).report()['technique_effects']['player_loadout'] == a['player_loadout']
    slot['name'] = 'modified client'
    assert b.report()['technique_effects']['player_loadout'][0]['name'] == book['name']


def test_insufficient_mana_is_snapshot_not_fake_payment():
    b = fight([manual(mana_cost=20.)], mana=0.)
    step(b, 1)
    shown = b.report()['technique_effects']
    assert shown['player_loadout'][0]['affordable'] is False
    assert shown['player_loadout'][0]['used'] == 0
    assert not any(e['event'] == 'paid' and e['owner'] == 'player' for e in shown['events'])


def test_lineage_energy_uses_original_receipts_and_cooldown():
    b = lineage_battle(lineage_manual())
    begin(b, 1)
    before = copy.deepcopy(dump_battle(b))
    slot = b.report()['technique_effects']['player_loadout'][0]
    assert slot['resource'] == 'energy' and slot['used'] == 1
    assert slot['cooldown'] == 3 and slot['paid'] == 2.
    assert dump_battle(b) == before


def test_empty_and_npc_only_battles_do_not_invent_loadouts():
    b = fight([], [manual()])
    assert b.report()['technique_effects']['player_loadout'] == []
    b.units['original-npc'] = b.units.pop('player')
    assert 'player_loadout' not in b.report()['technique_effects']
