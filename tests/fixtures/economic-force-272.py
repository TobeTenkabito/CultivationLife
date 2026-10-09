"""Run against the signed APK's own imported combat code and loaded catalog."""
import copy
from cultivation_life.content_registry import ITEM_CATALOG, MARKET_GOODS
from cultivation_life.economy_content import specification
from cultivation_life.models import Player
from cultivation_life.system.combat.contracts import Combatant, CombatCapabilities, resolve_source
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.combat_loadout import project_loadout

count=0
for good in MARKET_GOODS:
    spec=specification(good['content_id']) if good['kind']=='item' else None
    if not spec:
        continue
    item=ITEM_CATALOG[good['content_id']]
    assert good['tier']==spec['grade'],item.id
    expected=2 if not spec['raw'] and spec['use']=='artifact' and spec['grade']>=9 else 1
    assert item.force_tier==expected,item.id
    count+=1
assert count==1666,count

hits=0
for world,cap in [('human',5),('demon',5),('spirit',8),('true_demon',8),
                  ('monster_realm',8),('phantom_underworld',8),('hell',8),
                  ('celestial',12),('asura',12),('nether',12),('reincarnation',12)]:
    for grade in [1,2,5,8,9,12]:
        if grade>cap:
            continue
        for kind in ['artifact_attack','artifact_guard']:
            for stale in [False,True]:
                p=Player('成品攻击资格','none',world=world)
                item=copy.deepcopy(ITEM_CATALOG[f'econ_{world}_{grade}_{kind}'])
                if stale:
                    item.force_tier=grade
                p.inventory=[item]
                p=Player.from_dict(p.to_dict())
                before=p.to_dict()
                caps=resolve_source(None,{},project_loadout(None,p,player=True))
                battle=VoisinageBattle([
                    Combatant('player','持器者','player',1000,caps),
                    Combatant('enemy','护体金光','enemy',1000,CombatCapabilities(ward_tier=2))])
                battle.begin_round(1,player_condition=1,enemy_condition=1,player_mp=1,enemy_mp=1)
                damage,_=battle.ordinary_damage(.2,0)
                assert damage==(.2 if grade>=9 else 0),(world,grade,kind,stale,damage)
                assert before==p.to_dict()
                hits+=1
print(f'Signed APK economic force: {count} catalog entries; {hits} fresh/stale actual damage cases passed')
