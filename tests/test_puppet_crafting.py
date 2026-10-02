from pathlib import Path
import copy
import random
import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item
from cultivation_life.puppet_content import definitions, FORMS, WORLDS
from cultivation_life.system.puppet_crafting import preview
from cultivation_life.system import asura

@pytest.fixture
def ready(tmp_path):
    e=GameEngine(Path(__file__).resolve().parents[1],tmp_path)
    g=e.store.load(e.create_game('傀儡验收','supreme_metal','demonic',827,preset_id='asura_upper')['id'])
    g.player.asura_cultivation.update(conversion=5,body_level=20,souls=100000)
    g.pending_event=None
    add_item(g.player,'spirit_stone',100000000)
    return e,g


def parts(world='asura',tier=9,form='dragon'):
    return [f'puppet_{world}_{tier}_core_array',f'puppet_{world}_{tier}_shell_{form}',f'puppet_{world}_{tier}_energy_crystal']


@pytest.mark.parametrize('world',list(WORLDS))
def test_each_world_has_every_stage_component_and_real_market(ready,world):
    e,g=ready
    for tier in WORLDS[world][1]:
        p=g.player;p.world=world;p.realm_index=tier;p.layer=1
        p.location_id=e.maps.normalize_location(world,None)
        e._clear_market(g);e._ensure_market(g,random.Random(4))
        shown=e._public_market(g)['puppet_material_offers']
        assert len(shown)==12
        assert {r['tier'] for r in shown}=={tier}
        assert {r['form'] for r in shown if r['component_slot']=='shell'}==set(FORMS)
        assert all(r['content_id'] in definitions() for r in shown)
        before=copy.deepcopy(g.market_offers)
        assert not e._ensure_market(g,random.Random(4))
        assert g.market_offers==before


@pytest.mark.parametrize('form',list(FORMS))
def test_real_purchase_forge_training_and_asura_matching(ready,form):
    e,g=ready
    e.store.save(g)
    ids=parts(form=form)
    for material in ids:
        market=e.get_game(g.id)['market']['puppet_material_offers']
        offer=next(r for r in market if r['content_id']==material)
        e.buy_market_offer(g.id,offer['id'])
    before=e.store.load(g.id)
    q=e.preview_puppet(g.id,form,*ids)
    e.craft_mechanical_puppet(g.id,form,*ids)
    made=e.store.load(g.id)
    puppet=made.player.puppets[-1]
    assert puppet['combat_power']==q['combat_power'] and puppet['form']==form
    assert puppet['body_training']==100 and puppet['immortal_body_level']==5
    assert puppet['divine_sense_rank']==q['divine_sense_rank']
    assert all(not any(item.id==id_ for item in made.player.inventory) for id_ in ids)
    assert made.player.age==before.player.age
    eligible=asura.eligible_routes([asura.body_facts(puppet)])
    assert eligible==([FORMS[form]['route']] if FORMS[form]['route'] else [])
    old_level=puppet['immortal_body_level']
    e.train_owned(g.id,puppet['id'],'puppet','body',5)
    trained=e.store.load(g.id).player.puppets[-1]
    assert trained['immortal_body_level']==old_level+10
    e.asura_action(g.id,'condense',target_id=puppet['id'])
    body=e.store.load(g.id).player.asura_cultivation['bodies'][-1]
    assert body['form']==form and body['immortal_body_level']==15
    assert asura.eligible_routes([body])==eligible


def test_three_components_are_independent_and_preview_is_readonly(ready):
    e,g=ready
    ids=parts(); high=parts(tier=12)
    for id_ in ids+high:add_item(g.player,id_)
    snapshot=copy.deepcopy(g.player.to_dict())
    baseline=preview(g.player,'dragon',*ids)
    for index,key in [(0,'divine_sense_rank'),(1,'immortal_body_level'),(2,'realm_index')]:
        mix=ids[:];mix[index]=high[index]
        q=preview(g.player,'dragon',*mix)
        assert q[key]>baseline[key] and q['combat_power']>baseline['combat_power']
        for other in ['divine_sense_rank','immortal_body_level','realm_index']:
            if other!=key:assert q[other]==baseline[other]
    assert g.player.to_dict()==snapshot


def test_invalid_materials_and_capacity_never_consume(ready):
    e,g=ready;ids=parts()
    for id_ in ids:add_item(g.player,id_)
    e.store.save(g);e.get_game(g.id)
    before=e.store.load(g.id).player.to_dict()
    for args in [('bird',*ids),('dragon',ids[1],ids[0],ids[2]),('dragon',ids[0],ids[1],'missing')]:
        with pytest.raises(ValueError):e.craft_mechanical_puppet(g.id,*args)
        assert e.store.load(g.id).player.to_dict()==before
    g=e.store.load(g.id);g.player.divine_sense_rank=1;g.player.puppets=[dict(id=f'existing-{i}',type='mechanical',name='旧傀',combat_power=1) for i in range(100)]
    e.store.save(g)
    with pytest.raises(ValueError,match='上限'):e.craft_mechanical_puppet(g.id,'dragon',*ids)
    assert all(any(item.id==id_ for item in e.store.load(g.id).player.inventory) for id_ in ids)


def test_puppet_shelf_lock_and_old_market_migration(ready):
    e,g=ready
    e._ensure_market(g,random.Random(1))
    g.market_offers=[r for r in g.market_offers if r['kind']!='puppet_material']
    old=copy.deepcopy(g.market_offers)
    assert e._ensure_market(g,random.Random(2))
    assert all(r in g.market_offers for r in old)
    locked=next(r for r in g.market_offers if r['kind']=='puppet_material')
    locked['locked']=True
    held=copy.deepcopy(locked)
    g.player.age+=1
    e._ensure_market(g,random.Random(3))
    assert held in g.market_offers
    assert sum(r['kind']=='puppet_material' for r in g.market_offers)==12
