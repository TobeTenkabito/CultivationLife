"""Player actions for the optional Asura expansion."""
import copy

from ..models import HistoryRecord
from ..runtime import decode_rng, encode_rng, now_iso
from ..rules import opportunity_required
from . import asura


class AsuraSystemMixin:
    def asura_action(self, game_id, action, target_id='', body_ids=None, name=''):
        game = self._load(game_id)
        p = game.player
        if not asura.enabled() or p.path != 'demonic':
            raise ValueError('须开启修罗显圣 DLC 并主修魔道')
        if (not p.alive or game.pending_event or game.active_trial or p.imprisonment or p.ghost_captor
                or (game.guixu_state.get('player_session') or {}).get('trapped')
                or p.sealed_cultivation or p.cultivation_suppression):
            raise ValueError('当前状态无法修持八部')
        asura.ensure(game)
        s = p.asura_cultivation
        rng = decode_rng(game.seed, game.rng_state)
        if action == 'purify':
            soul = next((b for b in p.foreign_souls if b.get('id') == target_id and b.get('refined')), None)
            if not soul:
                raise ValueError('只能提纯已炼化且尚未提纯的元神')
            gain = max(1, int(soul.get('realm_index', 1))) * 10
            s['souls'] += gain
            p.foreign_souls.remove(soul)
            summary = f'将{soul["name"]}之元神提纯为 {gain} 精魂，炼化名录已移除。'
        else:
            if not asura.active(p):
                raise ValueError('须在修罗界达到修罗境')
            if action == 'convert':
                stage = s.get('conversion', 0)
                if stage >= 5:
                    raise ValueError('煞元已经完全转化')
                from ..engine.progression.asura_trials import queue
                game.active_trial = dict(kind='asura_conversion', stage=stage + 1,
                                         event_ids=[f'EVT_ASURA_CONVERSION_{stage + 1}'])
                queue(self, game)
                summary = f'开始煞元转化第 {stage + 1}/5 事件。'
            else:
                if s.get('conversion', 0) < 5:
                    raise ValueError('须先完成五重煞元转化')
                summary = self._asura_cultivate(game, action, target_id, body_ids, name, rng)
        game.rng_state = encode_rng(rng)
        game.history.append(HistoryRecord('SYS_ASURA_CULTIVATION', 1, p.age, '修罗显圣', None,
                                         'completed', summary, {}, ['system', 'asura', 'cultivation']))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def _asura_cultivate(self, game, action, target_id, body_ids, name, rng):
        p, cfg = game.player, asura.config()
        s = p.asura_cultivation
        if action == 'train_body':
            level = s.get('body_level', 0)
            if level >= 20 or p.body_training < 100:
                raise ValueError('须凡躯炼体达到100层，修罗之躯上限20层')
            cost = opportunity_required(p) * .04 * (level + 1)
            if p.opportunity < cost:
                raise ValueError('锻炼修罗之躯的机缘不足')
            p.opportunity -= cost
            s['body_level'] = level + 1
            return f'修罗之躯达到 {level + 1}/20 层。'
        if action == 'open_vein':
            from .immortal_cultivation import rules
            from .doctrine.cultivation import vein_cost
            rules = rules()
            veins = s.setdefault('veins', {})
            opened = veins.get(str(p.realm_index), 0)
            if opened >= p.layer * 3:
                raise ValueError('本层三条魔脉已贯通，请先突破')
            cost = vein_cost(p.realm_index, opened, rules)
            if p.opportunity < cost['opportunity']:
                raise ValueError('开辟魔脉的机缘不足')
            self._spend_asura_souls(s, cost['traces'])
            p.opportunity -= cost['opportunity']
            failures = s.setdefault('vein_pity', {})
            key = f'{p.realm_index}:{opened + 1}'
            index = min(8, opened // rules["veins_per_layer"])
            probability = min(1., rules['vein_success_rates'][index] + failures.get(key, 0) * rules['vein_pity_step'])
            if rng.random() < probability:
                veins[str(p.realm_index)] = opened + 1
                failures.pop(key, None)
                return f'本境第 {opened + 1}/27 条魔脉贯通。'
            failures[key] = failures.get(key, 0) + 1
            return f'开脉失败（成功率 {probability:.0%}），已积累下次保底。'
        if action == 'condense':
            if s.get('route') or s.get('body_level', 0) < 20:
                raise ValueError('须修罗之躯20层且尚未确定本命')
            candidates = p.prisoners + p.puppets
            body = next((b for b in candidates if b['id'] == target_id), None)
            if not body:
                raise ValueError('未找到可凝练的俘虏或傀儡')
            facts = asura.body_facts(body)
            if int(facts['body_training'] or 0) < cfg['minimum_body_training']:
                raise ValueError('肉身炼体不足60层')
            self._spend_asura_souls(s, 30 + int(facts['body_training'] or 0))
            facts['power'] = asura.body_power(facts)
            s['bodies'].append(facts)
            if body in p.prisoners:
                p.prisoners.remove(body)
            else:
                p.puppets.remove(body)
            return f'{facts["name"]}凝练完成，肉身战力 {facts["power"]:.0f}，等待融合。'
        if action == 'fuse':
            if s.get('route') or s.get('body_level', 0) < 20:
                raise ValueError('本命仅能确定一次，且须修罗之躯20层')
            if (not isinstance(body_ids, list) or not 1 <= len(body_ids) <= 2
                    or any(not isinstance(key, str) for key in body_ids)
                    or len(body_ids) != len(set(body_ids))):
                raise ValueError('须指定不重复的凝练肉身')
            bodies = [b for b in s['bodies'] if b['id'] in body_ids]
            if len(bodies) != len(body_ids):
                raise ValueError('肉身名录不匹配')
            routes = asura.eligible_routes(bodies)
            if len(routes) != 1:
                raise ValueError('所选肉身尚不满足任何八部路线')
            from ..engine.progression.asura_trials import start
            start(self, game, 'asura_fusion', bodies=copy.deepcopy(bodies), route=routes[0])
            return f'肉身条件指向{asura.ROUTE_NAMES[routes[0]]}，开始融合镇压战。'
        if not s.get('route'):
            raise ValueError('须先完成八部肉身融合')
        if action == 'rename':
            clean = str(name).strip()
            if not 1 <= len(clean) <= 24:
                raise ValueError('魔域名称须为1至24字')
            s['domain_name'] = clean
            return f'魔域定名为{clean}。'
        if action == 'train_route':
            if s['level'] >= 9:
                raise ValueError('八部本体已达9级')
            self._spend_asura_souls(s, 60 * s['level'])
            s['level'] += 1
            return f'{cfg["routes"][s["route"]]["part"]}修至 {s["level"]}/9 级。'
        if action == 'choose_branch':
            if s.get('branch') or s['level'] < 5 or p.realm_index < 10:
                raise ValueError('分支仅能确定一次，须本体5级且达到非天境')
            if target_id not in {b['id'] for b in s['branches'][s['route']]}:
                raise ValueError('分支不属于此本命')
            s.update(branch=target_id, branch_level=1)
            return '本命分支已经确定。'
        if action == 'train_branch':
            if not s.get('branch') or s.get('branch_level', 0) >= 9:
                raise ValueError('须已有分支且尚未达到9级')
            self._spend_asura_souls(s, 80 * s['branch_level'])
            s['branch_level'] += 1
            return f'分支修至 {s["branch_level"]}/9 级。'
        if action in {'train_domain', 'nourish_domain'}:
            key, maximum = ('domain_rank', 13) if action == 'train_domain' else ('domain_power', 99)
            value = s.get(key, 1 if key == 'domain_rank' else 0)
            if value >= maximum:
                raise ValueError('魔域该项已达到修炼上限')
            self._spend_asura_souls(s, 50 * (value + 1))
            s[key] = value + 1
            return '精魂融入魔域，境界或威能提升。'
        if action in {'learn_power', 'reroll_power'}:
            powers = s.setdefault('powers', [])
            slots = cfg['slots'][s['level'] - 1]
            if action == 'learn_power':
                if len(powers) >= slots:
                    raise ValueError('神通槽位已满')
                index = len(powers)
            else:
                index = next((i for i, row in enumerate(powers) if row['id'] == target_id), -1)
                if index < 0:
                    raise ValueError('须选择已有神通洗练')
            self._spend_asura_souls(s, 100)
            rule = asura.generate_rule(rng, f'asura:power:{index}')
            if index == len(powers):
                powers.append(rule)
            else:
                powers[index] = rule
            return f'精魂化生神通：{rule["name"]}。'
        raise ValueError('未知修罗修持操作')

    @staticmethod
    def _spend_asura_souls(state, cost):
        if state.get('souls', 0) < cost:
            raise ValueError(f'精魂不足，需要 {cost:g}')
        state['souls'] -= cost
