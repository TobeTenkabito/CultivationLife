"""Fixed-book scheduler over actual personal payments and ordinary receipts."""
import copy
import json
from .catalog_clauses import admits, choose
from .catalog_payloads import CatalogPayloads
from ...combat_costs import technique_cost


class CatalogRuntime(CatalogPayloads):
    def __init__(self, battle):
        self.battle = battle
        self.books = {}
        self.by_owner = {key:[] for key in battle.units}
        self.records = {}
        self.round = 0
        self.started = self.ended = 0
        self.sequence = 0
        self.events = []
        self.queue = []
        self.hit_sources = {}
        self.attack_packets = []
        self.ordinary_sides = None
        self.derived_damage = False
        self.facts = {k:{} for k in battle.units}
        self.observations = {k:{} for k in battle.units}
        self.initial_state = {k:s.vitality for k,s in battle.units.items()}
        for owner,s in battle.units.items():
            for b in s.unit.capabilities.technique_effects:
                if b['effect']['version'] != 3: continue
                key = json.dumps([owner,b['id']],ensure_ascii=False,separators=(',',':'))
                self.books[key] = (owner,b)
                self.by_owner[owner].append(key)
                self.records[key] = dict(used=0,last_cast=0,paid=0.,refunded=0.,receipts=[],packets=[],
                    opportunity=None,consumed=0,rotation=0,expired=0,completed=0,field=None,
                    forfeit_pending=False,forfeit_round=0,loss_seq=0,reset=False)
        self.capacities = {key:self.pool(owner,b)[1] for key,(owner,b) in self.books.items()}

    def usable(self, owner):
        s=self.battle.units[owner]
        return (self.battle._available(owner) and 'technique' not in s.restrictions
                and not self.battle._action_paused(owner) and
                (self.ordinary_sides[s.unit.side] if self.ordinary_sides is not None else self.battle._has_ordinary(s.unit.side)))

    def pool(self, owner, book):
        s=self.battle.units[owner]; c=s.unit.capabilities
        if book['effect']['resource']=='energy':
            return ('energy', (c.capacity if c.usable_capacity is None else c.usable_capacity) if c.resource_tier>=2 else 0., s.current)
        if c.resource_link=='legacy_mp':
            return 'energy', c.capacity, s.current
        return 'mana', c.mana_capacity, s.mana_current

    def change_resource(self, owner, book, delta):
        s=self.battle.units[owner]; kind,cap,current=self.pool(owner,book)
        after=max(0.,min(cap,current+delta))
        if kind=='energy': self.battle._energy(owner,after)
        else:
            s.mana_current=after
            s.technique_mp_spent=max(0.,s.technique_mp_spent+current-after)
        return after-current

    def note(self, owner, book, event, **data):
        self.events.append(dict(round=self.round,owner=owner,technique=book['id'],event=event,**data))
        self.events=self.events[-256:]
        labels={'paid':'运转付费','strike':'剑势追加','breach':'寻隙破法','absorbed':'护持承伤','guard':'守御减损',
                'restored':'回转态势','refunded':'返还实付法力','cleanse':'净除短效减益','mobility':'步势变换',
                'expired':'待用效果消散','interrupted':'运转被打断','prepared':'登记运转机会'}
        if event in labels:
            amount=data.get('amount')
            detail=f' {amount:.4g}' if amount is not None else ''
            self.battle.frame.events.append(f"{self.battle.units[owner].unit.name}《{book['name']}》{labels[event]}{detail}。")

    def targets(self, owner):
        s=self.battle.units[owner]; tier=self.battle.attack_tier(s)
        return [k for k,t in sorted(self.battle.units.items()) if t.unit.side!=s.unit.side and t.fighting
                and self.battle._can_reach(s,k) and tier>=self.battle.ward_tier(k)]

    def begin(self, number):
        if type(number) is not int or number<=self.round: raise ValueError('专属功法轮次必须递增')
        self.round=number;self.events=[];self.hit_sources={};self.attack_packets=[]
        self.expire_packets()

    def expire_packets(self):
        number=self.round
        for key,(owner,b) in self.books.items():
            r=self.records[key];e=b['effect']
            if r['opportunity'] and r['opportunity']['expires']<number:r['opportunity']=None
            for p in list(r['packets']):
                if p['expires']<number or (p['bound'] and p['target'] and not self.battle.units[p['target']].fighting):
                    if p['share']>0:
                        r['expired']+=1
                        if e['delivery']=='spent_receipt_on_expiry' and p['target'] and not self.battle.units[p['target']].fighting:
                            receipt=r['receipts'][p['receipt']]
                            if not receipt['spent']:self.refund(key,p['receipt'],.25)
                        self.note(owner,b,'expired')
                    p['share']=0.
            r['packets']=[p for p in r['packets'] if p['share']>1e-12]

    def debuff(self, owner, aged=False):
        semantics=self.battle.semantics
        if semantics is None:return None
        allowed={'ordinary.might','ordinary.guard','ordinary.breach','ordinary.mobility','ordinary.sense','ordinary.sustain',
                 'ordinary.dealt','ordinary.received'}
        for key,s in sorted(semantics.statuses.items(),key=lambda row:(row[1]['starts'],row[0])):
            mods=s['modifiers']
            # Only finite ordinary numerical debuffs qualify. Controls and
            # field rules never enter this registry of status modifiers.
            negative = mods and all(m['channel'] in allowed and
                (m['value']>0 if m['channel']=='ordinary.received' else m['value']<0) for m in mods)
            if (s.get('dispellable',False) and negative and s['owner']==owner and s['origin']!=owner and s['starts']<=self.round<=s['expires']
                    and s['expires']-self.round<=1 and (not aged or s['starts']<self.round)
                    and mods and all(m['channel'] in allowed for m in mods)):
                return key
        return None

    def _offer(self, key, fact):
        owner,b=self.books[key];r=self.records[key];e=b['effect']
        if not self.usable(owner) or r['opportunity'] or r['packets'] or r['used']>=e['uses']:return
        if r['used'] and self.round<=r['last_cast']+e['cooldown']:return
        if fact['seq']<=r['consumed']:return
        target=fact.get('target')
        valid=self.targets(owner)
        if target not in valid:target=valid[0] if valid else None
        if not target:return
        fact = dict(fact, target=target)
        if not admits(self,owner,b,r,fact):return
        cast=self.facts[owner].get('cast') or {}
        if 'source_latest' in e['clauses']:cast=dict(cast,count=cast.get('streak',0))
        if e['payload'].startswith('repeat_'):
            if cast.get('seq',0)<=r['consumed']:return
            if e['payload']=='repeat_paid_cast' and cast.get('paid_count',0)<2:return
            if e['payload']=='repeat_initiative_breach' and cast.get('count',0)<2:return
            if e['payload'] in {'repeat_source_response','repeat_initiative_breach'} and cast.get('target')!=owner:return
        flags=e['clauses']
        if 'first_target' in flags:target=self.facts[owner].get('first_target')
        loss=self.loss_receipt(key) if e['payload'] in {'receipt_shield','delayed_loss_recovery'} else None
        if e['payload'] in {'receipt_shield','delayed_loss_recovery'}:
            if not loss:return
            target=loss['source']
        if target not in valid:return
        r['opportunity']=dict(at=self.round,expires=self.round+3,seq=fact['seq'],target=target,
                             first=self.facts[owner].get('first'),source=(self.facts[owner].get('cast') or {}).get('book'),
                             kind=fact['kind'],paused=0,loss_seq=loss['seq'] if loss else 0)
        self.note(owner,b,'prepared',target=target)

    def observed_source(self,key):
        owner,b=self.books[key];op=self.records[key]['opportunity']
        if op and op['source']:
            key=json.dumps([op['target'],op['source']],separators=(',',':'))
            row=self.observations[owner].get(key,{})
            if 'source_latest' in b['effect']['clauses']:
                row=dict(row,count=(self.facts[owner].get('cast') or {}).get('streak',0))
            return dict(row,source=op['target'],book=op['source'])
        return self.facts[owner].get('cast') or {}

    def offer(self, owner, kind, target=None):
        self.sequence+=1
        fact=dict(kind=kind,target=target,seq=self.sequence)
        triggers={'opening':{'paid_preparation'},'incoming':{'actual_incoming','body_endured','ordinary_complete'},
                  'outgoing':{'actual_outgoing','ordinary_complete','existing_form_exchange'},'cast':{'observed_cast'}}
        for key in self.by_owner[owner]:
            actor,b=self.books[key]
            r=self.records[key]
            rotating=b['effect']['payload']=='five_step_rotation' and r['completed']>0 and kind=='opening'
            if actor==owner and (b['effect']['trigger'] in triggers[kind] or rotating):self._offer(key,fact)

    def start(self, factors):
        if self.started==self.round:return
        self.started=self.round
        for owner,s in self.battle.units.items():
            f=self.facts[owner]
            old=f.get('field')
            if s.active_voisinage:f['field_paid_round']=self.round
            elif old:f['field_ended_round']=self.round
            f['field']=s.active_voisinage
            if self.usable(owner):self.offer(owner,'opening')
        for key,(owner,b) in self.books.items():
            r=self.records[key];e=b['effect'];op=r['opportunity']
            if not self.usable(owner):
                if op:
                    if e['delivery']=='interrupted_once_resume' and not op['paused']:op['paused']=1
                    else:r['opportunity']=None
                for p in r['packets']:
                    if e['delivery']=='interrupted_once_resume' and not p['paused']:p['paused']=1
                    else:p['share']=0.
                continue
            if op and e['covenant']=='confirm_later' and self.round==op['at']:continue
            if op:
                self.commit(key)
        # All casts observed at this boundary are published after every caster
        # has committed; dictionary order cannot create same-boundary reactions.
        self.flush_casts()
        for key,(owner,b) in self.books.items():
            if not self.usable(owner):continue
            r=self.records[key];s=self.battle.units[owner]
            for p in r['packets']:
                if not self.ready(key,p):continue
                if p['channel']=='choice_flame':
                    shield=s.vitality<self.initial_state[owner]*.5
                    p['channel']='shield' if shield else 'strike'
                    p['amount']=self.support_amount(owner,p['recipient'],b['effect']['ward_bp']/10000*p['share']) if shield else 0.
                if p['channel']=='mobility':
                    factors[s.unit.side]['mobility']+=p['share']*self.strength(b)*s.unit.power/self.battle.totals[s.unit.side]
                    p['applied']=True
            if any(p['burden'] for p in r['packets']):
                factors[s.unit.side]['breach']-=.06*s.unit.power/self.battle.totals[s.unit.side]

    def commit(self, key):
        owner,b=self.books[key];r=self.records[key];e=b['effect'];op=r['opportunity'];s=self.battle.units[owner]
        valid = self.targets(owner)
        if op['target'] not in valid:
            strict=(e['covenant']=='observed_target_binding' or 'source_bound' in e['clauses']
                    or e['payload'].startswith('repeat_') or e['payload'] in {'receipt_shield','delayed_loss_recovery','barrier_followup','breach_then_restore','broken_shield_breach'})
            if e['delivery']=='retarget_before_commit' and valid and not strict:op['target']=valid[0]
            else:r['opportunity']=None;return
        branch=choose(self,owner,b,r)
        if not self.useful(key,branch):return
        capacity=self.capacities[key];cost=technique_cost(b,capacity)
        if capacity<=0 or self.pool(owner,b)[2]+1e-12<cost:return
        sacrifice=.002 if e['covenant']=='pay_state_nontriggering' else 0.
        if sacrifice and s.vitality<=sacrifice:return
        paid=-self.change_resource(owner,b,-cost)
        if sacrifice:self.battle._lose(owner,sacrifice,physical=False)
        r['used']+=1;r['last_cast']=self.round;r['paid']+=paid;r['consumed']=op['seq']
        receipt=len(r['receipts'])
        r['receipts'].append(dict(paid=paid,refunded=0.,spent=0.,success=False,round=self.round))
        if 'forgo_attack' in e['clauses']:r['forfeit_pending']=True
        self.make_packets(key,receipt,branch)
        r['opportunity']=None
        self.note(owner,b,'paid',amount=paid,resource=e['resource'])
        self.queue.append((owner,b['id'],True,False,None))

    def strength(self, book):
        return (.08+.01*(book['level']-1)) if book['effect']['prestige'] else book['effect']['strength_bp']/10000

    def ready(self,key,p):
        owner,b=self.books[key];s=self.battle.units[owner];e=b['effect']
        if not self.usable(owner) or p['share']<=0 or not p['starts']<=self.round<=p['expires']:return False
        if p['burden'] or p['wait_previous']:return False
        if p['bound'] and p['target'] and not self.battle.units[p['target']].fighting:return False
        if e['category']=='transformation' and not s.unit.capabilities.technique_context.get('form'):return False
        if e['delivery']=='initiative_reversal_gate' and self.facts[owner].get('first')==p['first']:return False
        if 'target_exchanged' in e['clauses'] and self.facts[p['target']].get('complete_round',0)<self.records[key]['receipts'][p['receipt']]['round']:return False
        return True

    def spent(self,key,p,fraction=None, *, event=None, amount=0., target=None):
        owner,b=self.books[key];r=self.records[key];receipt=r['receipts'][p['receipt']]
        fraction=p['share'] if fraction is None else min(p['share'],max(0.,fraction))
        p['share']=max(0.,p['share']-fraction);receipt['spent']+=fraction
        first_success=amount>0 and not receipt['success']
        if first_success:
            receipt['success']=True;r['completed']+=1
            if b['effect']['payload'] in {'alternating_choice','five_step_rotation'}:r['rotation']+=1
            for successor in r['packets']:
                if successor['receipt']==p['receipt'] and successor['wait_previous'] and successor['channel']!='followup' and successor['phase']!='sequential':
                    successor['wait_previous']=False
                    successor['starts']=min(successor['expires'],self.round+1)
        if first_success and not self.derived_damage:
            self.queue.append((owner,b['id'],False,True,target))
        if amount>0 and event:self.note(owner,b,event,amount=amount,target=target)

    def refund(self,key,receipt_index,ratio):
        owner,b=self.books[key];r=self.records[key];receipt=r['receipts'][receipt_index]
        if 'mana_refund_only' in b['effect']['clauses'] and b['effect']['resource']!='mana':return
        allowance=min(max(0.,receipt['paid']*ratio-receipt['refunded']),max(0.,self.capacities[key]*.02-r['refunded']),max(0.,self.capacities[key]*.01-receipt['refunded']))
        refunded=self.change_resource(owner,b,allowance)
        receipt['refunded']+=refunded;r['refunded']+=refunded
        if refunded:self.note(owner,b,'refunded',amount=refunded)

    def initiative(self,player_first):
        for owner,s in self.battle.units.items():
            if not self.usable(owner):continue
            f=self.facts[owner];first=player_first if s.unit.side=='player' else not player_first
            f['changed']='first' in f and f['first']!=first
            f['first']=first;f['ever_second']=f.get('ever_second',False) or not first
            for key in self.by_owner[owner]:
                actor,b=self.books[key]
                for p in self.records[key]['packets']:
                    if p['first'] is None:p['first']=first
                    if b['effect']['payload']=='initiative_choice' and p['channel'] in {'guard','breach'}:
                        p['channel']='breach' if first else 'guard'

    def observed(self,source,target,actual):
        for key,p,victim,gain in list(self.attack_packets):
            if self.books[key][0]==source and victim==target:
                self.spent(key,p,event='breach' if p['channel']=='breach' else 'strike',
                           amount=min(gain,actual),target=target)
                self.attack_packets.remove((key,p,victim,gain))
        if actual<=0:return
        self.sequence+=1;seq=self.sequence
        a,d=self.facts[source],self.facts[target]
        a.update(hit_round=self.round,hit_seq=seq,hit_target=target,complete_round=self.round)
        d.update(hurt_round=self.round,hurt_seq=seq,hurt_source=source,hurt_amount=actual,complete_round=self.round)
        losses=d.setdefault('losses',[])
        losses.append(dict(round=self.round,seq=seq,source=source,amount=actual))
        d['losses']=[row for row in losses[-32:] if row['round']>=self.round-2]
        a.setdefault('first_target',target);d.setdefault('first_target',source)
        if actual>.04:d['heavy_round']=self.round
        self.offer(source,'outgoing',target);self.offer(target,'incoming',source)
        for key in self.by_owner[source]+self.by_owner[target]:
            owner,b=self.books[key]
            for p in self.records[key]['packets']:
                if p['burden']:
                    p['burden']=False
                    if self.round+1>p['expires']:p['share']=0.
                    else:p['starts']=max(p['starts'],self.round+1)

    def barrier(self,owner,attackers,receipt):
        if self.derived_damage:return
        self.sequence+=1
        self.facts[owner].update(broken_seq=self.sequence,broken_round=self.round,broken_source=attackers[0] if attackers else None)
        for source in attackers:
            self.facts[source].update(broke_seq=self.sequence,broke_round=self.round,broke_target=owner)
        self.note_barrier=receipt

    def flush_casts(self):
        queued,self.queue=self.queue,[]
        for owner,book,paid,actual,target,*receipt in queued:
            self.observe_cast(owner,book,paid=paid,actual=actual,target=target,receipt=receipt[0] if receipt else None)

    def observe_cast(self,owner,book,*,paid=False,actual=True,target=None,receipt=None):
        source=self.battle.units[owner]
        if not source.fighting:return
        for observer,s in self.battle.units.items():
            if (s.unit.side==source.unit.side or not s.fighting or not self.battle._can_reach(s,owner)
                    or self.battle._semantic_environment.get('environment.forbidden_sense')):continue
            records=self.observations[observer];key=json.dumps([owner,book],separators=(',',':'))
            previous=self.facts[observer].get('cast') or {}
            info=records.get(key,dict(count=0,paid_count=0,ordinal=len(records)+1,receipts=[]))
            if actual and receipt is not None:
                if receipt in info['receipts']:continue
                info['receipts'].append(receipt)
            self.sequence+=1
            info.update(count=info['count']+int(actual),paid_count=info['paid_count']+int(paid),round=self.round,
                        target=target,seq=self.sequence)
            records[key]=info
            if len(records)>128:del records[next(iter(records))]
            self.facts[observer].update(source_kinds=len(records),cast=dict(source=owner,book=book,paid=paid,
                actual=actual,changed=bool(previous and (previous.get('book'),previous.get('source'))!=(book,owner)),
                streak=(previous.get('streak',0)+int(actual) if (previous.get('book'),previous.get('source'))==(book,owner) else int(actual)),**info))
            if actual:
                for book_key in self.by_owner[observer]:
                    _,listening=self.books[book_key]
                    if 'source_latest' not in listening['effect']['clauses']:continue
                    record=self.records[book_key];op=record['opportunity']
                    if op and (op['target'],op['source'])!=(owner,book):record['opportunity']=None
                    for p in record['packets']:
                        if (p['target'],p['watch'])!=(owner,book):p['share']=0.
                    record['packets']=[p for p in record['packets'] if p['share']>1e-12]
                self.offer(observer,'cast',owner)
            elif paid:
                self.sequence+=1
                for key in self.by_owner[observer]:
                    actor,b=self.books[key]
                    if actor==observer and (b['effect']['payload']=='repeat_paid_cast' or 'paid_source' in b['effect']['clauses']):
                        self._offer(key,dict(kind='cast',target=owner,seq=self.sequence))

    def finish(self):
        if self.ended==self.round:return
        self.ended=self.round
        self.finish_payloads()
        self.expire_packets()
        self.flush_casts()

    def report(self):
        return dict(events=copy.deepcopy(self.events),receipts={k:dict(used=r['used'],paid=r['paid'],refunded=r['refunded'])
                    for k,r in self.records.items() if r['used']})

    def dump(self):
        return copy.deepcopy(dict(version=1,round=self.round,started=self.started,ended=self.ended,sequence=self.sequence,
            records=self.records,facts=self.facts,observations=self.observations,capacities=self.capacities,initial_state=self.initial_state))

    def restore(self,value):
        from .catalog_snapshot import restore
        restore(self,value)
