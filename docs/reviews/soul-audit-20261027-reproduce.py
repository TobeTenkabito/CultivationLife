"""Read-only audit probes: only disposable saves; intentionally assert current defects."""
import copy
import json
import random
import runpy
import sys
import tempfile
import traceback
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.release_evidence import inputs_digest
from cultivation_life.engine import GameEngine
from cultivation_life.models import SectNpc
from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.rules import max_hp, max_mp, can_player_practice_technique
from cultivation_life.system import soul_lifecycle as life
from cultivation_life.system.second_nascent import power, unit
from cultivation_life.system.possession_system import enter_host_body, advance_player_age
from cultivation_life.system.soul_actions import require
from cultivation_life.soul_rules import lower_minor
from cultivation_life.content_registry import REALMS

results = []
def probe(key, fn):
    try:
        data = fn()
        results.append(dict(id=key, status='reproduced', evidence=data))
    except Exception:
        results.append(dict(id=key, status='probe_error', error=traceback.format_exc()))
    print(key, results[-1]['status'], flush=True)

before = inputs_digest(ROOT)
with tempfile.TemporaryDirectory(prefix='wendao-audit-') as tmp:
    engine = GameEngine(ROOT, Path(tmp)/'saves')
    gid = engine.create_game('只读审查隔离档', 'supreme_metal', 'dao', 320, preset_id='core')['id']
    runpy.run_path(str(ROOT/'tests/fixtures/soul_release.py'))['prepare_soul'](engine, gid)
    baseline = copy.deepcopy(engine.store.load(gid))

    def fresh(path='dao'):
        game=copy.deepcopy(baseline)
        game.player.path=path
        game.pending_event=None;game.active_trial=None
        game.player.hp=max_hp(game.player);game.player.mp=max_mp(game.player)
        engine.store.save(game)
        return game

    def action(action, **kw):
        g=engine.store.load(gid)
        return engine.soul_action(gid, action, dict(revision=g.player.nascent_state.get('revision',0),**kw))

    def integrity():
        fresh()
        action('study',id='second_nascent')
        for _ in range(3):
            action('refine',id='release-nascent')
            g=engine.store.load(gid);g.pending_event=None;engine.store.save(g)
        g=engine.store.load(gid)
        full=power(g)
        globals()['with_second']=copy.deepcopy(g)
        g.player.nascent_state['second']['integrity']=50
        u=unit(g)
        assert u.power==full*.5 and u.power*u.integrity==full*.25
        return dict(full=full,display_at_50=u.power,actual_contribution_at_50=u.power*u.integrity)
    probe('B01',integrity)

    def bodyless_train():
        g=fresh('ghost');life.leave_body(g,destroyed=True)
        t=next(copy.deepcopy(t) for t in TECHNIQUE_CATALOG.values() if t.category=='body' and t.grade==1 and can_player_practice_technique(g.player,t))
        g.player.body_technique=t;g.player.known_techniques.append(t)
        g.player.body_progress=0
        engine.store.save(g)
        engine.advance(gid,'body_train',1)
        after=engine.store.load(gid)
        assert after.player.spirit_state['body_intact'] is False and after.player.body_progress>0
        return dict(body_intact=False,body_energy=after.player.body_energy,body_progress=after.player.body_progress,age_advanced=after.player.age-g.player.age)
    probe('B02',bodyless_train)

    def host_book():
        g=fresh();life.leave_body(g)
        t=next(t for t in TECHNIQUE_CATALOG.values() if t.category=='spiritual' and t.grade==1 and t.path=='dao')
        target=g.player.prisoners[0]
        target.update(main_technique_id=t.id,main_technique_level=7,technique_levels={t.id:7})
        engine.store.save(g)
        with patch.object(random.Random,'random',return_value=0.):
            engine.captive_action(gid,target['id'],'possess')
        after=engine.store.load(gid)
        assert after.player.technique.level==1 and after.player.ghost_host_body
        return dict(book=t.id,npc_level=7,host_player_level=after.player.technique.level,entry='GameEngine.captive_action')
    probe('B03',host_book)

    def blocked_crisis():
        g=fresh();g.player.nascent_state['crisis']='possession'
        g.player.cultivation_suppression=dict(realm_index=6,layer=9)
        messages=[]
        for fn in (lambda:require(g,0,crisis=True),lambda:advance_player_age(g.player)):
            try:fn()
            except ValueError as e:messages.append(str(e))
        assert len(messages)==2
        return dict(resist_rejected=messages[0],time_rejected=messages[1],scope='guard reproduction; not a claim all escape routes are blocked')
    probe('D01',blocked_crisis)

    def nirvana_stagnant():
        g=fresh('buddhist');g.player.nascent_state['stagnant']=True
        g.buddhist_state.setdefault('wish',{})['value']=100
        g.player.realm_index=2;g.player.layer=1
        engine.store.save(g)
        engine.buddhist_action(gid,'nirvana')
        after=engine.store.load(gid)
        assert after.player.layer==1 and after.buddhist_state['wish']['value']==0
        return dict(before_layer=1,after_layer=after.player.layer,wish_before=100,wish_after=after.buddhist_state['wish']['value'],history=after.history[-1].summary if hasattr(after.history[-1],'summary') else str(after.history[-1]))
    probe('B04',nirvana_stagnant)

    def outer_stagnant():
        g=fresh('confucian');g.player.nascent_state['stagnant']=True
        g.player.haoran_exp=100000;g.player.realm_index=2;g.player.layer=1
        engine.store.save(g)
        engine.sage_outer_king(gid,'advance')
        after=engine.store.load(gid)
        assert after.player.layer==1 and after.player.haoran_exp<100000 and after.player.outer_king_advance_uses>0
        return dict(before_layer=1,after_layer=after.player.layer,haoran_spent=100000-after.player.haoran_exp,uses=after.player.outer_king_advance_uses)
    probe('B05',outer_stagnant)

    def rescued_possession_report():
        g=copy.deepcopy(with_second);g.pending_event=None
        life.leave_body(g)
        npc=SectNpc('audit-host','隔离宿身','散修',3,1,30,10000,spirit_root='supreme_metal')
        g.world_npcs[npc.id]=npc
        g.player.prisoners.append(g.detain_person(npc.to_dict()))
        engine.store.save(g)
        with patch.object(random.Random,'random',return_value=.999):
            result=engine.captive_action(gid,npc.id,'possess')
        after=engine.store.load(gid)
        assert after.player.alive and not after.player.nascent_state.get('second')
        assert '魂飞魄散' in after.history[-1].summary
        return dict(alive=after.player.alive,second_consumed=True,last_history=after.history[-1].summary)
    probe('B06',rescued_possession_report)

    def mortal_decline():
        actual=lower_minor(0,1,REALMS)
        assert actual==(0,REALMS[0].layers)
        return dict(before=[0,1],after=list(actual),mortal_layers=REALMS[0].layers)
    probe('D02',mortal_decline)

after=inputs_digest(ROOT)
assert before==after, 'Audit must not change runtime inputs'
output=dict(version='3.2.0',runtime_unchanged=True,inputs_sha256=before,probes=results)
Path(__file__).with_name('soul-audit-20261027-evidence.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if any(r['status']=='probe_error' for r in results):sys.exit(1)
