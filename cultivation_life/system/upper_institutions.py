"""Base upper-world governments. Fixed-size councils, one ledger per world.

Only elapsed action/travel time advances politics. Views never consume RNG,
refresh jobs, pay income or alter allegiance. Institutions do not own sect slots.
"""
import copy
from math import floor

from ..content_registry import WORLD_SYSTEMS
from ..rules import add_item
from ..runtime import now_iso, decode_rng, encode_rng

from .institution_state import (
    config as config,
    definition as definition,
    fresh as fresh,
    account as account,
    policy as policy,
    record as record,
)


def cultivation_discount(game):
    if not definition(game):
        return 0
    state = account(game)
    if not state['joined']:
        return 0
    extra = 0
    if game.player.world == 'asura' and state.get('court'):
        from .asura_court import benefits
        extra = benefits(game, state)['discount']
    return min(.6, policy(game, state)['cultivation_discount'] + extra)


def officials(game):
    cfg = definition(game)
    if game.player.world == 'asura':
        from .asura_court import public
        return public(game, account(game))['seats']
    entity = game.sects.get(cfg['id'])
    people = {n.id:n for n in entity.npcs} if entity else {}
    return [dict(id=f"{cfg['id']}_{i}", name=(people[f"{cfg['id']}_{i}"].name
                if f"{cfg['id']}_{i}" in people else name), title=cfg['titles'][i],
                present=bool(people.get(f"{cfg['id']}_{i}") and people[f"{cfg['id']}_{i}"].alive
                             and people[f"{cfg['id']}_{i}"].world == game.player.world))
            for i,name in enumerate(cfg['people'])]


def votes(game, target, *, player=False):
    state, cfg = account(game), definition(game)
    result=[]
    for i, person in enumerate(officials(game)):
        owns = state['joined'] and state['seat_active'] and i == state['bloc']
        yes = (player if owns else person['present'] and
               (cfg['preferences'][i] == target or player and state['support'][i] >= 70))
        result.append(dict(name='你' if owns else person['name'], yes=bool(yes),
                          weight=cfg['weights'][i], vacant=not owns and not person['present']))
    return result


def enact(game, state, target, author):
    if state['treasury'] < config()['policy_cost']:
        raise ValueError('机构府库不足以施行政务')
    state['treasury'] -= config()['policy_cost']
    state['policy'] = target
    state['agenda_at'] = state['unit'] + config()['agenda_interval']
    record(game, state, f"{author}施行【{policy(game, state)['name']}】。{policy(game,state)['description']}")


def advance_time(game, elapsed, unit_years):
    """O(completed units × 5); partial travel cannot mint a full stipend."""
    if not definition(game) or game.player.realm_index < 9 or elapsed <= 0:
        return
    state, cfg = account(game, create=True), definition(game)
    from . import asura_court
    if game.player.world == 'asura':
        asura_court.ensure(game)
    total = state['fraction'] + elapsed / unit_years
    count = floor(total + 1e-9)
    state['fraction'] = max(0.0, total - count)
    for _ in range(count):
        state['unit'] += 1
        if game.player.world == 'asura':
            asura_court.tick(game, state)
        else:
            state['treasury'] += config()['unit_income']
        obligation = state['obligation']
        if obligation and state['unit'] > obligation['deadline']:
            state['regard'] = max(0, state['regard'] - 15)
            state['obligation'] = None
            record(game,state,'王命失期，恩宠降低。' if game.player.world=='asura' else '誓愿失期，信望降低。')
        if state['unit'] >= state['agenda_at'] and not (game.player.world == 'asura' and asura_court.is_king(state)):
            target = cfg['policies'][(state['unit']//config()['agenda_interval']) % 3]['id']
            rulers = officials(game)
            ruler_present = (rulers[0]['present'] if game.player.world == 'asura' else any(o['present'] for o in rulers))
            if state['treasury'] >= config()['policy_cost'] and ruler_present:
                if game.player.world == 'nether':
                    tally=votes(game,target)
                    # Player's absent vote is an abstention, never an invented yes.
                    if sum(v['weight'] for v in tally if v['yes'])>sum(cfg['weights'])/2:
                        enact(game,state,target,'祖族议庭')
                    else:
                        record(game,state,f"门阀议案未过半（赞成议权 {sum(v['weight'] for v in tally if v['yes'])}/15），维持现政。")
                else:
                    enact(game,state,target,'修罗王' if game.player.world=='asura' else '轮回祭议')
            state['agenda_at'] = state['unit'] + config()['agenda_interval']
        if not state['joined'] or not game.player.alive:
            continue
        if game.player.world=='nether' and state['seat_active'] and state['support'][state['bloc']]<50:
            state['seat_active']=False
            record(game,state,'本族支持低于五十，门阀收回你的代言资格。')
        rank=state['rank'] if game.player.world!='nether' else int(state['seat_active'])
        amount=int((10000+rank*10000)*policy(game,state)['income'])
        paid=min(amount,state['treasury'])
        state['treasury']-=paid
        add_item(game.player,'spirit_stone',paid)
        if state['obligation'] is None and game.player.world=='asura' and not asura_court.is_king(state):
            state['obligation']=dict(name='王命：完成一次王庭委托',deadline=state['unit']+4)
        record(game,state,f"第 {state['unit']} 单位：领取{'神职供养' if game.player.world=='reincarnation' else '俸禄津贴'}，灵石 +{paid}。")


def require_action(game, *, local=True):
    cfg, p=definition(game),game.player
    if not cfg or p.realm_index<9:
        raise ValueError('须在修罗、幽冥或轮回界达到第九阶')
    if (not p.alive or game.pending_event or game.active_trial or p.imprisonment or p.ghost_captor
            or (game.guixu_state.get('player_session') or {}).get('trapped')):
        raise ValueError('当前无法办理机构事务')
    if local and p.location_id != cfg['location']:
        raise ValueError('须亲临本界机构驻地办理')


def begin_work(game):
    require_action(game)
    state=account(game)
    job=state['job']
    if not state['joined'] or not job or job['progress']>=job['years']:
        raise ValueError('须先接取尚未完成的机构委托')


def finish_work(game, action, elapsed):
    if action!='institution_work' or not definition(game):
        return
    job=account(game)['job']
    if job:
        job['progress']=min(job['years'],job['progress']+max(0,elapsed))


def spend(state, amount):
    if state['merit']<amount:
        raise ValueError('机构功勋不足')
    state['merit']-=amount


def act(engine, game_id, action, target=''):
    game=engine._load(game_id)
    require_action(game)
    cfg, state, p=definition(game), account(game,create=True),game.player
    from . import asura_court
    if p.world == 'asura':
        asura_court.ensure(game)
        asura_court.reconcile(game, state)
    if action=='work':
        begin_work(game)
        return engine.advance(game_id,'institution_work',1)
    if action=='join':
        if state['joined']:
            raise ValueError('已登记，无需重复加入')
        state['joined']=True
        if p.world == 'asura':
            # Legacy versions retained a numeric rank after resignation.
            # Rejoining cannot create a title without its corresponding seat.
            state['rank'] = 0
            state['court']['protected_until'] = state['unit'] + 8
        p.institution_affiliations[cfg['id']]={'joined_age':p.age}
        text=f"加入{cfg['name']}，原有宗门身份保留。"
    else:
        if not state['joined']:
            raise ValueError('请先登记机构身份')
        if p.world == 'asura' and action in ('blood_duel', 'answer_duel', 'yield_duel', 'appoint', 'build', 'decree', 'faction_decree', 'royal_tribute'):
            text = asura_court.act(engine, game, state, action, target)
        elif action=='leave':
            if state['job']:
                raise ValueError('请先交付或放弃委托')
            if p.world == 'asura':
                if state['court']['challenge']:
                    raise ValueError('须先应战或让位，再退出王庭')
                asura_court.vacate(game, state)
            state['joined']=False
            state['seat_active']=False
            if state['obligation']:
                state['regard']=max(0,state['regard']-15)
            state['obligation']=None
            p.institution_affiliations.pop(cfg['id'],None)
            text='退出机构，停止俸禄和政策收益；放下未竟王命或誓愿会降低恩宠或信望，既有功勋保留。'
        elif action=='accept':
            if state['job']:
                raise ValueError('已有待完成或待领取的委托')
            factor=policy(game,state)['service']*(1.2 if state['blessing_until']>state['unit'] else 1)
            if p.world == 'asura':
                factor *= asura_court.benefits(game, state)['service']
            state['job']=dict(years=int(WORLD_SYSTEMS['time_units'][str(p.realm_index)]),progress=0,
                              reward=round(config()['service_merit']*factor))
            text='接取驻地委托；须实际履约一个行动单位，途中中断可继续，正常修行不能代替履约。'
        elif action=='abandon':
            if not state['job']:
                raise ValueError('没有委托可放弃')
            state['job']=None
            text='放弃委托，未领取任何功勋。'
        elif action=='claim':
            job=state['job']
            if not job or job['progress']<job['years']:
                raise ValueError('委托尚未完成')
            reward=job['reward']
            state['job']=None
            state['merit']+=reward
            state['earned']+=reward
            state['completed']+=1
            state['regard']=min(100,state['regard']+10)
            state['support'][state['bloc']]=min(100,state['support'][state['bloc']]+5)
            if state['obligation']:
                state['obligation']=None
                state['regard']=min(100,state['regard']+15)
            text=f"交付委托，功勋 +{reward}，累计功绩 +{reward}；恩宠或信望 +10。"
        elif action=='promote':
            if p.world=='nether':
                raise ValueError('祖族席位须由门阀授予代言资格')
            rank=state['rank']+1
            if rank>=len(cfg['ranks']):
                raise ValueError('已达最高职阶')
            merits = cfg.get('rank_merit', config()['rank_merit'])
            if state['earned']<merits[rank] or p.realm_index<9+rank//2 or state['regard']<rank*20:
                raise ValueError('累计功绩、境界或恩宠信望未达到晋阶要求')
            if p.world == 'asura':
                if state['court']['challenge']:
                    raise ValueError('请先回应换位战书')
                asura_court.change_rank(game, state, rank)
            else:
                state['rank']=rank
            text=f"获授{cfg['ranks'][rank]}，后续俸禄随之提高。"
        elif action=='bloc':
            if p.world!='nether' or not target.isdigit() or int(target) not in range(5):
                raise ValueError('请选择五族中的一族')
            if state['seat_active'] or state['job']:
                raise ValueError('须先辞去代言资格并结束委托，才能改投门阀')
            state['bloc']=int(target)
            text=f"选择为{cfg['titles'][int(target)]}争取席位，不改变自身血脉。"
        elif action=='lobby':
            if p.world!='nether' or not target.isdigit() or int(target) not in range(5):
                raise ValueError('请选择要争取的族群')
            i=int(target)
            if state['support'][i]>=100:
                raise ValueError('支持已满')
            spend(state,60)
            state['support'][i]=min(100,state['support'][i]+15)
            text=f"投入 60 功勋争取{cfg['titles'][i]}，支持 +15。"
        elif action=='resign':
            if p.world!='nether' or not state['seat_active']:
                raise ValueError('当前没有门阀代言资格')
            state['seat_active']=False
            text='辞去门阀代言资格，保留宫内客卿身份与既有功绩。'
        elif action=='patronage':
            if p.world!='nether' or state['seat_active']:
                raise ValueError('当前不能争取门阀席位')
            if state['unit']-state['last_appointment']<4:
                raise ValueError('距上次授席不足四单位')
            bloc=state['bloc']
            required_realm=10 if cfg['weights'][bloc]>=4 else 9
            if (state['earned']<cfg['seat_merit'][bloc] or state['support'][bloc]<cfg['seat_support'][bloc]
                    or p.realm_index<required_realm):
                raise ValueError(f"该门阀须累计功绩 {cfg['seat_merit'][bloc]}、支持 {cfg['seat_support'][bloc]}、第 {required_realm} 阶修为")
            state['seat_active']=True
            state['last_appointment']=state['unit']
            text=f"获得{cfg['titles'][bloc]}代言资格，掌握 {cfg['weights'][bloc]}/15 议权，无固定任期；本族支持低于五十时收回资格。"
        elif action=='vow':
            if p.world!='reincarnation' or state['obligation']:
                raise ValueError('当前不能立誓')
            state['obligation']=dict(name='济度誓愿：完成一次轮回殿委托',deadline=state['unit']+4)
            text='立下济度誓愿，四单位内交付一次委托可额外积累信望；失约信望降低 15。'
        elif action=='rite':
            if p.world!='reincarnation' or state['blessing_until']>state['unit']:
                raise ValueError('当前不能重复求取赐福')
            spend(state,100)
            state['blessing_until']=state['unit']+4
            state['regard']=min(100,state['regard']+20)
            text='祭仪消耗 100 功勋，信望 +20；四单位内接取的委托功勋增加两成。'
        elif action=='policy':
            if target not in {r['id'] for r in cfg['policies']} or target==state['policy']:
                raise ValueError('请选择尚未生效的政务')
            if state['unit']-state['last_proposal']<4:
                raise ValueError('距上次议政不足四单位')
            if state['treasury']<config()['policy_cost']:
                raise ValueError('机构府库不足')
            if p.world == 'asura' and asura_court.is_king(state):
                if state['court']['challenge']:
                    raise ValueError('须先回应换位战书，再行使王权')
                state['last_proposal'] = state['unit']
                enact(game, state, target, p.name + '亲颁王令')
                text = '王令已颁行，无需请奏或消耗功勋；新政持续至你更替。'
            elif p.world=='nether':
                if not state['seat_active']:
                    raise ValueError('只有门阀代言人可提出议案')
                tally=votes(game,target,player=True)
                state['last_proposal']=state['unit']
                text='；'.join(f"{v['name']}（议权{v['weight']}）：{'赞成' if v['yes'] else '缺席' if v['vacant'] else '未赞成'}" for v in tally)
                if sum(v['weight'] for v in tally if v['yes'])>sum(cfg['weights'])/2:
                    enact(game,state,target,'祖族议庭')
                    for i,preferred in enumerate(cfg['preferences']):
                        if preferred!=target:
                            state['support'][i]=max(0,state['support'][i]-(10 if i==state['bloc'] else 5))
                    if state['support'][state['bloc']]<50:
                        state['seat_active']=False
                    text+='。议案通过；与法令政见不合的门阀支持降低五点，本族则降低十点，低于五十收回代言资格。'
                else:
                    text+='。赞成议权未过半，维持现政；不扣府库。'
            else:
                threshold=80 if p.world=='asura' else 60
                rulers = officials(game)
                ruler_present = rulers[0]['present'] if p.world == 'asura' else any(o['present'] for o in rulers)
                if state['rank']<2 or state['regard']<threshold or not ruler_present:
                    raise ValueError(f'须职阶三阶、恩宠或信望至少 {threshold}，且有在世主事者')
                spend(state,100)
                state['last_proposal']=state['unit']
                enact(game,state,target,'修罗王准奏' if p.world=='asura' else '祭议奉旨')
                text='奏请获准，消耗 100 功勋；法令只占一个政务席位，旧政立即结束。'
        elif action=='stones':
            amount=100*config()['stones_per_merit']
            if state['treasury']<amount:
                raise ValueError('机构府库不足')
            spend(state,100)
            state['treasury']-=amount
            add_item(p,'spirit_stone',amount)
            text=f'消耗 100 功勋领取灵石 {amount}。'
        elif action=='material':
            from .upper_voisinage_rules import world_config
            from .crafting_system import crafting_material_definitions, make_crafting_material_instance
            material=crafting_material_definitions()[world_config(p)['material_id']]
            spend(state,config()['material_merit'])
            rng=decode_rng(game.seed,game.rng_state)
            p.crafting_materials.append(make_crafting_material_instance(material,rng,source=cfg['name'],origin_world=p.world))
            game.rng_state=encode_rng(rng)
            text=f"消耗 {config()['material_merit']} 功勋领取{material['name']}一份。"
        else:
            raise ValueError('未知机构事务')
    record(game,state,text)
    game.updated_at=now_iso()
    engine.store.save(game)
    return engine.present(game)


def public_institution(game):
    cfg=definition(game)
    if not cfg or game.player.realm_index<9:
        return {'available':False}
    state=account(game)
    result=copy.deepcopy(state)
    result.update(available=True,name=cfg['name'],regime=cfg['regime'],description=cfg['description'],
                  location=cfg['location'],local=game.player.location_id==cfg['location'],world=game.player.world,
                  policies=copy.deepcopy(cfg['policies']),ranks=cfg['ranks'],people=officials(game),
                  rank_merit=cfg.get('rank_merit', config()['rank_merit']),material_merit=config()['material_merit'],
                  policy_cost=config()['policy_cost'],discount=cultivation_discount(game),
                  current_policy=policy(game,state))
    if game.player.world=='nether':
        result.update(weights=cfg['weights'],seat_merit=cfg['seat_merit'],seat_support=cfg['seat_support'])
        result['tallies']={r['id']:votes(game,r['id'],player=True) for r in cfg['policies']}
    if game.player.world == 'asura':
        from .asura_court import public
        result['court'] = public(game, state)
    return result


class UpperInstitutionMixin:
    def upper_institution_action(self, game_id, action, target_id=''):
        return act(self,game_id,action,target_id)
