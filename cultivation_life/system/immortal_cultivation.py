"""Small player ledgers and pure cultivation rules, independent of UI and NPC ticks."""
from ..content_registry import CONTENT_DOCUMENTS


def rules():
    return CONTENT_DOCUMENTS['doctrines.json']['cultivation']


def golden_light(player):
    return int(player.immortal_body.get('level', 0)) >= rules()['body']['golden_light_level']


def vein_probability(player):
    cfg = rules()
    opened = player.immortal_veins.get(str(player.realm_index), 0)
    key = f'{player.realm_index}:{opened + 1}'
    stage = min(8, opened // cfg['veins_per_layer'])
    return min(1.0, cfg['vein_success_rates'][stage]
               + player.immortal_vein_pity.get(key, 0) * cfg['vein_pity_step'])


def vein_ready(player):
    return player.immortal_veins.get(str(player.realm_index), 0) >= player.layer * rules()['veins_per_layer']


def grant_trace_chance(player, gain):
    """One 7% trial per positive award. O(1); separate persisted PRNG stream.

    SplitMix64 avoids allocating a Random or disturbing event/NPC random streams.
    No rolls on spending, refunds, loading, presentation or elapsed years alone.
    """
    if gain <= 0:
        return False
    mask = (1 << 64) - 1
    player.immortal_trace_rng = (player.immortal_trace_rng + 0x9E3779B97F4A7C15) & mask
    value = player.immortal_trace_rng
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & mask
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & mask
    value ^= value >> 31
    success = (value >> 11) / (1 << 53) < rules()['trace_gain_chance']
    player.immortal_traces += int(success)
    return success


def body_manual(player):
    key = player.immortal_body.get('active_manual')
    if key not in player.immortal_body.get('manuals', []):
        return None
    return next((m for m in rules()['body']['manuals'] if m['id'] == key), None)


def body_probability(player):
    cfg = rules()['body']
    level = player.immortal_body.get('level', 0)
    base = max(cfg['minimum_chance'], cfg['base_chance'] - level * cfg['chance_step'])
    manual = body_manual(player)
    return min(1.0, base + (manual['chance_bonus'] if manual else 0)
               + player.immortal_body.get('failures', 0) * cfg['pity_step'])


def body_recipe(player):
    manual = body_manual(player)
    if not manual:
        return {}
    target = player.immortal_body.get('level', 0) + 1
    return {key: count * target for key, count in manual['recipe'].items()}


def body_intrinsic_bonus(player, resource):
    return player.immortal_body.get('level', 0) * rules()['body'][f'{resource}_per_level']
