"""One-time advanced birth prerequisites. Never invoked by loading/migration."""
import math
import random

from ...content_registry import MONSTER_EVOLUTIONS, REALMS


def monster(player, seed):
    from ...system.monster_bloodline_system import (
        bloodline_content_available, _stable_history_for_realm, grant_generated_species_bloodline_trait,
    )
    if player.path != 'monster' or not bloodline_content_available() or player.realm_index < 1:
        return
    species = player.monster_species_id
    if player.realm_index >= 9:
        # An authored attained ancestry, not a fabricated self-founded rulebook.
        current = f'{species.upper()}_NETHER_TRUE_{player.realm_index - 8}'
        history = []
        while current:
            history.append(current)
            node = MONSTER_EVOLUTIONS[current]
            parents = node.get('parents', [])
            current = parents[0] if parents else None
        history.reverse()
    else:
        history = _stable_history_for_realm(species, player.realm_index)
    def prerequisites(condition):
        if not condition:
            return
        if 'all' in condition:
            for child in condition['all']:
                prerequisites(child)
        elif 'any' in condition:
            prerequisites(condition['any'][0])
        elif condition.get('op') == 'contains':
            values = {'player.monster.imprints': player.monster_bloodline_imprints,
                      'player.monster.adaptations': player.monster_adaptations}.get(condition['path'])
            if values is not None and condition['value'] not in values:
                values.append(condition['value'])
    for key in history:
        prerequisites(MONSTER_EVOLUTIONS[key].get('requirements'))
    player.monster_evolution_history, player.monster_evolution_id = history, history[-1]
    rng = random.Random(f'dlc-birth-monster:{seed}:{species}:{player.realm_index}')
    for _ in range(min(12, player.realm_index)):
        grant_generated_species_bloodline_trait(player, rng)


def ghost(player, seed):
    from ...system.ghost_resources import ghost_cultivation_active, ghost_phase_two_config, SOUL_SLOTS
    from ...ghost_soul_traits import generate_soul_trait
    from ...combat_benchmarks import expected_combat_power
    from ...system.ghost.progression import grant_wangsheng
    if not ghost_cultivation_active(player) or player.realm_index < 2:
        return
    grant_wangsheng(player, sum(r.layers for r in REALMS[1:player.realm_index]) + player.layer - 1)
    rng = random.Random(f'dlc-birth-ghost:{seed}:{player.realm_index}')
    pressure = ghost_phase_two_config().get('soul_pressure', {})
    for index, slot in enumerate(list(SOUL_SLOTS)[:min(10, player.realm_index)]):
        realm = max(1, player.realm_index - 1)
        power = round(expected_combat_power(realm, 1) * .8, 1)
        key = f'birth-soul:{seed}:{index}'
        trait = generate_soul_trait(rng)
        player.ghost_bound_souls.append(dict(id=key, npc_id=key, name=f'故契·{slot}', path='ghost', race='human',
            realm_index=realm, layer=1, combat_power=power, affinity=30, defeated=False, befriended=True,
            is_bound_soul=True, personality='守诺', npc_relations=[], skills=[trait['name']],
            faction_inclination='散魂', original_identity='开局前结契的独立遗魂', soul_trait=trait,
            soul_pressure=round(float(pressure.get('base', .5)) + float(pressure.get('power_cap', 2)) *
                (1-math.exp(-power/max(1, float(pressure.get('power_scale', 5000))))), 2)))
        player.ghost_soul_slots[slot] = key


def scholar(player):
    if player.path == 'confucian':
        from ...system.sage_system import sage_content_available, haoran_threshold
        if sage_content_available():
            player.haoran_exp = haoran_threshold(min(30, max(0, player.realm_index-1)*3))


def upper_path(game, custom=None):
    from ...system import asura
    p = game.player
    if asura.active(p):
        s = p.asura_cultivation
        s.setdefault('body_level', 20 if p.realm_index >= 10 else min(20, (p.layer-1)*2))
        s['souls'] = max(s.get('souls', 0), 100 * (p.realm_index-8))
        # Ninth-realm entry has not necessarily completed the one-time body
        # fusion. Preserve that choice; later attained births may inherit it.
        if p.realm_index == 9 and not s.get('route'):
            return
        # Respect explicit custom domain selection, otherwise seed the path's
        # attained native body. No NPC bodies are cloned into this birth grant.
        s.setdefault('route', 'yaksha')
        s.setdefault('level', min(9, 1 + (p.realm_index-9)*2 + (p.layer-1)//3))
        s.setdefault('domain_name', '夜叉本命魔域')
        s.setdefault('domain_rank', min(9, 1 + (p.realm_index-9)*2))
        s.setdefault('domain_power', 0)
        s.setdefault('branch', s['branches'][s['route']][0]['id'])
        s.setdefault('branch_level', min(9, s['level']))
        rng = random.Random(f'dlc-birth-asura:{game.seed}')
        s.setdefault('powers', [asura.generate_rule(rng, f'asura:power:{i}') for i in range(min(2, asura.config()['slots'][s['level']-1]))])
    if p.path == 'buddhist':
        from ...system.buddhist_wish import active, change
        from ...system.buddhist.rules import set_dharma_karma
        if active(game):
            change(game, min(60, max(0, p.realm_index-1)*5), '开局前清修积愿')
            set_dharma_karma(game, min(40, max(0, p.realm_index-1)*4))
