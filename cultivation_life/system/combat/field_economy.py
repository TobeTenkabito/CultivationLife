"""Shared field costs, temporary controls and round-local reserved actions."""
from dataclasses import replace
from .body_mechanisms import enter


class FieldEconomy:
    def _init_field_powers(self):
        self._field_reserved={};self._field_waited=set();self._field_tunes={}

    def _begin_field_powers(self):
        self._field_reserved={};self._field_waited=set();self._field_tunes={}
        for key in self._unit_order():
            state=self.units[key]
            state.field_debts={source:row for source,row in state.field_debts.items()
                if row['expires']>=self.frame.round_no and self.units[source].fighting and source not in self._light_muted}
            m=state.field_memory
            if m:
                m['marks']={k:r for k,r in m.get('marks',{}).items() if r['expires']>=self.frame.round_no and self.units[k].fighting}
                m['breaks']={k:r for k,r in m.get('breaks',{}).items() if r>=self.frame.round_no and self.units[k].fighting}
                m['cooldowns']={k:r for k,r in m.get('cooldowns',{}).items() if r>self.frame.round_no}
        self._expire_field_controls()
        for key in self._body_round.order:
            d=self.units[key].unit.capabilities.field_discipline
            if d:
                unlocked=', '.join(n for n,level in zip(d.names,(2,4,7)) if d.level>=level)
                if unlocked:self._field_note(key,d.name,f'本场冻结本命{d.level}级，已解锁{unlocked}；领域权能不计入高阶炼体触发种类。',level=d.level)

    def _expire_field_controls(self,*,live=False,end=False):
        for key in self._unit_order():
            state=self.units[key]
            retained={}
            for restriction,row in state.timed_controls.items():
                source=self.units[row['source']]
                expires=row['expires']<self.frame.round_no or end and row['expires']<=self.frame.round_no
                valid=source.fighting and row['source'] not in self._light_muted
                if live:valid=valid and any(f.owner==row['source'] for f in self.fields)
                if valid and not expires:retained[restriction]=row
                else:self._light_note('field_control_end',key,f'{state.unit.name}的短期{self._field_effect_name(restriction)}禁制解除。',restriction=restriction,source=row['source'])
            state.timed_controls=retained

    def _field_attempted_ordinary(self,keys):
        for key in sorted(keys):
            state=self.units[key]
            for restriction,row in tuple(state.timed_controls.items()):
                if row['attempt']:
                    state.timed_controls.pop(restriction)
                    self._light_note('field_control_end',key,f'{state.unit.name}本次普通行动已受禁制核验，短期{self._field_effect_name(restriction)}限制随尝试结束。',restriction=restriction)

    def _install_field_control(self,intent,key):
        owner=intent.field.owner;d=self._discipline(owner)
        if not d:return
        target=self.units[key];restriction=intent.effect.restriction
        deadline=self.frame.round_no+d.parameters.get('duration',1)
        target.timed_controls[restriction]=dict(source=owner,expires=deadline,attempt=restriction in {'artifact','technique'})
        m=self._field_memory(owner)
        m['cooldowns'][key]=deadline+d.parameters.get('interval',2)+1
        if intent.discipline_action=='break':m['breaks'][key]=deadline
        self._field_note(owner,d.names[2] if restriction=='voisinage' and d.kind=='interdict' else d.names[1],
            f'短封{target.unit.name}的{self._field_effect_name(restriction)}，最迟第{deadline}回合结束解除，不能用额外施权延长；刷新间隔另计。',
            target=key,restriction=restriction,expires=deadline)

    def _field_price(self,key,cost,data):
        state=self.units[key];d=self.units[key].unit.capabilities.field_discipline
        sources=tuple(sorted(source for source,row in state.field_debts.items()
            if row['expires']>=self.frame.round_no and self.units[source].fighting and source not in self._light_muted)) if cost>0 else ()
        tax=cost*sum(state.field_debts[s]['ratio'] for s in sources)
        extra=data.get('switch',0.)
        cost+=extra
        blood=bool(data.get('blood') and cost>0 and d and self._field_path(key,'blood',data.get('chain',())) is not None)
        hp=data.get('extra_body',0.)
        base_hp=hp
        if blood:
            scale=max(1.,next((f.definition.effect_cost for f in self.fields if f.owner==key),24.))
            base_hp+=d.parameters['body_cost']*cost/scale
            hp=base_hp+d.parameters['body_cost']*tax/scale
        return dict(mana=0. if blood else cost+tax,base_mana=0. if blood else cost,
                    body=hp,base_body=base_hp,blood=blood,debt=sources,tax=tax)

    def _field_can_quote(self,key,cost,data):
        price=self._field_price(key,cost,data);s=self.units[key]
        return s.current>=price['base_mana'] and s.body>price['base_body']+1e-9

    def _pay_field_intent(self,intent):
        key=intent.field.owner;state=self.units[key];data=dict(intent.discipline_data or {})
        data['chain']=intent.allowance.chain
        price=self._field_price(key,intent.effect.cost,data)
        d=self._discipline(key)
        m=self._field_memory(key) if d else {}
        if data.get('charge',0)>m.get('charge',0)+1e-9:return None
        if data.get('pressure') and data['pressure']>self.units[data['target']].pressure+1e-9:return None
        if data.get('record') and m.get('echo')!=data['record']:return None
        if data.get('marks',0)>m.get('marks',{}).get(data.get('target'),{}).get('count',0):return None
        if data.get('chorus') and not m.get('chorus'):return None
        # Only a still-legal selected action consumes its next-paid-attempt debt.
        for source in price['debt']:state.field_debts.pop(source)
        if state.current<price['mana'] or state.body<=price['body']+1e-9:
            if price['debt']:
                self._light_note('field_tithe_failed',key,f'{state.unit.name}本次施权因索元附加费用不足而失败；束缚已消费，不部分扣费。',cost=price['mana'],body_cost=price['body'])
            return None
        if intent.discipline_action=='blood' and not price['blood']:
            intent=replace(intent,discipline_action='')
        chain=intent.allowance.chain
        if intent.discipline_action:
            path=self._field_action_path(key,intent.discipline_action,chain)
            if path is None:return None
            chain=path
        if price['blood'] and intent.discipline_action!='blood':
            path=self._field_path(key,'blood',chain)
            if path is None:return None
            chain=path
        # Every cost is validated before any of the original resources changes.
        self._energy(key,state.current-price['mana'],chain)
        if price['body']:
            state.body-=price['body']
            if key=='player':self.frame.primary_loss+=price['body']/.46
            self._field_note(key,d.names[0] if price['blood'] else d.names[2],
                f'实扣肉身完整度{price["body"]:.2%}，元力实付{price["mana"]:g}；不免领域维持或覆盖费。',body_cost=price['body'],cost=price['mana'])
        if data.get('charge'):
            old=m['charge'];m['charge']=max(0.,m['charge']-data['charge'])
            self._field_note(key,d.names[2],f'消费天威{data["charge"]:.2%}，储量{old:.2%}→{m["charge"]:.2%}，本次不同时治疗。',spent=data['charge'],before=old,after=m['charge'])
        if data.get('pressure'):
            victim=self.units[data['target']];old=victim.pressure;victim.pressure-=data['pressure']
            self._field_note(key,d.names[2],f'消费{victim.unit.name}承压{data["pressure"]:.2%}，{old:.2%}→{victim.pressure:.2%}，以减弱压制换取仙伤。',target=data['target'],spent=data['pressure'],before=old,after=victim.pressure)
        if data.get('record'):
            m['echo']={}
            self._field_note(key,d.names[2] if intent.discipline_action=='rupture' else d.names[1],
                f'消费一份{self._field_effect_name(data["record"]["kind"])}听律记录，不复制敌方威能与行动。',record=data['record'])
        if data.get('marks'):
            m['marks'][data['target']]['count']-=data['marks']
            self._field_note(key,d.names[1],f'消费{data["marks"]}枚禁印，余{m["marks"][data["target"]]["count"]}枚；本次只尝试一项短封。',target=data['target'],spent=data['marks'])
        if intent.discipline_action=='hunt':m['hunt']=intent.targets[0]
        if intent.discipline_action=='pursue':m['breaks'].pop(data['target'],None)
        if intent.discipline_action=='melody':
            self._field_tunes[key]=data['tune']
            if data.get('switch'):m['notes']=0
            if data.get('chorus'):m['chorus']=0;m['notes']=0
        data.update(body_paid=price['body'],blood_paid=price['blood'],actual_cost=price['mana'])
        if price['tax']:
            self._light_note('field_tithe',key,f'{state.unit.name}本次施权支付索元附加费用{price["tax"]:g}，消费{len(price["debt"])}份束缚。',cost=price['tax'])
        if d and intent.discipline_action:
            action=intent.discipline_action
            index=2 if action in {'judgment','burst','rupture','pursue','annihilate'} else 1 if action in {'guardian','echo','interdict','break'} else 0
            label=d.names[index]
            if action=='melody':label=('稳域曲','削敌曲','归元曲')[data['tune']]+('·合鸣' if data.get('chorus') else '')
            self._field_note(key,label,f'占用一份原有{"额外" if intent.allowance.source else "基础"}领域额度，元力实付{price["mana"]:g}。',
                action=action,targets=list(intent.targets),cost=price['mana'],free=intent.allowance.free)
        return replace(intent,allowance=replace(intent.allowance,chain=chain),discipline_data=data)

    def _finish_field_powers(self):
        for key,(target,token) in self._field_reserved.items():
            self._field_note(key,self.units[key].unit.capabilities.field_discipline.names[1],
                '本轮未等到真实恢复，留招额度过期；未施权、不扣费、不计额外行动。',target=target)
        self._field_reserved={}
        self._expire_field_controls(end=True)
