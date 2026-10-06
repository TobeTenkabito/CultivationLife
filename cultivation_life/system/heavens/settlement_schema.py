"""Pure additive R3 save contract; R2 campaigns remain valid without this row."""
from .campaign_definitions import SOURCE, DEFENDER, TARGET_SITE
from .settlement_definitions import CONTROL_NAMES, TREATY_NAMES, TERM_YEARS, ADMIN_COST


def validate_settlement(state, row, now):
    keys = {'control', 'ever_occupied', 'governor_id', 'garrison_id', 'administration_spent',
            'mandates', 'treaty', 'treated', 'outcome', 'concluded_at'}
    if type(state) is not dict or set(state) != keys:
        raise ValueError('地方收束字段无效')
    units = {u['person_id']: u for u in row['units']}
    if not isinstance(state['control'], str) or state['control'] not in CONTROL_NAMES or type(state['ever_occupied']) is not bool:
        raise ValueError('地方控制状态无效')
    for key in ('governor_id', 'garrison_id'):
        if state[key] is not None and (not isinstance(state[key], str) or state[key] not in units):
            raise ValueError('地方职责缺少原人物')
    if (state['garrison_id'] and units[state['garrison_id']]['role'] != 'soldier'
            or state['governor_id'] and units[state['governor_id']]['role'] not in {'builder', 'defender'}):
        raise ValueError('地方职责与原编制不符')
    spent = state['administration_spent']
    if type(spent) is not int or spent < 0 or spent % ADMIN_COST or spent > row['budget']['spent']:
        raise ValueError('地方职责经费超出实支')
    if state['control'] in {'occupied', 'vassal'} and (not state['ever_occupied'] or not state['governor_id'] or not state['garrison_id']):
        raise ValueError('占领缺少地方职责或驻军')
    mandates = state['mandates']
    if type(mandates) is not dict or set(mandates)-{SOURCE, DEFENDER}:
        raise ValueError('议约委任主体无效')
    for faction, mandate in mandates.items():
        fields = {'faction_id', 'issuer_id', 'scope', 'source', 'delegate_id', 'world', 'location', 'granted_at', 'expires_at'}
        if type(mandate) is not dict or set(mandate) != fields:
            raise ValueError('议约委任字段无效')
        if not isinstance(mandate['delegate_id'], str):
            raise ValueError('议约代表引用无效')
        unit = units.get(mandate['delegate_id'])
        if (not unit or unit['faction_id'] != faction or unit['role'] != ('builder' if faction == SOURCE else 'defender')
                or mandate['faction_id'] != faction or mandate['scope'] != 'local_settlement'
                or mandate['world'] != 'human' or mandate['location'] != TARGET_SITE
                or not isinstance(mandate['source'], str)
                or mandate['source'] not in {'existing_office', 'native_sect_leadership'}
                or not isinstance(mandate['issuer_id'], str) or not mandate['issuer_id'] or mandate['issuer_id'] in {*units, 'player'}
                or type(mandate['granted_at']) is not int or not row['created_at'] <= mandate['granted_at'] <= now
                or type(mandate['expires_at']) is not int or mandate['expires_at'] != mandate['granted_at']+600):
            raise ValueError('议约委任越权或引用无效')
    treaty = state['treaty']
    if treaty is not None:
        fields = {'kind', 'status', 'signed_at', 'expires_at', 'world', 'location', 'signatories'}
        if (type(treaty) is not dict or set(treaty) != fields or not isinstance(treaty['kind'], str) or treaty['kind'] not in TREATY_NAMES
                or not isinstance(treaty['status'], str)
                or treaty['status'] not in {'active', 'expired', 'review', 'lapsed'}
                or treaty['world'] != 'human' or treaty['location'] != TARGET_SITE
                or set(mandates) != {SOURCE, DEFENDER}
                or treaty['signatories'] != {k: m['delegate_id'] for k, m in mandates.items()}
                or type(treaty['signed_at']) is not int or not row['created_at'] <= treaty['signed_at'] <= now
                or type(treaty['expires_at']) is not int or treaty['expires_at'] != treaty['signed_at']+TERM_YEARS):
            raise ValueError('地方协议范围、时限或签署引用无效')
        if any(not m['granted_at'] <= treaty['signed_at'] <= m['expires_at'] for m in mandates.values()):
            raise ValueError('签署时代表尚未取得有效委任')
    treated = state['treated']
    if type(treated) is not list or len(treated) > 4 or any(not isinstance(i, str) for i in treated) or len(set(treated)) != len(treated) or not set(treated) <= set(units):
        raise ValueError('救护记录重复或没有原人物')
    if state['outcome'] is not None and (not isinstance(state['outcome'], str)
            or state['outcome'] not in {*TREATY_NAMES, 'defended', 'occupation_ended', 'expedition_ended'}):
        raise ValueError('局部战争结局无效')
    if state['outcome'] is None:
        if state['concluded_at'] is not None:
            raise ValueError('尚未结清不能记录终局年份')
    elif (row['status'] not in {'withdrawn', 'failed'} or type(state['concluded_at']) is not int
          or not row['created_at'] <= state['concluded_at'] <= now):
        raise ValueError('战争结局尚未完成实际撤离与结清')
