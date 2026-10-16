"""Small, read-only whitelisted theatre projection, scoped to the current world."""
from ...content_registry import RACE_DEFINITIONS, WORLD_SYSTEMS
from ...race_diplomacy import relations_for
from ...world_state import race_pair
from .rules import OPEN, WORLDS, SIDES, organizations, owns, ref
from .politics import player_commander, player_eligible
from ..war.logistics import cash
from ..war.occupancy import busy


def public(deps, game):
    pool = organizations(game, game.player.world)
    names = {o.id: o.name for o in pool}
    result = []
    blocked = bool(game.pending_event or game.active_trial or not game.player.alive or game.player.imprisonment or game.player.ghost_captor)
    for row in reversed(game.strategic_war_state.get('wars', [])):
        if row['world'] != game.player.world:
            continue
        commitments = [{**c['org'], 'name': names.get(c['org']['id'], '原组织'), 'side': c['side'], 'budget': c['budget']}
                       for c in row['commitments']]
        for c in commitments:
            org=next((o for o in pool if o.id==c['id']),None)
            c['idle']=bool(org and not busy(game,org))
            original=next(r for r in row['commitments'] if r['org']['id']==c['id'])
            c['willingness']=original.get('willingness',70)
            c['will_factors']=dict(original.get('will_factors',{}))
        children = []
        for child in game.wars:
            if child.get('strategic_war_id') != row['id']:
                continue
            from ..war.occupancy import participant_ids
            own = next((o for o in pool if owns(deps, game, o) and o.id in participant_ids(child) and o.id not in child.get('withdrawn_orgs',[])), None)
            place = deps.maps.location(row['world'], child.get('location_id')) or {}
            paths=[j for js in child.get('journeys',{}).values() for j in js]+list(child.get('cargo_journeys',{}).values())+[r['cargo'] for r in child.get('reinforcements',[])]
            remaining = max((j['remaining'] for j in paths if j['phase'] in {'outbound','returning'}),default=0)
            coalitions={s:[] for s in SIDES}
            for side in SIDES:
                for participant in child['coalitions'][side]:
                    people=[j for j in child['journeys'][side] if child['roster_owner'].get(j['person_id'])==participant['id']]
                    from ...npc_custody import is_free
                    living=[j for j in people if (n:=deps.find_person(game,j['person_id'])) and is_free(n) and not deps.imprisoned(game,n.id)]
                    phase='lost' if not living else 'returning' if any(j['phase']=='returning' for j in living) else 'marching' if any(j['phase']=='outbound' for j in living) else 'home' if all(j['phase'] in {'home','lost'} for j in living) else 'engaged'
                    coalitions[side].append(dict(id=participant['id'],name=names.get(participant['id'],'原组织'),phase=phase,
                                                count=len(living),remaining=max((j['remaining'] for j in living if j['phase'] in {'outbound','returning'}),default=0),
                                                willingness=next((c['willingness'] for c in commitments if c['id']==participant['id']),70)))
            dispatch_choices=[]
            commander=player_commander(deps,game,row) if not blocked else None
            if commander and row['status']=='active' and child['status']=='active':
                from .dispatch import plan
                for c in row['commitments']:
                    org=next((o for o in pool if ref(o)==c['org']),None)
                    if c['side']!=commander or not org:
                        continue
                    try:
                        _,_,route,cost=plan(deps,game,row,child,org)
                    except ValueError:
                        continue
                    dispatch_choices.append(dict(**ref(org),name=org.name,cost=cost,years=route.years))
            from .willingness import personal_side
            from ..war.supply import turns
            own_side=next((s for s in SIDES if own and own.id in {r['id'] for r in child['coalitions'][s]}),None)
            children.append(dict(id=child['id'], attacker=names.get(child['attacker_id'], '原组织'),
                defender=names.get(child['defender_id'], '原组织'), phase=child['campaign_phase'],
                location=place.get('name', '原战场'), remaining=remaining, battles=child.get('battles', 0),
                next_in=max(0, child.get('next_battle_age', 0)-game.player.age),
                can_withdraw=bool(own and not blocked and child['status'] == 'active'),
                can_participate=bool(not blocked and personal_side(deps,game,row,child)),
                participation_reason='本人须到达实际战场；亲征每十年一次，沿用普通详细会战与敌方反击。',
                org=ref(own) if own else None,
                coalitions=coalitions,dispatch_choices=dispatch_choices,
                field={s:dict(morale=round(child['morale'][s]),exhaustion=round(child['exhaustion'][s]),
                    supplies=round(turns(game,child,s),1) if own_side in {None,s} else None) for s in SIDES},
                reports=[dict(log) for log in child.get('logs',[])[-6:]],
                # Receipts only. Enemy treasuries and personnel are never projected here.
                paid=sum(r.get('mobilized', 0) for r in child.get('logistics', {}).get('sides', {}).values())))
        from .peace import package, TERMS, DESCRIPTIONS, player_reply
        side=next((s for s in SIDES if game.player.allegiance_race==row[s]),None)
        peace_options=[]
        if side and not blocked and deps.has_race_voice(game) and row['status'] in {'active','mobilizing'}:
            for term,label in TERMS.items():
                try:
                    bundle=package(deps,game,row,side,term)
                except ValueError:
                    continue
                peace_options.append(dict(term=term,label=label,description=DESCRIPTIONS[term],
                                          total=sum(d['amount'] for d in bundle['demands']),**bundle))
        proposal=row.get('peace_proposal')
        pending=bool(proposal and proposal['status']=='pending' and game.player.age<proposal['expires'])
        result.append(dict(id=row['id'], revision=row['revision'], status=row['status'], score=row['score'],
            attacker=RACE_DEFINITIONS.get(row['attacker'], {}).get('name', row['attacker']),
            defender=RACE_DEFINITIONS.get(row['defender'], {}).get('name', row['defender']),
            elapsed=max(0,row.get('end_age',game.player.age)-row['start_age']),
            truce_remaining=max(0,relations_for(game,row['world']).get(race_pair(row['attacker'],row['defender']),{}).get('truce_until_age',0)-game.player.age),
            commanders={s: row['commanders'].get(s, {}).get('name', '待推举') for s in SIDES},
            player_commander=player_commander(deps,game,row) if not blocked else None,
            nomination_choices=[s for s in SIDES if not blocked and row['status'] in {'active','mobilizing'}
                                and player_eligible(deps,game,row,s) and game.player.age-row.get('nomination_age',-1000)>=10],
            commitments=commitments, campaigns=children, objectives=[{k:o[k] for k in ('id','name','status','result')} for o in row['objectives']],
            can_peace=bool(not blocked and row['status'] in {'active','mobilizing'} and deps.has_race_voice(game)
                           and game.player.allegiance_race in {row['attacker'],row['defender']}
                            and not pending and game.player.age-row.get('peace_proposal_age',-1000)>=10),
            peace_options=peace_options, peace_proposal={**proposal,'remaining':max(0,proposal['expires']-game.player.age)} if proposal else None,
            treaty=dict(row['treaty']) if row.get('treaty') else None,
            can_reply=bool(not blocked and row['status'] in {'active','mobilizing'} and pending and player_reply(deps,game,row,proposal)),
            peace_reason='本案十年内已提和谈' if game.player.age-row.get('peace_proposal_age',-1000)<10 else '需本界参战种族议席，且本案尚未停战',
            commit_choices=[{**ref(o), 'name':o.name, 'budget':int(cash(game,o)*.2)} for o in pool if not blocked and row['status'] in {'mobilizing','active'}
                            and o.allegiance_race in {row['attacker'],row['defender']} and owns(deps,game,o)
                             and not busy(game,o) and sum(c['side']==('attacker' if o.allegiance_race==row['attacker'] else 'defender') for c in row['commitments'])<6
                            and not any(c['org']==ref(o) for c in row['commitments'])],
            logs=[dict(l) for l in row['logs'][-12:]]))
    legacy=[]
    for key,value in game.race_relations.items():
        if ':' in key or value.get('adopted_world'):
            continue
        parts=set(key.split('|'))
        active_old=any(w.get('kind')=='race' and w.get('status') in {'active','peace_ready'}
                       and {w.get('attacker_id'),w.get('defender_id')}==parts for w in game.wars)
        eligible=(not blocked and deps.has_race_voice(game) and game.player.allegiance_race in parts
                  and parts <= {r for r,d in RACE_DEFINITIONS.items() if game.player.world in d.get('worlds',[])})
        legacy.append(dict(key=key,name=' / '.join(RACE_DEFINITIONS.get(r,{}).get('name',r) for r in sorted(parts)),
            status=value.get('status','neutral'),can_adopt=bool(eligible and not active_old
                and key not in relations_for(game)
                and game.player.age-value.get('adoption_vote',{}).get('age',-1000)>=10)))
    legacy_wars=[]
    for w in game.wars:
        if w.get('kind')!='race' or w.get('world')!=game.player.world or w.get('status') not in {'active','peace_ready'}:
            continue
        demands=(w.get('peace_offer') or deps.peace_preview(game,w,w['winner']))['demands'] if w.get('status')=='peace_ready' else []
        legacy_wars.append(dict(id=w['id'],status=w['status'],battles=w.get('battles',0),
            name=f"{RACE_DEFINITIONS.get(w['attacker_id'],{}).get('name',w['attacker_id'])} / {RACE_DEFINITIONS.get(w['defender_id'],{}).get('name',w['defender_id'])}",
            terms=[d['label'] for d in demands] or ['未定胜负，原案白和'],
            vote=game.strategic_war_state.get('legacy_votes',{}).get(w['id']),
            allowed=bool(not blocked and deps.has_race_voice(game) and game.player.allegiance_race in {w['attacker_id'],w['defender_id']}
                         and game.player.age-game.strategic_war_state.get('legacy_votes',{}).get(w['id'],{}).get('age',-1000)>=10)))
    return dict(available=game.player.world in WORLDS, wars=result, legacy_relations=legacy,
                legacy_wars=legacy_wars,
                command_seq=game.strategic_war_state.get('command_seq',0)+1,
                world=WORLD_SYSTEMS['world_names'].get(game.player.world, game.player.world))
