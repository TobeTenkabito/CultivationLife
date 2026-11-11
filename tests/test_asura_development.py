"""Paid original-asset development: replay, custody, stocks and handover attacks."""
import copy
import hashlib
import pytest
from test_asura_governorship import setup,command
from test_asura_politics import prepare
from cultivation_life.models import GameState
from cultivation_life.rules import add_item
from cultivation_life.system import institution_authority as authority,institution_operations as operations
from cultivation_life.system.asura_governorship import rules,development,management,actions,presentation
from cultivation_life.system.economy.ledger import balance
from cultivation_life.system.building_destruction import destroy


def act(e,g,operation):
    latest=e._load(g.id);row=rules.offices(latest)[0]
    q=development.quote(latest,row,operation) if operation!='cancel' else {'token':''}
    return command(e,g,'development',office=row['id'],operation=operation,quote=q['token'])[0]


def ready(e,g):
    g,row,people=prepare(e,g)
    # Fixture funds the original operator; production never creates this receipt.
    g.economy_v2['accounts']['operator:asura:'+row['location']]['balance']=10**12
    for product in operations.market(g,row)['commodities'].values():product['stock']=10000
    e.store.save(g)
    return g,row,people


def supply(e,g,*,bureau=False):
    if bureau:g=act(e,g,'facility:supply')
    row=rules.offices(g)[0];m=operations.market(g,row)
    from cultivation_life.economy_content import material_id
    item=material_id('asura',9,'ore_structure');m['commodities'][item]['stock']=0
    m['commodities'][item]['target']=100
    g.economy_v2['accounts']['market:'+m['id']]['balance']=10**12
    add_item(g.player,item,30);e.store.save(g)
    return act(e,g,'supply:ore_structure'),item


def test_city_real_receipt_once_per_year_and_original_owner(setup):
    e,g=setup;g,row,_=ready(e,g)
    owner=copy.deepcopy(rules.cities(g)[0]['owner'])
    g=act(e,g,'city:exchange');row=rules.offices(g)[0]
    with pytest.raises(ValueError,match='真实年份'):act(e,g,'city:settle')
    g.player.age+=1;e.store.save(g)
    q=development.quote(g,row,'city:settle');before=balance(g,row['wallet']);purse=balance(g,'player')
    g=act(e,g,'city:settle');row=rules.offices(g)[0];state=operations.book(row)
    salary=(q['receipt']-q['coins'])*5//100
    assert balance(g,row['wallet'])==before+q['receipt']-q['coins']-salary
    assert balance(g,'player')==purse+salary and state['salary']==salary
    assert rules.cities(g)[0]['owner']==owner
    before=e.store._path(g.id).read_bytes()
    with pytest.raises(ValueError):act(e,g,'city:settle')
    assert hashlib.sha256(e.store._path(g.id).read_bytes()).digest()==hashlib.sha256(before).digest()
    # A long absence produces exactly one current receipt, never back pay.
    g.player.age+=100;e.store.save(g);g=act(e,g,'city:settle')
    assert operations.book(rules.offices(g)[0])['settlements']==2
    GameState.from_dict(g.to_dict())


def test_facilities_charge_original_stock_and_rebuild_full_cost(setup):
    e,g=setup;g,row,_=ready(e,g);before=balance(g,row['wallet'])
    q=development.quote(g,row,'facility:training');m=operations.market(g,row)
    stock={k:m['commodities'][k]['stock'] for k in q['materials']}
    g=act(e,g,'facility:training');row=rules.offices(g)[0]
    assert balance(g,row['wallet'])==before-q['total']
    assert all(operations.market(g,row)['commodities'][k]['stock']==stock[k]-n for k,n in q['materials'].items())
    with pytest.raises(ValueError,match='已经建成'):act(e,g,'facility:training')
    b=rules.building(g,row);destroy(g,b,source='war');e.store.save(g)
    with pytest.raises(ValueError,match='修复'):act(e,g,'city:exchange')
    bill=actions.bill(g,row)
    assert bill['coins']>q['coins'] and all(bill['materials'][k]>n for k,n in q['materials'].items())
    g,_=command(e,g,'build',office=row['id'],quote=bill['token'],total=bill['total'])
    assert rules.building(g,rules.offices(g)[0])['office_facilities'][0]['id']=='training'
    GameState.from_dict(g.to_dict())


def test_training_original_person_and_cooldown_and_stale_stats(setup):
    e,g=setup;g,row,people=ready(e,g)
    g=act(e,g,'facility:training')
    g,_=command(e,g,'staff',office=row['id'],person=people[0].id)
    row=rules.offices(g)[0]
    from cultivation_life.relationship_records import find_person
    person=find_person(g,people[0].id);person.divine_sense_rank=80
    # Matching high-tier material is actually stocked by the fixture.
    target,q=operations.training(g,row,person.id,'sense')
    for key in q['materials']:operations.market(g,row)['commodities'][key]['stock']=20
    e.store.save(g);q=development.quote(g,row,'train:sense')
    person.divine_sense_rank+=1;e.store.save(g)
    with pytest.raises(ValueError,match='报价'):command(e,g,'development',office=row['id'],operation='train:sense',quote=q['token'])
    before=person.divine_sense_rank;opportunity=g.player.opportunity
    g=act(e,g,'train:sense');assert find_person(g,person.id).divine_sense_rank>before
    assert g.player.opportunity==opportunity
    with pytest.raises(ValueError,match='二十'):act(e,g,'train:sense')
    GameState.from_dict(g.to_dict())


def test_supply_three_periods_real_goods_money_refund_and_no_refresh(setup):
    e,g=setup;g,row,_=ready(e,g);g,item=supply(e,g,bureau=True)
    row=rules.offices(g)[0];c=operations.book(row)['contract'];source=c['source']
    assert c['funded']==3*c['price'] and balance(g,c['wallet'])==c['funded']
    with pytest.raises(ValueError,match='交货期'):act(e,g,'deliver')
    g.player.age=c['next'];e.store.save(g)
    g=e._load(g.id);row=rules.offices(g)[0]
    market_stock=operations.market(g,row)['commodities'][item]['stock']
    before=sum(i.quantity for i in g.player.inventory if i.id==item)
    cash=balance(g,'player');fee=c['fee'];net=c['price']-fee
    g=act(e,g,'deliver');row=rules.offices(g)[0];c=operations.book(row)['contract']
    assert sum(i.quantity for i in g.player.inventory if i.id==item)==before-c['quantity']
    assert operations.market(g,row)['commodities'][item]['stock']==market_stock+c['quantity']
    assert balance(g,'player')==cash+net-net//10+(net//10)*5//100
    assert c['completed']==1 and balance(g,c['wallet'])==2*c['price']
    with pytest.raises(ValueError,match='交货期'):act(e,g,'deliver')
    market_cash=balance(g,source);g=act(e,g,'cancel');row=rules.offices(g)[0];c=operations.book(row)['contract']
    assert balance(g,source)==market_cash+2*c['price'] and balance(g,c['wallet'])==0
    assert c['paid']+c['refunded']==c['funded']
    with pytest.raises(ValueError,match='五十'):act(e,g,'supply:ore_structure')
    with pytest.raises(ValueError):act(e,g,'cancel')
    GameState.from_dict(g.to_dict())


@pytest.mark.parametrize('ending',['revoked','expired','disabled'])
def test_contract_handover_returns_once_and_never_moves_goods(setup,monkeypatch,ending):
    e,g=setup;g,row,_=ready(e,g);g,item=supply(e,g)
    row=rules.offices(g)[0];c=operations.book(row)['contract'];cash=balance(g,c['source'])
    inventory=copy.deepcopy(g.player.inventory)
    if ending=='revoked':authority.revoke(g,row)
    elif ending=='expired':g.player.age=row['expires']+1
    else:monkeypatch.setattr(rules,'enabled',lambda:False)
    management.advance(g,e.maps);management.advance(g,e.maps)
    assert c['status']=='cancelled' and balance(g,c['source'])==cash+c['funded']
    assert g.player.inventory==inventory
    GameState.from_dict(g.to_dict())


def test_new_views_are_pure_and_foreign_or_private_city_cannot_operate(setup):
    e,g=setup;g,row,_=ready(e,g);g=act(e,g,'facility:supply');row=rules.offices(g)[0]
    before=copy.deepcopy(g.to_dict());presentation.public(g);presentation.public(g)
    assert g.to_dict()==before
    g.player.location_id='ten_thousand_battle_city';e.store.save(g)
    with pytest.raises(ValueError,match='亲临'):act(e,g,'city:exchange')
    assert development.public(g,row) is None
    g.player.location_id=row['location'];city=rules.cities(g)[0]
    from cultivation_life.system.building_projects import persist
    persist(g,city)['owner']=dict(kind='player',id=g.id);e.store.save(g)
    with pytest.raises(ValueError,match='许可'):act(e,g,'city:exchange')


def test_earned_revenue_can_be_remitted_without_corrupting_save(setup):
    e,g=setup;g,row,_=ready(e,g);g=act(e,g,'city:exchange')
    g.player.age+=1;e.store.save(g);g=act(e,g,'city:settle');row=rules.offices(g)[0]
    authority.return_funds(g,row)
    assert balance(g,row['wallet'])==0
    GameState.from_dict(g.to_dict())


def test_garrison_policy_transfers_only_new_surplus_to_original_army(setup):
    from test_asura_military import recruit
    from cultivation_life.system import institution_garrisons as troops
    e,g=setup;g,row,_=ready(e,g);g=act(e,g,'city:exchange')
    g,row,_=recruit(e,g,count=1);g=act(e,g,'policy:garrison')
    g.player.age+=1;e.store.save(g);g=e._load(g.id);row=rules.offices(g)[0]
    q=development.quote(g,row,'city:settle');profit=q['receipt']-q['coins']
    original=balance(g,troops.state(row)['wallet']);funds=balance(g,row['wallet'])
    g=act(e,g,'city:settle');row=rules.offices(g)[0]
    assert balance(g,troops.state(row)['wallet'])==original+profit*40//100
    assert balance(g,row['wallet'])==funds+profit-profit*40//100-profit*5//100
    GameState.from_dict(g.to_dict())


@pytest.mark.parametrize('invalid',['dead','displaced'])
def test_automatic_funding_rechecks_original_guard_not_stale_roster(setup,invalid):
    from test_asura_military import recruit
    from cultivation_life.system import institution_garrisons as troops
    from cultivation_life.relationship_records import find_person
    from cultivation_life.system.economy.ledger import transfer_value
    e,g=setup;g,row,_=ready(e,g);g,row,people=recruit(e,g,count=1)
    state=operations.mutable(row);state['policy']='garrison'
    # An actual finite operating receipt is ready to distribute, but the
    # original NPC became invalid before the annual roster reconciliation.
    transfer_value(g,'market:asura:'+row['location'],row['wallet'],100000,'测试原实际经营收款')
    state['income']+=100000
    n=find_person(g,people[0].id)
    if invalid=='dead':n.alive=False
    else:n.location_id='ten_thousand_battle_city'
    army=balance(g,troops.state(row)['wallet']);cash=balance(g,row['wallet'])
    development.distribute(g,row,100000)
    assert balance(g,troops.state(row)['wallet'])==army
    assert balance(g,row['wallet'])==cash-5000


def test_successor_cannot_claim_predecessor_performance(setup):
    e,g=setup;g,row,_=ready(e,g)
    state=operations.mutable(row);state.update(settlements=10,income=1000000,last_performance=g.player.age)
    authority.relinquish(g,row,'player')
    authority.nominate(g,row,'player',500);authority.assume(g,row,'player',row['world'],row['location'])
    assert state['term_baseline']==10
    g.player.age+=50;e.store.save(g)
    with pytest.raises(ValueError,match='本任须完成'):act(e,g,'reward')


def test_no_unfunded_contract_or_advance_personal_salary(setup):
    e,g=setup;g,row,_=ready(e,g)
    from cultivation_life.economy_content import material_id
    m=operations.market(g,row);item=material_id('asura',9,'ore_structure')
    m['commodities'][item].update(stock=0,target=100)
    g.economy_v2['accounts']['market:'+m['id']]['balance']=0;e.store.save(g)
    e._load(g.id)  # Settle normal load normalization before testing command atomicity.
    saved=e.store._path(g.id).read_bytes()
    with pytest.raises(ValueError,match='实款不足'):act(e,g,'supply:ore_structure')
    assert hashlib.sha256(e.store._path(g.id).read_bytes()).digest()==hashlib.sha256(saved).digest()
    purse=balance(g,'player');g=act(e,g,'policy:tribute')
    assert balance(g,'player')==purse and operations.book(rules.offices(g)[0])['salary']==0


def test_public_training_rejects_occupied_or_remote_original_staff(setup):
    e,g=setup;g,row,people=ready(e,g);g=act(e,g,'facility:training')
    g,_=command(e,g,'staff',office=row['id'],person=people[0].id)
    from cultivation_life.relationship_records import find_person
    n=find_person(g,people[0].id);n.location_id='ten_thousand_battle_city';e.store.save(g)
    saved=e.store._path(g.id).read_bytes()
    with pytest.raises(ValueError,match='不在约定'):act(e,g,'train:sense')
    assert hashlib.sha256(e.store._path(g.id).read_bytes()).digest()==hashlib.sha256(saved).digest()


def test_older_dlc_without_new_rules_hides_features_and_keeps_cleanup(setup,monkeypatch):
    e,g=setup;g,row,_=ready(e,g)
    with monkeypatch.context() as patch:
        patch.setattr(development,'config',lambda:{})
        assert development.public(g,row) is None
        with pytest.raises(ValueError,match='未启用'):development.quote(g,row,'city:exchange')
    g,_=supply(e,g);row=rules.offices(g)[0]
    monkeypatch.setattr(development,'config',lambda:{})
    assert [o['id'] for o in development.public(g,row)['options']]==['cancel']
    development.advance(g,row)
    assert operations.book(row)['contract']['status']=='cancelled'


def test_last_installment_must_precede_exclusive_term_end(setup):
    e,g=setup;g,row,_=ready(e,g)
    from cultivation_life.economy_content import material_id
    item=material_id('asura',9,'ore_structure');m=operations.market(g,row)
    m['commodities'][item].update(stock=0,target=100)
    g.economy_v2['accounts']['market:'+m['id']]['balance']=10**12
    row['expires']=g.player.age+10;e.store.save(g)
    with pytest.raises(ValueError,match='剩余任期'):act(e,g,'supply:ore_structure')
    loaded=e.store.load(g.id);scope=rules.offices(loaded)[0]
    assert operations.book(scope)['contract'] is None
    assert not any(k.startswith('institution-contract:') for k in loaded.economy_v2['accounts'])
    scope['expires']+=1
    assert not development.quote(loaded,scope,'supply:ore_structure')['reason']


def test_content_fee_is_reserved_in_original_contract_not_hardcoded_in_base(setup,monkeypatch):
    e,g=setup;g,row,_=ready(e,g)
    cfg=copy.deepcopy(development.config());cfg['consignment_fee_percent']=25
    with monkeypatch.context() as patch:
        patch.setattr(development,'config',lambda:cfg)
        g,_=supply(e,g)
    row=rules.offices(g)[0];c=operations.book(row)['contract']
    assert c['service_percent']==25
    g.player.age=c['next'];e.store.save(g);g=e._load(g.id)
    purse=balance(g,'player');net=c['price']-c['fee'];fee=net*25//100
    g=act(e,g,'deliver');row=rules.offices(g)[0]
    assert operations.book(row)['income']==fee
    assert balance(g,'player')==purse+net-fee+fee*5//100


def test_failed_original_inventory_removal_cannot_mint_delivery(setup):
    e,g=setup;g,row,_=ready(e,g);g,item=supply(e,g)
    row=rules.offices(g)[0];c=operations.book(row)['contract']
    g.player.age=c['next']
    # Duplicate partial stacks can satisfy a total count but cannot satisfy
    # the original raw-material removal operation's single-stack contract.
    original=next(i for i in g.player.inventory if i.id==item);original.quantity=2
    g.player.inventory.append(copy.deepcopy(original));e.store.save(g);g=e._load(g.id)
    saved=e.store._path(g.id).read_bytes()
    with pytest.raises(ValueError,match='未能扣除'):act(e,g,'deliver')
    assert hashlib.sha256(e.store._path(g.id).read_bytes()).digest()==hashlib.sha256(saved).digest()
    loaded=e.store.load(g.id);contract=operations.book(rules.offices(loaded)[0])['contract']
    assert contract['completed']==0 and balance(loaded,contract['wallet'])==contract['funded']


def test_performance_needs_new_receipt_not_new_application(setup):
    e,g=setup;g,row,_=ready(e,g);g=act(e,g,'city:exchange')
    for delta in (1,1,50):
        g.player.age+=delta;e.store.save(g);g=act(e,g,'city:settle')
    merit=rules.court(g)['earned'];g=act(e,g,'reward')
    assert rules.court(g)['earned']==merit+5
    g.player.age+=50;e.store.save(g)
    with pytest.raises(ValueError,match='新增履约'):act(e,g,'reward')
    g=act(e,g,'city:settle');g=act(e,g,'reward')
    assert rules.court(g)['earned']==merit+10


@pytest.mark.parametrize('field,value',[('income',-1),('salary',10**20),('last_training',True),('policy',[])])
def test_corrupt_public_receipts_rejected(setup,field,value):
    e,g=setup;g,row,_=ready(e,g);operations.mutable(row)[field]=value
    with pytest.raises(ValueError):GameState.from_dict(g.to_dict())
