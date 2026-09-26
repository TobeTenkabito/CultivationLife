"""Persistent NPC commission execution, milestones and settlement."""
import math
import random

from ..content_registry import REALMS, WORLD_SYSTEMS
from ..rules import add_item, max_hp, max_mp


class MerchantExecutionMixin:
    def _merchant_route_exists(self, game, alliance, world):
        return bool(alliance and world in alliance['linked_worlds']
                    and self._merchant_alliance(game, world, alliance['id']))

    def _migrate_merchant_routes(self, game):
        state = game.merchant_state
        for world, alliances in state['worlds'].items():
            for alliance in alliances:
                if alliance['id'] != 'xuanji':
                    continue
                if world not in {'human', 'monster_realm'}:
                    alliance['linked_worlds'] = ['spirit', 'true_demon']
                    continue
                replacement = f'{world}-2'
                alliance.update(id=replacement, name=WORLD_SYSTEMS['world_names'][world] + '通宝商盟',
                                cross_world=False, home_world=world, linked_worlds=[world],
                                chief_power=0, chief_name=alliance['leader']['name'])
                alliance['leader']['title'] = '盟主'
                for record in [state.get('membership'), state.get('active'), *state['posted']]:
                    if record and record.get('world') == world and record.get('alliance_id') == 'xuanji':
                        record['alliance_id'] = replacement
                        if record.get('influence_key'):
                            record['influence_key'] = record['influence_key'].replace(':xuanji:', f':{replacement}:')
                for key in list(state['influence']):
                    if key.startswith(f'{world}:xuanji:'):
                        state['influence'][key.replace(':xuanji:', f':{replacement}:')] = state['influence'].pop(key)
                self._merchant_notice(game, f"{WORLD_SYSTEMS['world_names'][world]}璇玑商盟据点已撤销，由{alliance['name']}承接当地事务；已有职衔、影响力和待完成任务保留。")
        for order in state['posted']:
            alliance = self._merchant_alliance(game, order['world'], order['alliance_id'])
            if order['status'] in {'open', 'working'} and not self._merchant_route_exists(game, alliance, order['source_world']):
                self._merchant_refund(game, order, 'cancelled', '目标界面未设本盟总部，商路已撤销', order['fee'])
        player = game.player
        sealed = player.sealed_cultivation
        if player.world in {'human', 'monster_realm'} and sealed and sealed.get('merchant_passage'):
            # A withdrawn route must not strand a visitor behind its old seal.
            self._cancel_auction_for_world_change(game)
            player.world = 'spirit'
            player.location_id = self._merchant_alliance(game, 'spirit', 'xuanji')['hq']
            hp, mp = player.hp / max(1, max_hp(player)), player.mp / max(1, max_mp(player))
            player.realm_index, player.layer = sealed['realm_index'], sealed['layer']
            player.lifespan = sealed.get('lifespan')
            remaining = sealed.get('tribulation_remaining')
            player.next_tribulation_age = player.age + remaining if remaining is not None else None
            player.sealed_cultivation = None
            player.hp, player.mp = max_hp(player) * hp, max_mp(player) * mp
            player.party = []
            self._clear_market(game)
            self._merchant_notice(game, '旧逆灵通道撤销，商盟已免费护送你返回灵界总部，恢复原有道果。')
        state['version'] = 2
        return True

    @staticmethod
    def _merchant_log(order, age, message):
        order.setdefault('logs', []).append({'age': age, 'message': message})
        order['logs'] = order['logs'][-16:]

    def _merchant_refund(self, game, order, status, reason, fee_refund=0):
        if order['status'] not in {'open', 'working'}:
            return
        order.update(status=status, settled_age=game.player.age, refund_principal=order['principal'], refund_fee=fee_refund)
        add_item(game.player, 'spirit_stone', order['principal'] + fee_refund)
        message = f"委托「{order['name']}」{'失败' if status == 'failed' else '取消'}：{reason}。退还全部本金 {order['principal']:,} 灵石、手续费 {fee_refund:,} 灵石。"
        self._merchant_log(order, game.player.age, message)
        self._merchant_notice(game, message)

    @staticmethod
    def _merchant_failure_chance(stars, worker_realm, required_realm):
        return min(.92, max(.03, .05 + .045 * stars + .10 * (required_realm - worker_realm)))

    def _merchant_start_order(self, game, order, rng):
        workers = [npc for npc in self._all_world_npcs(game)
                   if npc.alive and npc.world == order['source_world'] and npc.id != order.get('target_id')]
        if not workers:
            return  # No cultivator is available; leave the commission posted.
        worker = rng.choice(workers)
        required = max(1, self._merchant_realm_cap(order['source_world']) - 5 + order['stars'])
        required = max(required, int((order.get('spec') or {}).get('material_tier', 0)))
        if order.get('target_id'):
            required = max(required, self._find_npc(game, order['target_id']).realm_index)
        risk = self._merchant_failure_chance(order['stars'], worker.realm_index, required)
        order.update(status='working', started_age=game.player.age, finish_age=game.player.age + order['years'],
                     worker=worker.name, worker_id=worker.id, worker_realm=worker.realm_index,
                     worker_realm_name=REALMS[worker.realm_index].name, failure_chance=risk,
                     will_finish=rng.random() >= risk, progress=0, execution_stage=0)
        order['failure_age'] = game.player.age + max(1, math.ceil(order['years'] * rng.uniform(.35, .9)))
        message = f"{worker.name}（{REALMS[worker.realm_index].name}）接取「{order['name']}」，预计道历第 {order['finish_age']} 年完成；失败风险 {risk:.0%}。"
        self._merchant_log(order, game.player.age, message)
        self._merchant_notice(game, message)

    def _merchant_tick_order(self, game, order):
        worker = self._find_npc(game, order['worker_id']) if order.get('worker_id') else None
        failure_age = order.get('failure_age', order['finish_age'])
        end_age = min(game.player.age, order['finish_age'], order['deadline'])
        if not order.get('will_finish', True):
            end_age = min(end_age, failure_age)
        start = order.get('started_age', order['posted_age'])
        duration = max(1, order['finish_age'] - start)
        order['progress'] = min(.99, max(0, (end_age - start) / duration))
        stages = {
            'supply': ['已抵达产地，核对材料线索', '正在搜集并验收材料', '材料已归集，安排护送回盟'],
            'item': ['已查明遗迹及宝物线索', '正在探索并寻找目标道具', '正在核验所得并准备交付'],
            'formation': ['阵材筹备完毕，开始推演九宫', '正在炼制阵材并校验六维', '阵法成型，正在验阵封存'],
            'weapon': ['原料入坊，开始熔炼', '正在依模锻造并淬炼器身', '成品正在检验与封装'],
            'bounty': ['已确认悬赏目标踪迹', '正在追踪目标并寻找出手机会', '进入追捕收尾阶段'],
            'escort': ['已与雇主会合并规划路线', '正在护送雇主穿越商路', '已进入目的地附近，准备交接'],
            'recruit': ['已发布招募并联系候选修士', '正在核验修为与履历', '正在组织人手前往商盟'],
            'intel': ['已布置情报线索', '正在查访并交叉核验', '正在整理情报并回报商盟'],
        }[order['kind']]
        for index, message in enumerate(stages, 1):
            milestone = start + math.ceil(duration * index / 4)
            if index > order.get('execution_stage', 0) and milestone <= end_age:
                self._merchant_log(order, milestone, message)
                order['execution_stage'] = index
        if order.get('worker_id') and (not worker or not worker.alive):
            self._merchant_refund(game, order, 'failed', '承接修士陨落或失联，执行中止', math.ceil(order['fee'] / 2))
        elif not order.get('will_finish', True) and game.player.age >= failure_age:
            self._merchant_refund(game, order, 'failed', f"{order.get('worker', '承接修士')}回报：执行遭遇阻碍，未能完成委托", math.ceil(order['fee'] / 2))
        elif game.player.age >= order['finish_age'] and order['finish_age'] <= order['deadline']:
            self._merchant_deliver_order(game, order)
            order.update(status='completed', progress=1, settled_age=game.player.age)
            alliance = self._merchant_alliance(game, order['world'], order['alliance_id'])
            alliance['reserves'] += max(1, order['fee'] + order['principal'] // 10)
            message = f"委托「{order['name']}」已完成：{order['delivery']}。"
            self._merchant_log(order, order['finish_age'], message)
            self._merchant_notice(game, message)
        elif game.player.age >= order['deadline']:
            self._merchant_refund(game, order, 'failed', '执行逾期，商盟终止委托', math.ceil(order['fee'] / 2))
