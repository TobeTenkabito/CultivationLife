"""Probe real legal common-art builds and solve same-stage ordinary combat targets.

This is offline calibration, not gameplay. No world, inventory or yearly rules
are changed. Base mode loads an isolated copy of base content without DLCs.
"""
import argparse
import copy
import json
import math
import os
from pathlib import Path
import random
import shutil
import statistics
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT),str(ROOT/'tools')]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=12)
    parser.add_argument('--all-dlc',action='store_true')
    parser.add_argument('--solve',action='store_true')
    parser.add_argument('--normal-count',type=int,default=3,choices=(3,6))
    parser.add_argument('--open-only',action='store_true')
    args=parser.parse_args()
    temporary=tempfile.TemporaryDirectory(prefix='combat-calibration-')
    app=ROOT if args.all_dlc else Path(temporary.name)
    if not args.all_dlc:
        shutil.copytree(ROOT/'content',app/'content')
        os.environ['CULTIVATION_APP_ROOT']=str(app)
    from cultivation_life.content_registry import REALMS,ROOT_DEFINITIONS,TECHNIQUE_CATALOG,WORLD_SYSTEMS,MARKET_GOODS
    from cultivation_life.models import Player
    from cultivation_life.rules import (assign_technique,combat_power,max_hp,max_mp,can_player_practice_technique,
        opportunity_required,combat_root_mana_cost_multiplier,qi_level_threshold,qi_levels,combat_requirement_met)
    from cultivation_life.system.combat_system import BattleUnit,PlayerCombatSystem
    from cultivation_life.combat_benchmarks import expected_combat_power
    from generate_common_techniques import LINES,QI_LEVELS
    from scripts.release_evidence import inputs_digest
    root_ids=[next(k for k,v in ROOT_DEFINITIONS.items() if v['creation'] and set(v['elements'])==elements)
              for elements in ({'metal'},{'metal','water'},{'thunder'})]
    paths=('dao','demonic','ghost','monster','buddhist','confucian')
    tradable={r['content_id'] for r in MARKET_GOODS if r['kind']=='technique'}
    def build(rank,layer,path,root,tier):
        native=path if path in LINES else 'dao'
        world=({'dao':('human','spirit','celestial'),'demonic':('demon','true_demon','asura'),
                'ghost':('hell','phantom_underworld','reincarnation'),'monster':('human','monster_realm','nether')}[native]
               [0 if rank<=5 else 1 if rank<=8 else 2])
        p=Player('数值样本',root,path=path,world=world,realm_index=rank,layer=layer,
                 immortal_power_converted=rank>=9,divine_sense_rank=max(0,rank*3-2))
        # Ordinary source qualifications, not free all-source mastery.
        source=LINES[native][0]
        p.qi_experience[source]=qi_level_threshold(QI_LEVELS[rank-1])
        stage=0 if layer<=3 else 1 if layer<=6 else 2
        level={'basic':(1,2,3),'normal':(2,4,6),'advanced':(4,6,9)}[tier][stage]
        count={'basic':3,'normal':args.normal_count,'advanced':9}[tier]
        eligible=[copy.deepcopy(t) for t in TECHNIQUE_CATALOG.values()
            if (t.id.startswith('TECH_OPEN_') if args.open_only else t.id in tradable)
            and t.path==native and t.category=='spiritual' and not t.doctrine_id and t.active_in(world)
            and (not t.requires_immortal_power or p.immortal_power_converted)
            and t.required_body_training<=p.body_training and t.grade<=rank and can_player_practice_technique(p,t)
            and combat_requirement_met(t.combat_requirements,qi_levels(p))]
        for t in eligible:t.level=level
        for slot,preference in [('main','main'),('support','support')]:
            selected=max(eligible,key=lambda t:((t.opportunity_bonus*t.stat_multiplier('opportunity_bonus')
                if slot=='main' else t.hp_bonus*t.stat_multiplier('hp_bonus')+t.mp_bonus*t.stat_multiplier('mp_bonus')),t.grade,t.id))
            assign_technique(p,copy.deepcopy(selected),slot)
        chosen=sorted(eligible,key=lambda t:(t.combat_bonus*t.stat_multiplier('combat_bonus')*(1+.12*(t.grade-1)),t.id),reverse=True)[:count]
        for t in chosen:assign_technique(p,t,'combat')
        p.opportunity=opportunity_required(p)*.25
        p.hp,p.mp=max_hp(p),max_mp(p)
        return p
    def fight(p,power,seed):
        player=copy.deepcopy(p)
        units=[BattleUnit('player',player.name,'player',combat_power(player),player.realm_index,path=player.path)]
        target=dict(target_name='同阶标准修士',target_power=power,target_realm_index=player.realm_index,
            target_layer=player.layer,combat_type='cultivator',path=player.path,objective='repel',
            enemy_objective='defeat',max_rounds=5)
        result=PlayerCombatSystem.resolve(player,units,target,False,random.Random(seed),
            current_hp_ratio=1,current_mp_ratio=1,
            mana_cost_multiplier=combat_root_mana_cost_multiplier(player,player.realm_index,player.layer))
        return result.outcome
    def rates(players,power):
        wins,draws=0,0
        for p in players:
            for seed in range(args.samples):
                outcome=fight(p,power,seed)
                wins+=outcome in {'victory','victory_controlled'}
                draws+=outcome in {'stalemate','controlled'}
        total=len(players)*args.samples
        return dict(wins=wins,draws=draws,battles=total,win_rate=round(wins/total,4))
    rows=[]
    for rank in range(1,13):
        for layer in ((1,5,9,13) if rank==1 else (1,5,9)):
            groups={tier:[build(rank,layer,path,root,tier) for path in paths for root in root_ids]
                    for tier in ('basic','normal','advanced')}
            old=expected_combat_power(rank,layer)
            row=dict(rank=rank,realm=REALMS[rank].name,layer=layer,old_standard=old,
                profiles={tier:dict(median_power=statistics.median(combat_power(p) for p in players),
                    min_power=min(combat_power(p) for p in players),max_power=max(combat_power(p) for p in players),
                    technique_count=sorted(set(len(p.combat_techniques) for p in players)),
                    levels=sorted(set(t.level for p in players for t in p.combat_techniques)),
                    **rates(players,old)) for tier,players in groups.items()})
            if args.solve:
                # Seek a competitive ordinary fixture, never weaken old standards.
                low=old
                high=max(old,max(combat_power(p) for p in groups['normal'])*3)
                candidates=[]
                for _ in range(11):
                    candidate=(low+high)/2
                    result=rates(groups['normal'],candidate)
                    candidates.append((abs(result['win_rate']-.55),candidate,result))
                    if result['win_rate']>.55:low=candidate
                    else:high=candidate
                candidates.append((abs(row['profiles']['normal']['win_rate']-.55),old,
                    {k:row['profiles']['normal'][k] for k in ('wins','draws','battles','win_rate')}))
                _,power,result=min(candidates,key=lambda r:(r[0],r[1]))
                # Three significant digits make authored tables legible.
                unit=10**max(0,math.floor(math.log10(max(1,power)))-2)
                row['proposed_standard']=max(old,round(power/unit)*unit)
                row['proposed_results']={tier:rates(players,row['proposed_standard']) for tier,players in groups.items()}
            rows.append(row)
            print(json.dumps(row,ensure_ascii=False),flush=True)
    report=dict(source_sha256=inputs_digest(ROOT),all_dlc=args.all_dlc,samples_per_fixture=args.samples,
        paths=list(paths),roots=root_ids,rows=rows,normal_art_count=args.normal_count,open_only=args.open_only,
        assumptions=f'Ordinary six-stat 1v1, equal realm/layer and path, full HP/MP, 25% opportunity. All base tradable arts (or explicitly open-only) with exact root/source/body/world qualifications; 3/{args.normal_count}/9 equipped arts, Lv1-3/Lv2-6/Lv4-9. No armies, formations, special loot, soul or bloodline/domain bonuses. This samples finite playstyles, not the unlimited-equipment ceiling. Solver targets 55% ordinary wins and never lowers a previous standard; it is a declared calibration criterion, not a random power percentage.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temporary.cleanup()


if __name__=='__main__':main()
