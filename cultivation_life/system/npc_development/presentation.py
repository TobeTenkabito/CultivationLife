"""Bounded, read-only projection for the independent development dialog."""
from ...content_registry import PATH_NAMES
from ...spatial_people import accessible
from ...npc_development_content import definitions
from .targets import candidates, require, unrevealed, location
from .service import quote
from ..combat.actor_state import read
from ..spatial_capabilities import site_key
from .growth import facts as normalize_facts, realm_name
import copy

def public(game,power=None):
    rows=[]
    for target in candidates(game):
        n=target.person if target.person is not None else target.owner
        address=location(game,target) if target.kind=='npc' else None
        local=(target.kind in {'puppet','prisoner'} or '身外化身' in target.relations or (accessible(game,n) and bool(address) and address==site_key(game)))
        row=dict(id=target.identity,kind=target.kind,relations=list(target.relations),name='暂不可接触的人物',
                 reason='当前无法确认或接触',portrait=None,quotes=[],techniques=[])
        if not local:
            rows.append(row);continue
        facts=normalize_facts(target.facts(game))
        row['name']=facts.get('name','培养对象')
        if '弟子' in target.relations:
            from ..mentorship import record, rank_of, LABELS
            rank = rank_of(game, 'player', target.identity)
            entry = record(game, 'player', target.identity)
            if rank: row['mentorship'] = dict(rank_name=LABELS[rank], loyalty=entry['loyalty'] if entry else 60)
            from ..mentorship_advanced import precision
            row['precision_remaining'] = precision(game, target.identity)
        try:require(game,target);row['reason']=''
        except ValueError as e:row['reason']=str(e)
        # Concealed or non-public forms cannot leak true realm through art or quotes.
        if unrevealed(game,target):
            row['reason']='当前神识尚未探明人物的真实修为';rows.append(row);continue
        row['realm_name']=realm_name(facts)
        row['path_name']=PATH_NAMES.get(facts.get('path'),'未知道途')
        from .portraits import portrait
        row['portrait']=portrait(target,facts)
        if row['portrait']:row['portrait']['realm_name']=row['realm_name']
        row['facts']={k:facts.get(k,0) for k in ('body_training','immortal_body_level','divine_sense_rank')}
        row['facts']['conversion']=float((facts.get('transcendence') or {}).get('conversion',0))
        if target.kind=='puppet':
            from ..puppet_energy import current, CAPACITY, attack_cost, charge_quote, source_definition, source_id, force_tier, replacements, operation
            from ..combat_plan import effective_plan
            use=operation(target.owner)
            row['energy']=dict(current=current(target.owner),capacity=CAPACITY,action_cost=use['cost'],operation=use,
                immortal_attack_cost=attack_cost(target.owner) if facts['realm_index']>=9 else 0,
                source_id=source_id(target.owner),name=(source_definition(source_id(target.owner)) or {}).get('name','未安装／未标定能源'),
                force_tier=force_tier(target.owner),supply=effective_plan(game.player)['puppet_supply'],
                replacements=replacements(game,target.owner))
            try:row['charge']=charge_quote(game,target.owner)
            except ValueError as e:row['charge']=dict(can_charge=False,reason=str(e))
            if row['reason']:row['charge'].update(can_charge=False,reason=row['reason'])
        if power and target.person and target.kind!='puppet':
            row['combat_power']=round(power(copy.deepcopy(target.person)),1)
        elif target.kind=='puppet':row['combat_power']=facts.get('combat_power',0)
        if not row['reason']:
            from .body import options as body_options
            from .domains import options as domain_options
            row['specializations']=body_options(facts) if target.kind!='puppet' else []
            row['domains']=domain_options(game,facts) if target.kind!='puppet' else []
            state=facts.get('transcendence') or {}
            record=state.get('doctrine',{}) if game.player.world=='celestial' else state.get('world_voisinages',{}).get(game.player.world,{})
            for d in row['domains']:
                key=d['axis'][7:]
                d.update(active=record.get('active')==key,rank=record.get('progress',{}).get(key,{}).get('level',0) if game.player.world=='celestial' else record.get('levels',{}).get(key,0))
            row['domains'].sort(key=lambda d:not d['active'])
            from .techniques import options as technique_options
            row['learned_techniques']=technique_options(game,facts) if target.kind!='puppet' else []
            axes=['cultivation','body','sense','conversion','domain']+[r['axis'] for r in row['specializations']+row['domains']+row['learned_techniques']]
            for axis in axes:
                for method in (('material','infuse','inherit_material','inherit_infuse') if row.get('precision_remaining') else ('material','infuse')):
                    for batches in (1,5,10):
                        try:
                            q=quote(game,target.kind,target.identity,axis,method,batches,_target=target)
                            row['quotes'].append({k:v for k,v in q.items() if k!='result'})
                        except ValueError as e:
                            row['quotes'].append(dict(axis=axis,method=method,batches=batches,can_train=False,reason=str(e)))
            from ..npc_techniques import levels
            known=levels(facts)
            row['techniques']=[dict(id=t.id,name=t.name,category=t.category) for t in game.player.known_techniques if t.id not in known]
        rows.append(row)
    return dict(revision=game.updated_at,targets=rows,materials=[dict(r,quantity=sum(i.quantity for i in game.player.inventory if i.id==r['id'])) for r in definitions().values()],
                note=('独立空间内可查看人物、当面传法；主动升阶、专材培养与能源更换暂不开放。' if game.player.world in {'lost','rift'} else
                      '高阶修为每轮一层，转化每轮一重；不代替迁界，不补满资源。邻域每轮一阶，受修为与界面限制。'))

def legacy_quotes(game,kind,identity):
    result={}
    for axis in ('cultivation','body','sense'):
        result[axis]=[]
        for count in (1,5,10):
            try:q={k:v for k,v in quote(game,kind,identity,axis,'infuse',count).items() if k!='result'}
            except ValueError as e:q=dict(axis=axis,batches=count,rounds=0,label='培养',before='当前',after='未变化',opportunity=0,mp=0,power_before=0,power_after=0,can_train=False,reason=str(e))
            result[axis].append(q)
    return result
