"""Known celestial and three local-world traditions, without catalog duplication."""
from dataclasses import asdict
from ..content_registry import WORLD_SYSTEMS, CONTENT_DOCUMENTS
from .world_voisinage_projection import project


def origin(identity):
    if identity.startswith('celestial:'):
        return 'celestial'
    for world, cfg in WORLD_SYSTEMS['upper_voisinages']['worlds'].items():
        if any(identity == 'upper:' + row['id'] for row in cfg['fields']):
            return world
    return None


def identities(game):
    return [k for k in game.doctrine_state.get('definitions', {}) if k.startswith('celestial:')] + [
        'upper:' + row['id'] for cfg in WORLD_SYSTEMS['upper_voisinages']['worlds'].values() for row in cfg['fields']]


def definition(game, identity):
    if identity.startswith('celestial:'):
        return game.doctrine_state.get('definitions', {}).get(identity)
    for world, cfg in WORLD_SYSTEMS['upper_voisinages']['worlds'].items():
        for row in cfg['fields']:
            if identity != 'upper:' + row['id']:
                continue
            stages = []
            ranks = {4: 1, 5: 3, 6: 5, 7: 8, 8: 10, 9: 13}
            for level in range(1, 10):
                field = asdict(project(row, ranks[level])) if level >= 4 else None
                stages.append(dict(level=level, voisinage=field))
            path, energy = {'asura': ('demonic','demon'), 'nether': ('monster','monster'), 'reincarnation': ('ghost','yin')}[world]
            return dict(id=identity, name=row['name'] + '传承', stages=stages,
                        manuals=[dict(name=row['name'] + '真解', path=path, element='neutral', sources={energy: 1})])
    return None


def celestial_definition(source):
    """An explicitly adapted foreign tradition joins normal celestial cultivation."""
    rules = CONTENT_DOCUMENTS['doctrines.json']
    key = source['id']
    book = dict(id=key + ':manual:celestial', doctrine_id=key, name=source['manuals'][0]['name'] + '·仙解',
                path='dao', element='neutral', grade=9, level=1, category='spiritual',
                requires_immortal_power=True, immortal_power_cost=.025, opportunity_bonus=.5,
                hp_bonus=.4, mp_bonus=.4, combat_bonus=0, effective_worlds=['celestial'], sources={'spirit': 1},
                combat_requirements={'source': {'id': 'spirit', 'op': '>=', 'level': 30}})
    stages = []
    for level in range(1, 10):
        field = None
        if level >= 4:
            field = dict(source['stages'][level - 1]['voisinage'])
            field.update(id=key + ':voisinage', attainment=key, required_level=4,
                         opening_cost=100 + level * 15, upkeep_cost=20 + level * 5,
                         effect_cost=20 + level * 4, extra_target_cost=15, max_investment=80,
                         max_targets=min(4, 1 + (level - 4) // 2))
            field['effects'] = [dict(e, cost=field['effect_cost']) for e in field['effects']]
        stages.append(dict(level=level, title=f'异源承接第{level}章', years=rules['level_years'][level - 1],
                           realm=rules['level_realms'][level - 1], voisinage=field,
                           description='循原传承，以仙灵力重新参悟。', features=[], ability_name=source['name']))
    return dict(id=key, name=source['name'] + '·仙解', fixed=True, origin_world=origin(key),
                description='来自其它上界的残解，经明确补全后纳入仙界修持。', stages=stages, manuals=[book])
