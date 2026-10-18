"""Validate regional clocks and resumable travel without advancing either."""
import ast
import random
# Schema 10 normal-world identifiers; independent of the runtime registry.
WORLDS = frozenset({'human', 'demon', 'spirit', 'true_demon', 'monster_realm',
                   'phantom_underworld', 'hell', 'celestial', 'asura', 'nether', 'reincarnation'})


def validate(value):
    known = WORLDS
    age = value['player'].get('age', 16)
    state = value.get('world_simulation', {})
    if not isinstance(state, dict):
        raise ValueError('地区时间状态必须为对象')
    if state:
        if state.get('version') != 1 or set(state.get('regions', {})) != known:
            raise ValueError('地区时间版本或界面清单不兼容')
        base = state.get('base_year')
        if type(base) is not int or not 0 <= base <= age:
            raise ValueError('地区结算基准无效')
        for row in state['regions'].values():
            if (not isinstance(row, dict) or type(row.get('year')) is not int
                    or not base <= row['year'] <= age or type(row.get('initialized')) is not bool
                    or type(row.get('merchant_year')) is not int or not base <= row['merchant_year'] <= row['year']):
                raise ValueError('地区时钟无效或超前')
            if not isinstance(row.get('rng'), str) or len(row['rng']) > 30000:
                raise ValueError('地区随机状态无效')
            try:
                random.Random().setstate(ast.literal_eval(row['rng']))
            except (ValueError, TypeError, SyntaxError, OverflowError) as exc:
                raise ValueError('地区随机状态损坏') from exc
        if not isinstance(state.get('people'), dict) or any(
                not isinstance(k, str) or type(v) is not int or not base <= v <= age
                for k, v in state['people'].items()):
            raise ValueError('人物年度结算标记无效')
        if type(state.get('revision')) is not int or state['revision'] < 0 or not isinstance(state.get('recent'), list) or len(state['recent']) > 16:
            raise ValueError('地区同步记录无效')
    journey = value.get('map_journey')
    if journey is not None:
        if (not isinstance(journey, dict) or journey.get('world') not in known | {'lost', 'rift'}
                or not isinstance(journey.get('origin'), str) or not isinstance(journey.get('destination'), str)
                or type(journey.get('years')) is not int or journey['years'] < 0
                or type(journey.get('completed')) is not int or not 0 <= journey['completed'] <= journey['years']
                or not isinstance(journey.get('route'), list) or len(journey['route']) < 2
                or journey['route'][0] != journey['origin'] or journey['route'][-1] != journey['destination']):
            raise ValueError('远行进度无效')
