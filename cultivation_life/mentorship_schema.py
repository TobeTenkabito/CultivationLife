"""Structure-12 additive school ledger validation, independent of gameplay."""
RANKS = ('registered', 'true', 'personal', 'heir')
LABELS = dict(zip(RANKS, ('记名弟子', '真传弟子', '亲传弟子', '嫡传弟子')))


def validate(value):
    if not isinstance(value, dict) or set(value) - {'schools', 'avatar', 'rebellion'}:
        raise ValueError('师门状态结构无效')
    if 'avatar' in value:
        row = value['avatar']
        if not isinstance(row, dict) or set(row) != {'id', 'consented', 'enabled', 'last_age'} or not isinstance(row['id'], str) or not row['id'] or type(row['consented']) is not bool or type(row['enabled']) is not bool or type(row['last_age']) is not int or row['last_age'] < 0:
            raise ValueError('身外化身凭据无效')
    if 'rebellion' in value:
        row = value['rebellion']
        if not isinstance(row, dict) or set(row) != {'ids', 'at', 'cooldown_until'} or not isinstance(row['ids'], list) or len(row['ids']) > 4 or not all(isinstance(k, str) and k for k in row['ids']) or len(set(row['ids'])) != len(row['ids']) or any(type(row[k]) is not int or row[k] < 0 for k in ('at', 'cooldown_until')):
            raise ValueError('叛师预警凭据无效')
    schools = value.get('schools', {})
    if not isinstance(schools, dict): raise ValueError('师门名册无效')
    for teacher, school in schools.items():
        if not isinstance(teacher, str) or not teacher or not isinstance(school, dict): raise ValueError('师父身份无效')
        if type(school.get('initialized')) is not bool or not isinstance(school.get('students'), dict): raise ValueError('师门初始化记录无效')
        for identity, row in school['students'].items():
            if not isinstance(identity, str) or identity == teacher or not isinstance(row, dict): raise ValueError('弟子身份无效')
            if row.get('rank') not in RANKS or row.get('status') not in {'active', 'departed', 'graduated', 'expelled'}: raise ValueError('弟子位次或状态无效')
            state = row.get('advanced', {})
            requests = row.get('peer_requests', {})
            if not isinstance(requests, dict) or any(
                not isinstance(key, str) or not key or key in {identity, teacher}
                or not isinstance(actions, dict)
                or set(actions) - {'peer_consult', 'peer_spar', 'peer_item', 'peer_technique'}
                or any(type(cycle) is not int or cycle < 0 or cycle > row.get('cycle', 0) for cycle in actions.values())
                for key, actions in requests.items()
            ): raise ValueError('同门交流凭据无效')
            flags = {'pact_possession', 'pact_avatar', 'plot'}
            counters = {'pact_possession_cycle', 'pact_avatar_cycle', 'sow_cycle', 'challenge_cycle', 'precision_cycle', 'precision_used'}
            if not isinstance(state, dict) or set(state) - (flags | counters) or any(type(v) is not bool if k in flags else type(v) is not int or v < 0 for k, v in state.items()) or state.get('precision_used', 0) > 3:
                raise ValueError('师门传承凭据无效')
            if 'former_relation' in row:
                from .relationship_schema import PERSON_FIELDS, LABEL_FIELDS
                former = row['former_relation']
                if row['status'] == 'active' or not isinstance(former, dict) or set(former) & (PERSON_FIELDS | LABEL_FIELDS):
                    raise ValueError('离门履历只能保留原关系托管，不能复制人物')
            for field in ('loyalty', 'discontent'):
                if type(row.get(field)) is not int or not 0 <= row[field] <= 100: raise ValueError('师门情绪值无效')
            for field in ('merit', 'joined', 'period', 'due', 'last_tick', 'cycle', 'fulfilled', 'collected', 'promoted', 'honored', 'benefit_cycle', 'benefit_gain', 'support_cycle', 'support_used', 'discord_cycle', 'discord_gain'):
                if type(row.get(field)) is not int or row[field] < (-1 if field in {'fulfilled', 'collected', 'promoted', 'honored', 'benefit_cycle', 'support_cycle', 'discord_cycle'} else 0): raise ValueError('师门周期记录无效')
            if row['discord_gain'] > 15: raise ValueError('师门争执记录无效')
            if row['period'] < 1 or row['benefit_gain'] > 12 or row['support_used'] > 3: raise ValueError('师门额度无效')
            if type(row.get('warned')) is not bool or not isinstance(row.get('benefit_keys'), list) or len(row['benefit_keys']) > 12 or not all(isinstance(k, str) for k in row['benefit_keys']): raise ValueError('师门凭据无效')
