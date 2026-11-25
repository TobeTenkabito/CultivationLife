"""Encounter-only materialization. Roles reference one authoritative person."""
from ...definition_data import definition as _content_definition
from ...models import SectNpc
from ...relationship_records import find_person
from ...rules import expected_combat_power, combat_power, max_hp
from ...cultivation_coordinates import rank_for
from ...reputation import true_rank
from .ecology import close_realms, appearance_depth




def team_reason(game,role):
    npc=find_person(game,role['npc_id']) if role['npc_id'] else None
    realm=npc.realm_index if npc else role['realm']
    return '' if close_realms(game.player.realm_index,realm) else '同行修士的修为须与你相差至多一个大境界'


def available(game, site, role):
    if not role['npc_id']:
        return True
    from ...npc_custody import is_free
    from ...person_assignments import deployment_assignment, research_assignment
    npc = find_person(game, role['npc_id'])
    return bool(npc and npc.alive and is_free(npc)
                and (npc.world, npc.location_id) == (site['world'], site['location_id'])
                and not deployment_assignment(game, npc.id) and not research_assignment(game, npc.id))


def materialize(game, site, role):
    if role['npc_id']:
        if not available(game, site, role):
            raise ValueError('同行修士已离开当地，请重新查看名册')
        npc = find_person(game, role['npc_id'])
        if npc is None:
            raise ValueError('请重新查看当地同行名册')
        return npc
    identity = role['id']
    if find_person(game, identity):
        raise ValueError('副本人物身份冲突')
    field_rank=role['ledger'].get('domain_rank',0)
    from ...content_registry import REALMS
    life=REALMS[role['true_realm']].lifespan
    lifespan=round(sum(life)/2) if life else None
    sect=game.sects.get(role['sect_id'])
    race=(sect.allegiance_race if sect else None) or ('ghost' if role['path']=='ghost' else 'monster' if role['path']=='monster' else 'human')
    npc = SectNpc(id=identity, name=role['name'], title='道祖' if role['true_realm']==12 and role['layer']>=7 and field_rank==13 else '探境修士',
        realm_index=role['realm'], layer=role['layer'], age=min(80,max(18,int(lifespan*.3))) if lifespan else 8000, lifespan=lifespan,
        world=site['world'], location_id=site['location_id'], path=role['path'],race=race,
        faction_id=role['sect_id'], combat_factor=role['power_factor'], affinity=role['trust'],
        encountered_player=True,
        family_traits={'dungeon_origin': {'instance': site['id'], 'true_realm': role['true_realm'], 'domain_rank':field_rank}},
        birth_seed=game.seed)
    if role['true_realm'] >= 9:
        domain = identity + ':domain'
        npc.transcendence = dict(version=1, conversion=1., capacity=1200., current=1200.,
            force_tier=2, ward_tier=1, attack_cost=10., ward_cost=0.,
            attainments={'dungeon_domain': field_rank},
            voisinage_ids=[domain] if field_rank else [], doctrine={'manuals': [], 'manual_level': 0,
                'progress': {}, 'active': None, 'at': game.player.age, 'world': site['world']})
    game.world_npcs[identity] = npc
    role.update(npc_id=identity, materialized=True)
    return npc


def gratitude(game,role,amount):
    role['trust']=min(100,role['trust']+amount)
    npc=find_person(game,role['npc_id']) if role['npc_id'] else None
    if npc:npc.affinity=min(100,(npc.affinity or 0)+amount)


def power(game, role):
    npc = find_person(game, role['npc_id']) if role['npc_id'] else None
    realm, layer = (npc.realm_index, npc.layer) if npc else (role['realm'], role['layer'])
    return expected_combat_power(realm, layer) * (npc.combat_factor if npc else role['power_factor']) * (max(.35,1-npc.wounds*.15) if npc else 1)


def candidates(game):
    from ...person_assignments import require_unassigned
    from ...npc_custody import is_free
    # Only people already encountered and actually here can receive a local offer.
    people={**game.relationship_npcs, **game.notable_npcs, **game.world_npcs}
    for sect in game.sects.values():
        people.update({n.id:n for n in sect.npcs})
    if game.family:people.update({n.id:n for n in game.family.npcs})
    result=[]
    for npc in people.values():
        if not npc.encountered_player or not is_free(npc) or not npc.alive or (npc.world,npc.location_id)!=(game.player.world,game.player.location_id):continue
        if not close_realms(game.player.realm_index,npc.realm_index):continue
        try:require_unassigned(game,npc.id)
        except ValueError:continue
        result.append(npc)
    return result


def invite(game,site,identity):
    from .generation import stream
    from ...content_registry import FACTION_DEFINITIONS
    import copy
    npc=next((n for n in candidates(game) if n.id==identity),None)
    if not npc:raise ValueError('此修士须已结识、实际在场、未承担其他职责，且与你相差至多一个大境界')
    if identity in site['roles'] or any(r['npc_id']==identity for r in site['roles'].values()):raise ValueError('已经邀请过此人')
    if len(site['roles'])>=32:raise ValueError('此副本的可接触人数已达上限')
    rng=stream(site['seed'],'invite',identity)
    role=copy.deepcopy(next(iter(site['roles'].values())))
    purpose=rng.choice(('seek','heal','escort','observe','assassinate'))
    if purpose=='assassinate' and rank_for(npc.realm_index,npc.layer)<rank_for(*true_rank(game.player)):purpose='observe'
    role.update(id=identity,npc_id=identity,name=npc.name,sect_id=npc.faction_id,
        sect_name=game.sects[npc.faction_id].name if npc.faction_id in game.sects else FACTION_DEFINITIONS.get(npc.faction_id,{}).get('name','散修'),realm=npc.realm_index,layer=npc.layer,
        true_realm=npc.realm_index,path=npc.path,purpose=purpose,resolve=95 if purpose=='assassinate' else 50,
        trust=max(0,min(100,npc.affinity or 0)),preparation=rng.randint(20,40),desire=rng.randint(35,95),
        existing=True,state='invited',known=True,clues=[],target='player' if purpose=='assassinate' else 'treasure',
        story='应邀前来，愿在入口会合',power_factor=npc.combat_factor,joined_step=None,left_step=None,
        revealed=False,materialized=True,ledger={},offer_step=1)
    site['roles'][identity]=role
    from ...reputation import assess
    public_renown=assess(game.player,visible=True)['value']
    fit=min(1,expected_combat_power(game.player.realm_index,game.player.layer)/max(1,power(game,role)))
    deterrence=min(.3,max(0,game.player.infamy)/1000) if purpose!='assassinate' else 0
    accepts=purpose=='assassinate' or rng.random()<max(.05,min(.95,.2+public_renown/1200+max(0,npc.affinity or 0)/200+.2*fit-deterrence))
    if site.get('expedition'):
        target=rng.choice(site['nodes'])['reward']['id']
        site['expedition']['goals'][identity]=dict(target=target,
            desires={n['reward']['id']:role['desire'] if n['reward']['id']==target else 25 for n in site['nodes']},
            fulfilled=False,work=0,seen_power=0.)
    if not accepts:role['state']='declined'
    reply = _content_definition(__name__, 'INVITATION_REPLY')
    game.dungeon_state['mail'].append(dict(id=site['id']+':reply:'+identity,dungeon_id=site['id'],sender=npc.name,
        sender_id=identity,title=reply['title'],body=reply['accepted' if accepts else 'declined'],
        unread=True,status='reply',age=game.player.age))
    return role


def pressures(game, site, role, opponent=None):
    """Private decision factors; the public projection exposes evidence separately."""
    p = game.player
    goal=site.get('expedition',{}).get('goals',{}).get(role['id'],{})
    observed=goal.get('seen_power') or expected_combat_power(p.realm_index,p.layer)
    target_power=power(game,opponent) if opponent else observed*max(.15,p.hp/max(1,max_hp(p)))
    ratio = power(game, role) / max(1.,target_power)
    target_rank=rank_for(opponent['realm'],opponent['layer']) if opponent else rank_for(p.realm_index,p.layer)
    gap = rank_for(role['realm'], role['layer']) - target_rank
    agreement = 0 if opponent else site['agreements'].get(role['id'], 0)
    murder = role['purpose'] == 'assassinate' and opponent is None
    from .expedition import current_desire
    contract=site.get('expedition',{}).get('contracts',{}).get(role['id'],{})
    breach=0 if opponent else 20 if contract.get('state')=='broken' else -8 if contract.get('state')=='fulfilled' else 0
    intent = max(85, role['resolve']) if murder else current_desire(site,role)*.45 + role['resolve']*.35 - role['trust']*.3 - agreement*12+breach
    confidence = min(30, (ratio-1)*22) + min(12, gap*2)
    readiness = role['preparation']*.35 - role['caution']*.15
    return dict(ratio=ratio, gap=gap, intent=intent,
                risk=max(0, min(100, intent+confidence+readiness)))


def domains(site):
    result = []
    for role in site['roles'].values():
        if not role['materialized'] or role['existing'] or not role['ledger'].get('domain_rank'):
            continue
        from .domains import domain
        result.append(domain(role['id'], role['ledger']['domain_rank'], role['true_realm']))
    return result


OBSERVED_TERRAIN = _content_definition(__name__, "OBSERVED_TERRAIN")


def opposition(game,site,enemy):
    from .trails import present
    pending=site['pending'] or {}
    pursuers=pending.get('pursuers',[]) if pending.get('actor')==enemy['id'] else []
    followers=[site['roles'][key] for key in dict.fromkeys([*enemy['ledger'].get('supporters',[]),*pursuers])
        if key in site['roles'] and key not in site['party'] and site['roles'][key]['state'] not in {'dead','left','declined','missing'}
        and present(site,key) and (key in pursuers or appearance_depth(site,site['roles'][key])<=site['depth'])
        and available(game,site,site['roles'][key])]
    return [enemy]+followers


def fight(deps, game, site, enemy, allies=(), *, attack=False):
    npc = materialize(game, site, enemy)
    actual_power=deps.npc_power(npc)
    own_ids = [materialize(game, site, r).id for r in allies if r['id'] != enemy['id']]
    participants=opposition(game,site,enemy)
    members=[]
    for role in participants:
        member=materialize(game,site,role)
        if member.id in own_ids:continue
        role.update(known=True,state='hostile')
        members.append(dict(npc_id=member.id,id=member.id,name=member.name,kind='cultivator',
            realm_index=member.realm_index,layer=member.layer,power=deps.npc_power(member),path=member.path,
            faction_id=member.faction_id,world=member.world,race=member.race,treasure_item_id=member.treasure_item_id))
    target = dict(npc_id=npc.id, target_name=npc.name, faction_id=npc.faction_id,
        target_power=actual_power, target_realm_index=npc.realm_index, target_layer=npc.layer,
        combat_type='dungeon', objective='kill' if attack else 'repel', player_defending=not attack, non_story_combat=True,
        dungeon_allies=own_ids, local_dungeon=True,
        natural_terrain=site['terrain'], artificial_conditions=site['conditions'],
        members=members)
    if attack:
        if enemy['ledger'].get('outside_party'):target['relationship_kind']='party'
        target['exclude_allied_ids']=[r['npc_id'] for r in participants]
    if site['preparations']:
        target['enemy_debuffs']=[dict(id=OBSERVED_TERRAIN['id'], name=OBSERVED_TERRAIN['name'], stat=OBSERVED_TERRAIN['stat'],
            multiplier=max(OBSERVED_TERRAIN['floor'], 1 - OBSERVED_TERRAIN['reduction_per_preparation'] * site['preparations']))]
    from .generation import stream
    outcome, summary = deps.combat(game, target, True, stream(site['seed'], site['revision'], 'combat'))
    for role in participants:
        if role['state']=='hostile' and outcome in {'victory','killed','victory_escape','victory_controlled'}:
            role['state']='left'
    for r in site['roles'].values():
        person = find_person(game, r['npc_id']) if r['npc_id'] else None
        if person and not person.alive:
            r['state'] = 'dead'
            if r['id'] in site['party']:
                site['party'].remove(r['id'])
    return outcome, summary
