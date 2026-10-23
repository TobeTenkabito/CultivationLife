"""Bounded visual identities, read-only and independent of combat/randomness."""
from hashlib import sha256

from .relationship_records import find_person
from .visual_selection import select_assets


def beast_kind(name):
    if any(word in name for word in ('鹰', '鹫', '鸟', '禽', '鹏', '鹤', '鸦', '隼')):
        return 'avian'
    if any(word in name for word in ('虫', '螳', '蝎', '蛛', '蜂', '蛾', '蝶', '蚁', '蝉')):
        return 'insect'
    if any(word in name for word in ('虎', '狼', '熊', '豹', '狮', '兽', '猿', '鹿', '牛')):
        return 'quadruped'
    return ('avian', 'quadruped', 'insect')[int.from_bytes(sha256(name.encode()).digest()[:2], 'big') % 3]


def _gender(value, identity):
    return value if value in {'male', 'female'} else ('male', 'female')[sha256(identity.encode()).digest()[2] % 2]


def _human_assets(path, gender, identity, *, companion=False):
    faction = 'demonic' if path == 'demonic' else 'dao'
    first = int.from_bytes(sha256(identity.encode()).digest()[:2], 'big') % 3
    pool = [f"{faction}-{(first + i) % 3 + 1}-{'m' if gender == 'male' else 'f'}" for i in range(3)]
    if faction == 'dao':
        if companion:
            pool.insert(0, f'companion-{gender}')
        else:
            pool.append(f'companion-{gender}')
    return pool


def _team_visuals(game, target, hero, player_units=None):
    """Read the actual deployed units only; never synthesize extra combatants."""
    puppets = {str(row.get('id')): row for row in game.player.puppets}
    party = {str(row.get('npc_id') or row.get('id')): row for row in game.player.party}
    allies = {str(row.get('npc_id') or f'story-ally-{i}'): row for i, row in enumerate(target.get('player_allies', []))}
    members = target.get('members') or [dict(target, id=target.get('npc_id') or 'enemy-0',
        name=target.get('target_name', '未知对手'), kind='beast' if target.get('combat_type') == 'beast' else 'cultivator')]
    enemy = [dict(row, id=str(row.get('npc_id') or f'enemy-{i}')) for i, row in enumerate(members)]
    own = [vars(row) if not isinstance(row, dict) else row for row in player_units] if player_units is not None else [
        dict(id='player', name=game.player.name, kind='player', power=1, integrity=1)]
    pools, requests = [], []
    teams, counts = {}, {}
    for side, rows in [('hero', own), ('npc', enemy)]:
        eligible = [row for row in rows if float(row.get('integrity', 1)) > 0 and float(row.get('power', 1)) > 0]
        counts[side] = len(eligible)
        team = []
        for row in eligible[:3]:
            key, kind = str(row['id']), str(row.get('kind', 'cultivator'))
            facts = {**allies.get(key, {}), **party.get(key, {}), **puppets.get(key, {}), **row}
            source_id = str(facts.get('source_npc_id') or facts.get('npc_id') or
                            (row.get('name', target.get('target_name', key)) if key.startswith('enemy-') else key))
            person = find_person(game, source_id, include_inactive=True) if kind != 'player' else None
            cached = next((entry.get('npc') or {} for entry in game.encounter_npc_cache if str(entry.get('id')) == source_id), {}) if person is None else {}
            path = person.path if person else cached.get('path', facts.get('path', target.get('path', 'dao')))
            original_gender = person.gender if person else cached.get('gender', facts.get('gender', target.get('gender', target.get('target_gender')) if side == 'npc' and len(rows) == 1 else None))
            gender = _gender(original_gender, source_id)
            if kind == 'player':
                pool = [hero]
                gender = hero.rsplit('-', 1)[1]
                if gender == 'shared':
                    gender = None
            elif kind == 'mechanical':
                pool = ['mechanical-puppet']
                gender = None
            elif kind == 'corpse':
                pool = [f'corpse-{gender}']
            elif kind == 'beast':
                pool = [beast_kind(str(row.get('name', target.get('target_name', '妖兽'))))]
                gender = None
            else:
                pool = _human_assets(path, gender, source_id or str(row.get('name', '')), companion=kind in {'companion', 'living'})
            member = dict(id=key[:96], kind=kind, gender=gender,
                name=str(row.get('name', '无名参战者'))[:64],
                weight=round(max(.001, float(row.get('power', 1)) * float(row.get('integrity', 1))), 4))
            team.append(member)
            pools.append(pool)
            requests.append(member)
        teams[side] = team
    for member, asset in zip(requests, select_assets(pools)):
        member['asset'] = asset
    return teams, counts


def combat_identity(game, target, *, player_units=None):
    """Snapshot the participants before deaths/possession can change identity."""
    player = game.player
    host = player.ghost_host_body or {}
    hero_path = 'demonic' if host.get('path', player.path) == 'demonic' else 'dao'
    hero_gender = host.get('gender', player.gender)
    hero_gender = hero_gender if hero_gender in {'male', 'female'} else 'male'
    natal = game.natal_artifact or {}
    artifact = next((a for a in player.crafted_artifacts if a.get('id') == natal.get('crafted_artifact_id')), None) if natal.get('crafted_artifact_id') else None
    hero = f'{hero_path}-{hero_gender}'
    from .monster_visuals import fox_appearance
    appearance = fox_appearance(player)
    if appearance:
        hero = appearance['combat']
    teams, counts = _team_visuals(game, target, hero, player_units)
    return dict(schema_version=2, hero=hero, enemy=teams['npc'][0]['asset'] if teams['npc'] else None,
                teams=teams, team_counts=counts,
                natal_item_id=natal.get('item_id'), natal_mold_id=artifact.get('mold_id') if artifact else None)


def report_visuals(game, target, report, *, identity=None):
    domains = any(row.get('voisinage', {}).get('animation', {}).get('fields')
                  for row in report.get('rounds', []))
    if not any(row.get('ordinary_exchange') and row.get('initiative') in {'player', 'enemy'}
               for row in report.get('rounds', [])) and not domains:
        return None
    roster = report.get('player_roster')
    # Trial summaries intentionally expose only the player's name and power,
    # not BattleUnit IDs. Their authoritative participant is still the player.
    if not roster or not all('id' in row and 'kind' in row for row in roster):
        roster = None
    if identity is not None and not domains:
        return identity
    visual = dict(identity) if identity is not None else combat_identity(game, target, player_units=roster)
    if domains:
        # Local presentation preferences and OS entropy never consume combat RNG.
        from .runtime import persistence_root
        from .ui_preferences import load_ui_preferences
        from secrets import choice
        defaults = dict(outline='mist', pattern='mist', palette='jade', control='rings', density=65)
        settings = load_ui_preferences(persistence_root()).get('voisinage_appearance', defaults)
        owners = dict.fromkeys(f['owner'] for row in report['rounds']
            for f in row.get('voisinage', {}).get('animation', {}).get('fields', []))
        existing = report.get('visual', {}).get('domains', {})
        visual['domains'] = {owner: existing.get(owner) or (dict(settings) if owner == 'player' else
            dict(defaults, palette=choice(('rose','peach','gold','lime','green','jade','cyan','blue',
                                         'indigo','violet','lilac','pink')),
                 outline=choice(('mist','star','frost','lotus','sword','seal','water','mountain','wood','thunder','moon','void','time')),
                 pattern=choice(('mist','star','frost','lotus','sword','seal','water','mountain','wood','thunder','moon','void','time')),
                 control=choice(('rings','talismans','stars','lotus','pillars','crystal')))) for owner in list(owners)[:64]}
    return visual
