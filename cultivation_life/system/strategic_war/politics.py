"""Actual, deduplicated council ballots and revocable coalition mandates."""
from ...npc_custody import is_free
from ...spatial_people import instance_of
from .rules import organizations, owns, ref, committed_org, representatives


def council(deps, game, race, rng):
    pool = [*game.world_npcs.values(), *game.notable_npcs.values(),
            *(n for o in organizations(game, game.player.world) for n in deps.members(game, o))]
    voters = {n.id:n for n in pool if is_free(n) and n.world==game.player.world and n.race==race
              and n.realm_index>=8 and not instance_of(game,n.id) and not deps.imprisoned(game,n.id)}
    votes = [dict(id='player', yes=True)]
    votes.extend(dict(id=n.id,yes=rng.random()<deps.vote_probability(0,'truce',float(n.affinity or 0))) for n in voters.values())
    return dict(yes=sum(v['yes'] for v in votes), total=len(votes), age=game.player.age)


def player_eligible(deps, game, row, side):
    return any(c['side']==side and (org:=committed_org(game,row,c)) and owns(deps,game,org)
               for c in row['commitments'])


def player_commander(deps,game,row):
    return next((s for s,c in row['commanders'].items() if c.get('person_id')=='player'
                 and c['expires']>game.player.age and player_eligible(deps,game,row,s)),None)


def nominate(deps,game,row,side,rng):
    if not player_eligible(deps,game,row,side) or row['status'] not in {'mobilizing','active'}:
        raise ValueError('只有已承诺出征组织的实际决策者才能竞任联军统帅')
    if game.player.age-row.get('nomination_age',-1000)<10:
        raise ValueError('十年内不能重复发起统帅推举')
    reps={}
    for c in row['commitments']:
        if c['side']!=side:continue
        org=committed_org(game,row,c)
        if not org:continue
        if owns(deps,game,org):
            reps['player']=True
        else:
            n=next((n for n in representatives(deps,game,row,c) if n.id==c['representative']),None)
            if n:
                reps[n.id]=rng.random()<max(.15,min(.9,.45+float(n.affinity or 0)/200))
    result=dict(yes=sum(reps.values()),total=len(reps),age=game.player.age)
    row['nomination_age']=game.player.age
    row['nomination_vote']=result
    if result['yes']>result['total']/2:
        row['commanders'][side]=dict(person_id='player',name=game.player.name,expires=game.player.age+100,
                                     votes=result['yes'],electorate=result['total'])
    return result


def opposing_reply(deps,game,row,side,accept):
    reps={}
    for c in row['commitments']:
        if c['side']!=side:continue
        person=next((n for n in representatives(deps,game,row,c) if n.id==c['representative']),None)
        if person:
            reps[person.id]=accept
    return dict(yes=sum(reps.values()),total=len(reps),age=game.player.age)
