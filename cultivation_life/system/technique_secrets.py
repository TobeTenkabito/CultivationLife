"""Atomic, one-time activation using original personal resources and slots."""
import copy
import hashlib
import json
import math

from ..content_registry import REALMS, WORLD_SYSTEMS
from ..cultivation_experience import (ART_NAMES, body_progress_required, grant_body_progress,
    grant_qi_mastery, art_experience_gain, grant_art_experience)
from ..models import HistoryRecord
from ..rules import divine_sense_level, divine_sense_level_threshold, has_item, qi_level, remove_item
from ..runtime import now_iso
from ..secret_art_content import AFFINITIES
from ..technique_secret_content import SLOTS
from ..technique_requirements import QI_NAMES
from .technique_secret_rules import catalog
from .formation_system import available_formation_candidates, _extract_candidate
from .technique_secret_rules import equipped

GROWTH = {'body_progress','qi_experience','art_experience'}
ONCE = {'heart_relief','sense_experience','clone_pair',*GROWTH}


def growth_quote(player, art):
    """Exact gains and their inputs are part of the stale-page quotation."""
    effect=art['effect'];target=art.get('target');value=art['value']
    if effect=='body_progress':
        from ..soul_rules import require_body_training
        reason=''
        try:require_body_training(player)
        except ValueError as exc:reason=str(exc)
        if player.body_technique is None:reason=reason or '须先配置炼体功法，才能承接炼体积累'
        if player.body_training>=WORLD_SYSTEMS['body_cultivation']['max_layer']:reason=reason or '炼体已达上限，无需投入材料'
        required=body_progress_required(player)
        gain=max(0.,min(required*value,required-player.body_progress))
        if gain<=0:reason=reason or '本层炼体积累已满，请先在炼体页突破'
        return dict(reason=reason,gain=gain,before=player.body_progress,level=player.body_training,
                    text=f'炼体积累 +{gain:g}（{player.body_progress:g} → {player.body_progress+gain:g} / {required:g}）；积满后手动突破')
    if effect=='qi_experience':
        before=player.qi_experience.get(target,0.)
        return dict(reason='',gain=value,before=before,
                    text=f'{QI_NAMES[target]}经验 +{value:g}；等级 {qi_level(before)} → {qi_level(before+value)}。气等级门槛同步更新，有气等级上限的功法可能失效')
    if effect=='art_experience':
        before=player.art_experience.get(target,0.);gain=art_experience_gain(player,target,value)
        base=float(WORLD_SYSTEMS['spirit_field']['art_experience_base'])
        return dict(reason='',gain=gain,before=before,
                    text=f'{ART_NAMES[target]}经验 +{gain:g}（基础 {value:g}）；等级 {int(math.sqrt(max(0,before)/base))} → {int(math.sqrt(max(0,before+gain)/base))}')
    return None


def quote(game, art):
    from .secret_art_resources import blocked_reason, materials
    p=game.player; book=equipped(p,art)
    record=p.secret_art_state.get('manuals',{}).get(art['id'],{})
    reason=blocked_reason(game).replace('补灵秘法','功法秘术')
    if not book:reason=reason or '须学会原功法并配置在指定栏位，且满足功法使用条件'
    if art['effect']=='sense_rank':
        if p.realm_index in record.get('realms',[]):reason=reason or '本大境界已经施展知天，跌境或跨界不会重置次数'
    elif record.get('activated'):reason=reason or ('此秘术的一次性成果已经获得' if art['effect'] in ONCE else '此秘术已经激活，无需再次投入')
    if art['effect'] in ONCE-{'clone_pair'} and p.realm_index!=art['realm']:reason=reason or '一次性秘术须在其对应大境界施展'
    if art['effect'] not in {'sense_rank','clone_pair','frost_tribulation'} and not record.get('activated') and p.realm_index!=art['realm']:
        reason=reason or '已不在此秘术的适用大境界，无需投入材料'
    if art['effect']=='clone_pair':
        from .clone_support import dance_claim_reason
        reason=reason or dance_claim_reason(p)
    requirements=[]
    if art['effect']=='frost_tribulation' and book:
        requirements.append('当前为仙阶：劫战六属性各增加4%，已替换雷劫减伤' if book.level>=7 else '当前为凡阶：雷劫减伤增加7个百分点；Lv.7转仙后替换效果')
    for key,label,current in [('level','原功法等级',book.level if book else 0),('body','普通炼体层数',p.body_training),('sense','神识等级',divine_sense_level(p))]:
        if key not in art['requirements']:continue
        needed=art['requirements'][key];requirements.append(f'{label} {current}/{needed}')
        if current<needed:reason=reason or f'{label}不足'
    if q:=art['requirements'].get('qi'):
        current=qi_level(p.qi_experience.get(q['source'],0.));requirements.append(f'{QI_NAMES[q["source"]]}等级 {current}/{q["level"]}')
        if current<q['level']:reason=reason or '对应气经验等级不足'
    cost=art['cost']; realm=p.realm_index if art['effect']=='sense_rank' else art['realm']
    opportunity=math.ceil(REALMS[realm].opportunity_base*cost.get('opportunity_bp',0)/10000)
    stones=cost.get('stones',0);bill=[];used=set();used_items={};materials_text=[]
    if opportunity:
        materials_text.append(f'机缘 {opportunity}')
        if p.opportunity<opportunity:reason=reason or '机缘不足'
    if stones:
        materials_text.append(f'灵石 {stones}')
        if not has_item(p,'spirit_stone',stones):reason=reason or '灵石不足'
    candidates=available_formation_candidates(p) if cost.get('formations') else []
    for requirement in cost.get('formations',[]):
        label=f'{AFFINITIES[requirement["nature"]]}属至少{requirement["tier"]}阶闲置阵材一件'
        source=next((r for r in sorted(candidates,key=lambda r:(r['acquired_tier'],r['formation_value'],r['id']))
            if r['nature']==requirement['nature'] and r['acquired_tier']>=requirement['tier']
            and (r['source_kind'],r['id']) not in used),None)
        if source:
            used.add((source['source_kind'],source['id']));bill.append(dict(kind='formation',candidate=source))
            materials_text.append(label+'：'+source['name'])
        else:
            materials_text.append(label+'：缺少');reason=reason or '闲置阵法材料不足；已布阵材料不能投入'
    for requirement in cost.get('essences',[]):
        rows=materials(p,dict(affinity=requirement['nature'],material_realm=requirement['tier']))
        source=next((r for r in rows if r['kind']==requirement['kind'] and r['quantity']>used_items.get(r['id'],0)),None)
        label=f'{AFFINITIES[requirement["nature"]]}属至少{requirement["tier"]}级'+('内丹' if requirement['kind']=='core' else '元神')+'一份'
        if source:
            used_items[source['id']]=used_items.get(source['id'],0)+1
            bill.append(dict(kind='item',id=source['id'][5:],name=source['name']))
            materials_text.append(label+'：'+source['name'])
        else:
            materials_text.append(label+'：缺少');reason=reason or '对应属性与品阶的内丹或元神不足'
    if art['effect']=='heart_relief' and p.heart_demon<art['value']:reason=reason or '现有心魔不足本次消解量，无需投入材料'
    growth=growth_quote(p,art)
    if growth:reason=reason or growth['reason']
    canonical=dict(art=art['id'],book=book.id if book else None,level=book.level if book else None,
        realm=p.realm_index,world=p.world,location=p.location_id,space=game.spatial_state.get('current'),
        revision=p.secret_art_state.get('revision',0),record=record,bill=bill,
        opportunity=opportunity,stones=stones,growth=growth,
        sense=divine_sense_level(p) if art['effect'] in {'sense_experience','sense_rank'} else None)
    token=hashlib.sha256(json.dumps(canonical,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    return dict(reason=reason,token=token,bill=bill,opportunity=opportunity,stones=stones,
                costs=materials_text,requirements=requirements,record=record,growth=growth)


def project(game):
    rows=[];p=game.player
    for art in catalog().values():
        book=equipped(p,art)
        if not book:continue
        q=quote(game,art);record=q['record'];effect=art['effect'];active=bool(record.get('activated'))
        if effect=='sense_rank':
            status='本境已施展' if p.realm_index in record.get('realms',[]) else '本境可施展' if active else '待领悟'
        elif effect in ONCE:status='成果已获得' if active else '待施展'
        else:
            from .possession_system import is_possessed
            working=p.alive and (p.realm_index==art['realm'] or effect=='frost_tribulation') and not (p.cultivation_suppression or p.sealed_cultivation or is_possessed(p))
            status=('生效中' if working else '已激活·暂不生效') if active else '待激活'
        rows.append(dict(id=art['id'],name=art['name'],description=art['description'],linked=True,builtin=False,
            acquired=True,category='功法秘术',seal='诀',status=status,technique_id=book.id,technique_name=book.name,
            slot=SLOTS[art['slot']],realm=art['realm'],hint=f'《{book.name}》 · {SLOTS[art["slot"]]}',
            activated=active,used_realms=list(record.get('realms',[])),costs=q['costs'],requirements=q['requirements'],
            reason=q['reason'],quote=q['token'],once=effect in ONCE,
            gain_preview=q['growth']['text'] if q['growth'] and not active else '',
            command_label='本境施展' if effect=='sense_rank' and active else '领悟并施展' if effect=='sense_rank' else '施展秘术' if effect in ONCE else '激活秘术'))
    return rows


def execute(deps, game_id, identity, *, revision, token):
    if not isinstance(identity,str) or not isinstance(token,str):raise ValueError('功法秘术请求无效')
    original=deps.load(game_id)
    if type(revision) is not int or revision!=original.player.secret_art_state.get('revision',0):raise ValueError('秘术页面已过期，请刷新')
    art=catalog().get(identity)
    if art is None:raise ValueError('未知功法秘术；自创功法不能声明此类秘术')
    q=quote(original,art)
    if q['reason']:raise ValueError(q['reason'])
    if not token or token!=q['token']:raise ValueError('功法栏位、材料或人物状态已变化，请刷新后确认实际投入')
    game=copy.deepcopy(original);p=game.player
    if q['opportunity']:p.opportunity-=q['opportunity']
    if q['stones'] and not remove_item(p,'spirit_stone',q['stones']):raise ValueError('灵石已不足')
    for entry in q['bill']:
        if entry['kind']=='formation':_extract_candidate(p,entry['candidate'])
        elif not remove_item(p,entry['id']):raise ValueError('材料已经不足')
    if not p.secret_art_state:p.secret_art_state=dict(schema_version=1,revision=0,arts={})
    records=p.secret_art_state.setdefault('manuals',{})
    record=records.setdefault(identity,dict(activated=True,realms=[]))
    effect=art['effect'];result='激活记录已保存，原功法位于对应栏位且适用时自动生效。'
    if effect=='sense_rank':
        before=divine_sense_level(p);p.divine_sense_rank=before+1
        record['realms']=sorted([*record['realms'],p.realm_index]);result=f'神识由{before}级提升至{before+1}级，本大境界次数已使用。'
    elif effect=='sense_experience':
        rank=divine_sense_level(p);amount=(divine_sense_level_threshold(rank+1)-divine_sense_level_threshold(rank))*art['value']
        p.divine_sense_experience+=amount;result=f'永久获得{amount:g}神识经验，沿原神识升级入口使用。'
    elif effect=='heart_relief':
        p.heart_demon-=art['value'];result=f'已永久消解{art["value"]:g}点心魔。'
    elif effect=='clone_pair':
        from .clone_support import grant_dance_pair
        grant_dance_pair(p)
        result='已凝成岚影、魔影两具元婴初层分身，修为上限八阶圆满；初始能源为0，请沿原御傀能源入口配置。此生只领取一次，卸装不撤销、损毁不补发。'
    elif effect in GROWTH:
        if effect=='body_progress':grant_body_progress(p,q['growth']['gain'])
        elif effect=='qi_experience':grant_qi_mastery(p,art['target'],art['value'])
        else:grant_art_experience(p,art['target'],art['value'])
        result=q['growth']['text']+'。成果只领取一次，卸下原功法不撤销。'
    p.secret_art_state['revision']+=1
    game.history.append(HistoryRecord('SYS_TECHNIQUE_SECRET',1,p.age,art['name'],identity,'success',result,
        dict(technique_id=art['technique_id'],slot=art['slot'],realm=p.realm_index,
             opportunity=q['opportunity'],stones=q['stones'],materials=q['costs'],
             growth=q['growth'] or {}),['system','secret_art','technique']))
    deps.compact_history(game);game.updated_at=now_iso();deps.save(game);deps.commit(game)
    return deps.present(game)
