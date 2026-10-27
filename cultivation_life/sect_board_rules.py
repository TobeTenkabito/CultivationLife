"""Shared board defaults and withdrawal limits, including old depot claims."""
from .content_registry import WORLD_SYSTEMS


def defaults():
    return dict(revision=0,sequence=0,minimum_realm=1,recruitment_open=True,
        influence={},tasks=[],quota={},salaries=[],dismissals=0,salary_year=None,
        arrears=0,history=[],notices=[])


def minimum(rank,world):
    return 5*(rank+1)**2*WORLD_SYSTEMS['world_profiles'][world]['tier']


def limit(game):
    return max(100,minimum(game.player.realm_index,game.player.world)*2)


def quota(game,board):
    row=board.get('quota',{})
    return row if row.get('unit')==game.diplomacy_unit else dict(unit=game.diplomacy_unit,
        value=0,completions=0,npc_completions=0,posts=0)


def can_withdraw(game,used,value,quantity,*,item=False):
    return used+value<=limit(game) or (item and used==0 and quantity==1)


def claim(game,entity,value,quantity):
    if entity.kind!='sect' or game.player.faction_id!=entity.id or game.player.world!=entity.world:return
    row=game.intrigue_state['factions'][f'sect:{entity.id}']
    board=row.setdefault('task_board',defaults())
    q=dict(quota(game,board))
    if not can_withdraw(game,q['value'],value,quantity,item=True):
        raise ValueError('本单位府库额度不足；高价物资请每次申请一件，并在未使用额度的行动单位领取')
    q['value']+=value
    board['quota']=q
    board['revision']+=1
