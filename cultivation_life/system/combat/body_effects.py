"""Finite body-plan execution against the existing battle ledger and fields."""
from .contracts import VoisinageEffect
from .body_mechanisms import REACTION_KINDS


class BodyEffects:
    def _action_paused(self,key):
        return self.frame.round_no>0 and self.units[key].release_recovery_round==self.frame.round_no

    @staticmethod
    def _body_effect_label(effect):
        names={'strike':'杀伤','suppress':'镇压','seal':'封锁','restrict':'禁制','isolate':'隔绝',
               'restore_body':'治疗肉身与态势','restore_spirit':'稳定心神','restore_field':'修复邻域'}
        restrictions={'technique':'功法','artifact':'法宝','support':'支援','supply':'供给','voisinage':'邻域'}
        return names[effect.kind]+restrictions.get(effect.restriction,'')
    def _guard_state(self,key,amount):
        rate=min(1.,self._body_round.value(key,'state_guard'))
        if rate and amount>0:
            reduced=amount*(1-rate)
            self._light_note('state_guard',key,
                f'{self.units[key].unit.name}以玄肤减免仙级攻击的战斗态势削减{rate:.1%}，由{amount:.2%}降为{reduced:.2%}；肉身损伤另计。',
                before=amount,after=reduced,rate=rate)
            return reduced
        return amount

    @staticmethod
    def _usable_energy(state):
        c=state.unit.capabilities
        return c.capacity if c.usable_capacity is None else c.usable_capacity

    def _swap_body_energy(self):
        matched=set()
        for key in self._body_round.order:
            for row in self._body_round.records[key].values():
                plan=row['auxiliary'].get('exchange')
                if not row['triggered'] or not plan or key in self._light_muted:continue
                target=plan['target']
                if key in matched or target in matched:continue
                own,other=self.units[key],self.units[target]
                if not own.fighting or not other.fighting or own.exchange_used:continue
                chain=((key,row['id']),)
                self._energy(key,self._usable_energy(own)*plan['other_ratio'],chain)
                self._energy(target,self._usable_energy(other)*plan['own_ratio'],chain)
                own.exchange_used=True;matched.update((key,target))
                self._light_note('energy_exchange',key,
                    f'{own.unit.name}发动神魂，与{other.unit.name}交换可用元力比例：自身{plan["own_ratio"]:.1%}→{plan["other_ratio"]:.1%}，对方{plan["other_ratio"]:.1%}→{plan["own_ratio"]:.1%}；本场唯一次数已使用。',
                    target=target,**{k:v for k,v in plan.items() if k!='target'})

    def _release_body_domination(self):
        for key in self._body_round.order:
            if key not in self._dominated:continue
            state=self.units[key];fraction=self._body_round.value(key,'release_cost')
            if self._action_paused(key):continue
            capacity=self._usable_energy(state);cost=capacity*fraction
            if not fraction or not state.fighting:continue
            if capacity<=0 or state.current<cost:
                self._light_note('domination_release',key,
                    f'{state.unit.name}沸血解除支配失败：需要{cost:g}元力，现有{state.current:g}；未扣费。',success=False,cost=cost)
                continue
            source=self._dominated.pop(key);state.escape_locked=False
            entry=self._body_round.channel(key,'release_cost')
            self._energy(key,state.current-cost,entry[1] if entry else ())
            self.frame.relations[key]['relation']='released'
            if self._body_round.value(key,'release_recovery'):
                state.release_recovery_round=self.frame.round_no+1
                self._light_note('release_recovery_plan',key,
                    f'{state.unit.name}沸血解控后将在第{state.release_recovery_round}回合调息，暂停普通出手与全部邻域施权；仍支付维持费并保留被动。',round=state.release_recovery_round)
            self._light_note('domination_release',key,
                f'{state.unit.name}以沸血消耗{cost:g}元力（本场可用容量{fraction:.1%}），解除{self.units[source].unit.name}对自身的支配；本轮不重算邻域对抗，行动资格重新核验。',
                success=True,cost=cost,source=source)

    def _body_evade(self,intent,key):
        if intent.ordinary or key in self._light_muted:return False
        state=self.units[key]
        if not state.fighting or state.active_voisinage is None or key in self._disrupted:return False
        if not any(f.owner==key for f in self.fields):return False
        result=self._body_round.evade(key,intent.field.owner,intent.allowance.slot,intent.allowance.chain)
        if result is None:return False
        success=result['success']
        self._light_note('field_evade',key,
            f'{state.unit.name}的邻域以逆骨闪避{self.units[intent.field.owner].unit.name}的{self._body_effect_label(intent.effect)}：'+
            ('成功，此次作用无效，对方已付费用不退。' if success else '未成，继续结算。')+f'（本段闪避概率{result["probability"]:.1%}）',
            source=intent.field.owner,slot=intent.allowance.slot,**result)
        if success:
            if not self._action_paused(key) and self._body_round.arm_reaction(key,intent.field.owner,result['chain']):
                self._light_note('reaction_ready',key,f'{state.unit.name}实际闪避成功，兑现一份烈脏免费施权额度；从已解锁功能中择一，因果链禁止同一角色机制重入。',target=intent.field.owner)
        return success

    def _reaction_effect(self,field,token):
        key=field.owner;state=self.units[key];plan=self._body_round
        power=plan.value(key,'retaliate_power');choice=int(plan.value(key,'retaliate_choice'))
        target=token.target;enemy=self.units.get(target)
        hostile=bool(enemy and enemy.fighting and enemy.unit.side!=state.unit.side and self._can_reach(state,target))
        hurt=state.vitality<1 or state.body<1
        choices=[]
        for index,mode in enumerate(REACTION_KINDS,1):
            if not plan.value(key,'retaliate_'+mode):continue
            if mode in {'heal','spirit','field'}:
                needed=(hurt if mode=='heal' else state.pressure>0 or state.morale<100 if mode=='spirit' else state.field_strain>0)
                if needed:choices.append((index,VoisinageEffect({'heal':'restore_body','spirit':'restore_spirit','field':'restore_field'}[mode],0,power,target='self'),(key,)))
            elif hostile:
                restriction=mode if mode not in {'suppress','seal'} else None
                if restriction and restriction in enemy.restrictions:continue
                kind=mode if not restriction else 'isolate' if mode in {'support','supply'} else 'restrict'
                choices.append((index,VoisinageEffect(kind,0,power,restriction=restriction),(target,)))
        if choice:choices=[r for r in choices if r[0]==choice]
        if not choices:return None
        # Auto prioritizes self-recovery, then suppression, then sealing.
        _,effect,targets=choices[0]
        return effect,targets
