"""Data-selected field techniques. No world, player path or content lookups."""
from dataclasses import dataclass,field,replace
from .contracts import VoisinageEffect
from .body_mechanisms import enter


@dataclass(frozen=True)
class FieldOption:
    effect: VoisinageEffect
    action: str=''
    data: dict=field(default_factory=dict)
    priority: int | None=None


class FieldPowers:
    @staticmethod
    def _field_effect_name(kind):
        return {'strike':'杀伤','suppress':'镇压','seal':'封锁','restrict':'禁制','isolate':'隔绝',
            'restore_body':'修复肉身','restore_spirit':'稳定心神','restore_field':'修复稳固',
            'artifact':'法宝','technique':'功法','voisinage':'邻域'}.get(kind,kind)

    def _field_coverage_targets(self,state,definition,targets):
        d=state.unit.capabilities.field_discipline
        if d is None or not targets:return targets
        basic_hostile=any(e.target=='enemy' for e in definition.actions())
        if basic_hostile and not (d.kind=='restoration_charge' and d.mode=='heal'):return targets
        # A restoration-only field must not suppress every source of the actual
        # injury/record it needs. Shrinking coverage uses the normal field bill.
        m=state.field_memory
        ready=(d.level>=7 and m.get('charge',0)>=d.parameters['threshold']) if d.kind=='restoration_charge' else (
            d.level>=4 and bool(m.get('echo'))) if d.kind=='echo' else True
        if ready:return targets
        rank=state.unit.cultivation_rank
        if rank>=0 and all(0<=self.units[k].unit.cultivation_rank<rank for k in targets):return targets
        return []

    def _discipline(self,key,*,active=True):
        state=self.units[key];d=state.unit.capabilities.field_discipline
        if d is None or d.level<2:return None
        if active and (not state.fighting or key in self._light_muted or key in self._disrupted or
                       state.active_voisinage is None or not any(f.owner==key for f in self.fields)):
            return None
        return d

    def _field_memory(self,key):
        state=self.units[key]
        if not state.field_memory:
            d=state.unit.capabilities.field_discipline
            state.field_memory.update(charge=0.,hunt=None,echo={},melody=d.opening if d else 0,
                notes=0,melody_round=0,chorus=0,blood_round=0,ordinary_round=0,record_round=0,
                marks={},cooldowns={},breaks={})
        return state.field_memory

    def _field_path(self,key,action,chain):
        d=self.units[key].unit.capabilities.field_discipline
        return enter(chain,key,f'field:{d.id}:{action}') if d else None

    def _field_action_path(self,key,action,chain):
        # Base hits may repeat; their outcome hooks own causal children.
        if action in {'guardian','bond','hunt','imprint','strain','melody'}:return chain
        return self._field_path(key,action,chain)

    def _field_note(self,key,ability,message,**data):
        d=self.units[key].unit.capabilities.field_discipline
        self._light_note('field_power',key,f'{self.units[key].unit.name}【{ability}】{message}',
            discipline=d.id if d else '',ability=ability,**data)

    def _field_enemies(self,field):
        state=self.units[field.owner]
        return tuple(k for k in field.targets if self.units[k].fighting and self._can_reach(state,k) and self._covered_by(field,k))

    def _field_options(self,field,allowance):
        d=self._discipline(field.owner)
        original=[FieldOption(e) for e in field.definition.actions()]
        if not d:return original
        key=field.owner;state=self.units[key];m=self._field_memory(key);p=d.parameters;mode=d.mode
        enemies=self._field_enemies(field)
        def make(kind,action,*,power=None,restriction=None,data=None,priority=1,target=None,single=True):
            friendly=kind.startswith('restore_')
            effect=VoisinageEffect(kind,field.definition.effect_cost,
                field.definition.effect_power if power is None else power,
                target=target or ('self' if friendly else 'enemy'),restriction=restriction,
                defense='ward' if not friendly else 'bypass',
                tier=max(e.tier for e in field.definition.actions()),target_mode='single' if single else 'all')
            return FieldOption(effect,action,data or {},priority)
        def allowed(action):return self._field_path(key,action,allowance.chain) is not None
        if d.kind=='restoration_charge':
            options=original
            if d.level>=4:
                options=[FieldOption(replace(e.effect,target='ally',target_mode='single'),
                    'guardian',priority=2) if e.effect.kind=='restore_body' else e for e in options]
            if d.level>=7 and m['charge']>=p['threshold'] and enemies and allowed('judgment') and mode!='heal' and mode!='guardian':
                amount=min(p['release'],m['charge'])
                safe=.65 if d.policy=='steady' else .2
                priority=0 if min(state.body,state.vitality)>safe or mode=='judgment' else 3
                options.insert(0,make('strike','judgment',power=min(1.,.12+amount),
                    data=dict(charge=amount),priority=priority))
            if mode=='heal':options=[o for o in options if o.effect.kind.startswith('restore_')]
            return options
        if d.kind=='pressure_bond':
            options=[FieldOption(e.effect,'bond',priority=e.priority) if e.effect.kind=='suppress' else e for e in original]
            targets=[k for k in enemies if self.units[k].pressure>=p['threshold']]
            if d.level>=7 and targets and mode!='suppress' and allowed('burst'):
                target=max(targets,key=lambda k:(self.units[k].pressure,k));amount=min(p['consume'],self.units[target].pressure)
                options.insert(0,make('strike','burst',power=min(1.,.12+amount*p['bonus']),
                    data=dict(pressure=amount,target=target),priority=0))
            return options
        if d.kind=='hunter':
            return [FieldOption(replace(o.effect,target_mode='single'),'hunt' if o.effect.kind=='strike' else '',priority=o.priority) for o in original]
        if d.kind=='echo':
            echo=m['echo'];options=original
            if not echo or mode=='cleanse':return options
            kind=echo['kind'];restriction=echo['restriction']
            if d.level>=7 and mode!='echo' and enemies and allowed('rupture'):
                options.insert(0,make('strike','rupture',power=p['rupture'],data=dict(record=echo),
                    priority=(2 if d.policy=='steady' and state.vitality<.75 else 0) if min(state.body,state.vitality)>.2 or mode=='rupture' else 3))
            if d.level>=4 and allowed('echo'):
                if kind in {'restrict','isolate'} and restriction not in {'technique','artifact','voisinage'}:
                    kind,restriction='seal',None
                options.append(make(kind,'echo',power=min(1.,field.definition.effect_power*p['scale']),
                    restriction=restriction,data=dict(record=echo,timed=kind in {'restrict','isolate'}),priority=0 if mode=='echo' else 1))
            return options
        if d.kind=='interdict':
            options=[FieldOption(o.effect,'imprint',priority=o.priority) if o.effect.kind=='seal' else o for o in original]
            targets=[k for k in enemies if m['marks'].get(k,{}).get('count',0)>=p['marks'] and
                     m['cooldowns'].get(k,0)<=self.frame.round_no]
            if d.level>=4 and targets and mode!='seal' and allowed('interdict'):
                target=min(targets,key=lambda k:(-m['marks'][k]['count'],k));caps=self.units[target].unit.capabilities
                restriction=mode if mode in {'technique','artifact','voisinage'} else (
                    'voisinage' if d.level>=7 and d.policy!='steady' and self.units[target].active_voisinage else
                    'artifact' if caps.artifact_tier>=max(caps.technique_tier,caps.force_tier) else 'technique')
                if restriction not in self.units[target].restrictions and (restriction!='voisinage' or d.level>=7):
                    options.insert(0,make('restrict','interdict',restriction=restriction,
                        data=dict(target=target,timed=True,marks=p['marks']),priority=0))
            return options
        if d.kind=='melody':
            tune=self._field_tunes.get(key,m['melody']);switch=0.
            needs=(state.field_strain>1-field.definition.restore_threshold,bool(enemies),state.vitality<field.definition.restore_threshold)
            if key not in self._field_tunes and d.level>=4 and mode in {'auto','shift'}:
                order=(1,2,0) if d.policy!='steady' else (0,2,1)
                wanted=2 if state.vitality<.45 else tune if needs[tune] else next((i for i in order if needs[i]),tune)
                if wanted!=tune:tune=wanted;switch=p['switch_cost']
            kind=('restore_field','suppress','restore_spirit')[tune]
            chorus=bool(d.level>=7 and m['chorus'])
            target='ally' if chorus and kind.startswith('restore_') else None
            return [make(kind,'melody',power=p['power'],target=target,single=not chorus,
                data=dict(tune=tune,switch=switch,chorus=chorus,state_only=tune==2),priority=1)]
        if d.kind=='field_breaker':
            options=original
            broken=[k for k in enemies if m['breaks'].get(k,0)>=self.frame.round_no and not self.units[k].active_voisinage]
            if d.level>=7 and broken and mode!='strain' and mode!='break' and allowed('pursue'):
                return [make('strike','pursue',data=dict(target=broken[0]),priority=0)]
            targets=[k for k in enemies if self.units[k].active_voisinage and
                self.units[k].field_strain>=p['threshold'] and m['cooldowns'].get(k,0)<=self.frame.round_no]
            if d.level>=4 and targets and mode not in {'strike','strain'} and allowed('break'):
                options.insert(0,make('restrict','break',restriction='voisinage',
                    data=dict(target=targets[0],timed=True),priority=0))
            if mode!='strike':
                options=[FieldOption(replace(o.effect,power=o.effect.power*(1-p['fraction'])),
                    'strain',dict(fraction=p['fraction']),2) if o.effect.kind=='strike' and
                    any(self.units[k].active_voisinage for k in enemies) else o for o in options]
            return options
        if d.kind=='blood':
            options=original
            sacrifice=mode in {'blood','annihilate'} or mode=='auto' and state.body>p['auto_health'] and state.current<self._usable_energy(state)*p['auto_energy']
            if d.level>=7 and len(enemies)>1 and mode!='mana' and state.body>p['aoe_cost']+.2 and allowed('annihilate'):
                options=[make('strike','annihilate',power=field.definition.effect_power*p['aoe_scale'],
                    data=dict(extra_body=p['aoe_cost']),priority=0,single=False),*options]
            blood=sacrifice and not allowance.free and allowed('blood')
            choices=[]
            for o in options:
                choices.append(FieldOption(o.effect,o.action or ('blood' if blood else ''),dict(o.data,blood=blood),o.priority))
                if blood:choices.append(FieldOption(o.effect,o.action,dict(o.data,blood=False),o.priority))
            return choices
        return original

    def _field_option_targets(self,field,option,keys):
        data=option.data;key=field.owner;d=self._discipline(key)
        if data.get('target'):return [k for k in keys if k==data['target']]
        if option.action=='hunt' and keys:
            m=self._field_memory(key);target=m['hunt']
            if target not in keys:
                target=(max(keys,key=lambda k:(self.units[k].unit.power,k)) if d.policy=='aggressive' else
                    min(keys,key=lambda k:(self.units[k].body,self.units[k].vitality,k)) if d.policy=='steady' else
                    min(keys,key=lambda k:(self.units[k].vitality,self.units[k].body,k)))
            return [target]
        if option.action=='guardian':
            return sorted(keys,key=lambda k:(min(self.units[k].body,self.units[k].vitality),k))
        if option.action=='melody' and not data.get('chorus') and option.effect.target!='self':
            return sorted(keys,key=lambda k:(self.units[k].vitality,k))[:1]
        return keys

    def _field_idle(self,key,allowance):
        d=self._discipline(key)
        if d and d.kind=='melody' and not allowance.source and not self._action_paused(key):
            m=self._field_memory(key)
            if m['melody_round']!=self.frame.round_no:
                m['melody']=(m['melody']+1)%3;m['melody_round']=self.frame.round_no
                self._field_tunes[key]=(m['melody']-1)%3
                self._field_note(key,d.names[0],'本曲无合法收益，放弃本轮基础领域额度换曲；不施权、不收费、不积合鸣。')

    def _field_hold(self,intent):
        key=intent.field.owner;d=self._discipline(key)
        if not d or d.kind!='hunter' or d.level<4 or d.mode=='focus' or key in self._field_waited or intent.discipline_action!='hunt':return False
        target=intent.targets[0];victim=self.units[target]
        can_heal=any(e.kind.startswith('restore_') for f in victim.unit.capabilities.voisinages for e in f.actions())
        can_heal=can_heal and (target not in self._dominated or self.light_value(target,'zhen')) and not self._action_paused(target)
        if d.mode!='ambush' and not (can_heal and min(victim.body,victim.vitality)<.8):return False
        token=intent.allowance
        token.spent=False;token.ready=False
        self._field_reserved[key]=(target,token);self._field_waited.add(key)
        self._field_memory(key)['hunt']=target
        self._field_note(key,d.names[1],f'留下一份原有领域额度，等待{victim.unit.name}真实恢复后追击；未触发则轮末过期。',target=target)
        return True

    def _field_healed(self,target,amount):
        if amount<=0:return
        for key,(prey,token) in tuple(self._field_reserved.items()):
            if prey!=target:continue
            self._field_reserved.pop(key)
            path=self._field_path(key,'pursuit',tuple(dict.fromkeys((*self._body_chain,*token.chain))))
            if path is None or not self._discipline(key) or self._action_paused(key):continue
            token.chain=path;token.ready=True
            self._field_note(key,self.units[key].unit.capabilities.field_discipline.names[1],
                f'{self.units[target].unit.name}实际恢复，留招额度就绪，仍须重新核验目标并付费。',target=target)
