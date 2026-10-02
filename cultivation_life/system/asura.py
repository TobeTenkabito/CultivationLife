"""Optional eightfold cultivation, projected into the shared combat semantics."""
import copy
import random

from ..content_registry import WORLD_SYSTEMS
from ..combat_semantics import parse_rule
from .combat.contracts import CapabilitySource, VoisinageDefinition, VoisinageEffect
from .doctrine.voisinage_training import multiplier, label

ROUTE_NAMES = dict(zip(('deva', 'naga', 'yaksha', 'gandharva', 'mahoraga', 'kinnara', 'garuda', 'asura'),
                      ('天', '龙', '夜叉', '乾达婆', '摩睺罗', '紧那罗', '迦楼罗', '阿修罗')))


def config():
    return WORLD_SYSTEMS.get('asura_manifestation', {})


def enabled():
    return bool(config().get('enabled'))


def active(player):
    return enabled() and player.path == 'demonic' and player.world == 'asura' and player.realm_index >= 9


def generate_rule(rng, key, preferred=None):
    templates = config()['semantic_templates']
    index = preferred if preferred is not None and rng.random() < .65 else rng.randrange(len(templates))
    rule = copy.deepcopy(templates[index])
    rule.update(schema_version=3, id=key, source_id=key)
    for action in rule['actions']:
        action['value'] = round(action['value'] * rng.uniform(.8, 1.2), 3)
    parse_rule(rule)
    return rule


def ensure(game):
    if not enabled() or game.player.asura_cultivation.get('branches'):
        return False
    s = game.player.asura_cultivation
    # A private stream gives identical catalogs in new and migrated games,
    # without consuming the world/event RNG or depending on UI reads.
    rng = random.Random(f'asura-v1:{game.seed}')
    s['branches'] = {}
    for key, route in config()['routes'].items():
        rows = []
        names = [a + b for a in config()['branch_prefixes'] for b in config()['branch_suffixes']]
        for i, name in enumerate(rng.sample(names, 3)):
            branch_id = f'asura:{key}:{i}'
            rows.append(dict(id=branch_id, name=name,
                rules=[generate_rule(rng, f'{branch_id}:{j}', route['preferred']) for j in range(3)]))
        s['branches'][key] = rows
    s.setdefault('souls', 0)
    s.setdefault('bodies', [])
    return True


def body_power(body):
    """Only the body's independent training coordinate contributes."""
    from .cultivation_ranks import body_rank, describe, STARTS
    from ..rules import expected_combat_power
    rank = body_rank(int(body.get('body_training') or 0), int(body.get('immortal_body_level') or 0))
    realm = describe(rank)['realm_index']
    width = (STARTS[realm + 1] if realm < 12 else 209) - STARTS[realm]
    layer = max(1, min(9, 1 + (rank - STARTS[realm]) * 9 // width))
    return round(expected_combat_power(realm, layer), 1)


def body_facts(actor):
    from .cultivation_ranks import ensure_npc
    from .monster_identity import identity
    row = copy.deepcopy(actor if isinstance(actor, dict) else actor.to_dict())
    if row.get("body_training") is None:
        ensure_npc(row)
    row.update(identity(row))
    return {key: row.get(key) for key in ('id', 'name', 'path', 'race', 'realm_index', 'layer',
        'body_training', 'immortal_body_level', 'divine_sense_rank', 'monster_species_id',
        'monster_evolution_id', 'true_spirit_kind', 'type')}


def eligible_routes(bodies):
    if not bodies or any(int(b.get('body_training') or 0) < config()['minimum_body_training'] for b in bodies):
        return []
    if len(bodies) == 2:
        return ['asura']
    if len(bodies) != 1:
        return []
    b = bodies[0]
    species, path = b.get('monster_species_id'), b.get('path')
    if b.get('type') == 'mechanical':
        return []
    # More specific lineage takes precedence; a serpent with a dragon form
    # qualifies for Naga, otherwise Mahoraga. Two bodies always mean Asura.
    if b.get('true_spirit_kind') == 'dragon' or 'DRAGON' in str(b.get('monster_evolution_id') or '').upper():
        return ['naga']
    if b.get('true_spirit_kind') == 'bird':
        return ['garuda']
    if path == 'monster':
        return {'serpent': ['mahoraga'], 'avian': ['garuda'], 'aquatic': ['naga'],
                'flora': ['gandharva'], 'fox': ['kinnara'], 'ape': ['kinnara']}.get(species, [])
    if path == 'demonic':
        return ['yaksha']
    if path in {'dao', 'buddhist'}:
        return ['deva']
    return []


def field_for(player, cap=None):
    s = player.asura_cultivation
    route = config()['routes'].get(s.get('route'))
    if not route:
        return None
    value = min(s.get('domain_rank', 1), cap or 13)
    strength = (95 + 10 * s.get('level', 1) + 5 * s.get('domain_power', 0)) * multiplier(value)
    kind = route['effect']
    key = 'asura:' + s['route']
    return VoisinageDefinition(key, s['domain_name'], key, 1, strength, 45, 18,
        kind, 24, .2, max_investment=120, max_targets=3, extra_target_cost=5,
        stability=strength * (1.15 if kind.startswith('restore') else 1),
        incursion=strength * (1.15 if kind == 'strike' else 1), authority=strength,
        effects=(VoisinageEffect(kind, 24, .2, target='self' if kind.startswith('restore') else 'enemy'),))


def source(player, cap=None):
    if not active(player) or not player.asura_cultivation.get('route'):
        return CapabilitySource()
    s, rules = player.asura_cultivation, []
    field = field_for(player, cap)
    route = config()['routes'][s['route']]
    for index, unlock in enumerate((2, 4, 7)):
        if s['level'] >= unlock:
            rule = copy.deepcopy(config()['semantic_templates'][(route['preferred'] + index * 4) % len(config()['semantic_templates'])])
            rule.update(schema_version=3, id=f'base:{index}', source_id=f'asura:{s["route"]}:base:{index}')
            rules.append(rule)
    branch = next((b for b in s['branches'][s['route']] if b['id'] == s.get('branch')), None)
    if branch:
        level = s.get('branch_level', 1)
        for raw in branch['rules'][:1 + (level - 1) // 3]:
            rule = copy.deepcopy(raw)
            for action in rule['actions']:
                action['value'] = round(action['value'] * (1 + .05 * (level - 1)), 3)
            rules.append(rule)
    rules.extend(s.get('powers', []))
    return CapabilitySource((field,), {field.attainment: 1}, semantic_rules=tuple(copy.deepcopy(rules)))


def inherited_power(player):
    return float(player.asura_cultivation.get('inherited_power', 0)) if enabled() and player.path == 'demonic' else 0


def intrinsic_bonus(player, resource):
    if not enabled() or player.path != 'demonic':
        return 0
    from .immortal_cultivation import rules
    s = player.asura_cultivation
    values = rules()['vein_intrinsic'][resource]
    veins = sum(min(27, max(0, s.get('veins', {}).get(str(r), 0))) * values[r - 9] for r in range(9, 13))
    return veins + s.get('body_level', 0) * (1200 if resource == 'hp' else 800)


def vein_ready(player):
    return player.asura_cultivation.get('veins', {}).get(str(player.realm_index), 0) >= player.layer * 3


def describe_rule(rule):
    conditions = {
        'self.body': '自身肉身完整度', 'target.body': '目标肉身完整度',
        'self.energy_ratio': '剩余煞元比例', 'target.pressure': '目标承压',
        'self.pressure': '自身承压', 'self.sustained_rounds': '持续开域轮数',
        'round': '战斗轮数', 'self.active_field': '自身正在开域', 'target.active_field': '目标正在开域',
    }
    effects = {'ordinary.received': '普通战斗承伤', 'ordinary.dealt': '普通战斗伤害',
        'field.suppress': '魔域压制', 'field.seal': '魔域封镇', 'field.strike': '魔域打击',
        'field.upkeep_cost': '魔域维持消耗', 'field.effect_cost': '施权消耗',
        'field.stability': '魔域稳固', 'field.incursion': '魔域侵夺', 'field.authority': '魔域权能'}
    c, a = rule['when'], rule['actions'][0]
    value = c['value']
    suffix = '' if isinstance(value, bool) else (
        f"{value:.0%}" if c['fact'].endswith(('.body', '_ratio')) else str(value))
    comparison = '' if isinstance(value, bool) else {'lt':'低于', 'le':'不超过', 'ge':'达到'}[c['op']]
    return (f"当{conditions[c['fact']]}{comparison}{suffix}时，"
            f"{effects[a['channel']]}{'提高' if a['value'] > 0 else '降低'} {abs(a['value']):.1%}。")


def public(game):
    p, s = game.player, game.player.asura_cultivation
    if not enabled() or p.path != 'demonic':
        return {'available': False}
    route = config()['routes'].get(s.get('route'), {})
    bodies = [dict(body_facts(b), source=kind) for kind, rows in (('prisoner', p.prisoners), ('puppet', p.puppets)) for b in rows]
    exposed = copy.deepcopy(s)
    for rows in exposed.get('branches', {}).values():
        for branch in rows:
            branch['descriptions'] = [describe_rule(r) for r in branch['rules']]
    for rule in exposed.get('powers', []):
        rule['description'] = describe_rule(rule)
    return dict(available=True, can_cultivate=active(p), **exposed,
        route_name=route.get('name', ''), part=route.get('part', ''),
        routes=[dict(id=k, **v) for k, v in config()['routes'].items()],
        candidates=[dict(b, body_power=body_power(b), eligible=int(b.get('body_training') or 0) >= config()['minimum_body_training']) for b in bodies],
        domain_label=label(s.get('domain_rank', 1)),
        slots=config()['slots'][max(0, s.get('level', 1) - 1)],
        opened=s.get('veins', {}).get(str(p.realm_index), 0),
        rule_descriptions=[r['name'] + '：' + describe_rule(r) for r in source(p).semantic_rules])
