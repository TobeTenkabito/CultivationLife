"""Only visibly present people can be attacked; use the ordinary lethal battle."""
import copy
from .people import available, opposition, fight
from .companions import separate
from ...soul_rules import wandering


def visible_now(site):
    keys=set(site['party'])
    pending=site['pending']
    if pending:
        keys.add(pending['actor'])
        if pending.get('other'):keys.add(pending['other'])
    elif site['step']<len(site['nodes']):keys.add(site['nodes'][site['step']]['actor'])
    return keys


def reveal(game,site,log,label):
    if site['status']!='active':return
    keys=visible_now(site)
    for key in sorted(keys):keys.update(r['id'] for r in opposition(game,site,site['roles'][key])[1:])
    for key in sorted(keys):
        role=site['roles'][key]
        if role['state'] in {'dead','left','missing'} or not available(game,site,role):continue
        role['ledger']['encounter_step']=site['step']
        if role['state']=='unseen':role['state']='observed'
        if not role['known']:
            role['known']=True
            log(site,'你看见'+label(role)+'也在此处探查。',actors=[key])


def can_slay(game,site,role):
    return bool(site['status']=='active' and role['known']
        and role['state'] not in {'dead','left','missing'}
        and (role['id'] in visible_now(site) or role['ledger'].get('encounter_step')==site['step'])
        and available(game,site,role))


def slay(deps,game,site,key,log,close,offer_invited):
    role=site['roles'].get(key)
    if not role or not can_slay(game,site,role):raise ValueError('请选取眼前在场的修士')
    pending=copy.deepcopy(site['pending'])
    enemies=opposition(game,site,role)
    enemy_keys={r['id'] for r in enemies}
    for enemy in enemies:
        if enemy['id'] in site['party']:site['party'].remove(enemy['id'])
        separate(game,enemy)
        contract=site.get('expedition',{}).get('contracts',{}).get(enemy['id'])
        if contract and contract['state']=='promised':contract['state']='broken'
    allies=[site['roles'][k] for k in site['party'] if k not in enemy_keys and available(game,site,site['roles'][k])]
    log(site,'你向'+role['name']+'祭出杀招。',actors=[key])
    outcome,text=fight(deps,game,site,role,allies,attack=True)
    log(site,text,actors=[r['id'] for r in enemies])
    if (outcome not in {'victory','killed','victory_escape','victory_controlled'} or not game.player.alive
            or wandering(game.player) or game.player.nascent_state.get('crisis') or game.player.imprisonment or game.player.ghost_captor):
        close(game,site,'争斗过后，此次探境结束。');return
    site['pending']=pending
    if pending and enemy_keys.intersection({pending['actor'],pending.get('other')}):
        site['pending']=None
        if pending['kind']=='join':offer_invited(game,site)
    # Killing is not a reward receipt: the current scene still requires a choice.
