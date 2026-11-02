"""Battle integration for the neutral round-start mechanism planner."""
from .body_mechanisms import BodyRound,mechanisms
from .body_effects import BodyEffects


class DivineLights(BodyEffects):
    def has_qian(self):
        return any(s.fighting and (any(r.effects.get('silence') and r.chance>0 for r in s.unit.capabilities.body_mechanisms)
                   if s.unit.capabilities.body_mechanisms else s.unit.capabilities.divine_lights.get('qian',0)>0)
                   for s in self.units.values())

    def needs_body_initiative(self):
        return self.has_qian() or any(s.fighting and not s.exchange_used and
            any(r.effects.get('exchange_threshold') for r in s.unit.capabilities.body_mechanisms)
            for s in self.units.values())

    def light_value(self,owner,key):
        channels={'kun':'ward','kun_resist':'seal_resist','zhen':'heal_preserve','zhen_heal':'heal_bonus',
                  'kan':'extra','li':'erosion','qian':'silence'}
        if self._body_round is None:return self.units[owner].unit.capabilities.divine_lights.get(key,0.)
        value=self._body_round.value(owner,channels[key])
        return float(value>=2) if key=='kun' else value

    def _body_name(self,owner,channel):
        if self._body_round is not None:
            return next((r['name'] for r in self._body_round.records[owner].values() if channel in r['effects']),'高阶炼体')
        return next((r.name for r in mechanisms(self.units[owner].unit.capabilities) if channel in r.effects),'高阶炼体')

    def _light_note(self,kind,owner,message,**details):
        self.frame.events.append(message)
        details.setdefault('chain',list(self._body_chain))
        self._light_trace.append(dict(kind=kind,owner=owner,**details))

    def _begin_lights(self,rng,first_side):
        self._light_rng=rng
        self._light_trace=[];self._light_resists={};self._light_extra={};self._light_prevented={}
        side=first_side or ('player' if self.totals['player']>=self.totals['enemy'] else 'enemy')
        if side not in {'player','enemy'}:raise ValueError('Invalid body-mechanism initiative')
        self._body_round=BodyRound(self.units,rng,side)
        self._light_muted=self._body_round.muted
        for key,records in self._body_round.records.items():
            if records:
                triggered='、'.join(r['name'] for r in records.values() if r['triggered']) or '无'
                self._light_note('body_rolls',key,f'{self.units[key].unit.name}轮首统一判定，原始触发：{triggered}；此清单在静默裁决后保留。')
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
                if caps.body_mechanisms:
                    def description(row):
                        e=row.effects
                        if 'evade' in e:return f'逐次闪避概率{e["evade"]:.1%}'
                        if 'state_guard' in e:return f'免疫凡伤，仙级态势减伤{e["state_guard"]:.1%}'
                        if 'release_cost' in e:return f'解除支配消耗可用容量{e["release_cost"]:.1%}'
                        if 'exchange_threshold' in e:return f'元力比例低于{e["exchange_threshold"]:.1%}且低于对手时交换，本场一次'
                        if 'retaliate_power' in e:return f'闪避后免费择一，数值效果{e["retaliate_power"]:.1%}'
                        if 'recovery_bonus' in e:return f'免疫凡伤，态势与邻域回复效率提高{e["recovery_bonus"]:.1%}'
                        if 'split' in e:return f'一次行动三段，每段继承{e["split"]:.1%}，全体攻击仍为全体'
                        if 'death_restore' in e:return f'每人真实阵亡回复态势与可用元力{e["death_restore"]:.1%}'
                        if 'forget' in e:return f'比较实际目标集合，溢出或追加比例{e["forget"]:.1%}'
                        if 'karma_threshold' in e:return f'累计实际元力减少每{e["karma_threshold"]:.1%}，免费全体攻击一次'
                        return f'轮首触发概率{row.chance:.0%}'
                    text='；'.join(f'{r.name}{r.level}重（{description(r)}）' for r in caps.body_mechanisms)
                    self._light_note('body_profile',key,f'{state.unit.name}的高阶炼体机制：{text}。')
        if self.needs_body_initiative():self.frame.divine_first=side
        for event in self._body_round.events:
            key=event['owner'];name=self.units[key].unit.name
            if event['kind']=='silence_blocked':
                source=event['source']
                self._light_note('qian_blocked',key,f'{name}的乾古素光已被{self.units[source].unit.name}抢先静默，本回合无法发动。',source=source)
            else:
                rate=event['probability'];success=event['success']
                targets='、'.join(self.units[k].unit.name for k in event['targets'])
                message=(f'{name}发动乾古素光（概率{rate:.0%}），静默{targets}本回合的邻域与全部高阶炼体机制（含五色神光、五蕴、五蜕及鬼躯五法）。'
                         if success else f'{name}乾古素光未触发（概率{rate:.0%}），后手仍可发动神光。')
                self._light_note('qian',key,message,probability=rate,roll=event['roll'],success=success,targets=event['targets'])
        for key,rows in self._body_round.records.items():
            for row in rows.values():
                if 'exchange_threshold' in row['effects'] and not row['triggered']:
                    state=self.units[key];cap=self._usable_energy(state);ratio=state.current/cap if cap else 1.
                    reason='本场次数已使用' if state.exchange_used else '当前比例或对手条件不满足'
                    self._light_note('exchange_ineligible',key,f'{state.unit.name}神魂本轮未登记交换：{reason}；自身可用元力比例{ratio:.1%}，阈值{row["effects"]["exchange_threshold"]:.1%}。')
                if 'critical' in row['effects']:
                    result='成功，本轮合法的数值施权按200%计算' if row['triggered'] else '未触发'
                    if key in self._light_muted:result+='；已被静默，实际暴击停用'
                    self._light_note('critical_plan',key,f"{self.units[key].unit.name}的{row['name']}轮首暴击判定{result}（概率{row['probability']:.0%}）。",record=dict(row))
                if 'critical_extra' in row['effects'] and row['triggered']:
                    self._light_note('action_plan',key,f"{self.units[key].unit.name}的{row['name']}可在实际暴击后追加施权（免费概率{row['effects'].get('free',0):.0%}）；兑现时判定免费，同一角色机制禁止沿自身因果链重入。",record=dict(row))
        for state in self.units.values():
            state.controls={kind:owner for kind,owner in state.controls.items() if owner not in self._light_muted}

    def ward_tier(self,key,*,damage=True):
        caps=self.units[key].unit.capabilities
        if self._body_round is not None:
            if not any('ward' in r['effects'] for r in self._body_round.records[key].values()):return caps.ward_tier
            ward=self._body_round.value(key,'ward')
            return max(2,caps.ward_tier) if damage and ward>=2 else 1
        if mechanisms(caps):
            ward=self._body_round.value(key,'ward') if self._body_round else max((r.effects.get('ward',0) for r in mechanisms(caps)),default=0)
            return max(2,caps.ward_tier) if damage and ward>=2 else 1
        return caps.ward_tier

    def _resist_light_seal(self,target,owner):
        pair=(target,owner)
        if pair in self._light_resists:return self._light_resists[pair]
        rate=self._body_round.value(target,'seal_resist');success=self._body_round.resisted(target)
        self._light_resists[pair]=success
        if rate:
            name=self.units[target].unit.name;source=self.units[owner].unit.name
            text=f'{name}以{self._body_name(target,"seal_resist")}抵抗{source}的邻域封禁（轮首概率{rate:.0%}）：'+('抵抗成功，本轮保留普通行动与退路。' if success else '抵抗未成，按原封禁规则结算。')
            self._light_note('kun_resist',target,text,source=owner,probability=rate,success=success)
        return success

    def _covered_by(self,field,key):
        return self._dominated.get(key)==field.owner or (self._light_resists.get((key,field.owner),False)
            and key in field.targets and self.frame.relations.get(key,{}).get('attacker')==field.owner)

    def _field_lights(self):
        for field in self.fields:
            key=field.owner;state=self.units[key]
            for row in self._body_round.records[key].values():
                if 'extra' in row['effects'] and key not in self._light_muted:
                    success=row['triggered'];amount=int(row['effects']['extra']) if success else 0
                    self._light_note('kan',key,f"{state.unit.name}的{row['name']}"+('触发，邻域本回合行动次数由1增至'+str(1+amount) if success else '未触发，邻域本回合行动次数为1')+f"（轮首概率{row['probability']:.0%}，施权仍须支付资源）。",success=success)
            for target in field.targets:
                raw=self._body_round.amplification(key,target,raw=True)
                if raw:
                    value=self._body_round.amplification(key,target)
                    self._light_note('amplification_plan',key,f'{state.unit.name}的{self._body_name(key,"exploit")}按{self.units[target].unit.name}轮首原始触发{self._body_round.triggered_count(target)}种机制，候选削弱增幅{raw:.0%}，实际增幅{value:.0%}'+('（被乾古素光静默）。' if key in self._light_muted else '。'),target=target,raw=raw,effective=value)
            power=self._body_round.value(key,'erosion')
            if not power:continue
            for target in field.targets:
                victim=self.units[target]
                if not victim.fighting:continue
                defense=self.frame.relations.get(target,{}).get('defense_strength',0.)
                might=field.authority if field.authority is not None else field.strength
                reference=field.definition.authority_reference if field.authority is not None else max(1.,defense)
                ratio=max(0.,min(2.,might/max(1.,reference)))
                amount=min(.10,power*ratio)*(1-victim.unit.capabilities.body_voisinage_resistance)
                amount*=1+self._body_round.amplification(key,target)
                before=victim.vitality
                amount=min(max(0.,victim.vitality-.13),amount)
                if max(e.tier for e in field.definition.actions())>=2:amount=self._guard_state(target,amount)
                self._lose(target,amount,physical=False)
                actual=before-victim.vitality
                self._light_note('li',key,f'{state.unit.name}以{self._body_name(key,"erosion")}随【{field.definition.name}】侵蚀{victim.unit.name}，威能{might:g}，削弱战斗态势{actual:.2%}（{actual*victim.unit.power:.1f}点），不造成肉身伤害。',target=target,might=might,actual_loss=actual)

    def _execute_field_actions(self,previous):
        while self._body_round.pending({f.owner for f in self.fields}):self._resolve_effects(previous)

    def _complete_body_actions(self,completed):
        for key,token,critical in completed:
            self._body_round.complete(key,critical,token.chain)
        old_chain=self._body_chain
        try:
            for source,token,_ in completed:
                if not token.source:continue
                for key,state in self.units.items():
                    if not state.fighting or state.unit.side==self.units[source].unit.side:continue
                    entry=self._body_round.channel(key,'restore_state',token.chain)
                    if not entry:continue
                    row,path=entry;self._body_chain=path
                    heal=row['effects'].get('restore_state',0);energy=row['effects'].get('restore_energy',0)
                    before,previous=state.vitality,state.current
                    self._restore_state(key,heal)
                    self._energy(key,state.current+self._usable_energy(state)*energy)
                    self._light_note('counter_restore',key,f'{state.unit.name}以{row["name"]}响应敌方实际额外施权1次，回复战斗态势{state.vitality-before:.2%}、元力{state.current-previous:g}，不恢复肉身。',count=1,state=state.vitality-before,energy=state.current-previous)
        finally:self._body_chain=old_chain
