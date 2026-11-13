"""4258 compiled manuals, real exchanges, original resource ledgers and hostile snapshots."""
import copy
import json
import random
from pathlib import Path

import pytest

from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.system.combat.contracts import Combatant, CombatCapabilities
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.combat.trials import dump_battle, load_battle
from cultivation_life.system.npc_mana import prepare, commit
from tools.compile_fixed_techniques import compile_all

ROOT = Path(__file__).resolve().parents[1]


def manual(payload='finite_shield', **changes):
    book = copy.deepcopy(next(t for t in TECHNIQUE_CATALOG.values() if t.combat_effect['payload']==payload))
    book.combat_effect.update(trigger='paid_preparation', covenant='observed_event_once', delivery='next_window',
                              clauses=[], resource='mana', category='spiritual')
    book.combat_effect.update(changes)
    # Synthetic 100-MP fixture: keep timing/payload tests independent of the
    # source book's grade price. Real catalog prices have separate integration tests.
    if book.combat_effect['resource']=='mana':
        book.combat_effect['mana_cost']=changes.get('mana_cost',book.combat_effect['cost_bp']/100)
    else:
        book.combat_effect.pop('mana_cost',None)
    return dict(id=book.id, name=book.name, level=book.level, effect=book.combat_effect)


def fight(left=(), right=(), mana=100., context=None, debuff=False):
    rules=()
    if debuff:
        rules=(dict(schema_version=3,id='short-debuff',source_id='observed-enemy',trigger='ordinary_after_damage',
                    when={'fact':'role','op':'eq','value':'attacker'},
                    actions=[dict(op='status',key='slow',duration=2,recipient='target',
                                  modifiers=[dict(channel='ordinary.mobility',value=-.05)])]),)
    def actor(key,side,books):
        return Combatant(key,key,side,100.,capabilities=CombatCapabilities(
            mana_capacity=100., mana_initial=mana, technique_effects=books,
            technique_context=context or {},semantic_rules=rules if side=='enemy' else ()))
    return VoisinageBattle([actor('player','player',left),actor('enemy','enemy',right)])


def step(b,n,dealt=.03,received=.03,first=True):
    b.begin_round(n,player_condition=1-b.ordinary_loss('player'),enemy_condition=1-b.ordinary_loss('enemy'),
                  player_mp=b.mp_ratio('player',1),enemy_mp=b.mp_ratio('enemy',1),rng=random.Random(n))
    b.semantic_ordinary_start()
    b.semantic_initiative(first)
    result=b.ordinary_damage(dealt,received)
    b.finish_round(player_mp=b.mp_ratio('player',1),enemy_mp=b.mp_ratio('enemy',1))
    return result


def test_complete_catalog_preserves_original_stats_and_compiler_is_exact():
    design=json.loads((ROOT/'docs/technique-design-4258/techniques.json').read_text(encoding='utf-8'))
    compiled,audit=compile_all(design)
    assert len(compiled)==4258
    assert len(audit)==370
    for row in design['techniques']:
        book=TECHNIQUE_CATALOG[row['id']]
        assert book.combat_effect==compiled[book.id]['combat_effect']
        assert book.description==compiled[book.id]['description']
        for key,value in row['original_definition'].items():
            if key not in {'combat_effect','description'}:
                assert getattr(book,key)==value, (book.id,key)


def test_every_original_manual_runs_and_resumes_without_reroll_or_exception():
    for book in TECHNIQUE_CATALOG.values():
        if not book.combat_effect or book.combat_effect.get('version')!=3:continue
        row=dict(id=book.id,name=book.name,level=book.level,effect=book.combat_effect)
        b=fight([row],context=dict(form='recorded-form',bodiless=False,corpse=False))
        for n in range(1,5):step(b,n,first=n%2==0)
        try:restored=load_battle(dump_battle(b))
        except ValueError as exc:raise AssertionError(book.id) from exc
        assert restored.techniques.dump()==b.techniques.dump(),book.id


def test_low_tier_pays_own_mana_once_and_no_balance_cannot_cast():
    row=manual()
    b=fight([row],[row])
    step(b,1)
    cost=row['effect']['cost_bp']/100
    assert b.units['player'].mana_current==pytest.approx(100-cost)
    assert b.units['enemy'].mana_current==pytest.approx(100-cost)
    b.semantic_ordinary_start()
    assert b.units['player'].mana_current==pytest.approx(100-cost)
    empty=fight([row],[row],mana=0)
    step(empty,1)
    assert not empty.techniques.report()['receipts']
    assert all(s.mana_current==0 for s in empty.units.values())


def test_shield_is_finite_and_refund_never_creates_mana():
    row=manual('receipt_shield',trigger='actual_incoming')
    b=fight([row])
    step(b,1,received=.02)
    step(b,2,received=.04)
    events=b.techniques.catalog.report()['events']
    assert any(e['event']=='absorbed' and e['amount']>0 for e in events)
    assert b.units['player'].mana_current<100
    assert sum(e.get('amount',0) for e in events if e['event']=='absorbed')<=.005+1e-9


def test_derived_damage_does_not_create_a_second_original_exchange():
    b=fight([manual('budgeted_afterburn')])
    step(b,1)
    step(b,2,dealt=0,received=0)
    assert b.techniques.catalog.facts['player']['hit_round']==1
    assert b.units['enemy'].vitality<.97


def test_delayed_flame_spends_real_shield_without_new_observation_chain():
    b=fight([manual('budgeted_afterburn',clauses=['delayed_all'])],
            [manual('finite_shield',ward_bp=150)])
    step(b,1,dealt=.001,received=0)
    before=b.units['enemy'].vitality
    shield_before=sum(p['amount'] for key in b.techniques.catalog.by_owner['enemy']
                      for p in b.techniques.catalog.records[key]['packets'])
    step(b,2,dealt=0,received=0)
    assert b.units['enemy'].vitality==before
    shield_after=sum(p['amount'] for key in b.techniques.catalog.by_owner['enemy']
                     for p in b.techniques.catalog.records[key]['packets'])
    assert shield_after<shield_before
    assert b.techniques.catalog.facts['player'].get('hit_round') is None
    assert all(row['count']==0 for row in b.techniques.catalog.observations['enemy'].values())


def test_forgone_attack_also_blocks_legacy_lineage_damage():
    from tests.test_technique_effect_foundation import manual as legacy_manual
    from dataclasses import replace
    b=fight([manual('damage_to_shield',clauses=['forgo_attack']),legacy_manual('strike')])
    # A genuine high-tier owner can fund the old lineage technique as well.
    units=[replace(s.unit,capabilities=replace(s.unit.capabilities,
           current=100.,capacity=100.,resource_tier=2)) for s in b.units.values()]
    b=VoisinageBattle(units)
    step(b,1,dealt=.1,received=.01)
    assert b.units['enemy'].vitality==1
    assert b.units['player'].mana_current<100


def test_split_lineage_cast_is_observed_once_even_after_resume():
    from tests.test_technique_effect_foundation import manual as legacy_manual
    from dataclasses import replace
    b=fight([manual('repeat_source_response',trigger='observed_cast')],
            [legacy_manual('strike',delivery='split')])
    b=VoisinageBattle([replace(s.unit,capabilities=replace(s.unit.capabilities,
        current=100.,capacity=100.,resource_tier=2)) for s in b.units.values()])
    step(b,1)
    b=load_battle(dump_battle(b))
    step(b,2)
    observed=list(b.techniques.catalog.observations['player'].values())
    assert len(observed)==1
    assert observed[0]['count']==observed[0]['paid_count']==1
    step(b,3)
    step(b,4)
    assert list(b.techniques.catalog.observations['player'].values())[0]['count']==2


def test_loss_receipt_is_frozen_at_preparation_not_replaced_by_later_larger_hit():
    b=fight([manual('receipt_shield',trigger='actual_incoming',clauses=['largest_loss'])])
    step(b,1,received=.004)
    runtime=b.techniques.catalog
    key=runtime.by_owner['player'][0]
    locked=runtime.records[key]['opportunity']['loss_seq']
    runtime.observed('enemy','player',.04)
    assert runtime.loss_receipt(key)['seq']==locked
    step(b,2,dealt=0,received=.004)
    assert runtime.records[key]['loss_seq']==locked
    assert sum(e.get('amount',0) for e in runtime.events if e['event']=='absorbed')<=.001+1e-9


def test_latest_source_replaces_unpaid_listener_and_forgets_old_repeat_count():
    b=fight([manual('repeat_source_response',trigger='observed_cast',clauses=['source_latest'])])
    step(b,1,dealt=0,received=0)
    runtime=b.techniques.catalog;key=runtime.by_owner['player'][0]
    for book in ('seen-a','seen-a','seen-b','seen-a'):
        runtime.observe_cast('enemy',book,target='player')
        assert runtime.records[key]['opportunity']['source']==book
    assert runtime.observed_source(key)['count']==1
    assert load_battle(dump_battle(b)).techniques.catalog.records[key]['opportunity']['source']=='seen-a'


def test_named_target_must_complete_exchange_before_imprint_can_be_used():
    b=fight([manual('bound_breach',clauses=['target_exchanged'])])
    before=b.units['enemy'].vitality
    step(b,1,dealt=.03,received=.03)
    assert before-b.units['enemy'].vitality==pytest.approx(.03)
    before=b.units['enemy'].vitality
    step(b,2,dealt=.03,received=.03)
    assert before-b.units['enemy'].vitality>.03+1e-8


@pytest.mark.parametrize('body,wounds',[(1.,0),(.999,1),(.85,1),(.849,2)])
def test_original_npc_injuries_and_nonlethal_victory_are_preserved(body,wounds):
    from cultivation_life.system.combat.npc_lifecycle import commit_condition
    owner=dict(alive=True,wounds=0)
    commit_condition(owner,dict(vitality=0.,body=body,suppressed=False,lethal=False),lethal=True)
    assert owner['alive']
    assert owner['wounds']==wounds


@pytest.mark.parametrize('locked',[False,True])
def test_physical_defeat_preserves_soul_escape_but_respects_real_confinement(locked):
    from cultivation_life.system.combat.npc_lifecycle import commit_condition
    b=fight([manual()]);step(b,1,dealt=1.,received=0.)
    update=next(row for row in b.updates() if row['id']=='enemy')
    assert update['body']>0 and update['body_destroyed']
    update['escape_locked']=locked
    npc=dict(id='original-soul',realm_index=4,world='human',alive=True,wounds=0)
    escaped=commit_condition(npc,update,lethal=True,now=42)
    assert npc['alive'] is (not locked)
    assert bool(escaped) is (not locked)
    assert (npc.get('spirit_state',{}).get('mode')=='wandering') is (not locked)


def test_snapshot_cannot_forge_physical_defeat_flag():
    b=fight([manual()]);step(b,1)
    snapshot=dump_battle(b);snapshot['states']['enemy']['physical_defeat']='yes'
    with pytest.raises(ValueError,match='physical defeat'):load_battle(snapshot)


def test_taiyuan_upgrade_and_same_target_growth_remain_bounded():
    for level in (1,9):
        book=TECHNIQUE_CATALOG['TECH_COMMON_GUI']
        row=dict(id=book.id,name=book.name,level=level,effect=copy.deepcopy(book.combat_effect))
        for base in (.01,.08,.2):
            b=fight([row]);step(b,1,dealt=base,received=0)
            step(b,2,dealt=base,received=0)
            before=b.units['enemy'].vitality
            step(b,3,dealt=base,received=0)
            assert before-b.units['enemy'].vitality<=base*1.24+1e-9
            assert any(r['used'] for r in b.techniques.catalog.records.values())
            assert b.units['player'].mana_current<100


@pytest.mark.parametrize('mutation',['paid','share','owner','nan','unknown'])
def test_paid_snapshot_rejects_counterfeit_budgets(mutation):
    b=fight([manual(delivery='two_half_packets')]);step(b,1,received=.001)
    snapshot=dump_battle(b);runtime=snapshot['technique_runtime']['catalog']
    record=next(iter(runtime['records'].values()))
    if mutation=='paid':record['receipts'][0]['paid']*=2
    elif mutation=='share':record['packets'][0]['share']=2
    elif mutation=='owner':record['packets'][0]['recipient']='outsider'
    elif mutation=='nan':record['receipts'][0]['spent']=float('nan')
    else:runtime['records']['new-book']=copy.deepcopy(record)
    with pytest.raises(ValueError):load_battle(snapshot)


def test_npc_mana_persists_and_unknown_world_interval_does_not_restore():
    npc=dict(id='original',realm_index=3,layer=1,body_training=0,world='mortal',alive=True)
    initial=prepare(npc,10);capacity=initial['capacity']
    commit(npc,capacity/4)
    assert prepare(npc,10)['current']==capacity/4
    npc=json.loads(json.dumps(npc))
    assert prepare(npc,10)['current']==capacity/4
    npc['realm_index']=6
    assert prepare(npc,10)['current']==capacity/4
    npc['world']='celestial'
    assert prepare(npc,11)['current']==capacity/4
    assert prepare(npc,12)['current']>capacity/4


def test_body_and_sense_books_use_existing_combat_and_seven_selection():
    from cultivation_life.models import Player
    from cultivation_life.rules import assign_technique
    from cultivation_life.system.duel_techniques import select,player_books
    from cultivation_life.rules import QI_SOURCE_NAMES
    p=Player(name='测试',spirit_root='chaos',realm_index=8,layer=1,body_training=100,
             qi_experience={k:1e12 for k in QI_SOURCE_NAMES})
    for category in ('body','divine_sense'):
        book=copy.deepcopy(next(t for t in TECHNIQUE_CATALOG.values() if t.category==category and t.grade<9 and t.element=='neutral'))
        assign_technique(p,book,'combat');select(p,book.id)
    assert len(player_books(p))==2


def test_npc_mana_moves_with_original_person_and_only_known_time_recovers():
    from cultivation_life.system.combat.npc_lifecycle import move_world
    npc=dict(id='traveler',realm_index=3,layer=1,world='human',alive=True)
    cap=prepare(npc,10)['capacity'];commit(npc,0.)
    move_world(npc,'spirit',11,{})
    assert npc['ordinary_mana']==dict(capacity=cap,current=cap*.2,at=11,world='spirit')
    move_world(npc,'human',12,{})
    assert prepare(npc,12)['current']==pytest.approx(cap*.4)
    fresh=dict(id='unseen',realm_index=3,layer=1,world='human',alive=True)
    move_world(fresh,'spirit',12,{})
    assert fresh.get('ordinary_mana') is None


from cultivation_life.catalog_effect_schema import PAYLOADS, DELIVERIES


@pytest.mark.parametrize('payload',sorted(PAYLOADS-{'taiyuan_sword'}))
def test_each_payload_has_actual_paid_nonzero_result(payload):
    row=manual(payload)
    shield=manual('finite_shield',cooldown=0)
    attack=manual('charge_release',cooldown=0)
    left=[row]+([] if row['id']==shield['id'] else [shield])
    b=fight(left,[shield,attack],debuff=True)
    events=[]
    for n in range(1,21):
        step(b,n,dealt=.025,received=.025,first=n%2==0)
        events+=b.techniques.catalog.report()['events']
    record=next(r for k,r in b.techniques.catalog.records.items() if b.techniques.catalog.books[k][0]=='player' and b.techniques.catalog.books[k][1]['id']==row['id'])
    assert record['paid']>0,(payload,record,b.techniques.catalog.facts)
    assert record['completed']>0,(payload,record,events)


@pytest.mark.parametrize('delivery',sorted(DELIVERIES))
def test_every_delivery_retains_one_paid_budget_after_round_trip(delivery):
    row=manual('finite_shield',delivery=delivery)
    b=fight([row])
    for n in range(1,9):
        step(b,n,first=n%2==0)
        b=load_battle(dump_battle(b))
    record=next(iter(b.techniques.catalog.records.values()))
    assert record['completed']>0
    for receipt in record['receipts']:assert receipt['spent']<=1+1e-9


def test_no_overkill_guard_refund_and_no_recursive_extra_hit():
    row=manual('self_cost_rebate')
    b=fight([row]);step(b,1,dealt=0,received=10)
    record=next(iter(b.techniques.catalog.records.values()))
    assert record['refunded']==0 and record['completed']==0


def test_core_metadata_refresh_preserves_level_selection_and_generated_books():
    from cultivation_life.models import Player,Technique
    from cultivation_life.system.fixed_techniques import refresh_player
    original=copy.deepcopy(TECHNIQUE_CATALOG['TECH_COMMON_GUI']);original.combat_effect=None;original.level=7
    generated=Technique(id='celestial:original:manual:1',name='既有道统',description='原冻结文本')
    p=Player('旧书','supreme_metal',known_techniques=[original,generated],combat_techniques=[original],duel_technique_ids=[original.id])
    assert refresh_player(p)
    assert original.level==7 and original.combat_effect['prestige'] and p.duel_technique_ids==[original.id]
    assert generated.description=='原冻结文本' and not generated.combat_effect
    assert not refresh_player(p)


def test_real_player_npc_combat_commits_mana_even_when_story_waives_losses(tmp_path):
    from cultivation_life.engine import GameEngine
    from cultivation_life.models import SectNpc
    from cultivation_life.rules import learn_technique,assign_technique,max_mp,QI_SOURCE_NAMES
    from cultivation_life.system.duel_techniques import select
    e=GameEngine(ROOT,tmp_path)
    g=e.store.load(e.create_game('法力账本','chaos','dao',779,preset_id='core')['id'])
    g.pending_event=None
    p=g.player;p.spirit_root='supreme_earth';p.realm_index=6;p.body_training=50;p.qi_experience={'spirit':1e12}
    book=copy.deepcopy(next(t for t in TECHNIQUE_CATALOG.values() if t.category=='spiritual' and t.path=='dao'
                            and t.grade<7 and t.combat_effect.get('payload')=='finite_shield'))
    learn_technique(p,book);assign_technique(p,book,'combat');select(p,book.id)
    npc=SectNpc('mana-owner','同道','',6,1,30,None,spirit_root='supreme_earth',duel_technique_ids=[book.id],technique_levels={book.id:1})
    g.notable_npcs[npc.id]=npc
    p.mp=max_mp(p);before=p.mp
    target=dict(npc_id=npc.id,target_name=npc.name,combat_type='cultivator',target_realm_index=6,
                target_power=e._player_battle_power(g),loss_scale=0,single_combat=True)
    e._combat(g,target,False,random.Random(8))
    assert p.mp<before
    assert npc.ordinary_mana and npc.ordinary_mana['current']<npc.ordinary_mana['capacity']
    remaining=npc.ordinary_mana['current']
    e.store.save(g);g=e.store.load(g.id)
    assert g.notable_npcs[npc.id].ordinary_mana['current']==remaining
    events=[ev for row in g.last_combat_report['rounds'] for ev in row.get('voisinage',{}).get('technique_effects',{}).get('events',[])]
    assert any(ev['event']=='paid' and ev['owner']=='player' for ev in events)
    assert any(ev['event']=='paid' and ev['owner']!='player' for ev in events)
