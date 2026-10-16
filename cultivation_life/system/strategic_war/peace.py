"""War-result treaties, real organization compensation, explicit player consent."""
from .rules import SIDES, committed_org, owns, ref
from .politics import opposing_reply
from .records import note
from ..war.logistics import cash

TERMS = {'white_peace': '无条件停战', 'long_truce': '长期休战', 'reparations': '战争赔款',
         'heavy_reparations': '加重赔款', 'destroy_outpost': '拆除战区据点',
         'remove_influence': '退出争议战区', 'economic_rights': '移交战败宗产业'}
DESCRIPTIONS = {'white_peace': '各自撤军，保留现有产权，停战一千年，约十次百年行动。',
    'long_truce': '签订三千年停战约束，约三十次百年行动，保障双方长期休养。',
    'reparations': '补偿本方实际军需损耗与动员驻军费用，再加败宗现款25%；实付最多其现款75%。',
    'heavy_reparations': '索赔本方战争损耗的两倍，再加败宗现款50%；实付最多其现款90%。',
    'destroy_outpost': '仅拆除已获胜战役所在地的敌宗实际据点，影响力仍保留。',
    'remove_influence': '移除已获胜战区的敌宗影响；山门在此时依法迁址，原库存留在原地。',
    'economic_rights': '接管一个败宗的原产业、市税和可承接商队；产权交接后产业停产待安排。'}


def divide(total, weights):
    weights={k:v for k,v in weights.items() if v>0}
    denominator=sum(weights.values())
    result={k:total*v//denominator for k,v in weights.items()}
    remainder=total-sum(result.values())
    for k in list(result)[:remainder]:result[k]+=1
    return result


def war_losses(game,row,side):
    # Destroyed includes consumed goods/cash, transit loss and raided destruction.
    # Procurement is an asset exchange; mobilized principal and refunds are not losses.
    return sum(max(0,int(book.get('destroyed',0)))+max(0,int(book.get('mobilization_paid',0)))
               +max(0,int(book.get('stationing_paid',0)))+max(0,int(book.get('captured_loss',0)))
               for child in game.wars if child.get('strategic_war_id')==row['id']
               for book in [child.get('logistics',{}).get('sides',{}).get(side,{})])


def effects(deps, game, row, side, term):
    if term not in {'destroy_outpost', 'remove_influence', 'economic_rights'}:
        return []
    required = {'destroy_outpost': 50, 'remove_influence': 100, 'economic_rights': 100}[term]
    if row['score'] * (1 if side == 'attacker' else -1) < required:
        raise ValueError('实际战果不足以执行此项条款')
    enemy = 'defender' if side == 'attacker' else 'attacker'
    commitments = {c['org']['id']: c for c in row['commitments']}
    for child in game.wars:
        if (child.get('strategic_war_id') != row['id'] or child.get('winner') != side
                or not child.get('battles') or not row['receipts'].get(child['id'], {}).get('terminal')):
            continue
        loser = committed_org(game, row, commitments[child[f'{enemy}_id']])
        winner = committed_org(game, row, commitments[child[f'{side}_id']])
        if not loser or not winner:
            continue
        effect = dict(term=term, payer=ref(loser), receiver=ref(winner), payer_name=loser.name,
                      receiver_name=winner.name, campaign_id=child['id'], location=child['location_id'])
        if term in {'destroy_outpost', 'remove_influence'}:
            from ..territory.peace import validate
            try:
                target = validate(game, deps.maps, row['world'], loser.id, term, child['location_id'])
            except ValueError:
                continue
            effect.update(location_name=target['name'], headquarters=target['headquarters'])
        else:
            from ..economy.war_assets import eligible
            if not eligible(game, child, winner.id, loser.id):
                continue
            old_kind = 'family' if loser is game.family else 'sect'
            effect['estates'] = sorted(r['id'] for r in game.economy_v2.get('estates', {}).values()
                if (r['world'],r['owner_kind'],r['owner_id']) == (row['world'],old_kind,loser.id))
            effect['markets'] = sorted(r['id'] for r in game.economy_v2.get('markets', {}).values()
                if r['world']==row['world'] and (((r.get('control') or {}).get('id')==loser.id)
                    or (not r.get('control') and r['location']==loser.location_id)))
            effect['fleets'] = sorted(r['id'] for r in game.economy_v2.get('transport',{}).get('worlds',{}).get(row['world'],{}).get('fleets',{}).values()
                if (r['owner_kind'],r['owner_id'])==(old_kind,loser.id) and r['status']!='retired')
            if not any(effect[k] for k in ('estates','markets','fleets')):
                continue
        return [effect]  # One explicit defeated organization; never the whole race.
    raise ValueError('当前没有可依法执行此条款的已败战区或原资产')


def package(deps, game, row, side, term):
    import hashlib
    import json
    demands = quote(deps, game, row, side, term)
    changes = effects(deps, game, row, side, term)
    data = dict(demands=demands,effects=changes,truce_years=3000 if term=='long_truce' else 1000)
    data.update(war_losses=war_losses(game,row,side),claimed=sum(d.get('claimed',d['amount']) for d in demands),
                shortfall=sum(d.get('claimed',d['amount'])-d['amount'] for d in demands))
    data['quote_key'] = hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    return data


def quote(deps, game, row, side, term):
    if side not in SIDES or term not in TERMS:
        raise ValueError('未知和约条件')
    if term in {'white_peace', 'long_truce'}:
        return []
    if term in {'destroy_outpost', 'remove_influence', 'economic_rights'}:
        effects(deps, game, row, side, term)
        return []
    support = row['score'] * (1 if side == 'attacker' else -1)
    if support < (100 if term == 'heavy_reparations' else 50):
        raise ValueError('当前实际战果不足以提出此项赔款')
    enemy = 'defender' if side == 'attacker' else 'attacker'
    commitments = {c['org']['id']: c for c in row['commitments']}
    liable = {}
    beneficiaries = {}
    for c in row['commitments']:
        if c['side']!=side:continue
        org=committed_org(game,row,c)
        if not org:continue
        weight=sum(child.get('logistics',{}).get('sides',{}).get(side,{}).get('contributions',{}).get(org.id,0)
                   for child in game.wars if child.get('strategic_war_id')==row['id'])
        beneficiaries[org.id]=(org,weight)
    for child in game.wars:
        if (child.get('strategic_war_id') != row['id'] or child.get('winner') != side
                or child.get('battles', 0) < 1 or not row['receipts'].get(child['id'], {}).get('terminal')):
            continue
        if not committed_org(game, row, commitments[child[f'{side}_id']]):
            continue
        for participant in child['coalitions'][enemy]:
            c = commitments.get(participant['id'])
            loser = committed_org(game, row, c) if c else None
            if not loser:
                continue
            liable[loser.id]=loser
    funds={key:cash(game,org) for key,org in liable.items()}
    if not sum(funds.values()) or not beneficiaries:
        raise ValueError('没有可实际支付赔款的败宗或合法收款组织')
    heavy=term=='heavy_reparations'
    losses=war_losses(game,row,side)
    compensation=divide(losses*(2 if heavy else 1),funds)
    weights={key:weight for key,(_,weight) in beneficiaries.items() if weight>0}
    if not weights:
        winners={w[f'{side}_id'] for w in game.wars if w.get('strategic_war_id')==row['id'] and w.get('winner')==side}
        weights={key:1 for key in beneficiaries if key in winners}
    demands=[]
    for key,loser in liable.items():
        claimed=compensation.get(key,0)+funds[key]*(50 if heavy else 25)//100
        amount=min(claimed,funds[key]*(90 if heavy else 75)//100)
        if not amount:continue
        shares=divide(amount,weights)
        allocations=[dict(receiver=ref(beneficiaries[k][0]),receiver_name=beneficiaries[k][0].name,amount=n)
                     for k,n in shares.items() if n>0]
        first=allocations[0]
        demands.append(dict(payer=ref(loser),receiver=first['receiver'],receiver_name=first['receiver_name'],
            payer_name=loser.name,amount=amount,claimed=claimed,compensation=compensation.get(key,0),
            allocations=allocations))
    if not demands:
        raise ValueError('没有已败且具备实际可支付府库的参战组织')
    return demands


def player_reply(deps, game, row, proposal):
    side = 'defender' if proposal['side'] == 'attacker' else 'attacker'
    return (game.player.world == row['world'] and
            ((deps.has_race_voice(game) and game.player.allegiance_race == row[side]) or
             any(c['side'] == side and (org := committed_org(game, row, c)) and owns(deps, game, org)
                 for c in row['commitments'])))


def terms_valid(deps, game, row, proposal):
    try:
        current = quote(deps, game, row, proposal['side'], proposal['term'])
        changes = effects(deps, game, row, proposal['side'], proposal['term'])
    except ValueError:
        return False
    # A quoted amount is fixed. Extra treasury growth cannot silently increase it.
    actual = {(d['payer']['id'], d['receiver']['id']): d['amount'] for d in current}
    valid_receivers={c['org']['id'] for c in row['commitments'] if c['side']==proposal['side'] and committed_org(game,row,c)}
    return (changes == proposal.get('effects',[]) and all(actual.get((d['payer']['id'], d['receiver']['id']), 0) >= d['amount']
        and all(a['receiver']['id'] in valid_receivers for a in d.get('allocations',[d])) for d in proposal['demands']))


def settle(deps, game, row, proposal):
    if row.get('treaty') or not terms_valid(deps, game, row, proposal):
        raise ValueError('和约已执行或原付款条件已变化，请重新议和')
    from ..economy.war_finance import reparations
    from .settlement import armistice
    for d in proposal['demands']:
        for allocation in d.get('allocations',[d]):
            paid = reparations(game, dict(kind='sect', world=row['world']),
                               allocation['receiver']['id'], d['payer']['id'], allocation['amount'])
            if paid != allocation['amount']:
                raise ValueError('原府库不足，不能静默改写已批准的赔款')
    results = []
    for change in proposal.get('effects',[]):
        if change['term'] in {'destroy_outpost','remove_influence'}:
            from ..territory.peace import apply
            results.append(apply(game,deps.maps,row['world'],change['payer']['id'],change['term'],change['location']))
        else:
            from ..economy.war_assets import transfer
            child=next(w for w in game.wars if w['id']==change['campaign_id'] and w.get('strategic_war_id')==row['id'])
            results.append(transfer(game,deps.maps,child,change['receiver']['id'],change['payer']['id'],strict=True))
    row['treaty'] = dict(term=proposal['term'], side=proposal['side'], age=game.player.age,
                         demands=proposal['demands'], effects=proposal.get('effects',[]),results=results,
                         war_losses=proposal.get('war_losses',0),claimed=proposal.get('claimed',0),shortfall=proposal.get('shortfall',0),
                         truce_years=proposal.get('truce_years',1000), total=sum(d['amount'] for d in proposal['demands']))
    proposal['status'] = 'accepted'
    armistice(game, row, f"双方签订{TERMS[proposal['term']]}，实际赔付 {row['treaty']['total']} 灵石；{'；'.join(results)}；原军需另行归返结清。")


def propose(deps, game, row, side, term, *, player=False, expected_total=None, expected_quote=None):
    if row['status'] not in {'mobilizing', 'active'}:
        raise ValueError('当前已在执行停战')
    old = row.get('peace_proposal')
    if old and old['status'] == 'pending' and game.player.age < old['expires']:
        raise ValueError('已有待答复的和谈，请先处理原案')
    bundle = package(deps, game, row, side, term)
    demands = bundle['demands']
    if expected_quote is not None and expected_quote != bundle['quote_key']:
        raise ValueError('和约涉及的组织、资产或报价已变化，请刷新后重新审阅')
    total = sum(d['amount'] for d in demands)
    if expected_total is not None and (type(expected_total) is not int or expected_total != total):
        raise ValueError('赔款报价已变化，请刷新核对实际付款组织与金额')
    enemy = 'defender' if side == 'attacker' else 'attacker'
    proposal = dict(side=side, term=term, **bundle, total=total, age=game.player.age,
                    expires=game.player.age + 20, status='pending')
    row['peace_proposal'] = proposal
    row['peace_proposal_age'] = game.player.age
    support = row['score'] * (1 if side == 'attacker' else -1)
    fought = sum(w.get('battles', 0) for w in game.wars if w.get('strategic_war_id') == row['id'])
    completed = bool(row['objectives']) and all(o['status'] == 'completed' for o in row['objectives'])
    accepts = (support >= 50 or (fought > 0 and game.player.age - row['start_age'] >= 100)
               or (completed and term == 'white_peace'))
    vote = opposing_reply(deps, game, row, enemy, accepts)
    row['opposing_peace_vote'] = vote
    if player_reply(deps, game, row, proposal):
        note(game, row, '和谈待复', f"对方提出{TERMS[term]}，请在二十年内确认；交战不会因此暂停。")
    elif vote['total'] and vote['yes'] > vote['total'] / 2:
        settle(deps, game, row, proposal)
    else:
        proposal['status'] = 'rejected'
        note(game, row, '和谈答复', '对方拒绝本次条件，战役继续。')
    return proposal


def advance(deps, game, row):
    if row['status'] not in {'mobilizing', 'active'}:
        return
    proposal = row.get('peace_proposal')
    if proposal and proposal['status'] == 'pending':
        if game.player.age >= proposal['expires'] or not terms_valid(deps, game, row, proposal):
            proposal['status'] = 'expired'
            note(game, row, '和谈失效', '原提案已过期或付款条件变化，继续作战并重新交涉。')
        else:
            return
    completed = bool(row['objectives']) and all(o['status'] == 'completed' for o in row['objectives'])
    if not completed or game.player.age - row.get('objectives_done_age', game.player.age) < 20:
        return
    if game.player.age - row.get('peace_proposal_age', -1000) < 20:
        return
    side = 'attacker' if row['score'] >= 0 else 'defender'
    # The player's own political side retains the decision to demand/waive terms.
    if ((deps.has_race_voice(game) and game.player.world == row['world'] and game.player.allegiance_race == row[side])
            or any(c['side'] == side and (org := committed_org(game, row, c)) and owns(deps, game, org) for c in row['commitments'])):
        return
    term = 'heavy_reparations' if abs(row['score']) >= 100 else 'reparations' if abs(row['score']) >= 50 else 'white_peace'
    try:
        quote(deps, game, row, side, term)
    except ValueError:
        term = 'white_peace'
    propose(deps, game, row, side, term)
