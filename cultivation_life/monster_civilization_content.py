"""Independent DLC definitions and save boundary; no runtime/content-registry imports."""
from __future__ import annotations

WORLDS = {'human', 'monster_realm', 'phantom_underworld', 'nether'}


def validate_content(doc, maps):
    if doc.get('schema_version') != 1 or set(doc.get('worlds', {})) != WORLDS:
        raise ValueError('万灵内容版本或界面不合法')
    taxa = doc.get('taxa', {})
    if not 3 <= len(taxa) <= 12:
        raise ValueError('万灵种群数量不合法')
    if any(not isinstance(t, dict) or t.get('role') not in {'plant','grazer','predator'} or not isinstance(t.get('name'),str) for t in taxa.values()):
        raise ValueError('种群名称或食性不合法')
    for world, config in doc['worlds'].items():
        regions = config.get('regions', [])
        actual = {r['id'] for r in maps['worlds'][world]['locations']}
        if not 3 <= len(regions) <= 6 or len(set(regions)) != len(regions) or not set(regions) <= actual:
            raise ValueError(f'{world} 栖地须引用原地图')
        if not 3 <= len(config.get('taxa', [])) <= 8 or not set(config['taxa']) <= taxa.keys():
            raise ValueError('栖地种群不合法')
    blocs = doc.get('blocs', [])
    if [b.get('weight') for b in blocs] != [5, 4, 3, 2, 1] or [b.get('official_id') for b in blocs] != [f'myriad_beast_palace_{i}' for i in range(5)]:
        raise ValueError('五门阀须保留原议权和稳定人物编号')


def validate_state(state):
    if not isinstance(state, dict):
        raise ValueError('万灵存档必须为对象')
    if not state or state.get('schema_version') != 1:
        return  # Unknown optional sub-version is preserved, execution is blocked.
    if any(type(state.get(k)) is not int or state[k]<0 for k in ('revision','sequence')):
        raise ValueError('万灵序号不合法')
    worlds = state.get('worlds', {})
    if not isinstance(worlds, dict) or not set(worlds) <= WORLDS:
        raise ValueError('万灵存档界面不合法')
    for data in worlds.values():
        if not isinstance(data, dict) or len(data.get('regions', {})) > 6 or len(data.get('clans', {})) > 16:
            raise ValueError('万灵存档超出规模限制')
        if any(type(data.get(k)) is not int or data[k]<0 for k in ('ecology_clock','political_clock','political_elapsed','last_year')):
            raise ValueError('万灵纪历不合法')
        for region in data.get('regions', {}).values():
            if len(region.get('populations', {})) > 8:
                raise ValueError('种群超出规模限制')
            for pop in region.get('populations', {}).values():
                if any(type(pop.get(key)) is not int or not 0 <= pop[key] <= 100000 for key in ('p', 'k')):
                    raise ValueError('种群和承载量须为有限非负整数')
        clans = data.get('clans', {})
        members = set()
        for clan_id, clan in clans.items():
            if len(clan.get('members', [])) > 12 or type(clan.get('share')) is not int or not 0 <= clan['share'] <= 10000:
                raise ValueError('氏族人口或名册不合法')
            if clan.get('home') not in data['regions'] or clan.get('status') not in {'active','dormant','merged'} or clan.get('law') not in {'eldest_eligible','strongest_eligible','council_election'}:
                raise ValueError('氏族祖地或族约不合法')
            for npc_id in clan.get('members', []):
                if npc_id in members:
                    raise ValueError('同一人物不可同时登记于两个氏族')
                members.add(npc_id)
            cursor, visited = clan_id, set()
            while cursor:
                if cursor in visited or cursor not in clans:
                    raise ValueError('氏族祖源必须为无环、完整的编号链')
                visited.add(cursor)
                cursor = clans[cursor].get('parent_id')
        for region in data['regions']:
            if sum(c['share'] for c in clans.values() if c['home']==region)>10000:
                raise ValueError('栖地氏族份额不可重复认领')
        if len(data.get('facts', [])) > 192 or len(data.get('summaries', [])) > 24:
            raise ValueError('万灵志超出保留上限')
