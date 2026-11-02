"""Event-time body effects. Only the battle ledger and caller's RNG are used.

Paths belong to branches, not rounds. Siblings may invoke the same mechanism;
an ancestor (actor ID, mechanism ID) cannot be invoked again on that branch.
The queue is drained at settlement boundaries, never by recursive dispatch.
"""
from collections import deque
from dataclasses import replace
from types import SimpleNamespace

from .body_mechanisms import ActionAllowance
from .contracts import VoisinageEffect


class BodyEvents:
    def _init_body_events(self):
        self._body_queue=deque();self._body_chain=();self._draining_body=False
        self._death_exempt=frozenset()

    def _energy(self,key,value,chain=None):
        state=self.units[key];before=state.current
        state.current=max(0.,min(self._usable_energy(state),value))
        loss=max(0.,before-state.current)
        if not loss or self._body_round is None:return
        # Credit survives replenishment. Crossings consumed while muted do not
        # become delayed attacks when silence expires.
        capacity=self._usable_energy(state)
        threshold=next((r.effects.get('karma_threshold',0) for r in
            state.unit.capabilities.body_mechanisms if r.effects.get('karma_threshold')),0)
        if capacity<=0 or not threshold:return
        state.karma_spent+=loss/capacity
        count=int((state.karma_spent+1e-12)/threshold)
        state.karma_spent=max(0.,state.karma_spent-count*threshold)
        entry=self._body_round.channel(key,'karma_threshold',self._body_chain if chain is None else chain)
        if not count or entry is None or not state.fighting:return
        row,path=entry
        for _ in range(count):
            self._body_queue.append(('attack',dict(owner=key,scope='all',targets=(),power=row['effects'].get('karma_power',.12),
                chain=path,label=row['name'],extra=True)))
        self._light_note('karma',key,f'{state.unit.name}累计实际元力消耗越过{count}次阈值（每次{threshold:.0%}），因果各释放一次免费全体攻击；余量{state.karma_spent:.2%}。',
                         count=count,threshold=threshold,remainder=state.karma_spent,chain=list(path))

    def _body_death(self,key):
        state=self.units[key]
        if key in self._death_exempt:return
        if not state.death_observed and (state.vitality<=0 or state.body<=0):
            state.death_observed=True
            self._body_queue.append(('death',dict(target=key,chain=self._body_chain)))

    def _death_response(self,event):
        for key in sorted(self.units):
            state=self.units[key]
            entry=self._body_round.channel(key,'death_restore',event['chain'])
            if not entry or not state.fighting:continue
            row,path=entry;ratio=row['effects']['death_restore']
            before,old=state.vitality,state.current
            self._body_chain=path
            self._restore_state(key,ratio)
            self._energy(key,state.current+self._usable_energy(state)*ratio)
            self._light_note('death_restore',key,
                f'{state.unit.name}以御魂响应{self.units[event["target"]].unit.name}真实阵亡，回复态势{state.vitality-before:.2%}、元力{state.current-old:g}。',
                target=event['target'],state=state.vitality-before,energy=state.current-old)

    def _attack_targets(self,event):
        source=self.units[event['owner']]
        candidates=sorted(self.units) if event['scope']=='all' else event['targets']
        return tuple(k for k in candidates if k in self.units and self._body_attackable(k)
            and self.units[k].unit.side!=source.unit.side and self._can_reach(source,k))

    def _body_attackable(self,key):
        state=self.units[key]
        return state.vitality>0 and state.body>0 and not state.escaped

    def _queue_forget(self,owner,targets,losses,chain):
        state=self.units[owner]
        entry=self._body_round.channel(owner,'forget',chain)
        descriptor=next((r for r in state.unit.capabilities.body_mechanisms if r.effects.get('forget')),None)
        if not descriptor or (owner,descriptor.id) in chain or not targets:return
        current=tuple(sorted(set(targets)));previous=state.last_attack_targets
        state.last_attack_targets=current
        if not entry or previous is None or not any(losses.values()):return
        row,path=entry;ratio=row['effects']['forget'];same=tuple(previous)==current
        if same:
            keys=current;power={k:losses.get(k,0)*ratio for k in keys}
        else:
            keys=tuple(k for k in sorted(self.units) if k not in current and self._body_attackable(k)
                and self.units[k].unit.side!=state.unit.side and self._can_reach(state,k))
            power={k:sum(losses.values())*ratio for k in keys}
        self._light_note('forget',owner,
            f'{state.unit.name}忘情比较实际目标集合：'+('相同，追加一段伤害。' if same else '不同，向其余合法敌人溢出伤害。' if keys else '不同，但没有其余合法敌人，不溢出。'),
            previous=list(previous),targets=list(current),same=same,spill_targets=list(keys),chain=list(path))
        if keys:
            self._body_queue.append(('attack',dict(owner=owner,scope='fixed',targets=keys,power=power,
                chain=path,label=row['name'],extra=False)))

    def _split_entry(self,owner,chain):
        return self._body_round.channel(owner,'split',chain)

    def _body_recovery(self,key,amount):
        if self._body_round is None:return amount
        entry=self._body_round.channel(key,'recovery_bonus',self._body_chain)
        if not entry:return amount
        bonus=entry[0]['effects']['recovery_bonus']
        if bonus and amount>0:
            self._light_note('recovery_bonus',key,f'{self.units[key].unit.name}以无相提高本次态势或邻域回复效率{bonus:.0%}。',bonus=bonus)
        return amount*(1+bonus)

    def _drain_body_events(self):
        if self._draining_body or self._body_round is None:return
        from .effects import EffectIntent
        self._draining_body=True;old=self._body_chain
        try:
            while self._body_queue:
                kind,event=self._body_queue.popleft();self._body_chain=event['chain']
                if kind=='death':
                    self._death_response(event);continue
                if kind=='complete':
                    group=event['group']
                    if group['started']:
                        self._complete_body_actions([(event['owner'],group['token'],group['critical_hit'])])
                    continue
                owner=event['owner'];state=self.units[owner]
                if not state.fighting:continue
                if kind=='attack':
                    group=None
                    critical=self._body_round.channel(owner,'critical',event['chain']) if event['extra'] else None
                    if critical:event=dict(event,chain=critical[1])
                    split=self._split_entry(owner,event['chain'])
                    path=split[1] if split else event['chain']
                    if event['extra']:
                        group=dict(started=False,critical_hit=False,
                            token=ActionAllowance(source=event['label'],free=True,chain=path))
                        self._body_queue.appendleft(('complete',dict(event,group=group)))
                    if split:
                        row,path=split
                        self._light_note('split',owner,f'{state.unit.name}的{event["label"]}经照业化为三段'+('全体攻击。' if event['scope']=='all' else '攻击。'),segments=3,scope=event['scope'])
                        for index in reversed(range(3)):
                            self._body_queue.appendleft(('segment',dict(event,chain=path,scale=row['effects']['split'],group=group,critical=bool(critical))))
                    else:self._body_queue.appendleft(('segment',dict(event,scale=1.,group=group,critical=bool(critical))))
                    continue
                targets=self._attack_targets(event)
                if not targets:continue
                # Derived children settle before the next sibling segment.
                tail=self._body_queue;self._body_queue=deque()
                token=ActionAllowance(source=event['label'],free=True,chain=event['chain'])
                definition=SimpleNamespace(name=event['label'],authority=None,features=(),authority_reference=1.)
                field=SimpleNamespace(owner=owner,definition=definition,strength=0.,authority=None)
                losses={}
                for key in targets:
                    value=event['power'].get(key,0) if isinstance(event['power'],dict) else event['power']
                    if value<=0 or self.ward_tier(key,damage=True)>2:continue
                    before=self.units[key].vitality
                    multiplier=self._body_round.value(owner,'critical') if event['critical'] else 1.
                    intent=EffectIntent(field,VoisinageEffect('strike',0,min(1.,value*multiplier)*event['scale'],tier=2),targets,
                        allowance=token,direct_power=True)
                    if self._intervene(intent,key,self._responded):continue
                    applied=self._apply_effect(intent,key)
                    if event['group'] is not None:
                        event['group']['started']=True
                        event['group']['critical_hit']|=bool(applied and event['critical'])
                    losses[key]=max(0.,before-self.units[key].vitality)
                self._queue_forget(owner,targets,losses,event['chain'])
                self._light_note('body_attack',owner,f'{state.unit.name}的{event["label"]}完成一段攻击，锁定{len(targets)}个目标，实际削弱态势合计{sum(losses.values()):.2%}。',targets=list(targets),losses=losses)
                self._body_queue.extend(tail)
        finally:
            self._body_chain=old;self._draining_body=False
            self._refresh_relations()

    def _perform_body_intent(self,intent,keys):
        """One paid action, independent segments; history is one set per segment."""
        owner=intent.field.owner;chain=intent.allowance.chain
        critical=self._body_round.channel(owner,'critical',chain) if intent.critical else None
        if critical:chain=critical[1]
        split=None if intent.ordinary or intent.terminal else self._split_entry(owner,chain)
        count=3 if split else 1;scale=split[0]['effects']['split'] if split else 1.
        if split:
            chain=split[1]
            self._light_note('split',owner,f'{self.units[owner].unit.name}以照业将一次施权拆为三段，每段继承{scale:.0%}，只计一次行动与费用。',segments=3,scale=scale)
        applied=False;old=self._body_chain
        try:
            for index in range(count):
                if index and (not self.units[owner].fighting or owner in self._disrupted):break
                candidates=keys if not index else intent.targets
                valid=tuple(k for k in candidates if (self._body_attackable(k) if intent.effect.target=='enemy' else self.units[k].fighting))
                if index and intent.effect.target=='enemy':
                    valid=tuple(k for k in valid if self._can_reach(self.units[owner],k) and
                        (k==intent.allowance.target if intent.allowance.requires_evade else self._covered_by(intent.field,k)))
                # A field whose coverage contains several targets remains an AoE;
                # an explicitly single-target field chooses one live target per segment.
                if index and intent.effect.target!='self' and intent.effect.target_mode=='single' and valid:
                    choice=min(len(valid)-1,int(self._light_rng.random()*len(valid))) if split else 0
                    valid=(valid[choice],)
                token=replace(intent.allowance,chain=chain)
                segment=replace(intent,allowance=token,segment_scale=scale)
                if index:valid=tuple(k for k in valid if not self._intervene(segment,k,self._responded))
                losses={};self._body_chain=chain
                for key in valid:
                    before=self.units[key].vitality
                    applied=bool(self._apply_effect(segment,key)) or applied
                    losses[key]=max(0.,before-self.units[key].vitality)
                if intent.effect.kind=='strike':self._queue_forget(owner,valid,losses,chain)
                self._drain_body_events()
        finally:self._body_chain=old
        return applied,chain
