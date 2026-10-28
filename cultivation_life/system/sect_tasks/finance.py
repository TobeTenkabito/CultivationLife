"""Annual salaries debit the original treasury, highest cultivation first."""
from .state import ensure, members, minimum, record, merit, event, note, active
from ..economy.ledger import account, balance, transfer_value
from ..economy.organization_accounts import pay
from ..economy.depot import treasury
from ..sect_membership import release


def wallet(game, identity):
    key='player' if identity=='player' else f'person:{identity}'
    if identity!='player':
        account(game,key)
    return key


def donate(game,sect,identity,amount):
    if type(amount) is not int or not 100<=amount<=10**9:
        raise ValueError('每次捐献100至十亿灵石，每100灵石获得5贡献')
    source=wallet(game,identity)
    transfer_value(game,source,treasury(game,sect),amount,'宗门捐献')
    points=amount//100*5
    merit(game,sect,identity,points)
    board=ensure(game,sect)
    if identity=='player' and board['arrears']>0:
        board['rescue_donation']=dict(player_id=game.id,joined_age=game.player.faction_join_age,
            history_index=len(game.history),world=game.player.world)
    board['influence'][identity]=min(1000,board['influence'].get(identity,0)+amount//100)
    note(game,sect,f'{members(game,sect)[identity].name}捐献{amount}灵石，贡献+{points}。')


def salaries(game,sect,finance,years=1):
    if not active(game,sect):return 0
    years=1  # Never replay years spent outside this membership/world.
    board=ensure(game,sect)
    if board['salary_year'] is not None and board['salary_year']>=game.player.age:
        return 0
    # The annual economy owns this clock. Adoption never awards historic wages.
    board['salary_year']=game.player.age
    people=members(game,sect)
    ordered=sorted(people,key=lambda k:(-people[k].realm_index,-people[k].layer,k))
    dues={k:minimum(people[k].realm_index,sect.world)*years for k in ordered}
    total=sum(dues.values())
    cash=balance(game,treasury(game,sect))
    # Bonuses are funded only after all minimums plus three years' upkeep remain.
    bonus=min(total//2,max(0,cash-total-int(finance.get('expected_upkeep',0)*3)))
    board['salaries']=[]
    short=paid_total=0
    for identity in ordered:
        due=dues[identity]
        extra=bonus*due//max(1,total)
        paid=pay(game,treasury(game,sect),wallet(game,identity),due+extra,'宗门年度薪俸')
        short+=paid<due
        paid_total+=paid
        board['salaries'].append(dict(id=identity,name=people[identity].name,realm=people[identity].realm_index,
            minimum=due,paid=paid,year=game.player.age))
        board['influence'][identity]=min(1000,board['influence'].get(identity,0)+2+people[identity].realm_index)
    board['arrears']=sum(max(0,r['minimum']-r['paid']) for r in board['salaries'])
    board['unpaid_members']=short
    finance['expense']+=paid_total
    finance['shortfall']=finance.get('shortfall',0)+board['arrears']
    row=record(game,sect)
    if short:
        row['unrest']=min(100.,row.get('unrest',0)+2+10*short/max(1,len(ordered))+2*board['dismissals'])
        board['crisis_years']=board.get('crisis_years',0)+1
    else:
        row['unrest']=max(0.,row.get('unrest',0)-5)
        board['crisis_years']=0
    # A member may spend only actual salary savings, never a fabricated NPC purse.
    for identity in ordered:
        if identity=='player': continue
        spare=balance(game,wallet(game,identity))-3*dues[identity]
        gift=min(1000,max(0,spare//10)//100*100)
        if gift>=100 and (short or row['unrest']>=30):
            donate(game,sect,identity,gift)
    board['revision']+=1
    if not short:
        rescue=board.pop('rescue_donation',None)
        if rescue and rescue['player_id']==game.id and rescue['world']==game.player.world and rescue['joined_age']==game.player.faction_join_age:
            intervening=game.history[rescue['history_index']:]
            interrupted=any(r.event_id in {'SYS_PLAYER_LEAVE_FACTION','SYS_CROSS_WORLD'}
                or isinstance(r.state_diff.get('world'),list) and len(r.state_diff['world'])==2
                and r.state_diff['world'][0]!=r.state_diff['world'][1] for r in intervening)
            if not interrupted:
                game.player.milestones['rescued_sect_payroll']=1
        return paid_total
    severity=row['unrest']
    previous=board.get('crisis_stage',0)
    stage=3 if severity>=95 and board['crisis_years']>=3 else 2 if severity>=70 else 1 if severity>=40 else 0
    if not stage:
        board['crisis_stage']=0
        return paid_total
    if stage<=previous and game.player.age-board.get('crisis_event_year',game.player.age)<5:
        return paid_total
    board['crisis_stage']=stage
    board['crisis_event_year']=game.player.age
    if stage==1:
        event(game,sect,'conflict',f'{sect.name}有{short}人未领足最低薪俸，执事堂发生争薪冲突，门内不满{severity:.0f}。')
    elif stage==2:
        from ...person_assignments import research_assignment
        candidates=[people[k] for k in ordered if k!='player' and k not in game.intrigue_state.get('npc_prisons',{}) and not research_assignment(game,k)]
        if candidates:
            npc=candidates[0]
            release(game,sect,row,npc)
            event(game,sect,'departure',f'{sect.name}长期欠薪，{npc.name}率先离宗；其修为、寿元与个人财物保留。')
    else:
        board['dissolve_pending']=True
        event(game,sect,'dissolution',f'{sect.name}连年欠薪，门内冲突失控，门人宣布解散山门。')
    return paid_total
