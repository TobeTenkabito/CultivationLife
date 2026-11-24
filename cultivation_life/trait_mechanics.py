"""Distinct personal traits expressed in the ordinary battle's existing event vocabulary."""
from .trait_lineages import LINEAGES
from .trait_repertoires import REPERTOIRES
from .trait_rule_builders import ATTACK, DEFEND, HIT, ONCE, Signature, adjust, fact, modify, rule, status


SIGNATURES = {
    "iron_shirt": Signature("每战首次迎上基础威力达到自身满态势 16% 的普通攻击时，以铁衣硬接，本次交锋合计普通损耗封顶 13%。", (
        rule("硬接", "ordinary_before_damage", modify("ordinary.received_cap", .13),
             when={"all": [DEFEND, fact("event.amount", "ge", .16)]}, limits=ONCE),
    )),
    "brook_breath": Signature("上轮普通交锋受创、本轮未再受普通战损时，轮末恢复 2 个百分点肉身完整度。每战最多两次。", (
        rule("回息", "round_end", adjust("body", .02), limits={"per_battle": 2},
             when={"all": [fact("previous.self.ordinary_received", "gt", 0),
                           fact("self.ordinary_received", "eq", 0), fact("self.body", "lt", 1)]}),
    )),
    "swallow_turn": Signature("普通交锋失去先手时蓄一次回身。随后两轮内，下次参与普通交锋时身法提高 25%，用后消散。", (
        rule("回身", "initiative_resolved", status("回身", "ordinary.mobility", .25, 2,
             delay=1, consume_on="ordinary_start"), when=fact("event.first", "eq", False)),
    )),
    "willow_hook": Signature("普通攻击造成战损时钩住该敌。随后两轮内，自己对其下一次普通攻击增伤 15%。施钩后间隔两轮才能再次施钩。", (
        rule("牵丝", "ordinary_after_damage", status("钩丝", "ordinary.dealt", .15, 2,
             delay=1, bind_target=True, consume_on="ordinary_before_damage"), when=HIT, limits={"cooldown": 2}),
    )),
    "moss_veil": Signature("肉身自带木属性护身选项，空手或法宝遭封禁时仍可选择木护身。"),
    "warm_jade": Signature("战意低于 55 且自身态势高于 40% 时，轮末以 3 个百分点态势换回 12 点战意。每战一次。", (
        rule("舍劲定心", "round_end", adjust("state", -.03), adjust("morale", 12), limits=ONCE,
             when={"all": [fact("self.morale", "lt", 55), fact("self.state", "gt", .4)]}),
    )),
    "red_sand": Signature("选择火护身时，把每击土伤份额的三分之一转为火伤。土、火各自结算克制和抗性。"),
    "dawn_drum": Signature("每战首次夺得普通交锋先手时击鼓。本轮若实际击伤敌人，轮末本方回复 8 点战意，按本人参战战力占比分摊。", (
        rule("鸣鼓", "initiative_resolved", dict(op="status", key="鼓声", duration=1),
             when=fact("event.first", "eq", True), limits=ONCE),
        rule("应鼓", "round_end", adjust("morale", 8), when={"all": [
             dict(status="鼓声", op="gt", value=0), fact("self.ordinary_dealt", "gt", 0)]}),
    )),
    "winter_current": Signature("普通交锋后手时收势，威能降低 10%，换得一层雪衣。本轮第一份落向自己的普通攻击伤害降低 28%。", (
        rule("收势凝衣", "initiative_resolved", modify("ordinary.might", -.1),
             status("雪衣", "ordinary.received", -.28, 1, consume_on="ordinary_before_damage"),
             when=fact("event.first", "eq", False)),
    )),
    "silver_shear": Signature("选择金护身时，含金的混合攻击把其他灵属性份额收束为金伤。物理份额照常结算。"),
    "vine_coil": Signature("普通攻击造成战损后缠住该敌，使其下轮身法降低 20%，影响双方争先。敌方可以驱散，施缠后间隔两轮。", (
        rule("缠足", "ordinary_after_damage", status("缠足", "ordinary.mobility", -.2, 1,
             delay=1, recipient="target", dispellable=True), when=HIT, limits={"cooldown": 2}),
    )),
    "candle_shadow": Signature("每战首次对敌普通出手为虚掌，伤害降低 20%，在该敌身上留下烛影。随后两轮内自己首次再攻该敌时增伤 40%。", (
        rule("虚掌留影", "ordinary_before_damage", modify("ordinary.dealt", -.2),
             status("烛影", "ordinary.dealt", .4, 2, delay=1, bind_target=True,
                    consume_on="ordinary_before_damage"), when=ATTACK, limits=ONCE),
    )),
    "stele_breaker": Signature("每战首次普通攻击造成战损时打出一道裂口。随后两轮内，任一友方对该敌的第一份普通攻击增伤 25%，用后裂口合拢。", (
        rule("碎碑开隙", "ordinary_after_damage", status("裂口", "ordinary.received", .25, 2,
             delay=1, recipient="target", consume_on="ordinary_before_damage"), when=HIT, limits=ONCE),
    )),
    "river_banner": Signature("每个实际击伤敌人的普通交锋轮末积一层浪，最多两层。满层后下一份普通攻击耗尽两层、增伤 30%，命中当轮可以重新积浪。", (
        rule("积浪", "round_end", dict(op="counter_add", key="浪", value=1, max=2),
             when=fact("self.ordinary_dealt", "gt", 0)),
        rule("放浪", "ordinary_before_damage", dict(op="counter_consume", key="浪", value=2),
             modify("ordinary.dealt", .3), when=ATTACK),
    )),
    "orchid_shade": Signature("已选护身属性的所有来源被封禁时，以阴护身暂代。任一原来源恢复后，立即切回原属性。"),
    "sun_duster": Signature("轮初拂去自己身上最早生效的一项敌方短效减益。仅限可驱散且含本轮最多剩两轮的普通交锋减益，每战一次。", (
        rule("拂秽", "round_start", dict(op="dispel_short_debuff"),
             when=fact("event.short_debuff", "eq", True), limits=ONCE),
    )),
}


SIGNATURES.update({key: entry.signature for key, entry in REPERTOIRES.items()})


def combat_rules(traits):
    return tuple(dict(step, schema_version=3, source_id="特质·" + LINEAGES[key].name)
                 for key in traits if key in SIGNATURES for step in SIGNATURES[key].rules)
