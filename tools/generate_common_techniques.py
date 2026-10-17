"""Author the open elemental series deterministically; never runs during gameplay."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'TECH_OPEN_'
ATTRIBUTES = (.08, .15, .23, .32, .43, .55, .65, .75, .90, 1.05, 1.25, 1.45)
POWER = (16, 48, 145, 3300, 19100, 99600, 676800, 3144000, 11200000, 63000000, 350000000, 2100000000)
PRICES = (80, 320, 1600, 7200, 28000, 160000, 1000000, 6400000, 40000000, 260000000, 1800000000, 12000000000)
QI_LEVELS = (0, 3, 5, 8, 12, 17, 23, 30, 30, 30, 30, 30)
# Role coefficients: opportunity, HP, MP, combat. Existing level curves further
# specialize these four positive attributes without altering old techniques.
ROLES = {'main': (1.45,.45,.45,.45), 'support': (.45,1.45,1.55,.45), 'combat': (.45,.45,.45,1.60)}
LINES = {
    'dao': ('spirit', ('松窗','云岫','霜台','星渚','玉宸','碧落','清都','玄圃','紫府','上清','太清','无极'),
            ('SONGCHUANG','YUNXIU','SHUANGTAI','XINGZHU','YUCHEN','BILUO','QINGDU','XUANPU','ZIFU','SHANGQING','TAIQING','WUJI')),
    'demonic': ('demon', ('烬坛','赤窟','夜泉','血月','玄狱','黑莲','寂焰','冥宵','赤霄','劫海','无间','魔渊'),
                ('JINTAN','CHIKU','YEQUAN','XUEYUE','XUANYU','HEILIAN','JIYAN','MINGXIAO','CHIXIAO','JIEHAI','WUJIAN','MOYUAN')),
    'monster': ('monster', ('荒泽','石涧','苍岚','百岳','玄牝','洪荒','山海','祖庭','烛野','龙渊','万象','太古'),
                ('HUANGZE','SHIJIAN','CANGLAN','BAIYUE','XUANPIN','HONGHUANG','SHANHAI','ZUTING','ZHUYE','LONGYUAN','WANXIANG','TAIGU')),
    'ghost': ('yin', ('残灯','寒泉','孤冢','幽台','忘川','黄泉','长夜','轮台','三生','无始','彼岸','大寂'),
              ('CANDENG','HANQUAN','GUZHONG','YOUTAI','WANGCHUAN','HUANGQUAN','CHANGYE','LUNTAI','SANSHENG','WUSHI','BIAN','DAJI')),
}
# Main/support/combat titles. Every rank uses the same literary series form.
FAMILIES = {
    'neutral': ((), ('抱朴归真经','静渊养元录','长空御剑诀')),
    'metal': (('metal',), ('太白凝真经','金城护元录','庚光斩影诀')),
    'wood': (('wood',), ('青华纳息篇','长春养元经','苍藤缚影诀')),
    'water': (('water',), ('沧浪归源经','玄泉润生录','寒汀截流诀')),
    'fire': (('fire',), ('离照引灵经','丹霞温脉篇','赤焰焚尘诀')),
    'earth': (('earth',), ('厚土藏真经','坤岳承生录','镇岳崩山诀')),
    'wind': (('wind',), ('天籁御息篇','流岚护脉经','扶摇裂空诀')),
    'thunder': (('thunder',), ('紫枢引炁经','鸣霆淬元篇','震霄破障诀')),
    'yin': (('yin',), ('玄阴抱素经','素月养神篇','寒魄绝影诀')),
    'yang': (('yang',), ('晨曦炼真篇','纯阳温玉经','曜日破邪诀')),
    'metal_water': (('metal','water'), ('金津返照经','金泉涵脉录','霜涛洗锋诀')),
    'water_wood': (('water','wood'), ('甘霖生华经','雨露滋荣篇','碧潮缠枝诀')),
    'wood_fire': (('wood','fire'), ('薪传明照经','青灯养脉篇','燎原焚棘诀')),
    'fire_earth': (('fire','earth'), ('赤炉归藏经','陶元护藏录','熔岳开山诀')),
    'earth_metal': (('earth','metal'), ('山骨蕴锋经','岳镇金城录','玄砂裂甲诀')),
    'wind_thunder': (('wind','thunder'), ('巽震交泰经','风雷回护篇','九霄震羽诀')),
    'yin_yang': (('yin','yang'), ('两仪参玄经','日月同辉录','晦明断流诀')),
    'wind_thunder_yin': (('wind','thunder','yin'), ('巽霆涵月经','玄霆抱魄录','朔风惊雷诀')),
    'wind_thunder_yang': (('wind','thunder','yang'), ('风雷曜华经','朝曦养霆录','天风逐日诀')),
    'wind_yin_yang': (('wind','yin','yang'), ('清微合景经','素曜养风录','晦明裁风诀')),
    'thunder_yin_yang': (('thunder','yin','yang'), ('太枢参玄经','日月养雷录','两仪殛电诀')),
    'wind_thunder_yin_yang': (('wind','thunder','yin','yang'), ('玄枢合炁经','两仪御霆录','晦明震空诀')),
    'metal_water_wood': (('metal','water','wood'), ('三华滋荣经','玉露承生录','碧涛蕴锋诀')),
    'wood_fire_earth': (('wood','fire','earth'), ('三光归藏经','丹林镇元录','熔林裂岳诀')),
    'metal_wood_water_earth': (('metal','wood','water','earth'), ('四序回元经','山泽涵生录','川岳断锋诀')),
    'wood_water_fire_earth': (('wood','water','fire','earth'), ('四象参玄经','坤离养和录','青冥煮海诀')),
    'five_elements': (('metal','wood','water','fire','earth'), ('五炁朝元经','五德载生录','五岳分光诀')),
}
WORLD_PATHS = {'human':'dao','spirit':'dao','celestial':'dao',
               'demon':'demonic','true_demon':'demonic','asura':'demonic',
               'monster_realm':'monster','nether':'monster',
               'phantom_underworld':'ghost','hell':'ghost','reincarnation':'ghost'}


def affinity_multiplier(roots):
    """One/two mutations approach five elements; three/four earn larger premiums."""
    if set(roots) & {'wind','thunder','yin','yang'}:
        return {1:1.18, 2:1.19, 3:1.25, 4:1.30}[len(roots)]
    return 1.0 + .04 * len(roots)


def definitions(profiles, purity_caps):
    techniques, goods = [], []
    for path, (source, titles, stems) in LINES.items():
        for grade, (title, stem) in enumerate(zip(titles, stems), 1):
            for family, (roots, names) in FAMILIES.items():
                premium = affinity_multiplier(roots)
                for i, (role, weights) in enumerate(ROLES.items()):
                    identity = f'{PREFIX}{stem}_{family.upper()}_{role.upper()}'
                    source_requirement = {'source':{'id':source,'op':'>=','level':QI_LEVELS[grade-1]}}
                    limits = [{'source':{'id':key,'op':'<=','level':value}}
                              for key,value in purity_caps.get(path,{}).items()]
                    requirement = {'all':[source_requirement,*limits]} if limits else source_requirement
                    technique = dict(id=identity, name=names[i], path=path,
                                     element='five_elements' if len(roots)==5 else roots[0] if roots else 'neutral',
                                     grade=grade, level=1, category='spiritual', growth_preference=role,
                                     opportunity_bonus=round(ATTRIBUTES[grade-1]*weights[0]*premium,6),
                                     hp_bonus=round(ATTRIBUTES[grade-1]*weights[1]*premium,6),
                                     mp_bonus=round(ATTRIBUTES[grade-1]*weights[2]*premium,6),
                                     combat_bonus=round(POWER[grade-1]*weights[3]*premium,4),
                                     karma_multiplier=1.0, sources={source:1.0},
                                     combat_requirements=requirement,
                                     required_affinities=list(roots))
                    techniques.append(technique)
                    for world, native_path in WORLD_PATHS.items():
                        if path==native_path and grade<=int(profiles[world]['npc_realm_cap']):
                            goods.append(dict(world=world,kind='technique',content_id=identity,tier=grade,
                                              price=round(PRICES[grade-1]*premium)))
    return techniques, goods


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--write',action='store_true');args=parser.parse_args()
    profiles=json.loads((ROOT/'content/world.json').read_text(encoding='utf-8'))['systems']['world_profiles']
    caps=json.loads((ROOT/'content/techniques.json').read_text(encoding='utf-8'))['combat_purity_caps_by_path']
    techniques,goods=definitions(profiles,caps)
    for filename,key,generated in [('techniques.json','techniques',techniques),('market.json','goods',goods)]:
        path=ROOT/'content'/filename;doc=json.loads(path.read_text(encoding='utf-8'))
        existing=[r for r in doc[key] if not str(r.get('id' if key=='techniques' else 'content_id','')).startswith(PREFIX)]
        expected=existing+generated
        if args.write:
            # Keep authored entries readable; generated rows each occupy one line.
            marker='__GENERATED_OPEN_TECHNIQUES__'
            doc[key]=existing+[marker]
            rendered=json.dumps(doc,ensure_ascii=False,indent=2)
            rows=',\n'.join('    '+json.dumps(row,ensure_ascii=False,separators=(',',':')) for row in generated)
            rendered=rendered.replace('    '+json.dumps(marker),rows)
            path.write_text(rendered+'\n',encoding='utf-8')
        elif doc[key]!=expected:
            raise SystemExit(f'{filename}: open technique catalog differs; run --write')
    print(f'Open techniques: {len(techniques)} definitions, {len(goods)} local offers, 11 worlds, grades 1-12')


if __name__=='__main__': main()
