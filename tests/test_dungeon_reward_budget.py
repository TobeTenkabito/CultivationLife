"""Frozen reward budgets, real consumption and paired acceptance fixtures."""
import copy
import random
import pytest
from test_seeded_dungeons import local,discover,act
from cultivation_life.models import Item, GameState
from cultivation_life.content_registry import WORLD_SYSTEMS, MARKET_GOODS, ITEM_CATALOG, ACTIONS
from cultivation_life.rules import add_item, max_hp, max_mp,opportunity_multiplier
from cultivation_life.system.dungeons.rewards import equipment_anchor, recipe, bounded_recipe, bound_growth_budget


def pill(rank=2,quality='ordinary',world='human'):
    for seed in range(40):
        reward=recipe(random.Random(seed),'budget-test',rank,'dao','water',quality,world=world)
        if reward['kind']=='pill':
            bounded_recipe(reward,quality,world)
            return reward
    raise AssertionError('No medicine sample')


def test_real_local_equipment_anchors_cover_every_grade():
    for world,ceiling in WORLD_SYSTEMS['seeded_dungeons']['ceilings'].items():
        for rank in range(max(1,ceiling-3),ceiling+1):
            anchor=equipment_anchor(rank,world)
            local_ids={r['content_id'] for r in MARKET_GOODS if r.get('kind')=='item'
                and r.get('world')==world and r.get('tier')==rank
                and r['content_id'] in ITEM_CATALOG and ITEM_CATALOG[r['content_id']].combat_bonus>0
                and 'pill' not in ITEM_CATALOG[r['content_id']].tags}
            if local_ids:assert anchor.id in local_ids
            for seed in range(20):
                reward=recipe(random.Random(seed),'budget-test',rank,'dao','water','legendary',world=world)
                if reward['kind']=='artifact':
                    item=reward['item'];factor=item['combat_bonus']/anchor.combat_bonus
                    assert 1<=factor<=1.10001
                    assert abs(item['hp_bonus']-anchor.hp_bonus*factor)<=1
                    assert abs(item['mp_bonus']-anchor.mp_bonus*factor)<=1


@pytest.mark.parametrize('quality,units',[('ordinary',.75),('rare',2.25),('epic',6)])
def test_whole_site_growth_budget_includes_gratitude(quality,units):
    reward=pill(8,quality,'spirit')
    site=dict(quality=quality,realm=8,nodes=[dict(reward=copy.deepcopy(reward)) for _ in range(14)],
              expedition=dict(bonuses=[copy.deepcopy(reward) for _ in range(2)]))
    bound_growth_budget(site)
    items=[n['reward']['item'] for n in site['nodes']]+[r['item'] for r in site['expedition']['bonuses']]
    target=sum(ACTIONS['cultivate']['opportunity'])/2*WORLD_SYSTEMS['time_units']['8']*units
    assert sum(i['opportunity_bonus'] for i in items)==pytest.approx(target)
    assert all(i['opportunity_bonus']>0 and i['recovery_hp_limit']>0 for i in items)
    legendary=copy.deepcopy(site);legendary['quality']='legendary'
    before=copy.deepcopy(legendary);bound_growth_budget(legendary);assert before==legendary


def test_hoarded_low_grade_medicine_uses_frozen_cap_through_real_command(local):
    engine,game=local;discover(engine,game);act(engine,game,'enter')
    saved=engine.store.load(game.id);site=next(iter(saved.dungeon_state['instances'].values()))
    index=next(i for i,n in enumerate(site['nodes']) if n['reward']['kind']=='pill')
    node=site['nodes'][index];node['kind']='cache';site['step']=index;site['pending']=None
    for role in site['roles'].values():role.update(state='left',offer_step=0)
    engine.store.save(saved);act(engine,game,'choose',choice='seize');act(engine,game,'exit')
    game=engine.store.load(game.id);item=next(i for i in game.player.inventory if i.id==node['reward']['id'])
    game.player.realm_index=5
    assert node['reward']['realm']<game.player.realm_index
    # Multiple retained medicines must never multiply each other's grant.
    other=copy.deepcopy(item);other.id='dungeon:held-medicine'
    baseline=opportunity_multiplier(game.player,allow_untrained=True)
    add_item(game.player,other,3)
    assert opportunity_multiplier(game.player,allow_untrained=True)==baseline
    game.player.hp=1;game.player.mp=1;engine.store.save(game)
    frozen=engine.store.load(game.id).player.inventory[-1].to_dict()
    engine.use_item(game.id,item.id)
    after=engine.store.load(game.id)
    assert after.player.opportunity-game.player.opportunity==pytest.approx(item.opportunity_bonus*baseline)
    assert after.player.hp-1==pytest.approx(min(max_hp(game.player)*item.trial_restore_hp,item.recovery_hp_limit,max_hp(game.player)-1))
    assert after.player.mp-1==pytest.approx(min(max_mp(game.player)*item.trial_restore_mp,item.recovery_mp_limit,max_mp(game.player)-1))
    assert frozen['recovery_hp_limit']==item.recovery_hp_limit
    assert not any(i.id==item.id for i in after.player.inventory)
    with pytest.raises(ValueError):engine.use_item(game.id,item.id)
    assert GameState.from_dict(after.to_dict()).player.hp==after.player.hp


def test_medicine_stock_has_no_passive_growth_and_keeps_original_equipment(local):
    engine,game=local
    baseline=opportunity_multiplier(game.player,allow_untrained=True)
    add_item(game.player,Item(**pill()['item']),100)
    assert opportunity_multiplier(game.player,allow_untrained=True)==baseline
    add_item(game.player,Item(id='original-growth-equipment',name='原修炼器物',opportunity_bonus=1))
    assert opportunity_multiplier(game.player,allow_untrained=True)>baseline


@pytest.mark.parametrize('value',[-1,float('nan'),float('inf'),True])
def test_invalid_recovery_caps_rejected(value):
    with pytest.raises(ValueError,match='恢复上限'):Item(id='bad',name='bad',recovery_hp_limit=value)


def test_old_items_keep_original_optional_cap_behavior():
    item=Item.from_dict(dict(id='old',name='原丹药',trial_restore_hp=.5))
    assert item.recovery_hp_limit is None and item.recovery_mp_limit is None


def test_all_paths_and_grades_make_equippable_complete_books():
    from cultivation_life.rules import validate_technique,assign_technique
    from cultivation_life.models import Player,Technique
    from cultivation_life.content_registry import TECHNIQUE_CATALOG
    for path in ('dao','demonic','ghost','monster','buddhist','confucian'):
        for rank in range(1,13):
            for quality in ('ordinary','legendary'):
                reward=recipe(random.Random(81),'dungeon:book-check',rank,path,'water',quality,core=True)
                book=Technique(**reward['book']);validate_technique(book)
                candidates=[t for t in TECHNIQUE_CATALOG.values() if t.grade==rank and t.path==path
                    and t.category=='spiritual' and t.requires_immortal_power==book.requires_immortal_power]
                if not candidates:
                    candidates=[t for t in TECHNIQUE_CATALOG.values() if t.grade==rank and t.path=='dao'
                        and t.category=='spiritual' and t.requires_immortal_power==(rank>=9)]
                assert candidates,(path,rank)
                assert book.hp_bonus<=max(t.hp_bonus for t in candidates)*1.101
                assert book.requires_immortal_power==(path=='dao' and rank>=9)
                if book.requires_immortal_power:assert book.immortal_power_cost>0
                player=Player(name='验收',path=path,spirit_root='supreme_earth',realm_index=rank,layer=9,
                    world='celestial' if rank>=9 else 'spirit' if rank>=6 else 'human',immortal_power_converted=rank>=9)
                player.known_techniques=[book]
                assign_technique(player,copy.deepcopy(book),'main')
                assert player.technique.id==book.id


def test_original_expedition_book_completes_cost_without_rerolling():
    from cultivation_life.models import Technique
    from cultivation_life.rules import validate_technique
    reward=recipe(random.Random(81),'dungeon:celestial:map:0:reward:1',12,'dao','water','legendary',core=True)
    frozen=copy.deepcopy(reward['book']);frozen.pop('immortal_power_cost')
    before=copy.deepcopy(frozen);book=Technique(**frozen);validate_technique(book)
    assert book.immortal_power_cost==.08 and frozen==before
    assert book.combat_bonus==frozen['combat_bonus'] and book.id==frozen['id']
