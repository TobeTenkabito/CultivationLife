"""One adapter for frozen lineage effects and the complete fixed-book interpreter."""
from .techniques import TechniqueRuntime
from .catalog_runtime import CatalogRuntime


class TechniqueDispatch(TechniqueRuntime):
    def __init__(self,battle):
        super().__init__(battle)
        self.catalog=CatalogRuntime(battle) if any(b['effect']['version']==3 for s in battle.units.values()
                                                 for b in s.unit.capabilities.technique_effects) else None
        self.original_shares={}
        self.legacy_pending={}

    def begin(self,number):
        super().begin(number);self.original_shares={};self.legacy_pending={}
        if self.catalog:self.catalog.begin(number)

    def note(self,owner,book,event,**data):
        super().note(owner,book,event,**data)
        if self.catalog and not self.catalog.derived_damage and data.get('amount',0)>0:
            if event=='paid':self.catalog.queue.append((owner,book['id'],True,False,None))
            elif event in {'strike','breach'}:
                self.legacy_pending[owner,book['id'],data['receipt']]=data.get('target')
            elif event in {'absorbed','restored'}:
                self.catalog.queue.append((owner,book['id'],False,True,data.get('target'),data['receipt']))

    def execution(self,owner):
        if not self.catalog:return
        for key,(actor,b) in self.catalog.books.items():
            if actor==owner and b['effect']['covenant']=='no_execution_window':
                for p in self.catalog.records[key]['packets']:p['share']=0.

    def start(self,factors):
        super().start(factors)
        if self.catalog:self.catalog.start(factors)

    def damage(self,source,target,amount):
        if self.catalog and self.catalog.forfeit_attack(source):
            self.original_shares[source,target]=1.
            return 0.
        old=super().damage(source,target,amount)
        result=old if not self.catalog else max(0.,old+self.catalog.damage(source,target,amount)-amount)
        if self.catalog:
            self.catalog.hit_sources.setdefault((source,target),[]).extend(book for (owner,book,receipt),victim in self.legacy_pending.items()
                if owner==source and victim in (None,target))
        self.original_shares[source,target]=min(1.,amount/max(1e-12,result))
        return result

    def absorb(self,target,amount,contributions=()):
        before={key:sum(p['remaining'] for p in r['packets']) for key,r in self.records.items()
                if self.books[key][0]==target}
        result=super().absorb(target,amount)
        if self.catalog:
            if result<amount and not self.catalog.derived_damage:
                self.catalog.sequence+=1
                self.catalog.facts[target]['shield_used_seq']=self.catalog.sequence
                for source,value in contributions:
                    if value>0:self.catalog.facts[source]['attacked_shield_seq']=self.catalog.sequence
            for key,remaining in before.items():
                if remaining>0 and sum(p['remaining'] for p in self.records[key]['packets'])<=0:
                    self.catalog.barrier(target,[k for k,v in contributions if v>0],key)
            result=self.catalog.absorb(target,result,contributions)
        return result

    def observed(self,source,target,actual):
        original=actual*self.original_shares.get((source,target),1.)
        super().observed(source,target,original)
        if self.catalog:
            self.catalog.observed(source,target,original)
            if actual>0:
                for (owner,book,receipt),victim in list(self.legacy_pending.items()):
                    if owner==source and victim in (None,target):
                        self.catalog.queue.append((owner,book,False,True,target,receipt))
                        del self.legacy_pending[owner,book,receipt]

    def attempted(self,actors):
        if not self.catalog:return
        self.catalog.ordinary_sides=None
        for key,(owner,b) in self.catalog.books.items():
            if owner not in actors or 'next_attack_only' not in b['effect']['clauses']:continue
            for p in self.catalog.records[key]['packets']:
                if p['starts']<=self.catalog.round and not p['burden']:p['share']=0.

    def ordinary_boundary(self,sides):
        if self.catalog:self.catalog.ordinary_sides=sides

    def initiative(self,first):
        if self.catalog:self.catalog.initiative(first)

    def finish(self):
        if self.catalog:self.catalog.finish()

    def dump(self):
        legacy=super().dump()
        return dict(version=3,legacy=legacy,catalog=self.catalog.dump()) if self.catalog else legacy

    def restore(self,value):
        if self.catalog:
            if not isinstance(value,dict) or set(value)!={'version','legacy','catalog'} or value['version']!=3:
                raise ValueError('固定功法续战缺失原付款与运转记录')
            super().restore(value['legacy']);self.catalog.restore(value['catalog'])
        else:super().restore(value)

    def report(self):
        from .technique_presentation import presentation
        legacy=super().report()
        if self.catalog:
            new=self.catalog.report()
            legacy['events']+=new['events'];legacy['receipts'].update(new['receipts'])
        return presentation(self,legacy)
