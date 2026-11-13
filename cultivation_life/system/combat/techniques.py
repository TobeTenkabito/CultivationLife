"""Paid, bounded manual effects over the battle's existing original resources.

No registry lookups or RNG in combat. This component owns only effect receipts,
cooldowns and pending packets; UnitState.current remains the resource authority.
"""
from __future__ import annotations

import copy
import json

from ...technique_effect_schema import finite, integer


class TechniqueRuntime:
    def __init__(self, battle):
        self.battle = battle
        self.books = {}
        self.records = {}
        self.round = 0
        self.started = 0
        self.hits = {}
        self.hurts = {}
        self.first_exchanges = {}
        self.events = []
        for owner, state in battle.units.items():
            for book in state.unit.capabilities.technique_effects:
                if book['effect']['version'] == 3:
                    continue
                key = json.dumps([owner, book['id']], ensure_ascii=False, separators=(',', ':'))
                self.books[key] = (owner, book)
                self.records[key] = dict(used=0, last_cast=0, paid=0., refunded=0., receipts={}, packets=[])
        self.capacities = {key: self._capacity(s) for key, s in battle.units.items()}
        self.initial_state = {key: s.vitality for key, s in battle.units.items()}

    @staticmethod
    def _capacity(state):
        c = state.unit.capabilities
        return c.capacity if c.usable_capacity is None else c.usable_capacity

    def _usable(self, owner):
        s = self.battle.units[owner]
        return (self.battle._available(owner) and 'technique' not in s.restrictions
                and not self.battle._action_paused(owner)
                and self.battle._has_ordinary(s.unit.side))

    def begin(self, number):
        integer(number, 1, 1000000000, '战斗轮次')
        if number <= self.round:
            raise ValueError('功法效果轮次不能倒退或重复')
        self.round = number
        self.events = []
        for record in self.records.values():
            record['packets'] = [p for p in record['packets'] if p['expires'] >= number and p['remaining'] > 0]

    def note(self, owner, book, event, **data):
        row = dict(round=self.round, owner=owner, technique=book['id'], event=event, **data)
        self.events.append(row)
        self.events = self.events[-128:]

    def start(self, factors):
        if self.started == self.round:
            return
        self.started = self.round
        for owner in self.battle.units:
            if self._usable(owner):
                self.first_exchanges.setdefault(owner, self.round)
        # Freeze trigger facts before any book heals its owner or pays a cost.
        triggers = {key: self._trigger(owner, book['effect']['trigger'])
                    for key, (owner, book) in self.books.items()}
        for key in sorted(self.books):
            owner, book = self.books[key]
            if not self._usable(owner):
                continue
            state = self.battle.units[owner]
            effect, record = book['effect'], self.records[key]
            capacity = self.capacities[owner]
            triggered = triggers[key]
            eligible = bool(capacity > 0 and state.unit.capabilities.resource_tier >= 2 and triggered)
            if effect['kind'] == 'recover' and state.vitality >= self.initial_state[owner]:
                eligible = False
            if effect['kind'] in {'strike', 'breach'}:
                tier = self.battle.attack_tier(state)
                eligible = eligible and any(s.unit.side != state.unit.side and s.fighting
                    and self.battle._can_reach(state, target) and tier >= self.battle.ward_tier(target)
                    for target, s in self.battle.units.items())
            cooldown_done = not record['used'] or self.round > record['last_cast'] + effect['cooldown']
            pending = any(p['remaining'] > 0 for p in record['packets'])
            if eligible and not pending and record['used'] < effect['uses'] and cooldown_done:
                record['packets'] = []
                from ...combat_costs import technique_cost
                cost = technique_cost(book,capacity)
                if state.current + 1e-12 >= cost:
                    before = state.current
                    self.battle._energy(owner, state.current - cost)
                    paid = before - state.current
                    record['used'] += 1
                    record['last_cast'] = self.round
                    record['paid'] += paid
                    receipt = str(record['used'])
                    record['receipts'][receipt] = dict(paid=paid, refunded=0.)
                    delay = int(effect['delivery'] == 'delayed')
                    pieces = (0.5, 0.5) if effect['delivery'] == 'split' else (1.,)
                    for index, share in enumerate(pieces):
                        starts = self.round + delay + index
                        record['packets'].append(dict(starts=starts, expires=starts + effect['duration'] - 1,
                            remaining=effect['strength_bp'] / 10000 * share, receipt=receipt))
                    self.note(owner, book, 'paid', amount=paid)
                    self.battle.frame.events.append(f"{state.unit.name}运转《{book['name']}》，实付元力 {paid:.2f}。")
            for packet in record['packets']:
                if not packet['starts'] <= self.round <= packet['expires'] or packet['remaining'] <= 0:
                    continue
                if effect['kind'] == 'recover':
                    requested = min(packet['remaining'], max(0., self.initial_state[owner] - state.vitality))
                    before = state.vitality
                    self.battle._restore_state(owner, requested, maximum_gain=requested)
                    actual = max(0., state.vitality - before)
                    packet['remaining'] = 0.
                    if actual:
                        self.note(owner, book, 'restored', amount=actual, receipt=packet['receipt'])
                        self.battle.frame.events.append(f"《{book['name']}》恢复 {actual:.2%} 战斗态势。")
                elif effect['kind'] == 'breach':
                    gain = packet['remaining']
                    factors[state.unit.side]['breach'] += gain * state.unit.power / self.battle.totals[state.unit.side]
                    packet['remaining'] = 0.
                    self.note(owner, book, 'breach', amount=gain, receipt=packet['receipt'])

    def _trigger(self, owner, trigger):
        state = self.battle.units[owner]
        if trigger == 'opening':
            return True
        if trigger == 'after_hit':
            return self.hits.get(owner) == self.round - 1
        if trigger == 'after_hurt':
            return self.hurts.get(owner) == self.round - 1
        if trigger == 'first_exchange':
            return self.first_exchanges.get(owner) == self.round
        if trigger == 'low_state':
            return state.vitality <= self.initial_state[owner] * .5
        if trigger == 'steady':
            return self.round >= 3 and self.hurts.get(owner) != self.round - 1
        if trigger in {'odd_round', 'even_round'}:
            return self.round % 2 == int(trigger == 'odd_round')
        if trigger == 'target_wounded':
            tier = self.battle.attack_tier(state)
            return any(s.unit.side != state.unit.side and s.fighting
                       and s.vitality <= self.initial_state[key] * .5
                       and self.battle._can_reach(state, key) and tier >= self.battle.ward_tier(key)
                       for key, s in self.battle.units.items())
        raise ValueError('未知功法效果触发')

    def damage(self, source, target, amount):
        """Called only after tier/reach checks. Packets never dispatch new hits."""
        if amount <= 0:
            return amount
        original = amount
        for key in sorted(self.books):
            owner, book = self.books[key]
            if owner != source or book['effect']['kind'] != 'strike' or not self._usable(owner):
                continue
            for packet in self.records[key]['packets']:
                if packet['starts'] <= self.round <= packet['expires'] and packet['remaining'] > 0:
                    gain = original * packet['remaining']
                    packet['remaining'] = 0.
                    amount += gain  # Every book uses the same original input, never another book's output.
                    self.note(owner, book, 'strike', target=target, amount=gain, receipt=packet['receipt'])
        return amount

    def absorb(self, target, amount):
        """Spend shield balances after aggregated damage caps, before actual loss."""
        for key in sorted(self.books):
            owner, book = self.books[key]
            if owner != target or book['effect']['kind'] not in {'guard', 'frugal'} or not self._usable(owner):
                continue
            record = self.records[key]
            for packet in record['packets']:
                if not packet['starts'] <= self.round <= packet['expires'] or packet['remaining'] <= 0:
                    continue
                prevented = min(amount, packet['remaining'])
                if prevented <= 0:
                    continue
                vitality = max(0., self.battle.units[target].vitality)
                actual_prevention = max(0., min(vitality, amount) - min(vitality, amount - prevented))
                packet['remaining'] -= prevented
                amount -= prevented
                self.note(owner, book, 'absorbed', amount=actual_prevention, spent=prevented, receipt=packet['receipt'])
                if book['effect']['kind'] == 'frugal' and actual_prevention > 0:
                    receipt = record['receipts'][packet['receipt']]
                    allowance = max(0., receipt['paid'] * book['effect']['refund_bp'] / 10000 - receipt['refunded'])
                    allowance = min(allowance, max(0., self.capacities[owner] * .02 - record['refunded']))
                    state = self.battle.units[owner]
                    before = state.current
                    self.battle._energy(owner, state.current + allowance)
                    refunded = max(0., state.current - before)
                    receipt['refunded'] += refunded
                    record['refunded'] += refunded
                    if refunded:
                        self.note(owner, book, 'refunded', amount=refunded)
        return amount

    def observed(self, source, target, actual):
        if actual > 0:
            self.hits[source] = self.round
            self.hurts[target] = self.round

    def dump(self):
        return copy.deepcopy(dict(version=2, round=self.round, started=self.started, first_exchanges=self.first_exchanges,
            records=self.records, hits=self.hits, hurts=self.hurts,
            capacities=self.capacities, initial_state=self.initial_state))

    def restore(self, value):
        fields = {'version', 'round', 'started', 'records', 'hits', 'hurts', 'capacities', 'initial_state'}
        if not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] not in (1, 2):
            raise ValueError('功法效果续战结构无效')
        if value['version'] == 2:
            fields.add('first_exchanges')
        elif any(book['effect']['version'] == 2 for _, book in self.books.values()):
            raise ValueError('新传承效果缺失首次交锋记录')
        if set(value) != fields:
            raise ValueError('功法效果续战字段无效')
        value = copy.deepcopy(value)
        # V1 had no first-exchange-sensitive recipes. A neutral historical anchor
        # keeps later V2 snapshots resumable without changing any V1 trigger.
        value.setdefault('first_exchanges', {owner: 1 for owner in self.battle.units}
                         if value['started'] else {})
        integer(value['round'], 0, 1000000000, '续战轮次')
        integer(value['started'], 0, value['round'], '已开始轮次')
        for field, baseline in (('capacities', self.capacities), ('initial_state', self.initial_state)):
            if not isinstance(value[field], dict) or set(value[field]) != set(baseline):
                raise ValueError('功法效果初始基准归属无效')
            for owner, number in value[field].items():
                finite(number, baseline[owner], baseline[owner], '初始基准')
        if value['capacities'] != self.capacities or value['initial_state'] != self.initial_state:
            raise ValueError('功法效果初始基准不可改写')
        if not isinstance(value['records'], dict) or set(value['records']) != set(self.records):
            raise ValueError('功法效果续战来源不一致')
        for key, r in value['records'].items():
            if not isinstance(r, dict) or set(r) != {'used', 'last_cast', 'paid', 'refunded', 'receipts', 'packets'}:
                raise ValueError('功法效果收据结构无效')
            owner, book = self.books[key]
            effect, capacity = book['effect'], self.capacities[owner]
            integer(r['used'], 0, effect['uses'], '施展次数')
            integer(r['last_cast'], 0, value['round'], '上次施展')
            if bool(r['used']) != bool(r['last_cast']):
                raise ValueError('功法效果次数与施展轮次不符')
            from ...combat_costs import technique_cost
            expected_cost = technique_cost(book,capacity)
            # Subtracting two large legitimate balances loses a few low bits.
            # Scale only the rounding tolerance; never waive a paid receipt.
            tolerance = max(1e-8, expected_cost * 1e-12)
            total_tolerance = tolerance * max(1, r['used'])
            finite(r['paid'], 0, expected_cost * r['used'] + total_tolerance, '已付费用')
            finite(r['refunded'], 0, min(r['paid'] * effect['refund_bp'] / 10000, capacity * .02) + total_tolerance, '返还费用')
            if not isinstance(r['receipts'], dict) or set(r['receipts']) != {str(i) for i in range(1, r['used'] + 1)}:
                raise ValueError('功法效果付款回执缺失')
            for receipt in r['receipts'].values():
                if not isinstance(receipt, dict) or set(receipt) != {'paid', 'refunded'}:
                    raise ValueError('功法效果付款回执字段无效')
                finite(receipt['paid'], max(0., expected_cost - tolerance), expected_cost + tolerance, '单次付款')
                finite(receipt['refunded'], 0, receipt['paid'] * effect['refund_bp'] / 10000 + tolerance, '单次返还')
            if abs(sum(x['paid'] for x in r['receipts'].values()) - r['paid']) > total_tolerance or abs(sum(x['refunded'] for x in r['receipts'].values()) - r['refunded']) > total_tolerance:
                raise ValueError('功法效果付款与总账不符')
            if not isinstance(r['packets'], list) or len(r['packets']) > 2:
                raise ValueError('功法效果分包数量无效')
            seen_starts = set()
            first_start = r['last_cast'] + int(effect['delivery'] == 'delayed')
            valid_starts = {first_start, first_start + 1} if effect['delivery'] == 'split' else {first_start}
            for p in r['packets']:
                if (not isinstance(p, dict) or set(p) != {'starts', 'expires', 'remaining', 'receipt'}
                        or not isinstance(p['receipt'], str) or p['receipt'] not in r['receipts']
                        or p['receipt'] != str(r['used'])):
                    raise ValueError('功法效果分包回执无效')
                integer(p['starts'], 1, value['round'] + 1, '分包起始')
                if p['starts'] not in valid_starts or p['starts'] in seen_starts:
                    raise ValueError('功法效果分包重复或起始时间与施展不符')
                seen_starts.add(p['starts'])
                end = p['starts'] + effect['duration'] - 1
                integer(p['expires'], end, end, '分包结束')
                share = .5 if effect['delivery'] == 'split' else 1.
                finite(p['remaining'], 0, effect['strength_bp'] / 10000 * share, '剩余额度')
            if sum(p['remaining'] for p in r['packets']) > effect['strength_bp'] / 10000 + 1e-12:
                raise ValueError('功法效果分包超过一份预算')
        for field in ('hits', 'hurts', 'first_exchanges'):
            if not isinstance(value[field], dict) or set(value[field]) - set(self.battle.units):
                raise ValueError('功法效果损耗记录归属无效')
            for number in value[field].values():
                integer(number, 1, value['round'], '损耗记录轮次')
        if value['version'] == 2:
            for key, r in value['records'].items():
                owner, book = self.books[key]
                first = value['first_exchanges'].get(owner)
                if r['used'] and (first is None or first > r['last_cast']):
                    raise ValueError('付款缺失原人物首次交锋记录')
                if book['effect']['trigger'] == 'first_exchange' and r['used'] and (r['used'] != 1 or r['last_cast'] != first):
                    raise ValueError('首次交锋不能重复发动')
        for name in ('round', 'started', 'records', 'hits', 'hurts', 'first_exchanges'):
            setattr(self, name, copy.deepcopy(value[name]))

    def report(self):
        return dict(events=copy.deepcopy(self.events), receipts={k: dict(used=r['used'], paid=r['paid'],
            refunded=r['refunded']) for k, r in self.records.items() if r['used']})
