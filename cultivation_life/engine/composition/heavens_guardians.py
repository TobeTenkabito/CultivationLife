"""Materialize a local guardian from its scene and settle its existing wounds."""
from ...definition_data import definition as _content_definition


GUARDIANS = _content_definition(__name__, "GUARDIANS")
ENCOUNTER = _content_definition(__name__, "ENCOUNTER")


def fight_guardian(engine, game, kind, identity, base_power, wounds, rng, *, chamber=None):
    template = GUARDIANS[kind]
    power = base_power * (1 - .15 * wounds)
    member = dict(template, name=template['name'].format(chamber=chamber),
                  npc_id=identity, power=power, wounds=wounds)
    target = dict(ENCOUNTER, target_name=member['name'], target_power=power,
                  target_realm_index=member['realm_index'], target_layer=member['layer'],
                  combat_type=member['kind'], members=[member], artificial_conditions=[])
    before = game.last_combat_report
    result, summary = engine._combat(game, target, True, rng)
    report = game.last_combat_report if game.last_combat_report is not before else {}
    wounds = max(wounds, member.get('wounds', 0), min(4, int((1 - report.get('enemy_hp_ratio', 1)) * 4)))
    return result, summary, wounds
