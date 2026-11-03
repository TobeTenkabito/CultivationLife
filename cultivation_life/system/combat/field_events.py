"""Actual field outcomes feed finite, actor-scoped causal mechanisms."""
from .body_mechanisms import ActionAllowance


class FieldEvents:
    def _field_record(self,source,kind,restriction=None):
        for key in self._unit_order():
            d=self._discipline(key)
            if not d or d.kind!='echo' or key==source or self.units[key].unit.side==self.units[source].unit.side:
                continue
            if not self._can_reach(self.units[key],source) or self._field_path(key,'listen',self._body_chain) is None:continue
            m=self._field_memory(key)
            m['echo']=dict(kind=kind,restriction=restriction,source=source);m['record_round']=self.frame.round_no
            self._field_note(key,d.names[0],f'听取{self.units[source].unit.name}实际生效的{self._field_effect_name(kind)}；只存功能类别，按自身领域威能反调。',
                source=source,effect=kind,restriction=restriction)

    def _field_after_effect(self,intent,key,before,power):
        state=self.units[key];owner=intent.field.owner
        body_gain=max(0.,state.body-before['body']);state_gain=max(0.,state.vitality-before['state'])
        loss=max(0.,before['state']-state.vitality)
        changed=(state.body!=before['body'] or state_gain>0 or loss>0 or state.pressure!=before['pressure'] or
            state.morale!=before['morale'] or state.field_strain!=before['strain'] or
            state.seal_progress!=before['seal'] or tuple(state.restrictions)!=before['restrictions'])
        if not changed:return
        self._field_record(owner,intent.effect.kind,intent.effect.restriction)
        if body_gain:self._field_healed(key,body_gain)
        d=self._discipline(owner)
        if not d:return
        m=self._field_memory(owner);p=d.parameters;action=intent.discipline_action
        chain=intent.allowance.chain if intent.allowance else self._body_chain
        if d.kind=='restoration_charge' and intent.effect.kind=='restore_body' and max(body_gain,state_gain)>0:
            if self._field_path(owner,'charge',chain) is not None:
                old=m['charge'];m['charge']=min(p['capacity'],old+max(body_gain,state_gain)*p['gain'])
                self._field_note(owner,d.names[0],f'按本段真实恢复积累天威{m["charge"]-old:.2%}，现有{m["charge"]:.2%}；肉身与态势不重复计入。',
                    target=key,gain=m['charge']-old,charge=m['charge'])
        elif d.kind=='pressure_bond' and action=='bond' and loss>0 and self._field_path(owner,'pressure',chain) is not None:
            old=state.pressure;state.pressure=min(.85,state.pressure+p['pressure']*intent.segment_scale*(2 if intent.critical else 1))
            if d.level>=4:
                state.field_debts[owner]=dict(ratio=p['surcharge'],expires=self.frame.round_no+p['lifetime'])
            self._field_note(owner,d.names[0],f'镇压实际命中，令{state.unit.name}承压{old:.2%}→{state.pressure:.2%}'+('，下一次付费施权受索元束缚。' if d.level>=4 else '。'),target=key,pressure=state.pressure-old)
        elif d.kind=='interdict' and action=='imprint' and self._field_path(owner,'imprint_gain',chain) is not None:
            count=min(8,m['marks'].get(key,{}).get('count',0)+p['imprint'])
            m['marks'][key]=dict(count=count,expires=self.frame.round_no+p['lifetime'])
            self._field_note(owner,d.names[0],f'封锁实际命中，在{state.unit.name}留下禁印，现有{count}枚。',target=key,count=count)
        elif d.kind=='field_breaker' and action=='strain' and (loss>0 or state.body<before['body']) and state.active_voisinage:
            if self._field_path(owner,'strain_gain',chain) is not None:
                old=state.field_strain
                cap=p['strain']*(2 if intent.critical else 1)*intent.segment_scale
                converted=min(cap,power*p['fraction']/max(.01,1-p['fraction']))
                state.field_strain=min(.5,old+converted*(1+self._body_round.amplification(owner,key)))
                self._field_note(owner,d.names[0],f'将部分杀伤换成{state.unit.name}邻域稳固损耗{state.field_strain-old:.2%}；达到门槛才可另付行动断域。',target=key,strain=state.field_strain-old)
        elif d.kind=='melody' and action=='melody' and m['melody_round']!=self.frame.round_no:
            tune=intent.discipline_data['tune'];m['melody_round']=self.frame.round_no
            m['notes']|=1<<tune;m['melody']=(tune+1)%3
            if d.level>=7 and m['notes']==7:
                m['chorus']=1;m['notes']=0
                self._field_note(owner,d.names[2],'已真实完成三个不同曲位，取得下一次同效果群奏资格；不增加行动。')
            else:self._field_note(owner,d.names[0],f'本轮曲位实际生效，下轮转至第{m["melody"]+1}曲；同轮追加不再推进。',tune=tune)

    def _field_action_completed(self,intent,chain):
        key=intent.field.owner;d=self._discipline(key)
        if not d or self._action_paused(key):return
        if d.kind=='blood' and d.level>=4 and (intent.discipline_data or {}).get('blood_paid'):
            m=self._field_memory(key);path=self._field_path(key,'six_arms',chain)
            if m['blood_round']!=self.frame.round_no and path is not None:
                m['blood_round']=self.frame.round_no
                rows=self._body_round.allowances[key]
                rows.append(ActionAllowance(source=f'field:{d.id}:six_arms',chain=path,slot=len(rows)))
                self._field_note(key,d.names[1],'本轮首次实际血祭施权，取得一份额外领域额度；仍须付费，本机制每轮至多一次。')

    def _field_ordinary_hits(self,owner,hits,body_hits=None):
        # State guard can erase attitude loss while the original HP still takes
        # the hit. This remains a real attack for listening and Tianwei.
        if body_hits:
            hits={key:max(hits.get(key,0),body_hits.get(key,0)/.46) for key in sorted(hits.keys()|body_hits.keys())}
        living={k:v for k,v in hits.items() if v>0 and self._body_attackable(k)}
        if any(v>0 for v in hits.values()):self._field_record(owner,'strike')
        d=self._discipline(owner)
        if not d or d.kind!='restoration_charge' or not living or self._action_paused(owner):return
        m=self._field_memory(owner);path=self._field_path(owner,'ordinary_charge',self._body_chain)
        if m['ordinary_round']==self.frame.round_no or m['charge']<=0 or path is None:return
        field=next(f for f in self.fields if f.owner==owner)
        if max(e.tier for e in field.definition.actions())<2:return
        amount=min(d.parameters['ordinary'],m['charge']);m['charge']-=amount;m['ordinary_round']=self.frame.round_no
        total=sum(living.values());power={k:amount*v/total for k,v in living.items()}
        self._body_queue.append(('attack',dict(owner=owner,scope='fixed',targets=tuple(living),power=power,
            chain=path,label=d.names[0],extra=False)))
        self._field_note(owner,d.names[0],f'普通攻击真实命中，消费天威{amount:.2%}转为一段仙伤；不增加普通出手或领域行动。',charge=amount,targets=list(living))

    def _field_death(self,event):
        target=event['target']
        for key in self._unit_order():
            d=self._discipline(key)
            if not d or d.kind!='hunter':continue
            m=self._field_memory(key)
            if m['hunt']!=target:continue
            m['hunt']=None
            path=self._field_path(key,'hunt_restore',event['chain'])
            if d.level>=7 and path is not None:
                state=self.units[key];old=state.current
                self._energy(key,state.current+self._usable_energy(state)*d.parameters['restore'],path)
                self._field_note(key,d.names[2],f'猎物{self.units[target].unit.name}真实阵亡，回复元力{state.current-old:g}；下次正常施权可换猎物，不额外追杀。',target=target,energy=state.current-old)
