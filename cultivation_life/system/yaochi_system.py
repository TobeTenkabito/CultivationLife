"""Player economy: bounded jobs and escrowed commissions, no NPC/yearly polling."""
import copy
import math

from ..content_registry import WORLD_SYSTEMS, ITEM_CATALOG
from ..models import Technique, HistoryRecord
from ..rules import add_item, learn_technique, add_technique_copy
from ..runtime import now_iso
from .immortal_cultivation import rules


def config():
    return WORLD_SYSTEMS['yaochi']


def account(game):
    return game.yaochi_state


def spend(game, amount):
    amount = int(amount)
    if amount <= 0 or account(game).get('merit', 0) < amount:
        raise ValueError('瑶池功勋不足')
    account(game)['merit'] -= amount


def require_market(game):
    p = game.player
    if p.world != 'celestial' or p.realm_index < 9 or p.location_id != config()['location_id']:
        raise ValueError('须亲临仙界瑶池办理功勋交易与委托')
    if not p.alive or game.pending_event or game.active_trial or p.imprisonment or p.ghost_captor or (game.guixu_state.get('player_session') or {}).get('trapped'):
        raise ValueError('当前状态无法办理瑶池事务')


def offers(game, *, commission=False):
    from .doctrine_system import _offers
    result = []
    books = ([b for d in game.doctrine_state.get('definitions', {}).values() for b in d['manuals']
              if b['grade'] <= game.player.realm_index] if commission else _offers(game))
    locked = account(game).get('locked_offers', {}) if not commission else {}
    if not commission:
        books = [b for b in books if b['id'] not in locked][:max(0, 5-len(locked))]
        result.extend(copy.deepcopy(list(locked.values())))
    for book in books:
        result.append(dict(id=book['id'], name=book['name'], kind='doctrine', quantity=1,
                           price=config()['manual_prices'][max(0,min(3,book['grade']-9))], payload=book))
    for manual in rules()['body']['manuals']:
        result.append(dict(id=manual['id'], name=manual['name'], kind='body_manual', quantity=1,
                           price=config()['body_manual_prices'][manual['id']]))
    for supply in [*rules()['body']['supplies'], *config()['materials']]:
        price = supply['price'] if supply in config()['materials'] else config()['supply_prices'][supply['id']]
        result.append(dict(id=supply['id'], name=ITEM_CATALOG[supply['id']].name, kind='item', quantity=supply['quantity'], price=price))
    for pill in config()['breakthrough_pills']:
        if pill['realm'] == game.player.realm_index:
            item = ITEM_CATALOG[pill['id']]
            result.append(dict(id=item.id, name=item.name, kind='item', quantity=pill['quantity'],
                               price=pill['price'], description=item.description))
    return result


def grant(game, offer, amount=1):
    p = game.player
    if offer['kind']=='body_manual':
        if offer['id'] in p.immortal_body.get('manuals', []):
            raise ValueError('已经掌握此仙躯功法')
        p.immortal_body.setdefault('manuals', []).append(offer['id'])
        p.immortal_body.setdefault('active_manual', offer['id'])
    elif offer['kind']=='doctrine':
        from .doctrine.provider import player_record
        technique = Technique(**copy.deepcopy(offer['payload']))
        learned = learn_technique(p, technique)
        add_technique_copy(p, technique, amount - int(learned))
        player_record(game)['progress'].setdefault(technique.doctrine_id, {'level':0,'experience':0})
    else:
        add_item(p, offer['id'], offer['quantity'] * amount)


def experience(game):
    cfg = config()['experience']
    xp = max(0, int(account(game).get('experience', 0)))
    level = 1 + xp // cfg['per_level']
    return dict(level=level, total=xp, progress=xp % cfg['per_level'], required=cfg['per_level'],
                multiplier=1 + (level - 1) * cfg['reward_per_level'], per_job=cfg['per_job'])


def commission_reward(player, job, game=None):
    cfg = config()
    multiplier = cfg['realm_reward_multipliers'][max(0, min(3, player.realm_index-9))]
    multiplier *= experience(game)['multiplier'] if game else 1
    return round(job['reward'] * multiplier * (1 + cfg['layer_reward_step'] * max(0, min(8, player.layer-1))))


def lock_price(offer):
    return max(config()['lock_minimum'], math.ceil(offer['price'] * config()['lock_rate']))


class YaochiMixin:
    def _begin_yaochi_action(self, game, action):
        if action != 'yaochi_work': return
        require_market(game)
        job = account(game).get('job')
        if not job or job['progress'] >= job['years']:
            raise ValueError('须先接取尚未完成的瑶池委托')

    def _finish_yaochi_action(self, game, action, elapsed):
        if action != 'yaochi_work': return
        job = account(game).get('job')
        if job:
            job['progress'] = min(job['years'], job['progress'] + max(0, elapsed))

    def yaochi_action(self, game_id, action, target_id='', amount=1):
        game = self._load(game_id)
        require_market(game)
        p, state, cfg = game.player, account(game), config()
        unit = int(WORLD_SYSTEMS['time_units'][str(p.realm_index)])
        if type(amount) is not int or not 1 <= amount <= 1000000:
            raise ValueError('数量须为 1 至 1000000 的整数')
        if action == 'work':
            return self.advance(game_id, 'yaochi_work', 1)
        if action in {'lock', 'unlock'}:
            locked = state.setdefault('locked_offers', {})
            if action == 'unlock':
                if target_id not in locked:
                    raise ValueError('此货物尚未锁定')
                entry = locked.pop(target_id)
                summary = f"解除《{entry['name']}》的保留，锁货费用不退还。"
            else:
                if target_id in locked:
                    raise ValueError('此货物已经锁定，无须重复付费')
                if len(locked) >= cfg['lock_limit']:
                    raise ValueError('锁货名额已满，请先购买或解除保留')
                entry = next((o for o in offers(game) if o['id'] == target_id), None)
                if not entry or entry['kind'] != 'doctrine':
                    raise ValueError('只能锁定当期轮换的道统传承；常驻资材无需锁定')
                cost = lock_price(entry)
                spend(game, cost)
                locked[target_id] = copy.deepcopy(entry)
                summary = f"花费 {cost} 功勋锁定《{entry['name']}》，货物和兑换价格保留至购买或主动解锁。"
        elif action in {'buy','publish'}:
            if action == 'publish' and amount != 1:
                raise ValueError('求取委托每次发布一份')
            offer = next((o for o in offers(game, commission=action=='publish') if o['id']==target_id), None)
            if not offer: raise ValueError('当前没有这份仙家资材或传承')
            if offer['kind'] == 'body_manual' and amount != 1:
                raise ValueError('仙躯功法只能兑换一份')
            if offer['kind']=='doctrine' and offer['payload']['grade'] > p.realm_index:
                raise ValueError('当前修为尚不足以取得此品阶传承')
            if offer['kind']=='body_manual' and (target_id in p.immortal_body.get('manuals', []) or any(o['offer']['id']==target_id for o in state.get('orders', []))):
                raise ValueError('此仙躯功法已经掌握或已委托求取')
            if action == 'publish' and len(state.get('orders', [])) >= cfg['max_orders']:
                raise ValueError('待交付委托已达上限，请先领取')
            price = math.ceil(offer['price'] * (1 + cfg['order_fee'])) if action=='publish' else offer['price'] * amount
            spend(game, price)
            if action=='buy':
                grant(game, offer, amount)
                state.get('locked_offers', {}).pop(target_id, None)
                summary = f"以 {price} 功勋兑换《{offer['name']}》×{offer['quantity'] * amount}。"
            else:
                serial=state.get('order_sequence',0)+1;state['order_sequence']=serial
                state.setdefault('orders',[]).append(dict(id=str(serial), offer=copy.deepcopy(offer), price=price, ready_age=p.age+unit))
                summary = f"发布求取《{offer['name']}》的委托，预付 {price} 功勋（含撮合费），{unit} 年后可来领取。"
        elif action=='claim_order':
            order=next((o for o in state.get('orders',[]) if o['id']==target_id),None)
            if not order or p.age < order['ready_age']: raise ValueError('委托尚未交付或已经领取')
            grant(game,order['offer']);state['orders'].remove(order)
            summary=f"领取委托所得《{order['offer']['name']}》。"
        elif action=='accept':
            if state.get('job'): raise ValueError('须先交付当前委托')
            job=next((j for j in cfg['commissions'] if j['id']==target_id),None)
            if not job: raise ValueError('未知瑶池委托')
            state['job']=dict(job,years=unit,progress=0,reward=commission_reward(p, job, game))
            summary=f"接取【{job['name']}】，须在瑶池实际履约 {unit} 年。中途遇事可稍后继续。"
        elif action=='claim_job':
            job=state.get('job')
            if not job or job['progress']<job['years']: raise ValueError('委托履约尚未完成')
            state['merit']=state.get('merit',0)+job['reward'];state['earned']=state.get('earned',0)+job['reward']
            gain = cfg['experience']['per_job']
            state['experience'] = state.get('experience', 0) + gain
            summary=f"交付【{job['name']}】，获得 {job['reward']} 功勋、{gain} 瑶池经验。";state['job']=None
        elif action=='exchange_stones':
            spend(game,amount);add_item(p,'spirit_stone',amount*cfg['stones_per_merit'])
            summary=f"以 {amount} 功勋兑换灵石 ×{amount*cfg['stones_per_merit']}。"
        elif action=='exchange_court_merit':
            spend(game,amount*cfg['merit_per_court_merit']);self._add_court_merit(game,amount)
            summary=f"以 {amount*cfg['merit_per_court_merit']} 功勋兑换 {amount} 天庭功德。"
        elif action=='support':
            court=game.heavenly_court
            if court['player_support']>=100: raise ValueError('天庭支持度已满')
            spend(game,cfg['support_cost']);court['player_support']=min(100,court['player_support']+cfg['support_gain'])
            self._sync_player_court_identity(game)
            summary=f"通过瑶池联络天官，支持度提升至 {court['player_support']:g}。"
        elif action=='buy_vote':
            election=game.heavenly_court.get('open_election')
            if not election or 'player' not in election['candidates']: raise ValueError('须在本次选举中拥有候选资格')
            tickets=election.setdefault('yaochi_seats',[])
            if target_id in tickets or len(tickets)>=cfg['vote_max']: raise ValueError('该票已议定或已达本次交易上限')
            if target_id not in {s['id'] for s in game.heavenly_court['seats']}: raise ValueError('未知选举席位')
            spend(game,cfg['vote_cost']);tickets.append(target_id)
            summary='以功勋议定本次选举一席支持，重投仍有效，本次选举结束后失效。'
        else:
            raise ValueError('未知瑶池事务；不提供灵石兑换功勋')
        game.history.append(HistoryRecord('SYS_YAOCHI',1,p.age,'瑶池功勋',action,'completed',summary,{},['yaochi','economy']))
        game.updated_at=now_iso();self.store.save(game)
        return self.present(game)

    def _public_yaochi(self, game):
        p=game.player;cfg=config();state=account(game)
        if p.world!='celestial' or p.realm_index<9: return {'available':False}
        election=game.heavenly_court.get('open_election')
        definitions = game.doctrine_state.get('definitions', {})
        catalog = []
        for offer in offers(game, commission=True):
            book = offer.get('payload') if offer['kind'] == 'doctrine' else None
            catalog.append(dict(id=offer['id'], name=offer['name'], price=math.ceil(offer['price']*(1+cfg['order_fee'])),
                doctrine=definitions[book['doctrine_id']]['name'] if book else None,
                grade=book['grade'] if book else None))
        total_manuals = sum(len(d['manuals']) for d in definitions.values())
        rows=[]
        for o in offers(game):
            rows.append({k:v for k,v in o.items() if k!='payload'} | {'owned':o['kind']=='body_manual' and o['id'] in p.immortal_body.get('manuals',[]), 'commission_price':math.ceil(o['price']*(1+cfg['order_fee'])), 'locked':o['id'] in state.get('locked_offers',{}), 'lock_price':lock_price(o), 'can_lock':o['kind']=='doctrine', 'eligible':o['kind']!='doctrine' or o['payload']['grade']<=p.realm_index})
        return dict(available=True, local=p.location_id==cfg['location_id'], location_id=cfg['location_id'],
                    experience=experience(game), commission_catalog=catalog,
                    manual_catalog_counts={'total':total_manuals, 'eligible':sum(o['doctrine'] is not None for o in catalog)},
                    merit=state.get('merit',0), earned=state.get('earned',0), shop=rows, commissions=[dict(j,reward=commission_reward(p,j,game),years=int(WORLD_SYSTEMS['time_units'][str(p.realm_index)])) for j in cfg['commissions']],
                    lock_limit=cfg['lock_limit'], locked_count=len(state.get('locked_offers',{})),
                    job=copy.deepcopy(state.get('job')), orders=[dict(id=o['id'],name=o['offer']['name'],ready_age=o['ready_age'],ready=p.age>=o['ready_age']) for o in state.get('orders',[])],
                    exchange={k:cfg[k] for k in ('stones_per_merit','merit_per_court_merit','support_cost','support_gain','vote_cost')},
                    votes=[dict(id=s['id'],name=s['name'],bought=s['id'] in election.get('yaochi_seats',[])) for s in game.heavenly_court['seats']] if election and 'player' in election['candidates'] else [])
