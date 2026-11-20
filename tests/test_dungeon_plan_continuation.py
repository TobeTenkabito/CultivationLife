"""Real command regressions for frozen scenes, evidence and local step receipts."""
import copy
import random
import pytest
from test_seeded_dungeons import local, discover, act
from test_dungeon_completion import loaded
from cultivation_life.rules import max_mp
from cultivation_life.system.dungeons import scenes


def test_finite_scene_composition_and_structural_coverage(local):
    e,g=local
    for _ in range(4):discover(e,g)
    state=e.store.load(g.id).dungeon_state
    nodes=[n for s in state['instances'].values() for n in s['nodes']]
    assert len({n['text'] for n in nodes})==len(nodes)
    assert len({n.get('mechanism') for n in nodes})>=5
    assert all('重环纹，第' not in n['text'] for n in nodes)
    used=set()
    for _ in range(100):
        scenes.compose(random.Random(12),'古塞','fort','seal','东','fractured',used)
    assert len(used)==100
    before=copy.deepcopy(state)
    e.get_game(g.id);e.get_game(g.id)
    assert e.store.load(g.id).dungeon_state==before


@pytest.mark.parametrize('choice,mechanism,multiplier',[('disarm','fractured',0),('attune','resonant',.25)])
def test_survey_unlocks_real_resource_and_damage_choices(local,choice,mechanism,multiplier):
    e,g=local;discover(e,g);act(e,g,'enter');saved,site=loaded(e,g)
    site['quality']='ordinary';node=site['nodes'][0]
    node.update(kind='seal',mechanism=mechanism,variant=0,risk=.1)
    for role in site['roles'].values():role.update(state='declined',offer_step=99)
    e.store.save(saved)
    with pytest.raises(ValueError,match='勘察'):act(e,g,'choose',choice=choice)
    shown=act(e,g,'choose',choice='survey')
    assert any(c['id']==choice and c['enabled'] for c in shown['dungeons']['session']['choices'])
    saved,site=loaded(e,g);before_mp=saved.player.mp;before_hp=saved.player.hp
    from cultivation_life.rules import max_hp
    damage=max_hp(saved.player)*.1*.4*multiplier
    cost=max_mp(saved.player)*scenes.TACTICS[choice][1]
    stale=dict(dungeon_id=site['id'],revision=site['revision'],choice=choice)
    act(e,g,'choose',choice=choice)
    saved,site=loaded(e,g)
    assert saved.player.mp==pytest.approx(before_mp-cost)
    assert saved.player.hp==pytest.approx(before_hp-damage)
    assert site['claims'].count(node['reward']['id'])==1 and site['step']==1
    with pytest.raises(ValueError,match='过期'):e.dungeon_action(g.id,'choose',stale)


def test_tactic_shortfall_disables_button_and_preserves_save(local):
    e,g=local;discover(e,g);act(e,g,'enter');saved,site=loaded(e,g)
    site['nodes'][0].update(kind='seal',mechanism='fractured')
    site['branches'].append(site['nodes'][0]['id']);saved.player.mp=0;e.store.save(saved)
    shown=e.get_game(g.id)
    assert not next(c['enabled'] for c in shown['dungeons']['session']['choices'] if c['id']=='disarm')
    before=e.store._path(g.id).read_bytes()
    with pytest.raises(ValueError,match='法力'):act(e,g,'choose',choice='disarm')
    assert e.store._path(g.id).read_bytes()==before


@pytest.mark.parametrize('mistaken',[False,True])
def test_background_ownership_evidence_stays_separate_from_loot(local,mistaken):
    e,g=local;discover(e,g);act(e,g,'enter');saved,site=loaded(e,g)
    site['quality']='epic';keys=list(site['roles'])[:2]
    site['space']['positions'].update({key:3 for key in keys})
    fact=dict(id='audit-fact',actors=keys,direction='东',occurred=1,reported=2,verified=4,
        result='双方负伤后退',mistaken=mistaken,scope='person',winner=keys[0],
        treasure=dict(id='audit-fact:background',name='照影古镜'))
    site['expedition']['facts']=[fact]
    for role in site['roles'].values():role['offer_step']=99
    e.store.save(saved);inventory=copy.deepcopy(saved.player.inventory);people=set(saved.world_npcs)
    for step in range((len(site['nodes'])+1)//2):
        shown=act(e,g,'choose',choice='bypass')
        if step==0:
            row=next(r for r in shown['dungeons']['session']['logs'] if r.get('fact_id')==fact['id'])
            assert row['kind']=='听说' and not row['subjects']
    saved,site=loaded(e,g)
    chain=[r for r in site['logs'] if r.get('fact_id')==fact['id']]
    assert [r['kind'] for r in chain]==['听说','据说','实证']
    assert '当面接过照影古镜' in chain[-1]['text']
    assert ('修正' in chain[-1]['text'])==mistaken
    assert not site['claims'] and saved.player.inventory==inventory and set(saved.world_npcs)==people
    assert not any(r['materialized'] for r in site['roles'].values())


def test_same_step_combat_does_not_repeat_party_preparation(local):
    e,g=local;discover(e,g);saved,site=loaded(e,g);ally,enemy=list(site['roles'].values())[:2]
    for r in site['roles'].values():r.update(state='declined',offer_step=99)
    ally.update(state='invited',known=True,purpose='seek',resolve=0,trust=100,preparation=0,caution=100)
    site['expedition']['goals'][ally['id']]['target']=site['nodes'][-1]['reward']['id']
    e.store.save(saved);act(e,g,'enter');act(e,g,'choose',choice='accept');act(e,g,'choose',choice='bypass')
    saved,site=loaded(e,g);ally=site['roles'][ally['id']];enemy=site['roles'][enemy['id']]
    preparation=ally['preparation'];work=site['expedition']['goals'][ally['id']]['work']
    enemy.update(realm=1,true_realm=1,layer=1,known=True,state='hostile');enemy['ledger']['supporters']=[]
    site['pending']=dict(kind='ambush',actor=enemy['id']);e.store.save(saved)
    act(e,g,'choose',choice='fight');saved,site=loaded(e,g)
    assert saved.last_combat_report and site['step']==1
    assert site['roles'][ally['id']]['preparation']==preparation
    assert site['expedition']['goals'][ally['id']]['work']==work
