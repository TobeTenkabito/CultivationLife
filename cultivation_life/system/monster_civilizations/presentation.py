"""Discovery-limited projections; opening this view never activates a world."""
import copy
from . import core
from .actions import cost


def project(game, options=None):
    options = options or {}
    marker = core.marker(game)
    requested_world = options.get('world')
    world = game.player.world if requested_world is None else requested_world
    if not isinstance(world,str): raise ValueError('界面编号须为文字')
    if world not in core.config().get('worlds', {}) and world != game.player.world:
        raise ValueError('此界面没有可查阅的万灵图志')
    scoped = game.monster_civilization_state.get('worlds', {}) if marker['supported'] else {}
    data = scoped.get(world)
    maps = core.CONTENT_DOCUMENTS['maps.json']['worlds'].get(world, {})
    names = {r['id']:r['name'] for r in maps.get('locations', [])}
    local = world == game.player.world and game.player.location_id in core.config().get('worlds', {}).get(world,{}).get('regions', [])
    blocked = not local or not marker['supported'] or not game.player.alive or bool(game.pending_event or game.active_trial or game.player.imprisonment or game.player.ghost_captor)
    view = dict(**marker, world=world, year=game.player.age, location=game.player.location_id,
                world_name=core.CONTENT_DOCUMENTS['world.json']['systems']['world_profiles'].get(world,{}).get('name', world),
                regions=[], edges=[], clans=[], facts=[], summaries=[], court=None, player_clan=None, invitees=[], cooldowns={}, effect_years=0,
                actions_blocked=blocked, costs={a:cost(game,a) for a in ('observe','protect','guide','found','join','leave','invite','contest','law','branch','alliance','merge','revive','regime')},
                worlds=[w for w in core.config().get('worlds', {}) if w==game.player.world or w in scoped])
    if not marker['available'] or not marker['supported']:
        return view
    for region in core.config()['worlds'].get(world, {}).get('regions', []):
        observed = data['observations'].get(region) if data else None
        record = dict(id=region, name=names[region], current=local and region==game.player.location_id, known=bool(observed))
        if observed:
            record.update(copy.deepcopy(observed))
            for taxon, population in record['populations'].items():
                population['name']=core.config()['taxa'][taxon]['name']
                population['role']=core.config()['taxa'][taxon]['role']
            record['case_text']=core.config()['cases'].get(record.get('case'),'生息平稳')
        view['regions'].append(record)
    region_ids = {r['id'] for r in view['regions']}
    view['edges'] = [dict(source=r['from'],target=r['to']) for r in maps.get('routes',[]) if r['from'] in region_ids and r['to'] in region_ids]
    if not data: return view
    if local:
        prefix=':'+game.player.location_id
        view['cooldowns']={key[:-len(prefix)]:max(0,end-data['ecology_clock']) for key,end in data['cooldowns'].items() if key.endswith(prefix)}
        effect=data['regions'][game.player.location_id].get('effect')
        view['effect_years']=max(0,effect['until']-data['ecology_clock']) if effect else 0
    view['player_clan']=data['player_clan']
    for clan_id in data['known_clans']:
        clan = data['clans'].get(clan_id)
        if not clan: continue
        visible = {key:copy.deepcopy(clan[key]) for key in ('id','name','parent_id','home','founded','law','status','successor_id','alliances')}
        visible.update(home_name=names[clan['home']], leader_self=clan['leader']==core.PLAYER,
                       founder_self=clan['founder_id']==core.PLAYER,
                       member_self=core.PLAYER in clan['members'], law_name=core.LAWS[clan['law']],
                       lineage='祖源沉寂' if clan['lineage_ref'] and not core.CONTENT_DOCUMENTS.get('monster_bloodlines.json') else '已记祖源' if clan['lineage_ref'] else '文化传承')
        # Live leaders/member counts are only available at their home or to a member.
        if local and clan['home']==game.player.location_id or visible['member_self']:
            visible.update(important_members=len(clan['members']), share=clan['share'], vacant=clan['leader'] is None)
        view['clans'].append(visible)
    own=data['clans'].get(data['player_clan'])
    if local and own and own['leader']==core.PLAYER and own['home']==game.player.location_id:
        members={key for c in data['clans'].values() for key in c['members']}
        view['invitees']=[dict(id=n.id,name=n.name) for n in core.people(game,world).values()
                          if n.id not in members and n.location_id==game.player.location_id and n.path=='monster'
                          and n.encountered_player and (n.affinity or 0)>=50][:12]
    facts = [copy.deepcopy(row) for row in data['facts'] if row['visible']]
    kind = options.get('kind')
    if kind: facts=[r for r in facts if r['kind']==kind]
    query = options.get('query','')
    if not isinstance(query,str) or len(query)>40: raise ValueError('史册检索文字过长')
    if query: facts=[r for r in facts if query in r['text']]
    page = options.get('page',0)
    if type(page) is not int or not 0<=page<=15: raise ValueError('史册页码不合法')
    view.update(facts=list(reversed(facts))[page*12:page*12+12], page=page, total=len(facts), summaries=copy.deepcopy(data['summaries']))
    if world=='nether' and game.player.world==world:
        from .court import blocs
        view['court']=dict(regime=data['court']['regime'], regime_name=core.REGIMES[data['court']['regime']],
                           phase=data['court']['phase'], legitimacy=data['court']['legitimacy'],
                           ruler_self=data['court']['ruler']==core.PLAYER, clock=data['political_clock'],
                           blocs=blocs(game), regimes=core.REGIMES)
    return view
