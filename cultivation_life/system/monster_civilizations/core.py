"""Bounded aggregate simulation. Writes only its own additive state."""
from __future__ import annotations

from ...content_registry import CONTENT_DOCUMENTS
from ...monster_civilization_content import validate_state

DOCUMENT = 'monster_civilizations.json'
LAWS = {'eldest_eligible': '长幼传承', 'strongest_eligible': '强者继位', 'council_election': '族议推举'}
REGIMES = {'hereditary': '血裔世袭', 'strongest': '强者继位', 'council': '门阀共议', 'alliance': '百族盟约'}
PLAYER = '@player'


def config():
    return CONTENT_DOCUMENTS.get(DOCUMENT, {})


def executable(game):
    return bool(config()) and (not game.monster_civilization_state or game.monster_civilization_state.get('schema_version') == 1)


def marker(game):
    state = game.monster_civilization_state
    revision = state.get('revision', 0) if not state or state.get('schema_version')==1 else 0
    return dict(available=bool(config()), supported=executable(game),
                local=game.player.world in config().get('worlds', {}), revision=revision)


def people(game, world):
    """One authoritative index per political tick; never copy people into DLC state."""
    from ...person_assignments import in_transit, research_assignment, deployment_assignment
    from ...spatial_people import instance_of
    pools = [game.world_npcs, game.notable_npcs, game.relationship_npcs]
    result = {n.id: n for pool in pools for n in pool.values()}
    for sect in game.sects.values():
        result.update((n.id, n) for n in sect.npcs)
    if game.family:
        result.update((n.id, n) for n in game.family.npcs)
    return {key: n for key, n in result.items() if n.world == world and n.alive
            and n.roster_state == 'active' and not n.custody and key not in game.inactive_npcs
            and not instance_of(game, key) and not in_transit(game, key)
            and not research_assignment(game, key) and not deployment_assignment(game, key)}


def fact(game, world, kind, region, text, actors=(), cause='natural'):
    state = game.monster_civilization_state
    data = state['worlds'][world]
    state['sequence'] += 1
    row = dict(id=state['sequence'], year=game.player.age, world=world, region=region,
               kind=kind, actors=list(actors), cause=cause, text=text)
    # Only observed or personally participated facts become public information.
    row['visible'] = PLAYER in actors or (region in data['observations']
        and game.player.world==world and game.player.location_id==region)
    data['facts'].append(row)
    if len(data['facts']) > 192:
        old = data['facts'].pop(0)
        if old['visible']:
            summaries = data['summaries']
            if not summaries or summaries[-1]['end'] // 100 != old['year'] // 100:
                summaries.append(dict(start=old['year'], end=old['year'], count=0, kinds={}))
            summary = summaries[-1]
            summary['end'] = old['year']; summary['count'] += 1
            summary['kinds'][old['kind']] = summary['kinds'].get(old['kind'], 0) + 1
            if len(summaries) > 24:
                a, b = summaries[:2]
                b['start'] = a['start']; b['count'] += a['count']
                for key, value in a['kinds'].items():
                    b['kinds'][key] = b['kinds'].get(key, 0) + value
                summaries.pop(0)


def activate(game):
    world = game.player.world
    if not executable(game) or world not in config().get('worlds', {}):
        raise ValueError('当前界面没有可考察的万灵栖地')
    if not game.monster_civilization_state:
        game.monster_civilization_state = dict(schema_version=1, revision=0, sequence=0, worlds={})
    worlds = game.monster_civilization_state['worlds']
    if world in worlds:
        return worlds[world]
    cfg = config()['worlds'][world]
    regions = {}
    for i, region in enumerate(cfg['regions']):
        populations = {}
        for j, taxon in enumerate(cfg['taxa']):
            capacity = 800 + ((game.seed + i * 73 + j * 109) % 7) * 160
            populations[taxon] = dict(p=capacity * (50 + (i+j) % 20)//100, k=capacity, adaptation=0)
        regions[region] = dict(populations=populations, hunting=20, effect=None, case=None, case_year=-10000)
    data = dict(regions=regions, observations={}, clans={}, player_clan=None, facts=[], summaries=[],
                last_year=game.player.age, ecology_clock=0, political_clock=0, political_elapsed=0,
                court=dict(regime='council', phase='stable', ruler=None, legitimacy=55, last_proposal=-1000),
                cooldowns={}, known_clans=[])
    worlds[world] = data
    if world != 'human':
        homes = {}
        for sect in game.sects.values():
            home = getattr(sect, 'location_id', None)
            if home in regions:
                homes.update((n.id, home) for n in sect.npcs)
        roster = [n for n in people(game, world).values() if n.path == 'monster' and (n.location_id in regions or n.id in homes)]
        for n in sorted(roster, key=lambda n: n.id)[:4]:
            create_clan(game, world, n.location_id if n.location_id in regions else homes[n.id], n.id, n.name + '氏', share=1000)
    return data


def create_clan(game, world, region, founder, name, *, parent=None, share=1000):
    data = game.monster_civilization_state['worlds'][world]
    if len(data['clans']) >= 16:
        raise ValueError('本界祖源名录已满，仍可加入或复兴既有氏族')
    clan_id = f'{world}:clan:{len(data["clans"])+1}'
    clan = dict(id=clan_id, name=name, parent_id=parent, founder_id=founder, home=region,
                founded=game.player.age, law='strongest_eligible', leader=founder, members=[founder],
                share=share, status='active', successor_id=None, alliances=[], legitimacy=50, lineage_ref=None)
    data['clans'][clan_id] = clan
    fact(game, world, 'founded', region, f'{name}立族，立下祖源与族约。', [founder, clan_id], 'founder')
    return clan


def migrate(regions, edges):
    """Snapshot proposals, capacity-limited two-ended commit; no population creation."""
    proposals = []
    for source, target in edges:
        for a, b in ((source, target), (target, source)):
            if a not in regions or b not in regions:
                continue
            for taxon, pop in regions[a]['populations'].items():
                other = regions[b]['populations'].get(taxon)
                if not other or pop['k'] <= 0 or other['k'] <= 0:
                    continue
                if pop['p'] * other['k'] > other['p'] * pop['k'] * 1.25:
                    proposals.append((a, b, taxon, pop['p']//100))
    if not proposals:
        return 0
    remaining, spare, changes = {}, {}, {}
    moved = 0
    for a, b, taxon, count in proposals:
        source, target = (a, taxon), (b, taxon)
        if source not in remaining: remaining[source] = regions[a]['populations'][taxon]['p']
        if target not in spare:
            destination = regions[b]['populations'][taxon]
            spare[target] = max(0, destination['k']-destination['p'])
        accepted = min(count, remaining[source], spare[target])
        remaining[source] -= accepted; spare[target] -= accepted
        changes[source] = changes.get(source, 0)-accepted
        changes[target] = changes.get(target, 0)+accepted; moved += accepted
    for (r, t), delta in changes.items():
        regions[r]['populations'][t]['p'] += delta
    return moved


def ecology_year(game, world, data):
    content = config()
    roles = {key:row['role'] for key,row in content['taxa'].items()}
    season = (game.seed + game.player.age * 17) % 31 - 15
    weather_loss = max(0, -season)//3
    hundred_year = game.player.age % 100 == 0
    for region_index, (region_id, row) in enumerate(data['regions'].items()):
        # Wild pressure varies by habitat season, independently of every economic ledger.
        row['hunting'] = 15 + 10*((game.seed + region_index + data['ecology_clock']//50)%6)
        effect = row.get('effect')
        if effect and effect['until'] <= data['ecology_clock']:
            row['effect'] = effect = None
        hunt = max(0, row['hunting'] - (effect['relief'] if effect else 0))
        populations = row['populations']
        prey = predators = before = capacity = 0
        for taxon,pop in populations.items():
            count = pop['p'];before += count;capacity += pop['k']
            if roles[taxon]=='grazer': prey += count
            elif roles[taxon]=='predator': predators += count
        baseline_loss = 8 + hunt//4 + weather_loss
        predator_pressure = max(0, predators*2-prey)
        predator_denominator = max(1, (predators*2+prey)*25)
        grazer_denominator = max(1, (prey+predators)*(65 if effect and effect['kind']=='guide' else 40))
        after = 0
        for taxon, pop in populations.items():
            old, k = pop['p'], pop['k']
            if not k or not old:
                after += old
                continue
            role = roles[taxon]
            birth = old*(k-old)//(k*20) if old<k else 0
            mortality = old*baseline_loss//1000
            if role == 'predator':
                mortality += old*predator_pressure//predator_denominator
            elif role == 'grazer':
                mortality += old*predators//grazer_denominator
            pop['p'] = max(0, min(k, old + birth - mortality))
            after += pop['p']
            if hundred_year:
                pop['adaptation'] = min(3, pop.get('adaptation', 0) + (hunt > 35))
        ratio = after/max(1, capacity)
        case = ('depleted' if ratio < .45 else 'predators' if predators > prey*.35 else
                'recovery' if effect and after > before else 'forest' if ratio > .75 else
                'dispersal' if ratio > .65 else 'abundance' if season > 10 else None)
        if case and game.player.age-row['case_year'] >= 50 and row.get('case') != case:
            row['case'] = case; row['case_year'] = game.player.age
            fact(game, world, 'ecology', region_id, content['cases'][case], cause=case)
        elif row.get('case') and ((row['case']=='depleted' and ratio>.4) or (row['case']=='predators' and predators<=prey)):
            fact(game, world, 'recovery', region_id, '栖地的失衡已缓解，万灵逐渐恢复生息。', cause='resolved')
            row['case'] = None
    maps = CONTENT_DOCUMENTS['maps.json']['worlds'][world]
    regions = data['regions']
    edges = [(r['from'],r['to']) for r in maps['routes'] if r['from'] in regions and r['to'] in regions]
    moved = migrate(data['regions'], edges)
    if moved and game.player.age % 100 == 0:
        for region in data['observations']:
            fact(game, world, 'migration', region, '邻接栖地之间出现迁徙，族群沿既有山川道路流动。', cause='capacity')


def candidates(game, clan, roster):
    valid = [key for key in clan['members'] if key == PLAYER and game.player.alive
             and game.player.world in config().get('worlds', {}) or key in roster]
    def score(key):
        n = game.player if key == PLAYER else roster[key]
        if clan['law'] == 'eldest_eligible':
            return (n.age, n.realm_index, key)
        if clan['law'] == 'council_election':
            return (key == clan['founder_id'], n.realm_index, n.layer, key)
        return (n.realm_index, n.layer, n.age, key)
    return sorted(valid, key=score, reverse=True)


def politics(game, world, data):
    roster = people(game, world)
    for clan in data['clans'].values():
        if clan['status'] != 'active':
            continue
        eligible = candidates(game, clan, roster)
        if clan['leader'] not in eligible:
            old = clan['leader']; clan['leader'] = eligible[0] if eligible else None
            if not eligible:
                clan['status'] = 'dormant'
            fact(game, world, 'succession', clan['home'], f'{clan["name"]}完成继承审议。' if eligible else f'{clan["name"]}无人可承族约，暂入沉寂。', [clan['id'], old], 'eligibility')
    if world != 'human':
        _cultural_changes(game, world, data, roster)
    if world == 'nether':
        settle(game, data, roster)


def _cultural_changes(game, world, data, roster):
    """Sparse cultural choices by existing people, bounded to one change per tick."""
    members = {key for c in data['clans'].values() for key in c['members']}
    homes = {n.id:sect.location_id for sect in game.sects.values() if sect.world==world
             and sect.location_id in data['regions'] for n in sect.npcs}
    for n in sorted(roster.values(), key=lambda n:n.id):
        home = n.location_id if n.location_id in data['regions'] else homes.get(n.id)
        if n.path!='monster' or not home or n.id in members:
            continue
        local = [c for c in data['clans'].values() if c['home']==home and c['status']=='active'
                 and c['leader']!=PLAYER and len(c['members'])<12]
        if local:
            clan = min(local, key=lambda c:(len(c['members']),c['id']))
            clan['members'].append(n.id)
            clan['legitimacy']=min(100,clan['legitimacy']+3)
            fact(game, world, 'growth', home, f'{clan["name"]}有新的真实修士接受族约。', [clan['id'],n.id], 'cultural_admission')
            break
        available = 10000-sum(c['share'] for c in data['clans'].values() if c['home']==home)
        if len(data['clans'])<16 and available>=500:
            create_clan(game, world, home, n.id, n.name+'氏', share=min(1000,available))
            break
    for clan in list(data['clans'].values()):
        if clan['status']=='dormant' and candidates(game,clan,roster):
            clan.update(status='active',leader=candidates(game,clan,roster)[0])
            fact(game,world,'revival',clan['home'],f'{clan["name"]}原族员归来，重续文化传承。',[clan['id'],clan['leader']],'registered_member_return')
            break
        if clan['status']=='active' and clan['leader']!=PLAYER and data['political_clock']%4==0:
            eligible=[key for key in candidates(game,clan,roster) if key!=clan['leader'] and key!=PLAYER]
            if eligible and clan['share']>=1000 and len(data['clans'])<16:
                founder=eligible[-1];person=roster[founder]
                child=create_clan(game,world,clan['home'],founder,person.name+'支',parent=clan['id'],share=clan['share']//2)
                clan['members'].remove(founder);clan['share']-=child['share']
                fact(game,world,'split',clan['home'],f'{clan["name"]}分出{child["name"]}，族众与祖源分别登记。',[clan['id'],child['id']],'cultural_branch')
                break


def advance_year(game):
    if not executable(game) or not game.monster_civilization_state:
        return
    state = game.monster_civilization_state
    for world, data in state['worlds'].items():
        if game.player.age <= data['last_year']:
            continue
        data['last_year'] = game.player.age  # No replay after DLC pause or time jumps.
        data['ecology_clock'] += 1
        ecology_year(game, world, data)
        if game.player.world == world:
            data['political_elapsed'] += 1
            interval = 100 if world == 'nether' else 50
            if data['political_elapsed'] >= interval:
                data['political_elapsed'] = 0; data['political_clock'] += 1
                politics(game, world, data)
    state['revision'] += 1


def settle(game, data, roster):
    court = data['court']
    rulers = [c for c in data['clans'].values() if c['status']=='active' and c['leader']]
    if court['ruler'] and any(c['leader']==court['ruler'] for c in rulers):
        court['legitimacy'] = min(100, court['legitimacy']+2)
        return
    court['phase'] = 'succession'
    if not rulers:
        court.update(ruler=None, legitimacy=max(0, court['legitimacy']-5), phase='disputed')
        return
    if court['regime']=='hereditary':
        rulers = [c for c in rulers if c['parent_id'] or c['leader']==c['founder_id']]
    if not rulers:
        court['phase']='disputed'; return
    def rank(clan):
        leader = game.player if clan['leader']==PLAYER else roster.get(clan['leader'])
        power = (leader.realm_index, leader.layer) if leader else (0, 0)
        return (power if court['regime']=='strongest' else (clan['legitimacy'], len(clan['alliances'])), clan['id'])
    winner = max(rulers, key=rank)
    court.update(ruler=winner['leader'], phase='stable', legitimacy=max(40, winner['legitimacy']))
    fact(game, 'nether', 'court', winner['home'], f'{winner["name"]}获诸族承认为王庭正统。此承认不授万妖宫议席。', [winner['id'], winner['leader']], 'succession')

