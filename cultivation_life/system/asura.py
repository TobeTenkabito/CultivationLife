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


def body_cost(player):
    """Use the immortal meridian's base resource scale, not the legacy realm bar."""
    from .immortal_cultivation import rules
    level = player.asura_cultivation.get('body_level', 0)
    return rules()['vein_opportunity_base'] * (level + 1) if level < 20 else 0


def power_reroll_quote(state):
    powers = state.get('powers', [])
    locked = set(state.get('locked_power_ids', [])) & {r['id'] for r in powers}
    return dict(locked_ids=sorted(locked), unlocked=len(powers) - len(locked),
                cost=100 * 2 ** len(locked))


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
    from ..cultivation_coordinates import body_rank, describe, STARTS
    from ..combat_benchmarks import expected_combat_power
    rank = body_rank(int(body.get('body_training') or 0), int(body.get('immortal_body_level') or 0))
    realm = describe(rank)['realm_index']
    width = (STARTS[realm + 1] if realm < 12 else 209) - STARTS[realm]
    layer = max(1, min(9, 1 + (rank - STARTS[realm]) * 9 // width))
    return round(expected_combat_power(realm, layer), 1)


def body_facts(actor):
    from .npc_cultivation import ensure_npc
    from ..ancestry import species_identity
    row = copy.deepcopy(actor if isinstance(actor, dict) else actor.to_dict())
    if row.get("body_training") is None:
        ensure_npc(row)
    row.update(species_identity(row, WORLD_SYSTEMS.get('monster_species', {})))
    return {key: row.get(key) for key in ('id', 'name', 'path', 'race', 'realm_index', 'layer',
        'body_training', 'immortal_body_level', 'divine_sense_rank', 'monster_species_id',
        'monster_evolution_id', 'true_spirit_kind', 'type', 'form')}


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
        from ..puppet_content import FORMS
        route = FORMS.get(b.get('form'), {}).get('route')
        return [route] if route else []
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


def public_meridians(player):
    """One authoritative quote shared by the action and the cultivation screen."""
    if not active(player):
        return {'available': False}
    from .immortal_cultivation import rules
    from .doctrine.cultivation import vein_cost
    from ..cultivation_costs import breakthrough_cost
    cfg, state = rules(), player.asura_cultivation
    total, per_layer = cfg['veins_per_realm'], cfg['veins_per_layer']
    opened = min(total, max(0, int(state.get('veins', {}).get(str(player.realm_index), 0))))
    required = min(total, player.layer * per_layer)
    failures = state.get('vein_pity', {}).get(f'{player.realm_index}:{opened + 1}', 0)
    probability = min(1., cfg['vein_success_rates'][min(8, opened // per_layer)] + failures * cfg['vein_pity_step'])
    cost = vein_cost(player.realm_index, opened, cfg) if opened < required else None
    reason = ('须先完成五重煞元转化' if state.get('conversion', 0) < 5 else
              '本境二十七条魔脉已全部贯通' if opened >= total else
              '本层三条魔脉已贯通，请先手动突破' if opened >= required else
              '开辟魔脉的机缘不足' if player.opportunity < cost['opportunity'] else
              '开辟魔脉的精魂不足' if state.get('souls', 0) < cost['traces'] else '')
    values = cfg['vein_intrinsic']
    return dict(available=True, opened=opened, total=total, per_layer=per_layer,
        layer=player.layer, required=required, ready=opened >= required,
        realm=WORLD_SYSTEMS['demonic_cultivation']['realm_names'][str(player.realm_index)],
        opportunity=player.opportunity, souls=state.get('souls', 0),
        next_cost=dict(opportunity=cost['opportunity'], souls=cost['traces']) if cost else None,
        chance=probability, failures=failures, pity_step=cfg['vein_pity_step'],
        can_open=not reason, reason=reason,
        breakthrough_cost=breakthrough_cost(player, upper_cultivation=(player.world == 'celestial' or active(player))),
        intrinsic_per_vein={key: values[key][player.realm_index-9] for key in ('hp', 'mp')},
        intrinsic_total={key: sum(min(total, max(0, state.get('veins', {}).get(str(r), 0))) * values[key][r-9]
                                 for r in range(9, 13)) for key in ('hp', 'mp')},
        nodes=[dict(index=i, layer=(i-1)//per_layer+1,
                    status='open' if i <= opened else 'next' if i == opened+1 and i <= required else 'locked')
               for i in range(1, total+1)],
        last_attempt=copy.deepcopy(state.get('last_vein_attempt')))


def public_body(body):
    """Distinguish the material body's training from the player's own body."""
    from ..cultivation_coordinates import body_rank, describe, NAMES
    facts = body_facts(body)
    mortal, higher = int(facts.get('body_training') or 0), int(facts.get('immortal_body_level') or 0)
    rank = describe(body_rank(mortal, higher))
    name = rank['name']
    if facts.get('path') == 'demonic' and rank['realm_index'] >= 9:
        name = name.replace(NAMES[rank['realm_index']], WORLD_SYSTEMS['demonic_cultivation']['realm_names'][str(rank['realm_index'])])
    return dict(facts, body_training=mortal, immortal_body_level=higher,
                body_realm=name, body_power=body_power(facts),
                eligible=mortal >= config()['minimum_body_training'] and body.get('alive', True),
                matched_route=next((ROUTE_NAMES[key] for key in eligible_routes([facts])), ''),
                condense_cost=30 + mortal)


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
    if not active(p):
        return {'available': False}
    route = config()['routes'].get(s.get('route'), {})
    bodies = [dict(public_body(b), source=kind) for kind, rows in (('prisoner', p.prisoners), ('puppet', p.puppets))
              for b in rows if b.get('alive', True)]
    exposed = copy.deepcopy(s)
    for rows in exposed.get('branches', {}).values():
        for branch in rows:
            branch['descriptions'] = [describe_rule(r) for r in branch['rules']]
    for rule in exposed.get('powers', []):
        rule['description'] = describe_rule(rule)
    exposed['bodies'] = [dict(b, **{k:v for k,v in public_body(b).items() if k not in b}) for b in s.get('bodies', [])]
    field = field_for(p) if active(p) else None
    from .conversion import quote
    return dict(available=True, can_cultivate=active(p), **exposed, conversion_quote=quote(game, asura=True),
        route_name=route.get('name', ''), part=route.get('part', ''),
        routes=[dict(id=k, **v) for k, v in config()['routes'].items()],
        candidates=bodies, meridians=public_meridians(p),
        body_cost=body_cost(p), power_reroll=power_reroll_quote(s),
        minimum_body_training=config()['minimum_body_training'],
        domain_stats={key:getattr(field,key) for key in ('stability','incursion','authority')} if field else {},
        domain_label=label(s.get('domain_rank', 1)),
        slots=config()['slots'][max(0, s.get('level', 1) - 1)],
        opened=s.get('veins', {}).get(str(p.realm_index), 0),
        rule_descriptions=[r['name'] + '：' + describe_rule(r) for r in source(p).semantic_rules])
