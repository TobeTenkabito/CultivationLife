"""One-way campaign receipts and physical withdrawal, shared by treaty execution."""
from ...race_diplomacy import relations_for
from ...world_state import race_pair
from .rules import SIDES
from .records import note


def withdraw(game, child):
    if child.get('campaign_phase') == 'returning':
        return
    for side in SIDES:
        carriers=[(child[f'{side}_id'],child['cargo_journeys'][side])]+[
            (r['org']['id'],r['cargo']) for r in child.get('reinforcements',[]) if r['side']==side and r['delivered']]
        carrier=next((cargo for identity,cargo in carriers if identity not in child.get('withdrawn_orgs',[])
                      and cargo['phase'] in {'stationed','outbound'}),None)
        if carrier:
            child['logistics']['sides'][side]['return_location']=carrier['origin']
    child.update(status='withdrawing', campaign_phase='returning')
    for journeys in child.get('journeys', {}).values():
        for j in journeys:
            if j['phase'] in {'home', 'lost', 'returning'}:
                continue
            elapsed = j['years'] - j['remaining'] if j['phase'] == 'outbound' else j['years']
            j.update(destination=j['origin'], remaining=elapsed, phase='returning')
    for cargo in list(child.get('cargo_journeys',{}).values())+[r['cargo'] for r in child.get('reinforcements',[])]:
        if cargo['phase'] not in {'home','lost','returning'}:
            elapsed=cargo['years']-cargo['remaining'] if cargo['phase']=='outbound' else cargo['years']
            cargo.update(destination=cargo['origin'],remaining=elapsed,phase='returning')



def receipt(game, row, child):
    # Monotonic cumulative receipts: duplicate reads/callbacks cannot farm score.
    revision = int(child.get('battles', 0))
    previous = row['receipts'].get(child['id'], {})
    terminal = child.get('status') in {'peace_ready', 'ended', 'withdrawing'}
    if revision <= previous.get('revision', -1) and (not terminal or previous.get('terminal')):
        return
    row['receipts'][child['id']] = dict(revision=revision, terminal=terminal)
    objective = next(o for o in row['objectives'] if o['campaign_id'] == child['id'])
    if terminal and objective['status'] != 'completed':
        objective.update(status='completed', result={'attacker': 1, 'defender': -1}.get(child.get('winner'), 0))
        note(game, row, '战役结算', f"{objective['name']}结束，共 {revision} 次交锋；伤亡与军需已由原战役结算。")
        withdraw(game, child)
    row['score'] = round(sum(o['result'] for o in row['objectives']) * 100 / max(1, len(row['objectives'])))



def armistice(game, row, reason):
    if row['status'] in {'armistice', 'settling', 'ended'}:
        return
    row['status'] = 'armistice'
    if row.get('peace_proposal', {}).get('status') == 'pending':
        row['peace_proposal']['status'] = 'expired'
    row['outcome'] = 'attacker' if row['score'] > 0 else 'defender' if row['score'] < 0 else 'draw'
    for child in game.wars:
        if child.get('strategic_war_id') == row['id'] and child.get('status') != 'ended':
            withdraw(game, child)
    for objective in row['objectives']:
        if objective['status']=='active':
            objective['status']='cancelled'
    relation = relations_for(game, row['world']).setdefault(race_pair(row['attacker'], row['defender']), {})
    relation.update(status='truce', affinity=-10, since_age=game.player.age,
                    truce_until_age=game.player.age + row.get('treaty',{}).get('truce_years',1000))
    from .rules import committed_org
    for first in row['commitments']:
        if first['side']!='attacker' or not committed_org(game,row,first):continue
        for second in row['commitments']:
            if second['side']!='defender' or not committed_org(game,row,second):continue
            pact=game.sect_relations.setdefault(race_pair(first['org']['id'],second['org']['id']),{})
            pact['truce_until_age']=max(pact.get('truce_until_age',0),relation['truce_until_age'])
    note(game, row, '总停战', reason)

