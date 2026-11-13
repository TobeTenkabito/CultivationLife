"""Compile all 4258 reviewed designs into finite battle data, never parse prose in combat."""
import argparse
import copy
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cultivation_life.catalog_effect_schema import validate_catalog
from cultivation_life.combat_costs import mana_reference

# Reviewed clause order in the frozen 2026-11-12 design. Unlisted named clauses
# express the shared receipt/ownership/finite-budget invariants, not a new power.
# Every clause still appears by name, source text, and compiled operations in
# the generated audit. No Chinese condition is interpreted by the battle.
NAMED = {
    0:'forgo_attack',1:'two_paid_cycle',2:'source_repeat',3:'incoming_once',4:'next_attack_only',
    5:'reverse_to_first',6:'outgoing_required source_bound',7:'source_latest',8:'aged_debuff',
    9:'outgoing_required source_bound',11:'give_corpse',12:'stagger_recovery',13:'source_changed',
    15:'domain_ended',16:'two_sources',19:'target_defended',21:'incoming_once',24:'had_second',
    25:'outgoing_required source_bound',26:'source_latest',31:'repeat_refund',
    32:'restore_first',33:'next_attack_only',34:'source_hits_only',35:'had_second',36:'forecast_last',
    37:'mana_refund_only',39:'give_ally',42:'two_sources_memory',43:'split_ally',44:'reset_after_cycle',
    45:'give_ally',48:'next_incoming',50:'formation_required',51:'split_targets',52:'source_latest',
    53:'reset_after_cycle',54:'formation_required',55:'domain_paid',56:'outgoing_required',
    57:'body_required',58:'body_required',60:'restore_first body_required',61:'body_required',
    63:'source_latest',64:'paid_source',66:'source_latest',67:'form_required first_form_only',
    68:'form_required',69:'form_required',70:'form_required',71:'form_required mana_refund_only',
    72:'form_required',73:'form_required',74:'form_required',75:'form_required',76:'form_required',
    77:'form_required',82:'source_hits_only',83:'body_required',89:'source_repeat',90:'body_required',
    95:'mana_refund_only body_required',98:'source_latest',100:'body_required',102:'source_bound',
    103:'source_latest',114:'split_ally',116:'source_bound',118:'incoming_last',120:'source_repeat',
    122:'source_repeat',125:'source_hits_only',126:'source_hits_only outgoing_required',
    127:'forecast_last',129:'give_ally',130:'source_repeat',
    132:'next_attack_only',133:'sequential_shield',136:'source_hits_only',137:'source_bound',
    138:'reverse_to_second',140:'formation_required',142:'target_exchanged',148:'source_latest',
    149:'formation_required',151:'source_bound',153:'give_corpse',155:'body_required',
    156:'source_hurt_owner',157:'split_targets',160:'stagger_recovery',161:'delayed_all',
    163:'body_required',165:'source_repeat',170:'mana_refund_only',175:'outgoing_required',
    176:'largest_loss',177:'reverse_to_first',178:'source_latest',181:'source_bound',182:'incoming_once',
    183:'next_incoming',184:'source_repeat',191:'outgoing_required',192:'split_ally',194:'source_current',
    196:'give_ally',197:'reverse_to_second',199:'forecast_last',202:'reset_after_cycle',204:'source_repeat',
    205:'give_ally ally_required',206:'stagger_recovery',207:'source_latest',209:'forecast_last',213:'source_bound',
    214:'source_hits_only',216:'incoming_last',218:'source_bound',224:'source_hits_only',
    229:'body_required',230:'aged_debuff',231:'mana_refund_only',233:'body_required',
    239:'outgoing_required',241:'mana_refund_only',243:'body_required',244:'source_hits_only',
}
REGIONS = ['first_target','incoming_last','source_changed','source_repeat','both_directions',
           'second_source','paid_source','shield_used','attacked_shield','initiative_changed','expiry_seed']


def compile_all(design):
    rows = design['techniques']
    if len(rows) != 4258 or len({r['id'] for r in rows}) != 4258:
        raise ValueError('设计目录必须完整覆盖4258部原书')
    clauses = {r['rule']['exclusive_clause']['name']:r['rule']['exclusive_clause'] for r in rows if r['rule'].get('exclusive_clause')}
    if len(clauses) != 370:
        raise ValueError('具名附加规则目录发生变化，须重新审阅')
    names = list(clauses)
    flags = {}
    for index, name in enumerate(names):
        codes = NAMED.get(index, '').split()
        if 245 <= index < 293:
            role = (index-245) % 4
            codes += {0:[],1:['outgoing_required'],2:['body_required'],3:['source_hits_only']}[role]
        elif index >= 293:
            group, role = divmod(index-293, 7)
            gate = REGIONS[group]
            codes += ['reverse_either'] if gate == 'initiative_changed' else [gate]
            if role == 2: codes.append('restore_first')
            if role == 6: codes.append('source_hits_only')
        flags[name] = sorted(set(codes))
    result = {}
    realms=json.loads((ROOT/'content/world.json').read_text(encoding='utf-8'))['realms']
    for row in rows:
        rule = row['rule']; caps = rule['caps']; limits = rule['intrinsic_limits']
        clause = rule.get('exclusive_clause') or {}
        name = clause.get('name', '')
        effect = dict(version=3, generator_version=3, identity=row['id'], category=row['original_category'],
            trigger=rule['preparation']['event'], covenant=rule['path_covenant']['code'],
            delivery=rule['delivery']['code'], payload=rule['payload']['code'], clauses=flags.get(name, []),
            clause=name, signature=row['signature'], prestige=row['id']=='TECH_COMMON_GUI',
            cost_bp=round(rule['cost']['level_1_percent']*100), strength_bp=round(caps['ordinary_modifier_fraction']*10000),
            ward_bp=round(max(caps['recovery_fraction_of_initial_max_state'],caps['prevention_fraction_of_initial_max_state'])*10000),
            cooldown=limits['cooldown_full_rounds'], uses=limits['casts_per_battle'], duration=2,
            resource='energy' if row['grade']>=9 or row['original_definition'].get('requires_immortal_power') else 'mana')
        description = row['description'] + '\n' + row['battle_description']
        if effect['prestige']:
            effect.update(payload='taiyuan_sword',cost_bp=400,cooldown=1)
            description = ('归墟剑意随修士自身普通交锋成长：首次真实伤及敌人后留隙印，下一次对同一目标的合法攻击消耗。'
                'Lv.1—9的剑意加成由8%逐级提升至16%；若期间真实耗尽该敌人的临时护持，则改为12%—24%，两档不叠加。'
                '护持自然过期不算破持，换敌或两轮未用即失效。每战至多3次，冷却1个完整轮；'
                '每次支付开战法力容量4%，升级最多减费16%。元婴至大乘均按本人原始交锋计算，'
                '不乘旧等级倍率、不增加攻击次数、不越过仙凡资格；先登记剑意、下一合法窗口付费兑现。')
        if effect['resource']=='mana':
            effect['mana_cost']=round(mana_reference(realms[row['grade']]['base_power'])*effect['cost_bp']/10000,4)
            fee=f"{effect['mana_cost']:g}点法力"
            pricing=f'Lv.1费用：品阶低于自身境界时为{fee}，同阶为开战法力容量的{effect["cost_bp"]/100:g}%，越阶为两者之和'
            description=re.sub(r'Lv\.1费用为初始法力容量的[\d.]+%', pricing, description)
            description=description.replace('每次支付开战法力容量4%', pricing)
            description+=' Lv.1—9对本次总费用最多减费16%；费用规则不放宽装备与修炼资格。'
        else:
            description=re.sub(r'Lv\.1费用为初始法力容量的[\d.]+%',
                f'Lv.1同阶费用为开战可用元力容量的{effect["cost_bp"]/100:g}%',description)
            description+=' 费用按品阶与本人实际境界比较：低阶用对应品阶初层元力标准的固定费用，同阶用开战可用容量比例，越阶为两者之和；下界仿仙灵力使用原60点单位，Lv.1—9对总费用最多减费16%。'
        result[row['id']] = dict(combat_effect=validate_catalog(effect), description=description)
    return result, [{**value, 'operations':flags[name] or ['shared_invariants']} for name,value in clauses.items()]


def build(document, design):
    compiled, audit = compile_all(design)
    if set(compiled) != {r['id'] for r in document['techniques']}:
        raise ValueError('运行目录与设计目录身份不一致')
    changed = 0
    for row in document['techniques']:
        patch = compiled[row['id']]
        changed += any(row.get(k) != v for k,v in patch.items())
        row.update(copy.deepcopy(patch))
    return changed, audit


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--write',action='store_true')
    args=parser.parse_args()
    path=ROOT/'content/techniques.json'
    document=json.loads(path.read_text(encoding='utf-8'))
    design=json.loads((ROOT/'docs/technique-design-4258/techniques.json').read_text(encoding='utf-8'))
    changed,audit=build(document,design)
    if args.write:
        header=json.dumps({k:v for k,v in document.items() if k!='techniques'},ensure_ascii=False,indent=2)
        rendered=header[:-2]+',\n  "techniques": [\n'+',\n'.join(
            '    '+json.dumps(row,ensure_ascii=False,separators=(',', ':')) for row in document['techniques'])+'\n  ]\n}\n'
        path.write_text(rendered,encoding='utf-8')
        (ROOT/'build/fixed-technique-clause-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Fixed technique catalog: 4258 compiled; 370 clauses; drift={changed}')
    raise SystemExit(0 if args.write or not changed else 1)
