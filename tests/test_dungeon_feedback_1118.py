"""Player feedback: category boundaries, prose quality and frozen vocabulary."""
import copy
import random
import pytest
from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.models import Player
from cultivation_life.rules import assign_technique,combat_power,technique_special_effect
from cultivation_life.system import duel_techniques,npc_techniques
from cultivation_life.system.combat_system import PlayerCombatSystem, BattleUnit
from cultivation_life.system.dungeons import prose,scenes
from cultivation_life.system.dungeons import prose_expansion as extra
from cultivation_life.technique_effect_schema import describe
from test_seeded_dungeons import local


def specialty(category):
    return copy.deepcopy(min((t for t in TECHNIQUE_CATALOG.values() if t.category==category and t.element=='neutral'),key=lambda t:t.grade))


@pytest.mark.parametrize('category,slot,label', [('body','body','炼体'),('divine_sense','divine_sense','神识'),('transformation','transformation','变身')])
def test_specialty_books_only_cultivate_even_in_old_combat_lists(category,slot,label):
    p=Player(name='修持',spirit_root='heavenly',realm_index=8,body_training=100,divine_sense_rank=10)
    book=specialty(category)
    with pytest.raises(ValueError,match=label+'栏'):assign_technique(p,book,'combat')
    assign_technique(p,book,slot)
    base=combat_power(p)
    units=[BattleUnit(id='player',name='修持',kind='player',power=10000,realm_index=8)]
    # A cultivation slot must not apply a second, book-specific combat modifier.
    plain=copy.deepcopy(p)
    plain.body_technique=plain.divine_sense_technique=plain.transformation_technique=None
    stats=PlayerCombatSystem._aggregate_stats(units,player=plain,terrain_tags=[])
    p.combat_techniques=[book];p.duel_technique_ids=[book.id]
    assert combat_power(p)==base
    assert PlayerCombatSystem._aggregate_stats(units,player=p,terrain_tags=[])==stats
    assert duel_techniques.player_books(p)==[]
    assert duel_techniques.public(p)['selected']==[]
    assert duel_techniques.public(p)['candidates']==[]
    npc=dict(id='original',world='human',realm_index=8,spirit_root='heavenly',body_training=100)
    assert not duel_techniques.npc_eligible(npc,book)
    with pytest.raises(ValueError):npc_techniques.learn(npc,book,slot='combat')
    assert 'technique_levels' not in npc
    assert getattr(p,{'body':'body_technique','divine_sense':'divine_sense_technique','transformation':'transformation_technique'}[slot]).id==book.id


def test_specialty_books_excluded_from_effect_and_ability_snapshots(local):
    from cultivation_life.system.combat_loadout import project_loadout
    from cultivation_life.system.technique_effect_provider import project
    engine,game=local;p=game.player
    books=[specialty(c) for c in ('body','divine_sense','transformation')]
    p.combat_techniques=books;p.duel_technique_ids=[t.id for t in books]
    for t in books:t.force_tier=2
    p.technique=None
    assert not project(game,p,player=True)
    assert project_loadout(game,p,player=True).technique_tier==1
    old=copy.deepcopy(p.combat_techniques)
    project_loadout(game,p,player=True)
    assert p.combat_techniques==old


def test_all_catalog_and_generated_effect_descriptions_use_player_language():
    banned=('兑现','预算','载荷','监听','回执','收据','账本','入账','投影','付费','付款','不可证明','不确定','不可认定','不是','并非','而非')
    for book in TECHNIQUE_CATALOG.values():
        texts=[technique_special_effect(book)]
        if book.combat_effect and book.category=='spiritual':texts.append(describe(book.combat_effect))
        for text in texts:
            assert len(text)>10,(book.id,text)
            assert not any(word in text for word in banned),(book.id,text)
    for category in ('body','divine_sense','transformation'):
        for book in TECHNIQUE_CATALOG.values():
            if book.category==category:
                assert '每战至多' not in technique_special_effect(book),book.id


def test_old_authored_specialty_bonuses_are_inert_without_rewriting_facts():
    npc=dict(family_combat_bonus=130,technique_slots={},
             family_traits={'authored_combat_bonuses':{'body':30,'sense':20,'transformation':40,'combat':10}})
    before=copy.deepcopy(npc)
    assert npc_techniques.family_combat_bonus(npc)==40
    assert npc==before


def test_renown_event_conditions_and_real_unsilenced_action(local):
    engine,game=local
    game.settings['silent_events']=False
    before=game.player.renown
    assert engine._condition(dict(path='player.renown',op='eq',value=before),game)
    game.player.infamy=900
    assert game.player.renown==before
    assert engine._condition(dict(path='player.infamy',op='gte',value=900),game)
    engine.store.save(game)
    shown=engine.advance(game.id,'rest',1)
    assert shown['player']['age']>game.player.age
    assert engine.store.load(game.id).player.age==shown['player']['age']


@pytest.mark.parametrize('category',('body','divine_sense','transformation'))
def test_authored_specialty_books_reject_battle_buffs(category):
    from cultivation_life.system.authored_techniques import quote
    p=Player(name='著书',spirit_root='heavenly')
    p.known_techniques=[copy.deepcopy(next(t for t in TECHNIQUE_CATALOG.values() if t.category=='spiritual'))]
    payload=dict(name='养元录',grade=1,category=category,element='neutral',
        allocations={k:1 for k in ('opportunity_bonus','hp_bonus','mp_bonus','combat_bonus')},
        buffs=[dict(slot={'body':'body','divine_sense':'sense','transformation':'transformation'}[category],effect='might',value=5,level=1,condition='always',round=1)])
    with pytest.raises(ValueError,match='专属修持'):quote(p,payload)


def test_large_vocabulary_is_wired_to_frozen_generation():
    count=sum(len(v) for table in (extra.LANDMARKS,extra.DETAILS,extra.SENSES,extra.EVENTS,extra.OBSERVATIONS) for v in table.values())
    count+=sum(len(v) for v in (extra.STORIES,extra.EPIC_RESULTS,extra.LEGENDARY_RESULTS,extra.RUMORS,extra.DEPARTURES,extra.NAMES,extra.PERSON_NAMES,extra.TREASURES))
    assert count>=500
    for theme in prose.LANDMARKS:
        assert len(prose.LANDMARKS[theme])>=28
        assert set(extra.DETAILS[theme])<=set(prose.THEMED_DETAILS[theme])
        assert set(extra.SENSES[theme])<=set(prose.THEMED_SENSES[theme])
        seen=set()
        for seed in range(300):
            text=scenes.compose(random.Random(seed),'古境',theme,'cache','东','cache',seen)
            assert text
        assert len(seen)==300
        assert scenes.compose(random.Random(7),'古境',theme,'cache','东','cache',set())==scenes.compose(random.Random(7),'古境',theme,'cache','东','cache',set())
