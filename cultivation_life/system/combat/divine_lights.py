"""Battle-local five-light arbitration. No content, owner, time or asset lookup."""
class DivineLights:
    def has_qian(self):
        return any(s.fighting and s.unit.capabilities.divine_lights.get('qian',0)>0 for s in self.units.values())

    def light_value(self, owner, key):
        return 0. if owner in self._light_muted else self.units[owner].unit.capabilities.divine_lights.get(key,0.)

    def _light_note(self, kind, owner, message, **details):
        self.frame.events.append(message)
        self._light_trace.append(dict(kind=kind,owner=owner,**details))

    def _light_chance(self, probability):
        if probability<=0:return False,None
        if probability>=1:return True,None
        if self._light_rng is None:raise ValueError('Probabilistic divine lights require the battle RNG')
        rolled=self._light_rng.random()
        return rolled<probability,rolled

    def _begin_lights(self, rng, first_side):
        self._light_rng=rng
        self._light_muted={};self._light_trace=[];self._light_resists={};self._light_extra={}
        self._light_prevented={}
        if self.frame.round_no==1:
            names={'kun':'坤元缃光','zhen':'震合缥光','kan':'坎道玄光','li':'离上朱光','qian':'乾古素光'}
            for key,state in self.units.items():
                caps=state.unit.capabilities;rows=[]
                for light,name in names.items():
                    if not caps.divine_lights.get(light):continue
                    value=caps.divine_lights.get('kun_resist' if light=='kun' else 'zhen_heal' if light=='zhen' else light,0)
                    meaning='免疫凡伤，抵抗封禁' if light=='kun' else '治疗保留普通出手，治疗增强' if light=='zhen' else '基础态势削弱' if light=='li' else '触发概率'
                    rows.append(f"{name}{caps.divine_light_levels.get(light,0)}重（{meaning}{value:.1%}）")
                if rows:self._light_note('profile',key,f'{state.unit.name}的五色神光：'+'；'.join(rows)+'。',levels=dict(caps.divine_light_levels),effects=dict(caps.divine_lights))
        if not self.has_qian():return
        side=first_side or ('player' if self.totals['player']>=self.totals['enemy'] else 'enemy')
        if side not in {'player','enemy'}:raise ValueError('Invalid divine-light initiative')
        self.frame.divine_first=side
        ordered=sorted(self.units, key=lambda k:(self.units[k].unit.side!=side,-self.units[k].unit.power,k))
        for key in ordered:
            state=self.units[key];rate=state.unit.capabilities.divine_lights.get('qian',0.)
            if not state.fighting or not rate:continue
            if key in self._light_muted:
                source=self._light_muted[key]
                self._light_note('qian_blocked',key,f'{state.unit.name}的乾古素光已被{self.units[source].unit.name}抢先静默，本回合无法发动。',source=source)
                continue
            success,rolled=self._light_chance(rate)
            targets=[k for k,s in self.units.items() if s.fighting and s.unit.side!=state.unit.side]
            if success:
                for target in targets:self._light_muted.setdefault(target,key)
                names='、'.join(self.units[k].unit.name for k in targets)
                text=f'{state.unit.name}发动乾古素光（概率{rate:.0%}），静默{names}本回合的邻域与五色神光效果。'
            else:text=f'{state.unit.name}乾古素光未触发（概率{rate:.0%}），后手仍可发动神光。'
            self._light_note('qian',key,text,probability=rate,roll=rolled,success=success,targets=targets)
        for state in self.units.values():
            state.controls={kind:owner for kind,owner in state.controls.items() if owner not in self._light_muted}

    def ward_tier(self, key, *, damage=True):
        caps=self.units[key].unit.capabilities
        if caps.divine_lights:
            return max(2,caps.ward_tier) if damage and self.light_value(key,'kun') else 1
        return caps.ward_tier

    def _resist_light_seal(self, target, owner):
        pair=(target,owner)
        if pair in self._light_resists:return self._light_resists[pair]
        rate=self.light_value(target,'kun_resist')
        success,rolled=self._light_chance(rate)
        self._light_resists[pair]=success
        if rate:
            name=self.units[target].unit.name;source=self.units[owner].unit.name
            text=f'{name}以坤元缃光抵抗{source}的邻域封禁（概率{rate:.0%}）：'+('抵抗成功，本轮保留普通行动与退路。' if success else '抵抗未成，按原封禁规则结算。')
            self._light_note('kun_resist',target,text,source=owner,probability=rate,roll=rolled,success=success)
        return success

    def _covered_by(self, field, key):
        return self._dominated.get(key)==field.owner or (self._light_resists.get((key,field.owner),False)
            and key in field.targets and self.frame.relations.get(key,{}).get('attacker')==field.owner)

    def _field_lights(self):
        for field in self.fields:
            key=field.owner;state=self.units[key]
            rate=self.light_value(key,'kan')
            if rate:
                success,rolled=self._light_chance(rate)
                self._light_extra[key]=int(success)
                self._light_note('kan',key,f'{state.unit.name}的坎道玄光'+('触发，邻域本回合行动次数由1增至2' if success else '未触发，邻域本回合行动次数为1')+f'（概率{rate:.0%}，施权仍须支付资源）。',probability=rate,roll=rolled,success=success)
            power=self.light_value(key,'li')
            if not power:continue
            for target in field.targets:
                victim=self.units[target]
                if not victim.fighting:continue
                defense=self.frame.relations.get(target,{}).get('defense_strength',0.)
                might=field.authority if field.authority is not None else field.strength
                reference=field.definition.authority_reference if field.authority is not None else max(1.,defense)
                ratio=max(0.,min(2.,might/max(1.,reference)))
                amount=min(.10,power*ratio)*(1-victim.unit.capabilities.body_voisinage_resistance)
                before=victim.vitality
                self._lose(target,min(max(0.,victim.vitality-.13),amount),physical=False)
                actual=before-victim.vitality
                self._light_note('li',key,f'{state.unit.name}以离上朱光随【{field.definition.name}】侵蚀{victim.unit.name}，威能{might:g}，削弱战斗态势{actual:.2%}（{actual*victim.unit.power:.1f}点），不造成肉身伤害。',target=target,might=might,ratio=power,actual_loss=actual)
