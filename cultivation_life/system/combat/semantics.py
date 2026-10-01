"""Projection between neutral combat state and the finite semantic interpreter."""
import copy
from ...combat_semantics import SemanticRuntime, STATS, RESTRICTIONS


class CombatSemantics:
    def _init_semantics(self):
        rules = {key: s.unit.capabilities.semantic_rules for key, s in self.units.items()
                 if s.unit.capabilities.semantic_rules}
        self.semantics = SemanticRuntime(rules) if rules else None
        self._semantic_mp = {'player': 1., 'enemy': 1.}
        self._semantic_morale_base = {}
        self._semantic_totals = {}
        self._semantic_first = {}
        self._semantic_ended = False
        self._semantic_environment = {}

    def semantic_environment(self, natural, artificial):
        self._semantic_environment = {'environment.terrain': natural,
            'environment.forbidden_flight': '禁空' in artificial,
            'environment.forbidden_sense': '禁神识' in artificial,
            'environment.formation': '大阵' in artificial}

    def semantic_context(self, *, player_mp, enemy_mp, player_morale, enemy_morale):
        self._semantic_mp = {'player': player_mp, 'enemy': enemy_mp}
        self._semantic_morale_base = {side: value + self.frame.morale_loss.get(side, 0.)
                                     for side, value in (('player', player_morale), ('enemy', enemy_morale))}

    def _semantic_snapshot(self, key):
        s = self.units[key]
        c = s.unit.capabilities
        cap = c.capacity if c.usable_capacity is None else c.usable_capacity
        return dict(id=key, side=s.unit.side, rank=s.unit.cultivation_rank, power=s.unit.power,
            state=s.vitality, body=s.body,
            morale=max(0., min(100., self._semantic_morale_base[s.unit.side] - self.frame.morale_loss.get(s.unit.side, 0.)))
            if s.unit.side in self._semantic_morale_base else s.morale, energy=s.current, capacity=cap,
            energy_ratio=s.current / cap if cap else 0., mp_ratio=self._semantic_mp[s.unit.side],
            pressure=s.pressure, strain=s.field_strain, seal_progress=s.seal_progress,
            sustained_rounds=s.sustained_rounds, active_field=s.active_voisinage is not None,
            field_id=s.active_voisinage or '', stance=c.stance, fighting=s.fighting,
            suppressed=s.suppressed, escaped=s.escaped, escape_locked=s.escape_locked,
            dominated=key in self._dominated, has_field=bool(c.voisinages), field_sealed=c.sealed,
            force_tier=c.force_tier, ward_tier=c.ward_tier, resource_tier=c.resource_tier,
            technique_tier=c.technique_tier, artifact_tier=c.artifact_tier,
            ally_count=sum(v.fighting and v.unit.side == s.unit.side and k != key for k, v in self.units.items()),
            enemy_count=sum(v.fighting and v.unit.side != s.unit.side for v in self.units.values()),
            **{f'restricted_{name}': name in s.restrictions for name in RESTRICTIONS},
            **{f'{source}_{direction}': self._semantic_totals.get((key, source, direction), 0.)
               for source in ('ordinary', 'field', 'pressure') for direction in ('dealt', 'received')})

    def _semantic_preview(self, key, phase, target=None, role='self', **event):
        if self.semantics is None:
            return None
        facts = {f'self.{k}': v for k, v in self._semantic_snapshot(key).items()}
        if target in self.units:
            facts.update({f'target.{k}': v for k, v in self._semantic_snapshot(target).items()})
            if min(self.units[key].unit.cultivation_rank, self.units[target].unit.cultivation_rank) >= 0:
                facts['rank_delta'] = self.units[key].unit.cultivation_rank - self.units[target].unit.cultivation_rank
        facts['role'] = role
        facts.update(self._semantic_environment)
        if key in self._semantic_first:
            facts['event.first'] = self._semantic_first[key]
        facts.update({f'event.{k}': v for k, v in event.items()})
        return self.semantics.preview(key, target, phase, facts)

    @staticmethod
    def _semantic_factor(evaluation, channel):
        return evaluation.factor(channel) if evaluation else 1.

    def _semantic_commit(self, evaluation, channels=()):
        if evaluation is None:
            return
        adjustments = self.semantics.commit(evaluation, channels=channels)
        for key, stat, value in adjustments:
            s = self.units[key]
            if not s.fighting:
                continue
            if stat == 'state':
                if value >= 0:
                    self._restore_state(key, value)
                else:
                    self._lose(key, -value, physical=False)
            elif stat == 'body':
                old = s.body
                s.body = max(0., min(1., old + value))
                if key == 'player':
                    if value >= 0:
                        self.frame.primary_restore += s.body - old
                    else:
                        self.frame.primary_loss += (old - s.body) / .46
            elif stat == 'morale':
                old = self._semantic_snapshot(key)['morale']
                s.morale = max(0., min(100., old + value))
                side = s.unit.side
                self.frame.morale_loss[side] = self.frame.morale_loss.get(side, 0.) + (old - s.morale) * s.unit.power / self.totals[side]
            else:
                attr = 'field_strain' if stat == 'strain' else stat
                limit = .85 if stat == 'pressure' else .5 if stat == 'strain' else 1.
                setattr(s, attr, max(0., min(limit, getattr(s, attr) + value)))
        for row in self.semantics.log:
            if row['token'] != evaluation.token:
                continue
            self.frame.events.append(f"{self.units[row['actor']].unit.name}触发战斗规则【{row['source']}/{row['rule']}】（{row['trigger']}）。")

    def _semantic_event(self, key, phase, target=None, role='self', **event):
        ev = self._semantic_preview(key, phase, target, role, **event)
        self._semantic_commit(ev)
        return ev

    def _semantic_begin(self, number, player_mp, enemy_mp, player_morale=None, enemy_morale=None):
        if self.semantics is None:
            return
        self.semantics.begin_round(number)
        self._semantic_mp = {'player': player_mp, 'enemy': enemy_mp}
        self._semantic_morale_base = {side: value for side, value in (('player', player_morale), ('enemy', enemy_morale)) if value is not None}
        self._semantic_totals = {}
        self._semantic_first = {}
        self._semantic_ended = False
        # All peers see the same boundary snapshot, independent of actor order.
        plans = [self._semantic_preview(k, 'round_start') for k, s in self.units.items() if s.fighting]
        for plan in plans:
            self._semantic_commit(plan)

    def semantic_ordinary_start(self):
        """Called after field control, before ordinary initiative and stat use."""
        factors = {side: {stat: 1. for stat in STATS} for side in ('player', 'enemy')}
        if self.semantics is None:
            return factors
        plans = [(key, self._semantic_preview(key, 'ordinary_start')) for key in self.units
                 if self._available(key) and self._has_ordinary(self.units[key].unit.side)]
        for key, plan in plans:
            s = self.units[key]
            for stat in STATS:
                factors[s.unit.side][stat] += (plan.factor(f'ordinary.{stat}') - 1) * s.unit.power / self.totals[s.unit.side]
            self._semantic_commit(plan, {f'ordinary.{stat}' for stat in STATS})
        return factors

    def semantic_initiative(self, player_first):
        factors = {side: {stat: 1. for stat in STATS} for side in ('player', 'enemy')}
        if self.semantics is None:
            return factors
        for key, s in self.units.items():
            if self._available(key) and self._has_ordinary(s.unit.side):
                self._semantic_first[key] = player_first if s.unit.side == 'player' else not player_first
        plans = [(key, self._semantic_preview(key, 'initiative_resolved')) for key in self._semantic_first]
        for key, plan in plans:
            s = self.units[key]
            for stat in STATS:
                factors[s.unit.side][stat] += (plan.factor(f'ordinary.{stat}') - 1) * s.unit.power / self.totals[s.unit.side]
            self._semantic_commit(plan, {f'ordinary.{stat}' for stat in STATS})
        return factors

    def _semantic_record_loss(self, source, target, amount, kind):
        if self.semantics is None:
            return
        for actor, direction in ((source, 'dealt'), (target, 'received')):
            key = (actor, kind, direction)
            self._semantic_totals[key] = self._semantic_totals.get(key, 0.) + amount

    def _semantic_end(self):
        if self.semantics is None or self._semantic_ended:
            return
        plans = [self._semantic_preview(k, 'round_end') for k, s in self.units.items() if s.fighting]
        for plan in plans:
            self._semantic_commit(plan)
        self.semantics.finish_round({k: self._semantic_snapshot(k) for k in self.units})
        self._semantic_ended = True

    def semantic_report(self):
        if self.semantics is None:
            return {}
        return {'events': list(self.semantics.log), 'statuses': copy.deepcopy(list(self.semantics.statuses.values())),
                'counters': dict(self.semantics.counters)}
