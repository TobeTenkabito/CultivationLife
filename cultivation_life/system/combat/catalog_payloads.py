"""Distinct finite conversions. Every packet spends part of one paid budget."""


class CatalogPayloads:
    def support_amount(self, owner, recipient, amount):
        # Unit vitality is normalized by each participant's original power.
        # Transfer one caster-owned budget, never a percentage of the recipient.
        if owner==recipient:return amount
        source=self.battle.units[owner].unit.power
        target=self.battle.units[recipient].unit.power
        return min(1., amount*source/target)

    def useful(self,key,branch):
        owner,b=self.books[key];e=b['effect'];f=self.facts[owner];s=self.battle.units[owner]
        payload=e['payload'];cast=self.observed_source(key)
        if 'ally_required' in e['clauses'] and self.recipient(owner,b)==owner:return False
        if payload in {'cleanse_temporary','initiative_cleanse'} or branch=='cleanse':
            if not self.debuff(owner,'aged_debuff' in e['clauses']):return False
        if payload in {'receipt_shield','delayed_loss_recovery'}:
            if not self.loss_receipt(key):return False
        if payload in {'barrier_followup','breach_then_restore'} and f.get('broke_round',-10)<self.round-2:return False
        if payload=='broken_shield_breach' and f.get('broken_round',-10)<self.round-2:return False
        if payload in {'initiative_switch','initiative_charge','initiative_cleanse'} and not f.get('changed'):return False
        if payload=='repeat_source_response' and cast.get('count',0)<1:return False
        if payload=='repeat_initiative_breach' and (cast.get('count',0)<2 or cast.get('target')!=owner):return False
        if payload=='repeat_initiative_breach' and f.get('first') is not False:return False
        if payload=='repeat_paid_cast' and cast.get('paid_count',0)<2:return False
        if (payload in {'interruptible_restore','delayed_loss_recovery','breach_then_restore'} or branch=='recover'):
            recipient=self.recipient(owner,b)
            if self.battle.units[recipient].vitality>=self.initial_state[recipient]:return False
        return True

    def loss_receipt(self,key):
        owner,b=self.books[key];r=self.records[key]
        rows=[row for row in self.facts[owner].get('losses',[]) if row['round']>=self.round-2 and row['seq']>r['loss_seq']]
        if r['opportunity']:
            return next((row for row in rows if row['seq']==r['opportunity']['loss_seq']),None)
        if not rows:return None
        return max(rows,key=lambda row:row['amount']) if 'largest_loss' in b['effect']['clauses'] else rows[0]

    def recipient(self,owner,book):
        flags=book['effect']['clauses'];s=self.battle.units[owner]
        if not set(flags)&{'give_ally','give_corpse','split_ally'}:return owner
        if 'support' in s.restrictions:return owner
        allies=[k for k,a in self.battle.units.items() if k!=owner and a.unit.side==s.unit.side and a.fighting
                and self.battle._can_reach(s,k) and 'support' not in a.restrictions
                and ('give_corpse' not in flags or a.unit.capabilities.technique_context.get('corpse'))]
        return min(allies,key=lambda k:(self.battle.units[k].vitality,k)) if allies else owner

    def packet(self,key,receipt,channel,share=1.,delay=0,*,target=None,recipient=None,bound=False,amount=0.,wait=False,phase=''):
        owner,b=self.books[key];r=self.records[key];op=r['opportunity'];e=b['effect']
        delay=max(delay,int(e['delivery'] in {'hold_once','survive_full_round'}))
        start=self.round+delay
        packet=dict(receipt=receipt,channel=channel,share=share,initial_share=share,starts=start,
            expires=min(self.round+3,start+1),target=target if target is not None else op['target'],
            recipient=recipient or owner,bound=bound or e['covenant']=='observed_target_binding'
                or e['delivery'] in {'bind_event_source','retarget_before_commit'} or 'source_bound' in e['clauses'],
            first=op['first'],wait_previous=wait,burden=e['covenant']=='body_commitment',amount=amount,
            basis=0.,phase=phase,applied=False,watch=op['source'],seed=False,paused=0)
        r['packets'].append(packet)
        return packet

    def make_packets(self,key,receipt,branch):
        owner,b=self.books[key];r=self.records[key];e=b['effect'];f=self.facts[owner]
        payload=e['payload'];ward=e['ward_bp']/10000
        op=r['opportunity'];target=op['target'];recipient=self.recipient(owner,b)
        if payload in {'barrier_followup','breach_then_restore'}:target=f.get('broke_target',target)
        elif payload=='broken_shield_breach':target=f.get('broken_source',target)
        elif payload in {'receipt_shield','delayed_loss_recovery'}:
            loss=self.loss_receipt(key)
            if loss:
                target=loss['source'];r['loss_seq']=loss['seq']
                f=dict(f,hurt_amount=loss['amount'])
        cast=self.observed_source(key)
        if payload.startswith('repeat_'):target=cast.get('source',target)
        if 'expiry_seed' in e['clauses'] and r['expired']==0:
            p=self.packet(key,receipt,'seed',target=target);p['seed']=True;return
        chunks=[(1.,0,False)]
        if payload not in {'cleanse_temporary','initiative_cleanse'} and branch!='cleanse':
            if e['delivery']=='two_half_packets':chunks=[(.5,0,False),(.5,1,True)]
            elif e['delivery']=='successful_echo_split':chunks=[(2/3,0,False),(1/3,1,True)]
            elif e['delivery']=='attack_defense_split':
                chunks=[(.5,0,False)]
                self.packet(key,receipt,'shield',.5,amount=ward*.5,recipient=owner)
        for share,delay,wait in chunks:
            def make(channel, fraction=1., extra=0, **kw):
                return self.packet(key,receipt,channel,share*fraction,delay+extra,target=target,
                                   recipient=recipient,wait=wait,**kw)
            if payload=='cancel_afterburn_for_shield':make('choice_flame',extra=1,bound=True)
            elif branch and payload in {'offense_restore_choice','alternating_choice','four_way_choice',
                'initiative_choice','forecast_choice','five_step_rotation'}:
                extra=int(payload in {'forecast_choice','cancel_afterburn_for_shield'} or branch=='recover')
                make(branch,extra=extra,amount=ward*share if branch in {'shield','recover'} else 0.)
            elif branch=='shield':make('shield',amount=ward*share)
            elif payload=='self_cost_rebate':make('guard',phase='rebate')
            elif payload in {'bound_breach','barrier_followup','broken_shield_breach','repeat_initiative_breach','repeat_paid_cast'}:
                make('breach',bound=True)
            elif payload=='taiyuan_sword':make('sword',bound=True)
            elif payload=='interruptible_restore':make('recover',extra=1,amount=ward*share,phase='fragile')
            elif payload=='receipt_shield':make('shield',bound=True,amount=min(ward,f.get('hurt_amount',0)*.25)*share)
            elif payload=='budgeted_afterburn':
                if 'delayed_all' in e['clauses']:make('arm_afterburn',bound=True)
                else:make('strike',fraction=.5,bound=True);make('arm_afterburn',fraction=.5,bound=True)
            elif payload in {'finite_shield','damage_to_shield'}:make('shield',amount=ward*share)
            elif payload=='initiative_switch':make('mobility')
            elif payload in {'charge_release','initiative_charge'}:make('strike',extra=1,bound=True,phase='charged')
            elif payload=='repeat_source_response':
                p=make('response',bound=True);p['watch']=cast.get('book')
            elif payload in {'cleanse_temporary','initiative_cleanse'}:make('cleanse')
            elif payload=='delayed_loss_recovery':
                amount=min(ward,f.get('hurt_amount',0)*.2)*share/2
                make('recover',fraction=.5,extra=1,amount=amount)
                p=make('recover',fraction=.5,extra=2,amount=amount)
                p['wait_previous']='stagger_recovery' in e['clauses'] or wait
            elif payload=='breach_then_restore':make('recover',extra=1,amount=ward*share,bound=True)
            elif payload=='shield_then_breach_or_restore':
                make('shield',fraction=.5,amount=ward*share*.5,phase='shield_chain')
                p=make('followup',fraction=.5,extra=1);p['wait_previous']=True
            else:raise ValueError('未实现的固定功法效果：'+payload)
        if 'split_ally' in e['clauses'] and recipient!=owner:
            import copy
            for p in list(r['packets']):
                if p['channel'] not in {'shield','recover'}:continue
                p['share']/=2;p['initial_share']/=2;p['amount']/=2
                other=copy.deepcopy(p);other['recipient']=owner;r['packets'].append(other)
        if 'split_targets' in e['clauses']:
            import copy
            other=next((t for t in self.targets(owner) if t!=target),None)
            if other:
                for p in list(r['packets']):
                    if p['channel'] not in {'breach','strike','arm_afterburn'}:continue
                    p['share']/=2;p['initial_share']/=2;p['amount']/=2
                    second=copy.deepcopy(p);second['target']=other;r['packets'].append(second)
        if 'sequential_shield' in e['clauses']:
            import copy
            for p in list(r['packets']):
                if p['channel']!='shield':continue
                p['share']/=2;p['initial_share']/=2;p['amount']/=2;p['phase']='sequential'
                second=copy.deepcopy(p);second['wait_previous']=True;r['packets'].append(second)
        for p in r['packets']:
            if p['channel'] in {'shield','recover'}:
                p['amount']=self.support_amount(owner,p['recipient'],p['amount'])
        if payload in {'damage_to_shield','shield_then_breach_or_restore'}:
            for p in r['packets']:
                if p['channel']=='shield':p['expires']=p['starts']

    def pair_modifier(self,key,p,source,target,original):
        owner,b=self.books[key];r=self.records[key];e=b['effect'];channel=p['channel']
        if owner!=source or p['target']!=target:return 0.
        if channel not in {'strike','breach','sword','arm_afterburn'}:return 0.
        strength=self.strength(b);share=p['share']
        if channel=='sword':
            f=self.facts[owner]
            if f.get('broke_target')==target and f.get('broke_round',-10)>=self.round-2:
                strength+=.04+.005*(b['level']-1)
        if channel=='arm_afterburn':
            p.update(channel='afterburn',amount=min(1.,original)*strength*share,basis=min(1.,original),
                     starts=min(p['expires'],self.round+1),expires=min(p['expires'],self.round+2))
            return 0.
        gain=min(1.,original)*strength*share
        if channel=='breach':
            # The shared ordinary damage formula caps its breach term. Extra
            # breach improves that term; it is not another full damage multiplier.
            ratio=self.battle._ordinary_breach_ratios.get(self.battle.units[source].unit.side,
                self.battle.units[source].unit.power/max(1.,self.battle.units[target].unit.power))
            gain=min(1.,original)*((.88+min(.28,ratio*.13*(1+strength*share)))/(.88+min(.28,ratio*.13))-1)
        self.attack_packets.append((key,p,target,gain))
        return gain

    def forfeit_attack(self,source):
        for key in self.by_owner[source]:
            r=self.records[key]
            if r['forfeit_pending']:
                r['forfeit_pending']=False;r['forfeit_round']=self.round
            if r['forfeit_round']==self.round:return True
        return False

    def damage(self,source,target,amount):
        original=amount;gain=0.;reduction=0.
        if self.forfeit_attack(source):return 0.
        sources=[]
        for key in self.by_owner[source]:
            owner,b=self.books[key]
            for p in self.records[key]['packets']:
                if self.ready(key,p):
                    added=self.pair_modifier(key,p,source,target,original)
                    if added>0:sources.append(b['id'])
                    gain+=added
        self.hit_sources[source,target]=sources
        return max(0.,original+gain-min(original,reduction))

    def absorb(self,target,amount,contributions):
        attackers=[k for k,v in contributions if v>0]
        remaining_by_source={k:amount*v/max(1e-12,sum(v for _,v in contributions)) for k,v in contributions}
        original=amount
        for key in self.by_owner[target]:
            owner,b=self.books[key]
            for p in self.records[key]['packets']:
                if not self.ready(key,p) or p['channel'] not in {'guard','response'}:continue
                covered=[k for k in attackers if not p['bound'] or k==p['target']]
                if p['channel']=='response':covered=[k for k in covered if p['watch'] in self.hit_sources.get((k,target),[])]
                if not covered:continue
                flags=b['effect']['clauses'];r=self.records[key]
                if 'repeat_refund' in flags and (self.facts[owner].get('cast') or {}).get('count',0)<2:continue
                rebate=p['phase']=='rebate'
                covered_amount=sum(remaining_by_source[k] for k in covered)
                prevention=min(amount,covered_amount,original*(1-(1+self.strength(b)*p['share']*(.8 if rebate else 1))**(-.58)))
                actual=max(0.,min(self.battle.units[target].vitality,amount)-min(self.battle.units[target].vitality,amount-prevention))
                amount-=prevention
                for source in covered:remaining_by_source[source]*=1-prevention/max(1e-12,covered_amount)
                self.spent(key,p,event='guard',amount=actual,target=target)
                if rebate and actual>0:
                    index=p['receipt']-int('two_paid_cycle' in flags)
                    if index>=0:self.refund(key,index,.05)
        for key,(owner,b) in self.books.items():
            for p in self.records[key]['packets']:
                if p['recipient']!=target or p['channel']!='shield' or not self.ready(key,p):continue
                if 'next_incoming' in b['effect']['clauses']:
                    if self.derived_damage and not p['applied']:continue
                    if not self.derived_damage:p['applied']=True
                available=remaining_by_source.get(p['target'],0.) if p['bound'] else amount
                prevention=min(amount,available,p['amount'])
                if prevention<=0:continue
                before=p['amount'];p['amount']-=prevention;amount-=prevention
                actual=max(0.,min(self.battle.units[target].vitality,amount+prevention)-min(self.battle.units[target].vitality,amount))
                fraction=p['share']*(prevention/before)
                self.spent(key,p,fraction,event='absorbed',amount=actual,target=target)
                covered=[p['target']] if p['bound'] else [k for k in attackers if remaining_by_source[k]>0]
                if not self.derived_damage:
                    self.sequence+=1;self.facts[target]['shield_used_seq']=self.sequence
                    for source in covered:self.facts[source]['attacked_shield_seq']=self.sequence
                if p['amount']<=0:
                    self.barrier(target,covered,key)
                    if p['phase']=='sequential':
                        for follow in self.records[key]['packets']:
                            if follow['receipt']==p['receipt'] and follow['phase']=='sequential':follow['wait_previous']=False
                    if p['phase']=='shield_chain':
                        for follow in self.records[key]['packets']:
                            if follow['receipt']==p['receipt'] and follow['channel']=='followup':
                                channel='recover' if self.battle.units[owner].vitality<.75 else 'breach'
                                follow.update(channel=channel,starts=self.round+1,wait_previous=False,
                                              amount=self.support_amount(owner,follow['recipient'],b['effect']['ward_bp']/10000*follow['share']) if channel=='recover' else 0.)
                if p['bound']:remaining_by_source[p['target']]=max(0.,available-prevention)
                else:
                    for source in remaining_by_source:remaining_by_source[source]*=amount/max(1e-12,amount+prevention)
        return amount

    def finish_payloads(self):
        for key,(owner,b) in self.books.items():
            r=self.records[key];e=b['effect'];s=self.battle.units[owner]
            if not self.usable(owner):
                if e['delivery']!='interrupted_once_resume':
                    for p in r['packets']:p['share']=0.
                continue
            for p in r['packets']:
                if not self.ready(key,p):continue
                recipient=p['recipient'];beneficiary=self.battle.units[recipient]
                if not beneficiary.fighting:p['share']=0.;continue
                if p['channel']=='recover':
                    if p['phase']=='fragile' and self.facts[recipient].get('heavy_round',-10)>=r['receipts'][p['receipt']]['round']:
                        p['share']=0.;self.note(owner,b,'interrupted');continue
                    requested=min(p['amount'],max(0.,self.initial_state[recipient]-beneficiary.vitality))
                    before=beneficiary.vitality
                    self.battle._restore_state(recipient,requested,maximum_gain=requested)
                    self.spent(key,p,event='restored',amount=beneficiary.vitality-before,target=recipient)
                elif p['channel']=='cleanse':
                    status=self.debuff(owner,'aged_debuff' in e['clauses'])
                    if status is not None:
                        del self.battle.semantics.statuses[status]
                        self.spent(key,p,event='cleanse',amount=1.)
                elif p['channel']=='afterburn':
                    target=p['target']
                    if target not in self.targets(owner):p['share']=0.;continue
                    before=self.battle.units[target].vitality
                    # Derived damage deliberately does not call observed(): no
                    # recursive hit, loss, source or new preparation receipt.
                    amount=p['amount']
                    if self.battle.attack_tier(s)>=2:amount=self.battle._guard_state(target,amount)
                    self.derived_damage=True
                    try:
                        amount=self.battle.techniques.absorb(target,amount,[(owner,amount)])
                        self.battle._lose(target,amount,physical=False,body_fatal=True)
                        self.spent(key,p,event='strike',amount=before-self.battle.units[target].vitality,target=target)
                    finally:self.derived_damage=False
                elif p['channel']=='mobility' and p['applied'] and self.facts[owner].get('complete_round')==self.round:
                    self.spent(key,p,event='mobility',amount=self.strength(b)*p['share'])
            r['packets']=[p for p in r['packets'] if p['share']>1e-12]
