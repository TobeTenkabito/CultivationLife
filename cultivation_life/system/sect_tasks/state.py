"""A board belongs to the original sect; contributions retain their old authority."""
from math import ceil
from functools import lru_cache
from ...content_registry import REALMS, ITEM_CATALOG, WORLD_SYSTEMS
from ...npc_custody import is_free
from ...models import HistoryRecord
from ..faction_geography import faction_site
from ..economy import depot
from ..economy.organization_accounts import faction_record
from ..organization_heritage import controls, decision
from ... import sect_board_rules as shared


def active(game, sect):
    root = getattr(game, '_game', game)
    return bool(sect and sect.kind=='sect' and not sect.extinct and root.player.alive
                and root.player.world not in {'lost','rift'}
                and root.player.faction_id==sect.id and root.player.world==sect.world
                and game.player.age==root.player.age)


def record(game, sect):
    return game.intrigue_state.get('factions', {}).get(f'sect:{sect.id}', {})


def snapshot(game, sect):
    return record(game, sect).get('task_board', shared.defaults())


def members(game, sect):
    people = {n.id:n for n in sect.npcs if is_free(n) and n.world == sect.world
              and n.faction_id in (None, sect.id)}
    if game.player.alive and game.player.faction_id == sect.id and game.player.world == sect.world:
        people['player'] = game.player
    return people


def leader(game, sect):
    offices = record(game, sect).get('positions', {})
    if 'leader' in offices:
        return offices['leader']
    people = members(game, sect)
    if controls(game, sect):
        return 'player'
    return max(people, key=lambda k:(people[k].realm_index,people[k].layer,k), default=None)


def ensure(game, sect):
    row = faction_record(game, 'sect', sect.id)
    if 'task_board' not in row:
        import copy
        row['task_board'] = copy.deepcopy(snapshot(game, sect))
    row.setdefault('positions', {}).setdefault('leader', leader(game, sect))
    row.setdefault('member_contribution', {})
    row.setdefault('unrest', 0.)
    return row['task_board']


def contribution(game, sect, identity):
    return game.player.faction_contribution if identity == 'player' else record(game,sect).get('member_contribution',{}).get(identity,0)


def merit(game, sect, identity, amount):
    if identity == 'player':
        game.player.faction_contribution = max(0,game.player.faction_contribution+amount)
    else:
        values = faction_record(game,'sect',sect.id).setdefault('member_contribution',{})
        values[identity] = max(0,values.get(identity,0)+amount)


def influence(game, sect, identity):
    return snapshot(game,sect)['influence'].get(identity,0)


def note(game, sect, text):
    board = ensure(game,sect)
    board['revision'] += 1
    board['history'] = (board['history']+[dict(year=game.player.age,text=text)])[-30:]


@lru_cache(maxsize=16)
def ordinary(world):
    # Only locally tradable raw materials; unique drops, pills and manuals excluded.
    return {k:r for k,r in depot.catalog(world).items() if r['kind']=='item'
            and set(ITEM_CATALOG[r['id']].tags) & {'material','crafting_material','formation_material','talisman_material','alchemy_material'}}


def minimum(rank, world):
    return shared.minimum(rank,world)


def quota(game, sect):
    return shared.quota(game,snapshot(game,sect))


def limit(game):
    return shared.limit(game)


def blocked(game, sect, *, at_site=True):
    p=game.player
    if not p.alive or not sect or sect.extinct or sect.kind!='sect' or p.faction_id!=sect.id or p.world!=sect.world:
        return '请先加入本界仍存续的宗门'
    if (at_site and p.location_id != faction_site(sect,persist=False)['id']) or p.world in {'lost','rift'}:
        return '请亲赴宗门驻地办理'
    from ..buddhist.rules import buddhist_active
    assembly=game.buddhist_state.get('assembly') or {}
    at_assembly=buddhist_active(game) and (assembly.get('world'),assembly.get('location'))==(p.world,p.location_id)
    if (game.pending_event or game.active_trial or p.imprisonment or p.ghost_captor
            or game.guixu_state.get('player_session') or at_assembly or p.nascent_state.get('crisis')):
        return '请先结束当前事件、战斗或受制状态'
    return None


def permissions(game,sect):
    is_leader=leader(game,sect)=='player'
    control=controls(game,sect)
    return dict(policy=is_leader or control, recruit=is_leader or decision(game,sect),
                expel=is_leader or control, dismiss=decision(game,sect))


def event(game,sect,kind,text):
    board=ensure(game,sect)
    note(game,sect,text)
    board['notices']=(board['notices']+[dict(kind=kind,text=text,year=game.player.age)])[-6:]
    game.history.append(HistoryRecord('SYS_SECT_FINANCE_'+kind.upper(),1,game.player.age,
        {'conflict':'门内争薪','departure':'高阶修士出走','dissolution':'宗门财政崩溃'}[kind],
        None,kind,text,{'sect_id':sect.id},['system','faction','finance','world_news',f'world:{sect.world}']))
