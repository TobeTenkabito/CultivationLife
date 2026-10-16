"""Atomic commands for explicit political war and legacy treaty adoption."""
import copy
from ...runtime import decode_rng, encode_rng, now_iso
from ...race_diplomacy import relations_for
from ...world_state import race_pair
from ..composition.strategic_war import bind
from ...system.strategic_war.rules import organizations, owns, ref, SIDES
from ...system.strategic_war.lifecycle import start, commit, note, withdraw, armistice
from ...system.strategic_war.politics import council, nominate, player_commander, opposing_reply


def _save(host,game,rng,command_id,sequence):
    state=game.strategic_war_state
    state.setdefault('commands',[]).append(command_id)
    state['commands']=state['commands'][-64:]
    state['command_seq']=sequence
    game.rng_state=encode_rng(rng)
    game.updated_at=now_iso()
    host.store.save(game)
    return host.present(game)


def act(host, game_id, payload):
    game = copy.deepcopy(host._load(game_id))
    p = game.player
    if not p.alive or p.imprisonment or p.ghost_captor or game.pending_event or game.active_trial:
        raise ValueError('当前状态无法处理战争议事')
    command_id = payload.get('command_id')
    if not isinstance(command_id, str) or not 1 <= len(command_id) <= 80:
        raise ValueError('缺少有效命令编号，请刷新页面')
    state = game.strategic_war_state
    if command_id in state.get('commands', []):
        raise ValueError('此命令已经提交，请刷新页面查看结果')
    sequence = payload.get('command_seq')
    if type(sequence) is not int or sequence != state.get('command_seq', 0) + 1:
        raise ValueError('命令序号已过期，请刷新页面')
    deps = bind(host)
    action = payload.get('action')
    rng = decode_rng(game.seed, game.rng_state)
    if action == 'adopt_relation':
        key = payload.get('relation_key', '')
        if ':' in key or key not in game.race_relations or not deps.has_race_voice(game):
            raise ValueError('没有可确认的本界旧约或缺少族议资格')
        from ...system.strategic_war.rules import local_races
        parts = key.split('|')
        if len(parts) != 2 or not set(parts) <= set(local_races(p.world)):
            raise ValueError('该旧约不能归属当前界面')
        if host._player_allegiance_race(p) not in parts:
            raise ValueError('你不是原约任一方的政治代表')
        relation = game.race_relations[key]
        if relation.get('adopted_world'):
            raise ValueError('该旧约已经确认归属')
        if key in relations_for(game):
            raise ValueError('本界已有独立条约，不能覆盖')
        adopted=copy.deepcopy(relation)
        if relation.get('status') == 'war':
            if p.age-relation.get('adoption_vote',{}).get('age',-1000)<10:
                raise ValueError('十年内不能重复提出旧案收束表决')
            records=[w for w in game.wars if w.get('kind')=='race' and {w.get('attacker_id'),w.get('defender_id')}==set(parts)]
            if any(w.get('status') in {'active','peace_ready'} for w in records):
                raise ValueError('旧战争关系须先沿原案和谈结清')
            if records and {w.get('world') for w in records}!={p.world}:
                raise ValueError('原战争事实不属于当前界面，不能改记此处')
            vote=council(deps,game,host._player_allegiance_race(p),rng)
            relation['adoption_vote']=vote
            if vote['yes']<=vote['total']/2:
                return _save(host,game,rng,command_id,sequence)
            adopted.update(status='truce',since_age=p.age,truce_until_age=p.age+50)
        relations_for(game)[key] = adopted
        relation['adopted_world'] = p.world
    elif action == 'settle_legacy':
        war = next((w for w in game.wars if w['id'] == payload.get('legacy_id') and w.get('kind') == 'race'), None)
        if (not war or war['world'] != p.world or war['status'] not in {'active','peace_ready'}
                or host._player_allegiance_race(p) not in {war['attacker_id'],war['defender_id']}
                or not deps.has_race_voice(game)):
            raise ValueError('没有本界旧族战的政治结清权限')
        if payload.get('expected_battles') != war.get('battles',0) or payload.get('expected_status') != war['status']:
            raise ValueError('原案战果已变化，请刷新核对')
        votes=state.setdefault('legacy_votes',{})
        if p.age-votes.get(war['id'],{}).get('age',-1000)<10:
            raise ValueError('十年内不能重复表决同一旧案')
        vote = council(deps,game,host._player_allegiance_race(p),rng)
        votes[war['id']]=vote
        state['legacy_votes']=dict(list(votes.items())[-20:])
        if vote['yes'] <= vote['total']/2:
            return _save(host,game,rng,command_id,sequence)
        if war['status'] == 'peace_ready':
            offer = war.get('peace_offer') or host._generate_ai_peace_offer(game, war, war['winner'])
            host._conclude_war_bundle(game, war, offer['demands'], war['winner'], automatic=True)
        else:
            host._conclude_war(game, war, 'white_peace', 'attacker', automatic=True)
        key = race_pair(war['attacker_id'],war['defender_id'])
        if key in game.race_relations:
            game.race_relations[key]['adopted_world'] = p.world
        war['legacy_settlement'] = dict(age=p.age, command_id=command_id)
    else:
        row = next((w for w in state.get('wars', []) if w['id'] == payload.get('war_id')), None)
        if not row or row['world'] != p.world or row['status'] == 'ended':
            raise ValueError('本界战争已结束或不存在')
        if type(payload.get('expected_revision')) is not int or payload['expected_revision'] != row['revision']:
            raise ValueError('战争态势已变化，请刷新后重新下令')
        pool = organizations(game, row['world'])
        if action == 'commit':
            org = next((o for o in pool if o.id == payload.get('org_id') and o.kind == payload.get('org_kind')), None)
            if not org or not owns(deps, game, org):
                raise ValueError('你无权批准此组织的人员与府库承诺')
            from ...system.war.logistics import cash
            if type(payload.get('expected_budget')) is not int or payload['expected_budget']!=int(cash(game,org)*.2):
                raise ValueError('原府库余额已变化，请核对最新军费上限后再批准')
            commit(deps, game, row, org)
        elif action == 'nominate':
            result=nominate(deps,game,row,payload.get('side'),rng)
            note(game,row,'统帅推举',f"你的统帅提名获 {result['yes']}/{result['total']} 票。")
        elif action == 'stance':
            side=player_commander(deps,game,row)
            stance=payload.get('stance')
            if not side or row['status']!='active' or stance not in {'hold','advance'}:
                raise ValueError('只有本案有效统帅能调整本方联军作战方针')
            for child in game.wars:
                if child.get('strategic_war_id')==row['id'] and child.get('status')=='active':
                    child.setdefault('stances',{})[side]=stance
            note(game,row,'联军方针','本方转入守备，敌军继续正常行动。' if stance=='hold' else '本方恢复按期进攻。')
        elif action == 'dispatch':
            from ...system.strategic_war.dispatch import send
            side=player_commander(deps,game,row)
            org=next((o for o in pool if o.id==payload.get('org_id') and o.kind==payload.get('org_kind')),None)
            child=next((w for w in game.wars if w['id']==payload.get('campaign_id')),None)
            if not side or not org or org.allegiance_race!=row[side] or not child:
                raise ValueError('只有有效统帅能调遣本方已承诺的闲置组织')
            if type(payload.get('expected_cost')) is not int:
                raise ValueError('请先核对本次实际出征经费')
            send(deps,game,row,child,org,expected_cost=payload['expected_cost'])
        elif action in {'withdraw','campaign_stance'}:
            child = next((w for w in game.wars if w.get('strategic_war_id') == row['id'] and w['id'] == payload.get('campaign_id')), None)
            org = next((o for o in pool if o.id == payload.get('org_id') and o.kind == payload.get('org_kind')), None)
            from ...system.war.occupancy import participant_ids
            if not child or not org or not owns(deps, game, org) or org.id not in participant_ids(child):
                raise ValueError('只能撤回本人有权指挥的组织战役')
            if child.get('status') != 'active':
                raise ValueError('此战役已结算或正在撤军')
            side = next(s for s in SIDES if any(r['id']==org.id for r in child['coalitions'][s]))
            if org.id in child.get('withdrawn_orgs',[]):
                raise ValueError('此组织已经撤回，不能继续指挥该战役')
            if action=='campaign_stance':
                if payload.get('stance') not in {'hold','advance'}:
                    raise ValueError('未知作战方针')
                child.setdefault('org_stances',{})[org.id]=payload['stance']
                note(game,row,'战役军令',f'{org.name}调整本部作战方针。')
            else:
                from ...system.strategic_war.dispatch import recall
                if recall(game,child,org):
                    from ...system.strategic_war.lifecycle import receipt
                    receipt(game,row,child)
                note(game,row,'本部撤回',f'{org.name}沿原路撤回，其他参战宗门继续执行军令。')
        elif action == 'participate_round':
            from ...system.strategic_war.willingness import personal_side
            child = next((w for w in game.wars if w.get('strategic_war_id') == row['id'] and w['id'] == payload.get('campaign_id')), None)
            side = personal_side(deps, game, row, child) if child else None
            if not side:
                raise ValueError('须本人在实际战场、属于唯一合法参战方，且距上次亲征至少十年')
            host._resolve_player_war_round(game, child, side, rng)
            child['last_personal_age'] = p.age
            child['next_battle_age'] = p.age + 10
            from ...system.strategic_war.lifecycle import receipt
            receipt(game, row, child)
        elif action == 'reply_peace':
            from ...system.strategic_war.peace import player_reply, accept
            proposal = row.get('peace_proposal')
            if (row['status'] not in {'mobilizing', 'active'} or not proposal or proposal['status'] != 'pending'
                    or p.age >= proposal['expires'] or not player_reply(deps, game, row, proposal)
                    or payload.get('reply') not in {'accept', 'reject'}):
                raise ValueError('没有当前可由你答复的和谈')
            if payload['reply'] == 'accept':
                accept(deps, game, row, proposal)
            else:
                proposal['status'] = 'rejected'
                note(game, row, '拒绝和谈', '本方拒绝此项和约条件，原战役与战时授权继续。')
        elif action == 'offer_peace':
            if not deps.has_race_voice(game) or host._player_allegiance_race(p) not in {row['attacker'], row['defender']}:
                raise ValueError('没有本案种族的和谈提案资格')
            if row['status'] not in {'active', 'mobilizing'}:
                raise ValueError('双方已在执行停战')
            prior = row.get('peace_proposal_age', -1000)
            if p.age - prior < 10:
                raise ValueError('十年内只能提出一次总和谈')
            side = 'attacker' if host._player_allegiance_race(p) == row['attacker'] else 'defender'
            from ...system.strategic_war.peace import propose, package
            term = payload.get('term', 'white_peace')
            bundle = package(deps, game, row, side, term)
            demands = bundle['demands']
            if term != 'white_peace' and payload.get('expected_quote') != bundle['quote_key']:
                raise ValueError('和约涉及的组织、资产或报价已变化，请刷新后重新审阅')
            if demands and type(payload.get('expected_total')) is not int:
                raise ValueError('请核对本次赔款报价')
            old = row.get('peace_proposal')
            if old and old['status'] == 'pending' and p.age < old['expires']:
                raise ValueError('请先答复现有和谈')
            vote=council(deps,game,host._player_allegiance_race(p),rng)
            row['peace_vote']=vote
            row['peace_proposal_age'] = p.age
            if vote['yes'] > vote['total']/2:
                propose(deps, game, row, side, term, player=True, expected_total=payload.get('expected_total'),expected_quote=payload.get('expected_quote'))
            else:
                note(game, row, '和谈未获批准', '本方族议未通过提案，继续执行原战时授权。')
        else:
            raise ValueError('未知战争命令')
        row['revision'] += 1
    return _save(host,game,rng,command_id,sequence)
