"""Validated initial-life configuration; never an in-game relocation command."""
import copy

from ...content_registry import (WORLD_SYSTEMS, REALMS, ITEM_CATALOG, TECHNIQUE_CATALOG,
                                 FACTION_DEFINITIONS, ROOT_NAMES, PATH_NAMES)
from ...models import SectState, SectNpc, Technique
from ...rules import add_item, remove_item, learn_technique, can_player_practice_technique

TENDENCIES = {'strike': '杀伐', 'restore_hp': '回复', 'suppress': '镇压', 'seal': '封禁'}


def birth_families():
    return {f'birth-family-{world}-{index}': dict(name=WORLD_SYSTEMS['world_names'][world] + surname + '氏仙族',
             world=world, kind='family', path='dao')
            for world, profile in WORLD_SYSTEMS['world_profiles'].items() if profile['tier'] > 0
            for index, surname in enumerate(('周', '沈', '叶'))}


def catalog():
    from ...system.tianji_system import tianji_content_available
    from ...system.asura import enabled, ROUTE_NAMES
    return dict(
        realms=[dict(id=i, name=r.name, layers=r.layers) for i, r in enumerate(REALMS)],
        worlds={k: WORLD_SYSTEMS['world_names'][k] for k, p in WORLD_SYSTEMS['world_profiles'].items() if p['tier'] > 0},
        items=[dict(id=k, name=v.name, natal=bool(v.combat_bonus > 0 and
                    (set(v.tags) & {'artifact', 'equipment'} or k in WORLD_SYSTEMS['natal_artifact'].get('eligible_item_ids', []))))
               for k, v in ITEM_CATALOG.items()],
        techniques=[dict(id=k, name=t.name) for k, t in TECHNIQUE_CATALOG.items()],
        factions=[dict(id=k, name=v['name'], world=v.get('world', 'human'), kind=v.get('kind', 'sect'))
                  for k, v in {**FACTION_DEFINITIONS, **birth_families()}.items() if v.get('kind') != 'institution'],
        tendencies=TENDENCIES, asura_enabled=enabled(), asura_routes=ROUTE_NAMES,
        tianji_enabled=tianji_content_available(),
        tianji_brackets=15 if tianji_content_available() else 0)


def integer(data, key, default, minimum, maximum):
    value = data.get(key, default)
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'自定义 {key} 须为 {minimum} 至 {maximum} 的整数')
    return value


def validate(data, spirit_root, path):
    if not isinstance(data, dict):
        raise ValueError('自定义开局配置必须是对象')
    data = copy.deepcopy(data)
    data['realm_index'] = integer(data, 'realm_index', 1, 0, len(REALMS) - 1)
    realm = data['realm_index']
    data['layer'] = integer(data, 'layer', 1, 1, REALMS[realm].layers)
    world = data.get('world', 'human')
    if world not in WORLD_SYSTEMS['world_profiles'] or WORLD_SYSTEMS['world_profiles'][world]['tier'] <= 0:
        raise ValueError('自定义出生须选择已开放的普通界面')
    data['world'] = world
    if spirit_root not in ROOT_NAMES or path not in PATH_NAMES:
        raise ValueError('未知灵根或道途')
    roots = data.get('additional_roots', [])
    if not isinstance(roots, list) or any(r not in {'metal', 'wood', 'water', 'fire', 'earth'} for r in roots):
        raise ValueError('补全灵根须选择五行属性')
    data['additional_roots'] = list(dict.fromkeys(roots))
    for key, default, cap in [('body_training', 0, 100), ('immortal_body_level', 0, 100),
                               ('divine_sense_rank', 0, 1000), ('domain_rank', 0, 13), ('warming', 0, 100),
                               ('tianji_bracket', 0, 15)]:
        data[key] = integer(data, key, default, 0, cap)
    if data['tianji_bracket']:
        from ...system.tianji_system import tianji_content_available
        if not tianji_content_available():
            raise ValueError('携带神机需要启用巧夺天工 DLC')
    inventory = data.get('inventory', [])
    if not isinstance(inventory, list) or len(inventory) > 2000:
        raise ValueError('行囊最多配置 2000 类物品')
    for row in inventory:
        if not isinstance(row, dict) or row.get('id') not in ITEM_CATALOG:
            raise ValueError('行囊含未启用或不存在的物品')
        integer(row, 'quantity', 1, 1, 10**12)
    data['inventory'] = inventory
    techniques = data.get('techniques', [])
    if not isinstance(techniques, list) or len(techniques) > 2000 or any(k not in TECHNIQUE_CATALOG for k in techniques):
        raise ValueError('功法须来自本次启用的内容目录')
    data['techniques'] = list(dict.fromkeys(techniques))
    natal = data.get('natal_artifact')
    if natal:
        item = ITEM_CATALOG.get(natal)
        if not item or not any(row['id'] == natal for row in inventory):
            raise ValueError('本命法宝须选择自定义背包中已有的装备')
        if not (item.combat_bonus > 0 and (set(item.tags) & {'artifact', 'equipment'} or natal in WORLD_SYSTEMS['natal_artifact']['eligible_item_ids'])):
            raise ValueError('所选物品不是可认主的法宝装备')
    for kind in ('sect', 'family'):
        identity = data.get(kind, '')
        if identity and identity != 'new':
            faction = {**FACTION_DEFINITIONS, **birth_families()}.get(identity)
            if not faction or faction.get('world', 'human') != world or faction.get('kind', 'sect') != kind:
                raise ValueError('所属势力须为出生界面的相应宗门或家族')
        if identity == 'new':
            data[kind + '_name'] = str(data.get(kind + '_name', '')).strip()[:24] or ('自立宗门' if kind == 'sect' else '自立家族')
    if data.get('tendency', 'strike') not in TENDENCIES:
        raise ValueError('未知邻域倾向')
    if data['domain_rank'] and (realm < 6 or WORLD_SYSTEMS['world_profiles'][world]['tier'] < 2):
        raise ValueError('灵域开局须炼虚且位于二级界面；上界邻域须九阶修为')
    if data['domain_rank'] and WORLD_SYSTEMS['world_profiles'][world]['tier'] == 3 and realm < 9:
        raise ValueError('上界邻域需要九阶修为')
    return data


def preset(data, root, path):
    realm = data['realm_index']
    candidates = [r for r in WORLD_SYSTEMS['quick_start_presets'] if r['path'] == path and not r.get('select_path')]
    template = copy.deepcopy(min(candidates or WORLD_SYSTEMS['quick_start_presets'], key=lambda r: abs(r['realm_index'] - realm)))
    template.update(id='custom', name='自定义开局', spirit_root=root, path=path, world=data['world'],
                    realm_index=realm, layer=data['layer'], age=18, race='monster' if path == 'monster' else 'human',
                    inventory=data['inventory'], additional_roots=data['additional_roots'], body_training=data['body_training'],
                    divine_sense_rank=data['divine_sense_rank'], immortal_body={'level': data['immortal_body_level']},
                    world_voisinages={}, immortal_aperture={}, story_flags=['custom_start'],
                    immortal_power_converted=realm >= 9, opportunity_reserve=0, opportunity_fraction=0)
    for key in ('location_id', 'doctrine_starter', 'combat_techniques', 'body_technique', 'divine_sense_technique'):
        template.pop(key, None)
    # Starting manuals match the selected path and rank. Player-selected books
    # remain independent inventory grants, with ordinary equip rules thereafter.
    for slot, category in [('main', 'spiritual'), ('support', 'spiritual'), ('body', 'body'), ('divine_sense', 'divine_sense')]:
        books = [t for t in TECHNIQUE_CATALOG.values() if t.category == category and t.grade <= max(1, realm)
                 and t.path == path and t.element == 'neutral'
                  and (not t.requires_immortal_power or template['immortal_power_converted'])
                  and t.required_body_training <= data['body_training']
                 and (not t.effective_worlds or data['world'] in t.effective_worlds)]
        if books:
            template[slot + '_technique'] = max(books, key=lambda t: (t.grade, t.id)).id
    return template


def configure(game, data, rng, *, sync_natal):
    p = game.player
    # This is birth initialization, before any command/save is published.
    p.divine_sense_rank = data['divine_sense_rank']
    p.additional_roots = list(data['additional_roots'])
    for identity in data['techniques']:
        learn_technique(p, copy.deepcopy(TECHNIQUE_CATALOG[identity]))
    from ...system.faction_geography import faction_site
    from ...system.combat.npc_lifecycle import initialize_native
    for identity, definition in birth_families().items():
        if definition['world'] != p.world:
            continue
        clan = SectState(identity, definition['name'], p.world, [], kind='family', path='dao', founded_by_npc=True)
        site = faction_site(clan)['id']
        tier = WORLD_SYSTEMS['world_profiles'][p.world]['tier']
        for index in range(2):
            realm = max(1, {1:3, 2:6, 3:9}[tier] - index)
            npc = SectNpc(f'{identity}-{index}', definition['name'][-4] + ('承远' if index else '明玄'),
                '族长' if not index else '族人', realm, 1, 35, None if realm >= 6 else REALMS[realm].lifespan[1],
                world=p.world, faction_id=identity, location_id=site, spirit_root='supreme_earth')
            initialize_native(npc, WORLD_SYSTEMS.get('transcendent_combat', {}), now=p.age)
            clan.npcs.append(npc)
        clan.founder_npc_id = clan.npcs[0].id
        game.sects[identity] = clan
    for kind in ('sect', 'family'):
        choice = data.get(kind)
        if not choice:
            continue
        if choice == 'new':
            entity = SectState(f'custom-{kind}-{game.id}', data[kind + '_name'], p.world, [],
                path=p.path, kind=kind, founded_by_player=True, founder_player_id=game.id,
                location_id=p.location_id, player_founded_site=True, allegiance_race=p.race)
            from ...system.combat.npc_lifecycle import initialize_native
            for index, title in enumerate(('执事', '门人')):
                realm = max(1, p.realm_index - index - 1)
                member = SectNpc(f'{entity.id}-member-{index}', p.name + title, title,
                    realm, 1, 18, None if realm >= 6 else max(100, REALMS[realm].lifespan[1]),
                    world=p.world, faction_id=entity.id, location_id=p.location_id, path=p.path,
                    spirit_root=p.spirit_root, race=p.race)
                initialize_native(member, WORLD_SYSTEMS.get('transcendent_combat', {}), now=p.age)
                entity.npcs.append(member)
        else:
            entity = game.sects[choice]
        if kind == 'family':
            game.sects.pop(entity.id, None)
            game.family = entity
        else:
            game.sects[entity.id] = entity
            p.faction_id = entity.id
            p.faction_join_age = p.age
    if data.get('natal_artifact'):
        from ...system.natal_binding import bind_standard
        bind_standard(game, data['natal_artifact'])
        sync_natal(game)
    if data['domain_rank']:
        configure_domain(game, data)
    if data['tianji_bracket']:
        from ...system.tianji.starting_artifact import grant
        from ...system.tianji_system import _scaled_effects, tianji_content_available
        grant(game, data['tianji_bracket'], rng, scale=_scaled_effects, available=tianji_content_available())


def configure_domain(game, data):
    p, rank, warming = game.player, data['domain_rank'], data['warming']
    tendency = data.get('tendency', 'strike')
    from ...system.asura import active, config as asura_config
    p.immortal_aperture = dict(version=1, current=1000, capacity=1000, imitation_current=60, imitation_capacity=60)
    if active(p):
        routes = asura_config()['routes']
        route = data.get('asura_route') or next((k for k, r in routes.items() if r['effect'] == tendency), next(iter(routes)))
        if route not in routes:
            raise ValueError('未知八部本命')
        p.asura_cultivation.update(route=route, level=4, domain_name='本命魔域', domain_rank=rank,
                                  domain_power=warming, conversion=5, body_level=data['immortal_body_level'])
        return
    from ...system.upper_voisinage_rules import world_config
    upper = world_config(p)
    if upper:
        if rank > 13 or warming:
            raise ValueError('此道途邻域支持初成至至臻共十三阶，尚无独立温养轴')
        definition = max(upper['fields'], key=lambda r: int(tendency in r['effects']))
        p.world_voisinages[p.world] = dict(progression_version=2, levels={definition['id']: rank}, active=definition['id'])
        return
    from ...system.doctrine.state import ensure, player_record
    ensure(game, celestial_context=True)
    definitions = list(game.doctrine_state['definitions'].values())
    def score(row):
        field = row['stages'][3]['voisinage']
        return int(field.get('effect') == tendency) + sum(e.get('kind') == tendency for e in field.get('effects', []))
    definition = max(definitions, key=score)
    key = definition['id']
    if p.world != 'celestial':
        if rank > 9 or warming:
            raise ValueError('灵域残解支持一至九级，温养须飞升后修习仙域')
        from ...system.spirit_voisinage import grant
        book = grant(game, 'spirit:' + key, rank)
        p.spirit_voisinage_manual = book.id
        return
    record = player_record(game)
    record['progress'][key] = dict(level=4, experience=0)
    record['active'] = key
    record['annotations'][key] = list(range(1, 5))
    book = Technique(**copy.deepcopy(definition['manuals'][0]))
    book.level = 4
    learn_technique(p, book)
    record['voisinage_training'][key] = dict(rank=rank, stability=warming, incursion=warming, authority=warming)
