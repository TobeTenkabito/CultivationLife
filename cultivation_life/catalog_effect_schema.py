"""Executable vocabulary for the reviewed fixed-book catalog; data only."""
import copy
import math

PAYLOADS = frozenset('''self_cost_rebate bound_breach interruptible_restore receipt_shield budgeted_afterburn
finite_shield initiative_switch charge_release repeat_source_response cleanse_temporary barrier_followup
delayed_loss_recovery offense_restore_choice damage_to_shield broken_shield_breach initiative_charge
alternating_choice repeat_initiative_breach initiative_cleanse initiative_choice repeat_paid_cast four_way_choice
breach_then_restore cancel_afterburn_for_shield shield_then_breach_or_restore forecast_choice five_step_rotation taiyuan_sword'''.split())
DELIVERIES = frozenset('''next_window hold_once bind_event_source two_half_packets initiative_reversal_gate
survive_full_round interrupted_once_resume retarget_before_commit attack_defense_split spent_receipt_on_expiry
successful_echo_split convert_before_payment'''.split())
TRIGGERS = frozenset('''paid_preparation actual_incoming actual_outgoing ordinary_complete body_endured
observed_cast existing_form_exchange'''.split())
COVENANTS = frozenset('''confirm_later pay_state_nontriggering body_commitment observed_target_binding
no_execution_window observed_event_once'''.split())
CLAUSES = frozenset('''forgo_attack two_paid_cycle source_repeat incoming_once next_attack_only reverse_to_first
outgoing_required source_latest aged_debuff give_corpse stagger_recovery source_changed domain_ended two_sources
restore_first target_defended repeat_refund had_second forecast_last give_ally two_sources_memory split_ally
reset_after_cycle next_incoming formation_required split_targets domain_paid body_required form_required
source_hits_only source_bound reverse_to_second target_exchanged largest_loss first_target incoming_last
both_directions second_source paid_source shield_used attacked_shield expiry_seed first_form_only
mana_refund_only delayed_all source_current reverse_either sequential_shield ally_required source_hurt_owner'''.split())
FIELDS = frozenset('''version generator_version identity trigger covenant delivery payload clauses clause
cost_bp strength_bp ward_bp cooldown uses duration resource category signature prestige'''.split())


def validate_catalog(value):
    if set(value) not in (FIELDS, FIELDS | {'mana_cost'}) or value.get('version') != 3 or value.get('generator_version') != 3:
        raise ValueError('固定功法配方字段或版本无效')
    if 'mana_cost' in value:
        if value.get('resource') != 'mana':raise ValueError('固定法力费用不能用于元力功法')
        fee=value['mana_cost']
        if isinstance(fee,bool) or not isinstance(fee,(int,float)) or not math.isfinite(fee) or not .01<=fee<=10000000.:
            raise ValueError('固定法力费用超出有限范围')
    for key, allowed in (('trigger', TRIGGERS), ('covenant', COVENANTS), ('delivery', DELIVERIES),
                         ('payload', PAYLOADS), ('resource', {'mana','energy'}),
                         ('category', {'spiritual','body','divine_sense','transformation'})):
        if not isinstance(value[key], str) or value[key] not in allowed:
            raise ValueError('固定功法未知规则：' + key)
    if (not isinstance(value['clauses'], list) or len(value['clauses']) > 8
            or any(not isinstance(k,str) or k not in CLAUSES for k in value['clauses'])
            or len(set(value['clauses'])) != len(value['clauses'])):
        raise ValueError('固定功法附加条款无效')
    for key in ('identity', 'clause', 'signature'):
        if not isinstance(value[key], str) or len(value[key]) > 200:
            raise ValueError('固定功法身份无效')
    if not value['identity'] or len(value['signature']) != 64:
        raise ValueError('固定功法来源缺失')
    if type(value['prestige']) is not bool or value['prestige'] != (value['identity'] == 'TECH_COMMON_GUI'):
        raise ValueError('卓绝功法必须显式登记')
    if (value['payload'] == 'taiyuan_sword') != value['prestige']:
        raise ValueError('归墟剑专属机制不得复制给其他功法')
    for key, lo, hi in (('cost_bp',100,600),('strength_bp',1,1000),('ward_bp',1,150),
                         ('cooldown',0,3),('uses',1,5),('duration',1,2)):
        if type(value[key]) is not int or not lo <= value[key] <= hi:
            raise ValueError('固定功法数值越界：' + key)
    if value['uses'] > 3 and value['payload'] != 'five_step_rotation':
        raise ValueError('仅五式轮转可运行五次缩额效果')
    return copy.deepcopy(value)
