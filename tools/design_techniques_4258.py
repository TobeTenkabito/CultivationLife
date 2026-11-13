"""Author a reviewable design catalog. Never imported by the game or save loader.

The expanded JSON is the deliverable: every book has its own complete rule.
Shared authoring primitives are deliberately exposed, not presented as 4258
unrelated combat engines. Numeric checks are design checks, not battle tests.
"""
from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "technique-design-4258"
SOURCE = ROOT / "content" / "techniques.json"

PATHS = {
    "dao": ("道修", "循序周流", "首个窗口只登记机会，可以放弃；下一个合法窗口确认付费，随后才建立效果。未确认不产生任何收益。", "不能在登记机会的同一事件兑现", "confirm_later"),
    "demonic": ("魔修", "逆脉先偿", "确认付费时另付自身初始最大战斗态势的0.2%；这笔自损不触发受创收益，不允许付至零；效果按本书时序兑现。", "被打断也不退自损；低态势时无法使用", "pay_state_nontriggering"),
    "monster": ("妖修", "筋骨承载", "付费后暂占自身一次普通交锋的破法能力：该次破法-6%；等该次交锋结束后才允许兑现，封禁普通交锋时不能跳过承载。", "须先完成一次实际普通交锋；不能依靠旁观蓄力", "body_commitment"),
    "ghost": ("鬼修", "照影系敌", "付费时绑定本场已经观察到的一个实际敌人；收益只由该敌人的交锋触发或用于与其交锋，自身恢复也须该敌人仍在场。", "绑定敌人退出后本次收益消散，不改绑陌生目标", "observed_target_binding"),
    "buddhist": ("佛修", "持戒收锋", "付费后本次兑现窗口不发动终结处决，普通交锋仍按原规则结算；打破收锋承诺便清除本次尚未兑现的收益。", "与追求即时处决的打法冲突；不授予不死或免罪", "no_execution_window"),
    "confucian": ("儒修", "据实立应", "付费只依据本场已发生且本人可知的敌方动作记录；对同一记录仅可取得一次收益，未知行为不补造证据。", "需要先观察；更换招式的对手不容易反复供给机会", "observed_event_once"),
}

# Each family specifies a concrete conversion, not an element damage multiplier.
# The effect budgets below replace {p}/{h}/{r}; percentages use an immutable
# pre-new-rules baseline and never use the result of another new rule.
FAMILIES = {
    "neutral": ("归息", "吐纳有节，散乱之气归于一线", "self_cost_rebate",
        "下一次普通交锋防护+{g}%，占本次预算80%；其实际参与防护结算后，另用20%预算返还本书本次已付法力的5%。无实际付款不返还，单次不超过初始容量1%、整战不超过2%。", "需要先防护再回气；返还小于支出，不能单靠吐纳无限补充法力", ["paid_cost_receipt"]),
    "metal": ("寻隙", "敛锋入骨，先辨坚甲纹理再出剑", "bound_breach",
        "在实际交锋对象上登记一个隙印；下一次对同一对象的合法普通攻击破法+{p}%，真正用于计算后消耗；两轮内未用则消失。", "换敌会丢失隙印，不能以弱敌铺印再打强敌", ["target_mark"]),
    "wood": ("续芽", "生机伏于枯处，须得片刻安宁才萌发", "interruptible_restore",
        "埋下一枚续芽；到下一轮末，若期间未遭单次超过初始最大态势4%的敌方实际损耗，则恢复{h}%初始最大态势；否则芽毁，不退款。", "持续强攻可以阻断恢复；不能治疗肉身或复活", ["loss_window"]),
    "water": ("回澜", "不与来势硬争，借已受之力回转护身", "receipt_shield",
        "只记录兑现前一轮本人所受敌方实际损耗；下一次同源普通攻击可减免其中25%，并受{h}%初始最大态势上限约束；没有受损记录时不产生护持。", "第一击没有收益；自伤、友伤和零损耗都不能供给回澜", ["loss_receipt", "finite_shield"]),
    "fire": ("伏焰", "将火意压入一击，余焰随后才显", "budgeted_afterburn",
        "从本书至多{p}%的额外普通伤害预算中取一半用于当前合法交锋，另一半在下一轮对原目标结算；后半仍须通过原作用资格，目标离场即消散，不生成额外攻击。", "延后部分可能落空；余焰不能递归触发命中收益", ["deferred_damage"]),
    "earth": ("承岳", "立身如岳，护持一经承重便会耗尽", "finite_shield",
        "建立总额为{h}%初始最大态势的临时护持，持续两轮；每次真实减免都扣同一余额，余额为零即结束；未用完不转成回复。", "连续攻击会耗尽同一份护持，不按受击次数重复发放", ["finite_shield"]),
    "wind": ("错步", "不求凭空消失，只求下一步不在旧节奏中", "initiative_switch",
        "比较本人最近两次真实普通交锋的先后手；发生变化才使下一次交锋身法+{p}%，否则本次只保留两轮等待变化，不强制取得先手。", "先手长期不变时收益难以兑现；不产生地图移动", ["initiative_history"]),
    "thunder": ("候雷", "雷意先敛而后发，未成之雷不可催取", "charge_release",
        "记录一次已经付费的雷引；至少经过一轮，再于本人下一次合法普通攻击加入{p}%额外伤害；同一雷引只用一次，等待期间被封禁功法则熄灭。", "起手没有追加伤害，封禁可破坏等待中的雷引", ["delayed_token"]),
    "yin": ("识复", "从敌人重复的起势中听见未尽之音", "repeat_source_response",
        "记录一个本人已观察到的敌方招式来源；该来源再次作用于本人时，本次损耗降低{p}%，随后记录消费；不识别未见招式，不永久记忆场外敌人。", "敌人改变来源即可避开针对，普通未标明来源的事件不伪造招式", ["observed_source"]),
    "yang": ("照垢", "阳意照见附着之物，清浊须逐一辨明", "cleanse_temporary",
        "移除自身一项已登记为可驱散、剩余不超过一轮的普通交锋数值减益；不移除领域、剧情、拘禁或资格限制；每次只处理一项。", "没有合法减益就不付款；不能把所有控制一概清除", ["dispel_registry"]),
    "metal_water": ("洗锋", "以水洗去旧势，使锋芒落在护持将尽之处", "barrier_followup",
        "在本人的合法交锋实际耗尽目标一份临时护持后，保留一个两轮隙印；下一次对该目标攻击破法+{p}%，不附赠额外行动。", "没有临时护持的目标不供给机会；不能把护持过期当击破", ["barrier_receipt"]),
    "water_wood": ("润芽", "受损之处先留水意，再让生机慢慢接续", "delayed_loss_recovery",
        "把前一轮所受敌方实际损耗的20%登记为待恢复额，至多{h}%初始最大态势；下一轮末恢复其中一半，再下一轮末恢复另一半，未兑现部分受功法封禁中断。", "恢复分期发生，不能挽回已经死亡或被制伏的人物", ["loss_receipt", "staged_recovery"]),
    "wood_fire": ("薪息", "生机与火势共用一根薪，燃尽便不能再养", "offense_restore_choice",
        "确认时二选一：把本次预算用于下一击至多{p}%额外伤害，或于下一轮末恢复{h}%初始最大态势；确定后锁定，不能先伤敌再领取恢复。", "输出和恢复互斥，选择后不能追溯更改", ["exclusive_choice"]),
    "fire_earth": ("熔垒", "将尚未喷薄的火压入土壁，攻守只取其一", "damage_to_shield",
        "放弃本书本次全部额外伤害，将其换成持续一轮的有限护持，余额至多{h}%初始最大态势；护持碎裂不再爆炸，不重复领取攻击预算。", "面对不进攻的敌人容易空耗；无攻防双领", ["budget_conversion", "finite_shield"]),
    "earth_metal": ("裂甲", "护壳碎裂之时，留下可供出锋的断口", "broken_shield_breach",
        "本人一份真实临时护持被敌方攻击耗尽后，下一次对该攻击者的普通交锋破法+{p}%；护持自然过期、主动取消或友方打破均不触发。", "需要先付出护持破损，不能靠反复开关制造裂口", ["barrier_receipt"]),
    "wind_thunder": ("转霆", "雷随步转，变换攻守次序才落下一击", "initiative_charge",
        "在本人先后手相较上次真实交锋改变时登记雷引；下一次对同一目标的合法攻击加入至多{p}%额外伤害，持续两轮，不强改先后手。", "固定先手或频繁换敌都会打断配合", ["initiative_history", "target_mark"]),
    "yin_yang": ("两仪", "阴阳交接，上一用决定下一用", "alternating_choice",
        "本书成功兑现后在攻式与息式间交替：攻式下一击至多{p}%额外伤害，息式下一轮末恢复{h}%初始最大态势；初式在战前确定，不能连续取同一式。", "当前轮式未必符合紧急需求；失败不算成功切式", ["alternating_state"]),
    "wind_thunder_yin": ("听隙雷", "听过一遍敌势，借步差把雷送回旧处", "repeat_initiative_breach",
        "记录已见敌方来源；它再次攻击本人且本人本轮后手时，保留下一次对其破法+{p}%的机会；本次仍正常承受伤害，机会两轮失效。", "必须见过来源且处于后手，不直接反射伤害", ["observed_source", "initiative_history"]),
    "wind_thunder_yang": ("开霁", "以变势催雷，阳意只扫去挡在身前的一缕阴翳", "initiative_cleanse",
        "真实先后手发生变化后，可清除自身一个剩余不超过一轮的可驱散普通数值减益；本次不同时获得增伤，不能驱散领域和永久状态。", "变化与减益须同时存在，不能在无目标时储存万能驱散", ["initiative_history", "dispel_registry"]),
    "wind_yin_yang": ("晦明步", "进退之间调换明暗，不把两面的好处一并占尽", "initiative_choice",
        "兑现时若本次交锋先手，将本次预算用于破法+{p}%；若后手，则用于本人普通防护+{p}%；只对该次交锋生效，不同时取两项。", "分支由实际先后手决定，不能自行宣称有利分支", ["initiative_history", "exclusive_choice"]),
    "thunder_yin_yang": ("阴阳雷印", "雷印记住一次消耗，待敌再运同法时才回应", "repeat_paid_cast",
        "只记录本人已见且实际付费的敌方招式；其再次成功付费时，为本人下一次对其的普通攻击提供破法+{p}%；不增加敌方费用，不窃取资源。", "免费被动与未知费用不提供雷印；不读取隐秘法力账本", ["observed_source", "paid_cost_receipt"]),
    "wind_thunder_yin_yang": ("四象择应", "风雷阴阳同在一炉，每次运转却只开一门", "four_way_choice",
        "确认时从破法、普通防护、身法各+{p}%或一次合法短效驱散中选一；前三项只作用于一次交锋，四者共用本书次数与费用，不轮流免费领取。", "用途广但每次只能选一门，费用高于专一手段", ["exclusive_choice", "dispel_registry"]),
    "metal_water_wood": ("洗锋养息", "剑锋洗净后归于枝脉，攻势也能成为收息的起点", "breach_then_restore",
        "本人的合法攻击实际耗尽一份敌方临时护持后，下轮末恢复{h}%初始最大态势；恢复依赖真实破持回执，单次破持只登记一份。", "对无护持目标无效；恢复来得晚，不能当场免死", ["barrier_receipt", "staged_recovery"]),
    "wood_fire_earth": ("薪垒", "余焰尚未落下时，也可封回土中护身", "cancel_afterburn_for_shield",
        "本次先登记一份尚未造成伤害的余焰；在下一轮开头选择对原目标结算至多{p}%额外普通伤害，或永久取消该余焰换取{h}%初始最大态势护持；两者互斥。", "护持与伤害共用一份预算，已经造成的伤害不能回收", ["deferred_damage", "budget_conversion"]),
    "metal_wood_water_earth": ("四序回护", "护持、回流与锋意依次相接，不容四序倒行", "shield_then_breach_or_restore",
        "先获得至多{h}%初始最大态势的一轮护持；其真实被敌方耗尽后，才在下一轮选择破法+{p}%或恢复{h}%初始最大态势；两阶段各只使用本次预算的一半。", "后半必须以护持真实耗尽为前提，未破不能领，不能满额叠加", ["barrier_receipt", "exclusive_choice", "budget_split"]),
    "wood_water_fire_earth": ("四时藏用", "生、润、焚、藏并非同发，须先定下一时", "forecast_choice",
        "付费时预定下一轮用于进攻、恢复或护持：分别至多{p}%额外普通伤害、{h}%初始最大态势恢复或同额护持；只能选一，下一轮局势变化不自动改选。", "需要提前判断，错误预定会浪费窗口", ["exclusive_choice", "delayed_token"]),
    "five_elements": ("五行递用", "五行各守一用，轮转需要实际兑现而非空念次序", "five_step_rotation",
        "五式依次为破法、恢复、护持、额外普通伤害、身法；各次仅兑现当前一式，交锋修正至多{p}%，恢复或护持至多{h}%初始最大态势。首次按本书前置开轮，之后每轮最多实付一次费用运行下一式，不重复开轮等待；成功才推进，跨战不保存轮序。", "不能跳过不需要的式；空过不算成功，短战通常只能使用前几式", ["rotation_state"]),
}

# Twelve timing designs, not twelve larger multipliers. All are final expanded
# into individual records; any unavailable fact must remain unknown.
FORMS = [
    ("直承", "next_window", "满足本书前置后，在下一次符合效果要求的合法窗口兑现；最多等两轮，过期清空。", "窗口短，错过即失去已投入的费用"),
    ("留势", "hold_once", "满足前置后可主动延后一次：原窗口不领取收益，延到随后一轮的同类窗口；不得继续顺延，总等待不超过三轮。", "保留意味着放弃当前收益"),
    ("追源", "bind_event_source", "把机会绑定到触发准备的实际敌人；若准备事件无方向，则选一名本场已见且实际在场的敌人。只在与其再次交锋时兑现，恢复和护持也须其仍在场；没有可选敌人不能开启。", "更换敌人或敌人离场便失去机会"),
    ("折半", "two_half_packets", "把同一份预算分成两半，先在一个合法窗口兑现前半，再在下一轮同类窗口兑现后半；前半未成功则不派生后半。", "不能把两半各按完整额度结算"),
    ("逆候", "initiative_reversal_gate", "准备后只在本人实际先后手相较准备时改变的交锋窗口兑现；等待最多三轮，不强行改变先手；轮末效果由该次交锋解锁。", "次序未变就可能空耗"),
    ("守成", "survive_full_round", "准备后须完整经历一轮且保持未死亡、未被制伏，随后才兑现；期间禁止提前取得本书护持或恢复。", "需要先承受一轮风险"),
    ("断续", "interrupted_once_resume", "准备后遇一次实际功法封禁可暂停机会至封禁解除后的首个合法窗口；只暂停一次，仍受四轮绝对期限，封禁期间无任何收益。", "第二次封禁或超过期限直接失败，不保留到场外"),
    ("移锋", "retarget_before_commit", "准备绑定一个已见敌人；付费前允许改选另一名实际在场且可合法作用的已见敌人一次；付费后锁定，未改选也可正常兑现。", "不提供额外目标、不扩大攻击范围；受更严格的道途绑定约束"),
    ("分进", "attack_defense_split", "把一次预算拆成效果本体与自护两半：前半按本书效果兑现，后半仅在随后一次敌方普通攻击中减免损耗；两部分共用原本书总额度。", "进攻效果减半；未受攻击则后半过期"),
    ("留根", "spent_receipt_on_expiry", "效果按原窗口兑现；若已付款后因目标离场而整次未兑现，可在结束时退回该次已付法力的25%，且至多初始容量的1%；其他失败不退款。", "不能退款自损、机会成本或已兑现的份额，退款仍计入本书返还上限"),
    ("回照", "successful_echo_split", "预算先用三分之二；首次实际产生非零效果后，余下三分之一在下一轮同类窗口使用；余响不产生新的余响，原目标规则不变。", "首次无效则后续也无效，总额没有增加"),
    ("取舍", "convert_before_payment", "付费前选择原效果，或放弃全部原效果改为一次自护，余额至多本书护持额度；选择确定后锁定，不在遇险时追溯改选。", "通用自护需要放弃该书专长，不同时取得两者"),
]

ROLES = {
    "main": ("修炼", "paid_preparation", "本轮开头确认运转，先按本书道途与时序准备；不要求攻击命中，也不因单纯等待自动积累无限收益。", 2.0, 6.0, 1.0),
    "support": ("辅助", "actual_incoming", "本人实际承受一次合法敌方普通交锋损耗后可以准备；被完全挡住、自伤、友伤和效果自身派生损耗均不触发。", 2.5, 7.0, 1.5),
    "combat": ("杀伐", "actual_outgoing", "本人一次合法普通交锋对实际目标造成非零损耗后可以准备；只读取本人贡献，不把队友或余焰的损耗再次归给本人。", 3.0, 10.0, 1.0),
    "balanced": ("兼修", "ordinary_complete", "本人完成一次有效普通交锋后可以准备，攻守任一侧有真实损耗即可；一次交锋只登记一次。", 2.5, 8.0, 1.25),
    "body": ("炼体", "body_endured", "本人参与普通交锋并实际承受敌方损耗后可以准备；使用原肉身与伤势资格，神游或无适用肉身时不借此生成肉身。", 2.5, 7.0, 1.5),
    "divine_sense": ("神识", "observed_cast", "本人实际观察到一项敌方招式结算后可以准备；禁神识或未知来源不产生记录，不能读取未公开配置。", 2.0, 6.0, 1.0),
    "transformation": ("变身", "existing_form_exchange", "原规则下已经合法维持适用变身，并完成一次普通交锋后可以准备；本书不赠送形态，不绕过原变身消耗。", 3.0, 8.0, 1.25),
}

INVARIANTS = [
    "所有作用先通过原功法修习、世界适用、仙凡层级、目标和禁制检查；品阶本身不创造作用资格。",
    "法力容量、最大战斗态势和普通交锋基线在战斗开始时固定；新增专属规则不能彼此放大这些基准。",
    "态势恢复只回到开战时的态势上限，不等于肉身治疗、HP回复、解控、复活或高阶储量补充。",
    "本人、原目标、付款和损耗回执唯一；不复制人物、装备、资源池，不通过改写地点或world实现机制。",
    "派生损耗、护持、回复、退款和自损不再作为本书的新触发来源；不能循环自激。",
    "每次先确认合法窗口和足额资源，再原子提交费用与效果；预览不改变状态，未知事实不能当成满足。",
    "只限制这部功法自身的次数、费用和额度；本稿不规定全角色生效数量、槽位、跨书叠加或主动行动配额。",
    "跨书叠加风险尚未解决，单书数值有界不等于全部同时生效时系统已平衡；实装前必须另做组合校准。",
]

DEPENDENCIES = {
    "book_dispatch": "待本体新增：普通固定功法的统一规则读取、本人/原目标事件投影；不复用DLC开关作为本体资格。",
    "paid_cost_receipt": "待本体新增：普通法力逐人物支付回执及仅退本人实际付款；现有NPC普通法力并非完整独立账本。",
    "budget_ledger": "待本体新增：按人物+功法+战斗记录实际兑现额度、分包、回收和消耗，续战不重置。",
    "target_mark": "可复用目标绑定语义状态；需固定功法适配器及真实目标事件。",
    "finite_shield": "待本体新增：可消耗余额的临时普通护持；不能用固定减伤百分比冒充有限余额。",
    "loss_receipt": "可复用实际损耗事实；待补来源去重、归因与过去窗口账本。",
    "loss_window": "待本体新增有界窗口内最大单次敌方实际损耗查询，不扫描历史日志代替。",
    "deferred_damage": "待本体新增原伤害预算分包、延期资格复核；不是免费新增攻击。",
    "initiative_history": "可复用先后手事实与上轮快照；需明确无普通交锋时保持未知。",
    "delayed_token": "可复用限时状态、计数和轮次；需在固定功法入口投影。",
    "observed_source": "待本体新增本人可见招式来源与有限观察记录；不读取隐藏配装。",
    "dispel_registry": "待本体新增可驱散状态注册、所有权和优先级；不得清除永久/剧情禁制。",
    "barrier_receipt": "待本体新增原护持余额与真实耗尽回执；与自然过期严格区分。",
    "staged_recovery": "可复用轮末态势adjust与状态；需增加恢复预算与分期取消。",
    "exclusive_choice": "待本体新增战前/触发时互斥决策记录；本稿不设计按钮和槽位。",
    "alternating_state": "可复用计数和状态；成功提交后才改变轮式，续战持久。",
    "rotation_state": "可复用有限状态机；需正确记录成功兑现，不能失败也推进。",
    "budget_conversion": "待本体新增同一份预算的互斥转换及取消回执。",
    "budget_split": "待本体新增总额守恒的多阶段效果包，未知后续目标不能提前结算。",
    "legacy_specialty": "待本体新增该书的专属事实门槛/用途；须逐项按本书说明接入，不将文案视为已可执行。",
}

# Deliberately authored named-book hooks. They are additional eligibility/choice
# rules, not free second effects. Ordinary numeric budgets also govern them.
# Keys are exact existing titles; no runtime inference from Chinese book names.
SPECIAL = {
    "无名吐纳诀": ("neutral", "ordinary_complete", "停攻吐纳", "准备时明确放弃下一次主动攻伐；完成该轮普通守御后才允许返还本书实付法力。初学者可以使用，不依赖领域或仙器。"),
    "太虚周天经": ("neutral", "paid_preparation", "小周天闭环", "记录本书连续两次实际付款，第二次成功兑现才返还第一笔付款的一部分；中途换用本书的互斥分支便重新起周。"),
    "明镜因果篇": ("yin", "observed_cast", "照见复因", "只针对本人见过且再次出现的同一招式来源建立回应，第一次见招不产生防护；观察不读取对方尚未施展的功法。"),
    "血河真解": ("water", "actual_incoming", "血痕逆流", "只从敌方造成的实际损耗提取护持依据；本书逆脉自损和任何友方伤害不进入血痕账本，同一损耗回执只能兑现一次。"),
    "魔煞引气诀": ("fire", "paid_preparation", "煞息封口", "预先付费后封存一口煞息，第一次自己的普通交锋必须用掉，未交锋而到期则散去；不能在等待中不断囤积。"),
    "扶摇风经": ("wind", "ordinary_complete", "借后转先", "仅在上一次交锋后手、本次先手时建立步势；反向变化不供给本书机会，不强制获得先手。"),
    "九霄雷法": ("thunder", "actual_outgoing", "雷引同敌", "雷引必须由本人对原目标的一次真实普通损耗点亮；后续雷意仍作用于同一目标，不能以弱敌蓄雷再换强敌。"),
    "玄阴真经": ("yin", "observed_cast", "藏声听复", "每次只选择一个已见来源监听；重新选择便清除旧记录，不能同时监听全场所有招式。"),
    "纯阳道典": ("yang", "paid_preparation", "温阳逐垢", "只能处理已经持续到下一轮的普通可驱散减益，刚附着时不立即抹除；净除后本次不再追加攻击。"),
    "九霄御剑典": ("metal", "actual_outgoing", "一剑试隙", "前一次剑势先按普通交锋结算，实际造成非零损耗才记下隙印；后续剑势消费隙印，失去原目标即清空。"),
    "万魔化生经": ("wood_fire", "actual_incoming", "魔息分途", "在真实受创后选择将本次预算用于追击或恢复；选择恢复便注销追击资格，不能从同一伤口取得两份收益。"),
    "尸阴御傀录": ("earth", "paid_preparation", "护持原傀", "存在一具实际可参战且未失效的原尸傀时，可将本次护持改给该傀；从本人预算实扣，仅护持战斗态势，不修复尸体完整度。"),
    "血海魔胎经": ("water_wood", "actual_incoming", "魔胎缓养", "把合法恢复拆给未来两个轮末，第二份须第一份实际恢复非零才开启；满态势时不把溢出恢复存为第二条命。"),
    "天魔游玄录": ("wind_yin_yang", "observed_cast", "见招改势", "只在敌方实际施展的来源较上次改变后准备；依据本次实际先后手选攻守，不能自行任选有利结果。"),
    "四源吞灵魔功": ("neutral", "observed_cast", "辨源回收", "只从本人本场已经支付且来源可核验的费用中回收；观察到不同敌方气源只改变可准备时机，不窃取敌方资源、不创造四源。"),
    "无相魔域典": ("earth", "paid_preparation", "域隙收束", "已有合法魔域实际停止维持后才准备一次普通护持；未拥有或未实际展开领域不触发，不借此免费再开领域。"),
    "诸天化魔经": ("wood_fire_earth", "observed_cast", "见异择化", "在本场见到第二种不同敌方招式来源后，选择余焰或自护；两支共用同一份额度，不把多来源视为多倍奖励。"),
    "太初魔尊法": ("five_elements", "paid_preparation", "魔枢次第", "首次付费时选定五式的起始位置，此后只按固定方向推进；重新准备和断续战不能把轮序重置到有利一式。"),
    "菩提无相经": ("yang", "actual_incoming", "受垢不留", "只有本人受损且仍带有合法普通减益时才准备驱散；没有减益不付款，驱散不改写已有业力和敌我关系。"),
    "庚金铸锋经": ("metal", "paid_preparation", "藏锋待坚", "先观察目标一次实际普通防护结算，再铸一枚针对该目标的隙印；防护未参与结算时不能凭面板预知弱点。"),
    "青帝长生篇": ("wood", "actual_incoming", "断枝续芽", "恢复依据本人实际损耗，续芽被重击摧毁后进入本书冷却；不能在同一轮反复补种抵消打断。"),
    "沧海归元录": ("water_wood", "actual_incoming", "归流有据", "一份实际受创记录仅供一次分期恢复，已被本书取用的记录不得在后续轮次再次选择。"),
    "离火焚心诀": ("wood_fire", "actual_outgoing", "留薪或尽燃", "命中后选择留薪恢复或继续余火；恢复支不造成后续灼伤，强攻支不返还法力。"),
    "厚土载道经": ("earth", "paid_preparation", "一垒承重", "同一份土垒按余额承受连续普通攻击，护持未耗尽时不刷新剩余期限；新准备不能给旧垒续满。"),
    "罡风无相典": ("wind", "ordinary_complete", "先后皆变", "本场必须已经亲历一次先手和一次后手，才可将之后的先后手变化转为身法收益。"),
    "紫霄神雷经": ("wind_thunder", "actual_outgoing", "变势落雷", "本人命中后记录当次先后手，下一次交锋先后手改变才允许雷意释放；对同一目标保留，换敌散去。"),
    "太阴炼神书": ("yin", "observed_cast", "听过方知", "观察记录仅在本人神识可用时建立，神识被禁期间不续记；已建立记录仍须正常功法资格才能消费。"),
    "大日纯阳章": ("yang", "paid_preparation", "正午独照", "一次只驱散最早附着的合法短效数值减益，不能越过先来的减益指定最有利的一项。"),
    "周天纳气篇": ("neutral", "ordinary_complete", "息随交锋", "每次有效普通交锋后只能登记一笔本书费用，按真实先后顺序结清，不能优先退款最大的一笔。"),
    "玉台固本经": ("earth", "actual_incoming", "稳台不叠", "受创后建立一次护持，旧护持还有余额时本书不再次付款开新护持；不能通过刷新覆盖损耗。"),
    "抱朴玄经": ("wood", "paid_preparation", "守朴养息", "准备恢复后若主动消费本书的另一待兑现机会，则取消本次续芽；要求在进取与安养间取舍。"),
    "玄都真解": ("neutral", "observed_cast", "解法归账", "本人见过敌方同一招式两次后，才允许回收一笔自身本书费用；观察次数不增加退款额度。"),
    "黄庭内景经": ("yin_yang", "paid_preparation", "内景两用", "首次选择守养起式，之后攻息交替；恢复到开战态势上限时不视为成功恢复，也不自动推进轮式。"),
    "太元归墟剑": ("metal_water", "actual_outgoing", "破持后剑", "实际耗尽敌方临时护持后所得隙印只能用于下一次对其的普通攻击，不得跨越多次出手一直保留。"),
    "玄览天机卷": ("yin", "observed_cast", "后见之明", "只针对已经在本人面前成功兑现过的敌方招式建立回应，被打断且无实际效果的起手不算已知。"),
    "海日生残夜": ("yin_yang", "ordinary_complete", "夜尽见日", "先经历一次后手交锋才进入攻式，之后攻息交替；没有后手记录时只可准备，不能直接取得攻式加成。"),
    "先天无极卦": ("wood_water_fire_earth", "observed_cast", "定卦不改", "依据本人已见敌方上一轮动作预定下一轮用途，付费后即锁定；实际局势不同也不能自动改卦。"),
    "虚界炼元篇": ("neutral", "paid_preparation", "炼余不生源", "仅回收本书尚未退回的实际普通法力支出，不回收高阶储量、物品消耗或代价性态势损失。"),
    "万法归一典": ("wind_thunder_yin_yang", "observed_cast", "万法只取一", "每次准备依据一个已见来源选择一种回应，同一次付款只允许一个分支；观察来源变多不提高数值上限。"),
    "太上济世经": ("wood", "paid_preparation", "济人先让己", "可将本次续芽交给一名原参战且合法可援助的同伴；本人放弃全部恢复，不能远程治疗场外人物。"),
    "玄潮冷焰": ("wood_fire_earth", "actual_outgoing", "冷焰收放", "后续余焰尚未造成损耗时，可整份撤回改成一次自护；已经命中的部分绝不回收。"),
    "五行转岳诀": ("five_elements", "ordinary_complete", "岳轮实转", "只有本次轮式对实际交锋产生非零效果才推进；免疫、无合法目标和满态势恢复都不转轮。"),
    "太虚分神篇": ("yin", "observed_cast", "分念不分身", "记录两名已见敌人的来源但每次只选一名回应；共用本书额度，不创建分身、额外攻击或第二份法力。"),
    "合欢秘典": ("water_wood", "paid_preparation", "同息相让", "仅当原有合法同伴实际参战时，可将一份恢复额度在本人和该同伴之间分配；没有同伴则只恢复本人，总额不增加。"),
    "阴阳参同契": ("yin_yang", "ordinary_complete", "参同守序", "攻息两式的成功兑现各记一次，只有两式均实际生效后才可重新选择下一轮起式；不能凭空与场外人物联动。"),
    "云雨神合经": ("water_wood", "actual_incoming", "共济一流", "对本人或一名实际同伴的恢复必须在付费时选定，后续分期不得改收款人，同一额度不能两边各领。"),
    "太一真罡": ("earth", "actual_incoming", "罡尽即散", "真罡只减免普通交锋损耗，原资格不允许挡住的作用不转成可挡；余额耗尽立即移除，不留下永久防护。"),
    "青木归元剑": ("metal_water_wood", "actual_outgoing", "剑后归元", "恢复来自本次真实破持回执，在下一轮末兑现；不得将攻击吸血直接叠到当前命中上。"),
    "玄岳真经": ("earth", "paid_preparation", "守岳候敌", "护持准备后须等待一次敌方普通攻击才启用，之前不计入防护面板，等不到敌人攻击便过期。"),
    "紫府金章": ("neutral", "paid_preparation", "府藏独账", "本书可标记一笔费用待退，标记期间新的付款不替换该笔；退回或过期后才能选择下一笔。"),
    "万木生灭阵": ("wood_fire", "actual_outgoing", "剑阵生灭", "只在原有实际阵势合法运转时允许在攻与息之间选用本次预算，不生成阵法实体或额外阵材；无阵时保留原功法基础用途。"),
    "太乙分光经": ("metal", "actual_outgoing", "分光同额", "可把一份隙印预算分给至多两名原本就会被合法攻击覆盖的目标，总额按份分摊，不扩大目标集合。"),
    "空明洞微典": ("yin", "observed_cast", "洞微择旧", "只回应最近一次成功观察到的敌方来源；新来源覆盖旧来源，不能保留全套抗性。"),
    "九转合道书": ("yin_yang", "ordinary_complete", "九转有限", "本场每次成功攻息转换只记进度，不额外赠送伤害或永久属性；进度仅允许一次调整起式，不能靠九转刷新次数。"),
    "苍木盘天阵": ("earth", "paid_preparation", "盘根护阵", "原阵势实际在场且可用时，可把本次护持作用于本人受其支持的普通交锋；不修复阵法耐久，不增加阵势库存。"),
    "春生剑域": ("wood", "paid_preparation", "域中续芽", "已有合法邻域的维持费实际支付后才能准备续芽；领域不在场不能伪造付款，回复仍只作用于态势。"),
    "混沌开天录": ("five_elements", "actual_outgoing", "开辟有序", "首次真实命中后确定五式起点，此后失败不跳式；不凭功法名获得开界、传送或越级攻击资格。"),
    "铁骨锻身诀": ("earth", "body_endured", "铁骨受力", "仅本人有合法肉身并承受普通交锋实际损耗后提供短时护持；护持不改写骨骼永久属性。"),
    "百炼真身经": ("earth_metal", "body_endured", "百炼识裂", "本人原临时护持真实被耗尽后才取反击隙印；同一护持只能登记一次，重建后须另有真实支出。"),
    "龙象镇狱功": ("fire_earth", "body_endured", "负重成垒", "本次放弃攻伐预算换取护持时，下一次普通交锋仍承受原身法与压制规则；不以护持解除镇压。"),
    "周天星辰体": ("yin_yang", "body_endured", "星次转体", "以第一次真实受创确定守养起式，成功恢复后才轮到攻式；不把自损算成星次开启。"),
    "太虚百炼体": ("water", "body_endured", "虚实承伤", "只使用本人普通态势损耗生成回澜，不把肉身完整度下降和态势下降重复计入两次。"),
    "万劫混元身": ("wood", "body_endured", "劫后续身", "恢复必须发生在本人仍存活且未被制伏的轮末；致命结算优先，不能靠待恢复额取消死亡。"),
    "凝神观想法": ("yin", "observed_cast", "一念一源", "只维持一个已观察来源的回应记录；转移观察时清空原记录，不能低阶全知。"),
    "血魂御念诀": ("thunder_yin_yang", "observed_cast", "付费见念", "仅对本人可知且已实际付款的敌方招式记印，未知费用不能按零处理后套利。"),
    "天魔分神典": ("wind_yin_yang", "observed_cast", "两念择一", "观察到敌方招式后只依本次实际先后手选择攻守，分神不增加行动次数和独立人物。"),
    "万魂驭神书": ("yin", "observed_cast", "众声归一", "群体攻击中只选择一名真实来源记录，其他人的损耗不并入该人的账本，人数不扩大本书额度。"),
    "百兽化形诀": ("earth", "existing_form_exchange", "兽形初护", "本场首次以实际合法兽形完成交锋后可准备护持；没有已学形态不自动赠送，解除变身清除待用护持。"),
    "万相图录": ("wind_yin_yang", "existing_form_exchange", "相随先后", "既有形态维持时根据实际先后手取一种回应，不依据形态数量增加收益；无形态不启动。"),
    "真灵化生经": ("wood", "existing_form_exchange", "形中续养", "仅在合法形态仍维持到恢复轮末时兑现续芽，形态提前结束则取消余下恢复。"),
    "诸天化形篇": ("wind_thunder_yin_yang", "existing_form_exchange", "一形一用", "本次选择的回应与付费时的原形态绑定，变换形态不复制机会，旧机会立即结束。"),
    "万相归一典": ("neutral", "existing_form_exchange", "归形结费", "只返还本书自身实际支付的法力，不返还原变身启动费用或材料，不能靠反复变化获利。"),
    "太初真灵图": ("five_elements", "existing_form_exchange", "真形轮式", "五式状态属于原人物和本书，变形或还原不重置轮序；退出合法变身时暂停收益但期限继续。"),
    "血影化魔经": ("fire", "existing_form_exchange", "影焰有主", "余焰绑定变身中的原施术者和原目标，身形变化不生成第二份火，也不凭血影产生移动。"),
    "天魔万化诀": ("wood_fire", "existing_form_exchange", "魔形攻息", "本次变身期间攻或息只选其一，变形不允许把已选攻式改成恢复领取第二份收益。"),
    "无相魔胎经": ("water_wood", "existing_form_exchange", "胎息不换命", "分期恢复不跨越形态结束，更不跨越肉身死亡；不存在以解除变身重置态势的收益。"),
    "诸天魔相图": ("wind_thunder_yin_yang", "existing_form_exchange", "相图锁用", "回应选定后跨本次形态维持期锁定，改选需结束旧机会并重新付费，旧费用不补退。"),
    "元始魔身谱": ("earth_metal", "existing_form_exchange", "魔身裂护", "合法魔身下护持真实碎裂才开启反击隙印；还原造成护持消失不算碎裂。"),
    "餐霞承露经": ("neutral", "paid_preparation", "霞息后返", "一笔费用须经过一次有效交锋才可部分返还；普通法力与仙灵力按原账本分开，不把回气升级成高阶储量。"),
    "太初仙光诀": ("yang", "paid_preparation", "仙光照俗垢", "仅驱散注册为普通短效减益的一项状态，名字中的仙光不授权解除其他仙法、领域或剧情限制。"),
    "太乙庚金剑典": ("metal", "actual_outgoing", "仙锋审资格", "隙印强化只作用于原本就能合法伤及的目标；攻击资格不足时不产生印记、不以破法替代资格。"),
    "九霄仙雷经": ("thunder", "actual_outgoing", "仙雷再核", "雷引延后释放时重新核验原攻击资格和目标存续，初次合法不代表后续永久合法。"),
    "紫府天心观想法": ("yin", "observed_cast", "天心记实", "记录只来自本人神识未被禁止时见到的成功招式，敌方隐藏配置和队友私有观察不自动共享。"),
    "玄黄不灭仙躯": ("earth", "body_endured", "玄黄有量", "临时护持独立于原仙躯资格，不能把有限护持描述为永久免伤；护持耗尽后立即回到原规则。"),
    "天河炼元经": ("water_wood", "paid_preparation", "天河分流", "恢复分期严格属于本人，人数增加不扩大总量，跨场景不携带待恢复包。"),
    "修罗战天经": ("fire", "actual_outgoing", "战意封焰", "余焰只跟随本次真实交锋目标，杀敌后余焰失效，不将剩余额度自动搬到下一敌人。"),
    "血海不灭功": ("water_wood", "actual_incoming", "血海非复生", "记录受创后分期恢复；死亡和制伏结算先于恢复，不能以待结算恢复阻止合法终结。"),
    "万劫魔相": ("earth_metal", "actual_incoming", "劫裂成锋", "反击机会要求实际临时护持耗尽，不把长期伤势和历史劫数变成开战免费积蓄。"),
    "寂灭天刀录": ("metal_water", "actual_outgoing", "断护再斩", "破持后的第二次攻击仍是正常交锋，不能以刀意追加免费处决，也不把击退写成击杀。"),
    "无生炼神典": ("yin", "observed_cast", "无生听旧", "回应只针对第二次见到的同源招式；目标死亡后记录清空，不从死人反复获得观察收益。"),
    "阿修罗不灭身": ("water", "body_endured", "战躯回势", "回澜只减少下一次普通损耗，不修复残肢、不抹除持久伤势、不改变原生命阶段。"),
    "血河逆脉功": ("wood_fire", "actual_incoming", "逆脉舍一", "自损是施法代价而非可回收伤害，攻击与恢复支仍只选一，不能先自伤再用本书全额收回。"),
    "太阴照魂篇": ("yin", "observed_cast", "照魂循源", "仅监听已见招式来源，不能把可见肉身身份推断成隐藏神魂身份或取得场外情报。"),
    "裂界行魔身": ("wind", "body_endured", "裂势不裂界", "只调整下一次普通交锋身法，不穿过界壁、不移动玩家、不跳出封逃或原场景。"),
    "黑日焚心典": ("fire", "actual_outgoing", "黑日不递燃", "余焰不能再次点燃余焰，也不计为新的招式命中；一次实际付款只产生一份伤害预算。"),
    "吞星魔躯": ("neutral", "body_endured", "吞余不吞库", "所谓吞星仅表现为本书费用部分回收，不抽取敌人高阶储量、世界灵气或后台资金池。"),
    "万魔归渊经": ("wood_water_fire_earth", "observed_cast", "归渊先定", "根据上一轮本人可见事实预定下轮攻守息之一，不能在看到结算结果后重新选择。"),
    "引阴凝魂诀": ("neutral", "paid_preparation", "阴息守账", "以原神魂可使用的法力支付本书费用，退款不增加魂寿、肉身或夺舍次数。"),
    "听魂术": ("yin", "observed_cast", "近声可闻", "只记录本场本人能观察到的敌人来源，无神识或隔绝感知时不建立新记录。"),
    "幽火斩魂篇": ("fire", "actual_outgoing", "幽火同权", "延后幽火仍受原目标神魂/肉身和作用资格判定，不把普通损耗改写成必定灭魂。"),
    "白骨载魂功": ("earth", "body_endured", "骨架承势", "护持使用原可用肉身，不凭书名制造骨身；身体不适用时只保留原已定义的非战斗功能。"),
    "命灯守魄经": ("wood", "actual_incoming", "灯续不还魂", "续芽只在当前生命阶段合法存续时恢复态势，魂灭和死亡后未兑现额度直接清除。"),
    "冥潮归一录": ("water", "actual_incoming", "潮账归一", "多人围攻的损耗分别归因，单次只选一名敌方来源建立护持，不能复制团队总损耗。"),
    "忘川照念法": ("yin", "observed_cast", "忘旧照新", "新观察到的来源可替换旧记录但会丢失原机会；忘记不是清除对方记忆或存档历史。"),
    "九狱空行典": ("wind", "ordinary_complete", "空行有界", "步势只参与原普通交锋身法，不解除拘禁、封逃、空间实例和跨界门槛。"),
    "阴阳合魄书": ("yin_yang", "paid_preparation", "合魄双序", "攻息轮式按当前原人物保存，换肉身或魂体外观不在本场重置起式和已用次数。"),
    "不灭阴身": ("water_wood", "actual_incoming", "阴身续势", "恢复的是原神魂角色当前战斗态势，不生成肉身、不延魂寿，也不刷新魂体消耗。"),
    "轮回门观想经": ("wood_water_fire_earth", "observed_cast", "观门择应", "在本场预定下一轮回应，不能提前读取未来事件，也不触发转世、复活或重置战斗。"),
    "万灵吐纳法": ("neutral", "paid_preparation", "万灵一息", "不同种族都从各自原法力账本结算，参战同族人数不提高返还额度。"),
    "铁骨化妖经": ("earth", "actual_incoming", "化骨承力", "真实受创后提供有限普通护持，不免费改变种族、血脉或炼体境界。"),
    "赤炉养元篇": ("wood_fire", "paid_preparation", "炉火养战", "确认时决定将本次炉火用于恢复还是下一击，战斗中不产生丹药或可出售材料。"),
    "月兽真形录": ("wind_yin_yang", "ordinary_complete", "月形取势", "按实际先后手择一作用，不读取现实月相来重掷效果，也不凭名称赠送变身。"),
    "万灵吞月典": ("neutral", "actual_outgoing", "吞月取余", "本人真实交锋后才允许回收自身费用，不向队友征收法力，不给多人各算一份退款。"),
    "天骨镇界经": ("earth", "actual_incoming", "天骨立界", "护持仅护本人普通交锋态势，不创造世界边界、禁止移动或改变地图权属。"),
    "万妖祖庭圣典": ("earth", "paid_preparation", "祖庭分护", "可将同一护持总额分给本人和一名原参战同伴，份额之和不超过本书额度，不随军队人数放大。"),
    "太古万兽真经": ("wind_thunder_yin_yang", "ordinary_complete", "兽性择用", "每次只选择一个回应，已有血脉机制仍按原规则运行，本书不叠加新的种族身份或免费血脉。"),
    "百兽锻皮术": ("water", "body_endured", "皮受一源", "回澜只针对选定的实际攻击者；其他攻击者不能共享其损耗记录来获得额外护持。"),
    "担岳真形篇": ("fire_earth", "body_endured", "负岳舍攻", "把本次攻伐预算全部换成一轮护持，下一次普通攻击不再保留被转换的增伤。"),
    "太古不灭妖躯": ("wood", "body_endured", "妖躯缓续", "已受创且存活时才能种下续芽，恢复不消除原持久伤势，重击仍可打断。"),
    "夜行炼魂录": ("wind_yin_yang", "observed_cast", "夜行审势", "只依据真实先后手选择攻守，不因名称自动获得夜间隐身、远程行动或地图穿行。"),
    "蒙学养气篇": ("neutral", "ordinary_complete", "一事一记", "初次成功观察仅建立记录，第二次同类可见动作后才结清本书一笔费用，不能靠重复查看面板积累。"),
    "礼乐正气诀": ("yin_yang", "paid_preparation", "礼乐守序", "先声明攻或息的起式，之后遵循交替，偏离预定则放弃本次机会而非获得处罚敌人的权限。"),
    "春秋微言章": ("yin", "observed_cast", "微言据实", "仅对本人见到两次的同一来源准备回应，不依据阵营、恶名或道途自动判定敌人犯错。"),
    "五经通义": ("five_elements", "observed_cast", "五义轮用", "五式按成功兑现推进，观察五种招式不等于同时获得五式，书名数量不增加额度。"),
    "正心诚意经": ("yang", "actual_incoming", "正心除蔽", "只驱散自身一项合法短效数值减益，不改变他人好感、意志归属或长期人格。"),
    "浩然正气歌": ("earth", "observed_cast", "正气自守", "依据已见实际敌方动作建立自护，不按魔修或鬼修身份无条件增伤，也不改变业力。"),
    "知行合一录": ("metal", "actual_outgoing", "知后须行", "先见招再以本人实际交锋验证，验证成功才保留隙印；只观察而未交锋不得领收益。"),
    "天人策论": ("wood_water_fire_earth", "observed_cast", "先策后验", "提前预定下一轮用途，若战况不同只能承受落空，不能事后重写预案以追认成功。"),
    "大学明德篇": ("wood", "paid_preparation", "明德自养", "只在本人当前仍存活且受损时恢复态势，不把道德评价换成免费生命或持久属性。"),
    "民本王道经": ("earth", "observed_cast", "分护同袍", "可将本次自护额度让给一名原参战同伴，本人相应扣除，不调用凡人信仰或地方人口作资源池。"),
    "乾嘉证义书": ("yin", "observed_cast", "两证一应", "需要同一来源两次实际成功结算的观察记录才回应；猜测、失败起手及隐藏配置不构成证据。"),
}

# Ten actual books per Guixu lineage, in their existing numbered IDs.
GUIXU = {
    "CANGHAI": [
        ("water_wood", "潮生回岸", "恢复先结算最早的一份受创记录；后来的较大损耗不能替换已经封存的恢复依据。"),
        ("metal_water", "沧溟试锋", "破持隙印只留给本人下一次对原目标的攻击；该次被挡也消费本次机会，不重抽目标。"),
        ("water", "九曲分流", "把一次回澜护持分为两份顺序承受，第二份只在第一份实际耗尽后启用，两份总额不增加。"),
        ("earth", "叠浪不叠额", "同一份护持可分两轮承受，但未用余额只递减不补满，不能每轮重新获得完整额度。"),
        ("earth_metal", "归潮试身", "普通护持被敌方真实耗尽后才准备反击，不以历史炼体等级或已付自损替代当前破持事实。"),
        ("yin", "照海辨源", "只记本人实际受其作用的一种来源，旁观他人受击的招式不自动成为本书回应对象。"),
        ("fire_earth", "镇流舍锋", "将本次额外伤害全额换为有限护持，护持只能应对选定敌人的普通交锋，其他敌人仍照原规则攻击。"),
        ("wind", "镜月反步", "只在本次从先手变成后手后准备步势，从后手变先手不触发本书。"),
        ("wood_fire", "水火不并取", "确认时选择恢复便放弃本次余火，选择余火便放弃本次恢复，局势变化不能撤销已兑现部分。"),
        ("earth", "观阵余护", "本人实际受原有合法阵势支持并完成一次交锋后才准备，护持不修复原阵法耐久。"),
    ],
    "WEIR": [
        ("neutral", "万流只还己", "只返还本书本人实付款，不把同伴费用、领域维持费和敌方损耗合并成退款本金。"),
        ("metal", "星潮留隙", "隙印须等原目标完成一次普通交锋后才可用于攻击，不能在同一命中事件自造印再自消费。"),
        ("wood", "鲸息待静", "准备后的等待轮若本人遭到超过阈值的单次敌方损耗，整枚续芽作废，不顺延至下一轮重试。"),
        ("water", "无岸有账", "同一受创记录只提供一次回澜，离开原目标后不把记录转交给新敌人。"),
        ("yin", "照界见实", "只记录原战场可感知来源，不将跨界人物、未参战守卫或界面预览纳入观察。"),
        ("wind", "折空改步", "仅影响下一次普通交锋身法，真正撤离仍走原判定；步势不能解除封逃。"),
        ("five_elements", "界轮不越界", "五式次序只记录本场战斗状态，实际换界会按原战斗结束规则清除，不把轮序作为通行资格。"),
        ("yin", "雾海遮旧", "准备新的监听来源时必须放弃旧来源，神识受阻时不能靠旧监听自动识别陌生敌人。"),
        ("fire_earth", "星槎稳枢", "只有原阵势当次实际维持成功后可把本书攻击预算转为护持，不赠送阵材或替代维持费。"),
        ("yin_yang", "虚实丹息", "本书攻息交替不生成丹药，恢复实际为零时不推进轮式；满态势不能空刷下一攻式。"),
    ],
    "BLOODRIVER": [
        ("water", "逆河同源", "回澜仅针对最近一次真实伤及本人的敌人，新的攻击来源替换旧来源时舍弃旧记录。"),
        ("yin", "九阴择一", "多名敌人使用相同目录招式仍按实际人物分别记录，一次只回应其中一人。"),
        ("earth", "白骨一潮", "护持附于原本人或一具合法参战尸傀，付费时二选一且不可中途转移余额。"),
        ("neutral", "噬魂不夺库", "只回收本书实付款，击杀敌方不增加退款上限，不产出额外魂魄或寿元。"),
        ("wood", "魔胎缓形", "续芽等待期间若原适用肉身失效，待恢复额消散，不自动转给第二肉身。"),
        ("yin", "血月照复", "只在本人已经真实承受过该来源损耗后建立监听，免疫和未命中不算受过。"),
        ("fire", "万煞一焰", "群体交锋只分配一份余焰预算给原合法目标集合，不为每名敌人各生成一份。"),
        ("wind", "逆脉有偿", "步势的自损和法力代价必须分别实际支付，不把自损计入任何本书受创奖励。"),
        ("wood_fire", "黑莲闭开", "恢复支只在本人已有实际损耗时可选；满态势不能选恢复后改领攻击补偿。"),
        ("water_wood", "吞潮分期", "第一期恢复因封禁失败后，第二期一并取消；不能跳过失败前段只领取后段。"),
    ],
    "DEMON_GRAVE": [
        ("fire", "黑日落后", "把全部额外伤害留到下一轮同一目标，当前交锋不提前增加伤害，目标离场时全部落空。"),
        ("wood", "古胎拒续", "同一轮内只能存在一枚本书续芽，重击打断后本轮不能立即重新种下。"),
        ("earth", "神骸有壳", "只保护原适用身体的普通态势，不给尸骸、神游和活体同时复制三份护持。"),
        ("water_wood", "万劫不返死", "恢复不先于终结判定，不以历史渡劫次数增加本场恢复上限。"),
        ("yin", "无相见招", "面对没有可识别来源的普通攻击时不虚构来源；只对实际有来源的重复动作建立回应。"),
        ("wood_fire_earth", "堕星取舍", "余焰待落时只能在原伤害与自身护持间选一，选护持则注销原目标的整个待伤害包。"),
        ("wind_thunder_yin_yang", "九渊一门", "每次只开一个回应分支；本场已经成功使用过的分支不能靠取消后立即重新选择来刷新冷却。"),
        ("wind_thunder", "血焰随步", "雷引只在本人先后手真实变化且原目标仍在场时出现，变更目标不视作先后手变化。"),
        ("yin", "葬神不逆死", "监听对象被合法终结后清除全部机会，不通过待响应规则取消原死亡回执。"),
        ("neutral", "混沌返己源", "只退本书普通法力，无法用混沌名义把四种气源、领域储量或材料折算成法力。"),
    ],
    "BEAST_VORTEX": [
        ("neutral", "万兽独账", "参战兽类数量不影响退款本金，本书始终按原人物自身付款逐笔回收。"),
        ("fire", "祖血不燃自损", "本书余焰须来自本人对敌方的真实交锋，自损、血脉代价和队友受伤都不点火。"),
        ("earth", "百骸同垒", "多段普通攻击连续扣同一护持余额，不为每个身体部位新增护持。"),
        ("wood_fire", "妖胎留一用", "选择恢复后必须等待原轮末，不能因敌人倒下把尚未发生的恢复改成攻击下一人。"),
        ("metal", "星落见隙", "隙印只在本人真实命中后建立，攻击资格被阻挡时不登记零伤害印记。"),
        ("water", "鳞承一流", "优先记录最大的一次已知普通损耗，但选定后锁定，不能临到使用再换成更大记录。"),
        ("wind_thunder", "雷羽后转", "只有本人由后手变先手才建立雷引，反向变化不产生雷引。"),
        ("yin", "青丘辨旧", "新观察覆盖旧观察，仅保留最近已知来源；不提供对陌生招式的通用减伤。"),
        ("wood", "蜕命留伤", "恢复态势后仍保留原持久伤势和寿命损耗，不以蜕命之名重置人生状态。"),
        ("five_elements", "万象有序", "切换原合法形态时不重置五式，旧轮式未成功兑现便不得跳到下一式。"),
    ],
    "YELLOW_SPRING": [
        ("water", "冥津逆受", "回澜只响应同一原敌人下一次普通攻击，不把其对同伴的攻击算作本人可用记录。"),
        ("water_wood", "忘川不忘账", "每份恢复关联具体损耗回执，分期完成后永久标记本场已取用，不能重新选入。"),
        ("earth", "九泉藏势", "护持只在第一记敌方普通攻击到来时开始消耗，不提供场外隐身或移动权限。"),
        ("yin", "十殿只证一", "从已见来源中选一个监听；多个来源的观察次数不能拼成同一来源的重复证据。"),
        ("fire", "罪业不定伤", "余焰按本人实际攻击预算计算，不把敌人恶名、业力或阵营直接变成倍率。"),
        ("wood", "鬼柏有根", "续芽只在当前原魂体仍合法存续时兑现，转世、魂灭或退出战斗立即清除。"),
        ("wind", "冥关不越禁", "身法改善不改变拘禁、追击路线或界壁，成功脱战仍需原结算。"),
        ("yin_yang", "六道双序", "同一场战斗只保留当前攻息轮式，不因六道名称创建六份收益或六次行动。"),
        ("metal", "幽关隙印", "隙印只能改善原合法普通攻击的破法，不能把普通兵器提升为灭魂或仙级资格。"),
        ("wood_water_fire_earth", "无岸先择", "预定恢复但目标已满态势时本次自然落空，不自动改成护持或伤害。"),
    ],
    "MONSTER_REALM": [
        ("neutral", "荒原自息", "只有本人完成有效普通交锋才可结清一笔费用，队伍其他人物的战斗不能代为完成。"),
        ("earth", "群山不乘人", "护持预算不随己方人数扩大，若让给同伴则从本人份额中实扣。"),
        ("earth_metal", "百骸鸣裂", "只有本人护持被敌方耗尽才开隙印，场景建筑或阵势受损不代替个人护持回执。"),
        ("yin", "烛野看一招", "只监听本轮本人实际观察到且成功结算的来源，战报外的隐藏来源不补记。"),
        ("water", "蜕鳞不刷壳", "原护持主动取消不产生受创依据，不能通过脱换装备反复生成回澜。"),
        ("wood", "同春一枝", "可让渡一次续芽给一名原合法同伴，但不能把一枝恢复复制给全队。"),
        ("wind", "伏草候后", "本轮后手且上一轮先手时才准备步势，长期先手时不产生伏草收益。"),
        ("wind_yin_yang", "乘飙审序", "攻守分支仅按实际先后手判断，身法面板高不等于已经取得先手。"),
        ("wood_water_fire_earth", "祖庭先藏", "先定下一轮用途再付款，收到伤害后不能把已定攻击改为恢复追认保护。"),
        ("five_elements", "山海不生兽", "五式只改变原人物交锋能力，不召唤不存在的兽群、分身或额外参战者。"),
    ],
    "CELESTIAL": [
        ("neutral", "云笈回原费", "返还只针对本书未结清费用，天庭俸禄、功德和功勋不作为战斗回气本金。"),
        ("yin_yang", "天衡次第", "攻息成功各一次后才允许调整下一轮起式，失败、免疫和零恢复均不计成功。"),
        ("earth", "金阙不增甲", "有限护持不复制法宝、不增加仙甲等级，原仙凡资格保持不变。"),
        ("yin", "玉宸明见", "观察到两次相同来源才形成回应，天庭官位不授予读取敌人隐藏配置的权限。"),
        ("wood", "星槎济一人", "恢复对象必须是本场原合法同伴，提前选定后不因更远处有人受伤而跨场景改投。"),
        ("water_wood", "清都缓生", "两期恢复都不得超过开战时态势上限，超出部分作废，不积存为战后治疗。"),
        ("yin", "烟霞弃旧", "每次改选监听来源必须清除旧来源回应，不能借敛迹保留多个隐形记录。"),
        ("wind", "蹑景不移界", "只调整下一次交锋身法，不能借步法穿越空间实例或绕过行动地点。"),
        ("wood_water_fire_earth", "河图先验", "依据上一轮已知动作作预定，不根据本轮尚未公开结算结果自动选最优支。"),
        ("five_elements", "无极有终", "整战额度耗尽后五式停止，不以完成一周为理由恢复费用、次数或额度。"),
    ],
    "ASURA": [
        ("fire", "烬海一因", "只用本人真实普通攻击作为余焰来源，军队人数、权位和派系支持不放大本书预算。"),
        ("earth", "铁狱不禁人", "镇疆体现为本人有限护持，不直接禁锢目标、不改变城址或地方控制权。"),
        ("earth_metal", "赤铜碎护", "护持真实破裂后隙印只针对破护者，其离场后不转给最弱的新目标。"),
        ("yin", "血月见招", "窥心只记录可见招式来源，不读取忠诚、谋反计划或其他隐藏人物状态。"),
        ("metal", "断劫不免判", "破法提高仍通过原作用资格，不能用无回名称跳过镇压、捕获和死亡区别。"),
        ("water", "百战当前账", "只读取本场最近一轮损耗，历史战斗次数不成为无限回澜库存。"),
        ("wind_yin_yang", "暗尘取一", "按当前交锋实际先后手决定攻守，不同时享有匿锋防护和进攻破法。"),
        ("wind_thunder", "掠火逐同敌", "变势雷引绑定触发时的原目标，追击别人需重新准备并重新付费。"),
        ("wood_fire_earth", "兵主弃焰护", "余焰转护持时彻底删除原待伤害包，不能在护持耗尽后再恢复该包。"),
        ("neutral", "无间有账", "断续战沿用原费用和退款累计，不因进入下一批敌人重置回收上限。"),
    ],
    "NETHER": [
        ("neutral", "苍溟留一笔", "同一时刻只登记最早一笔未返费用，新的支出排队而不覆盖旧金额。"),
        ("earth", "龙庭不授域", "护持只影响原普通交锋，不凭镇域书名生成领域或免费领域容量。"),
        ("water", "玄鳞归源", "受创依据必须来自同一原攻击者的真实普通损耗，邻域压力不冒充普通伤害。"),
        ("yin", "渊龙照明", "只在本人感知未被阻断时建立监听，黑暗或外观叙述不自动提供全场视野。"),
        ("wind_yin_yang", "游渊辨次", "同一轮只选实际先后手对应分支，重新计算面板不能重触发另一分支。"),
        ("wood", "蟠天缓养", "续芽恢复成功才消费恢复额度，失败仍消耗已付法力与本次施展次数。"),
        ("yin", "蜃影不造敌", "监听只绑定原真实敌人，幻影文本和召唤外观不生成第二个可刷来源。"),
        ("wind_thunder", "御霆实转", "必须两次真实普通交锋的先后手发生变化，没有普通交锋的轮次不伪造变化。"),
        ("water_wood", "九渊回原身", "恢复只归付费时的原人物，变更关系身份不产生新的恢复对象和额度。"),
        ("yang", "烛龙照短垢", "只能处理剩余一轮以内且已注册可驱散的普通减益，不能把时间神通解释为回滚战斗。"),
    ],
    "REINCARNATION": [
        ("neutral", "忘川清实费", "退款按本场实际已付普通法力结算，前世记录、死亡次数和轮回次数不进入本金。"),
        ("yin_yang", "冥衡不改业", "攻息轮式不修改人物业力或审判记录，成功切式只影响本场战斗。"),
        ("earth", "幽莲护原魄", "护持绑定当前原生命载体，不在魂体与肉身之间各生成一份。"),
        ("yin", "三生只见今", "监听仅使用本场已见来源，不凭前世或宿命名义读取未发生招式。"),
        ("wood", "彼岸渡存者", "只恢复原场内仍合法存续的人物，已经死亡或被制伏者不成为复活目标。"),
        ("water_wood", "幽烛余量", "两期恢复共用一份额度，第一期因上限溢出作废的部分不挪到第二期。"),
        ("wind_yin_yang", "残梦守实序", "只按真实先后手分支，幻觉、隐藏名称和战报修辞不改变先手事实。"),
        ("wind", "履影不越川", "身法不等于离开战场；封逃、拘禁及实际路线仍由原系统处理。"),
        ("metal", "宿世不预印", "开战不预置隙印，须本场真实交锋重新建立，历史击败过同一人不直接获得机会。"),
        ("five_elements", "无始亦有界", "本场五式与额度随原战斗结束清除，读档续战不视为新一生而刷新。"),
    ],
}

EXTRA_FOUR = {
    "TECH_REINCARNATION_BREATH": ("neutral", "轮生返本费", "本场所有退款只核对本次生命阶段的实际支出，不跨前世和旧肉身借款。"),
    "TECH_REINCARNATION_SWORD": ("metal_water", "渡厄看破持", "只在原目标临时护持实际耗尽后取得隙印，过往业缘和敌人阵营不替代破持事实。"),
    "TECH_REINCARNATION_BODY": ("wood", "莲华续存身", "必须原肉身仍合法存在且本人未被制伏才允许续芽兑现，不把不灭名称当复生权限。"),
    "TECH_REINCARNATION_SENSE": ("yin", "三生记今招", "本场首次遇到仍必须观察，前世关系、已知人物姓名不等于知道其本次招式。"),
}

# Region traditions describe different fighting habits, not a requirement to
# stand in that region. This avoids adding movement, instance or world rules.
HERITAGE_STYLES = {
    "HUMAN": ("青岚", "first_observed", "只对本场第一个实际交锋对象建立本书准备记录；该对象离场便清除，不改绑后来者。"),
    "DEMON": ("赤砂", "recent_loss", "准备前一轮须本人实际受过敌方损耗；代价性自损不满足此前置。"),
    "SPIRIT": ("清微", "changed_source", "须本人实际观察到敌方使用不同于其上一次的来源，才开启本次准备。"),
    "TRUE_DEMON": ("幽渊", "same_source", "须同一敌人连续两次使用相同的可见来源，才开启本次准备。"),
    "MONSTER_REALM": ("山海", "exchange_survival", "须本人完成一攻一受两种有实际损耗的普通交锋记录，顺序不限，每组记录只用一次。"),
    "PHANTOM_UNDERWORLD": ("幻月", "second_observed", "只对本场第二种本人实际观察到的招式来源建立准备，没有第二种就不预填。"),
    "HELL": ("冥关", "paid_enemy", "须本人见到原敌方招式实际成功付费，免费被动不提供准备机会。"),
    "CELESTIAL": ("太清", "after_guard", "本人一份原合法临时护持真实减免过损耗后才可准备，自然存在但未使用的护持不算。"),
    "ASURA": ("血曜", "after_breach", "本人实际攻击过拥有普通护持的目标后才可准备，须有真实交锋回执，不要求无条件击穿。"),
    "NETHER": ("忘川", "after_reversal", "须本人真实先后手发生一次变化才准备，没有普通交锋的轮次不增加变化次数。"),
    "REINCARNATION": ("三生", "after_expiry", "本场一次已付费的本书机会自然过期后才开启后续准备；首次准备仅作种子，不即时兑现收益。"),
}

HERITAGE_ROLES = [
    ("neutral", "main", "养息", "只退本书最早一笔未结清费用，已退本金不能再次入账。"),
    ("wood", "main", "归元", "续芽需要完整等待轮，等待中单次重击可摧毁它，不把过期改成延期。"),
    ("yin_yang", "main", "会通", "以息式起步，实际恢复非零才转攻式，满态势不能空转。"),
    ("wood_water_fire_earth", "main", "承统", "预先锁定下一轮用途，只改变当前一次运转，不赠送新的领域或身份。"),
    ("metal", "combat", "问锋", "隙印仅归原交锋目标，敌人离场不转给新目标，不增加攻击次数。"),
    ("earth_metal", "body", "铸躯", "护持真实耗尽才打开反击窗口，不把换装导致的消失当作破持。"),
    ("yin", "divine_sense", "观神", "只回应本人已知来源，感知受阻时不累积观察；先前已知不等于未来全知。"),
]

UPPER_PROFILES = {
    "ASURA": ("demonic", [("fire", "封焰"), ("wood_fire_earth", "舍攻"), ("thunder", "候杀"), ("metal_water", "断护")]),
    "NETHER": ("monster", [("water", "承鳞"), ("water_wood", "缓续"), ("earth_metal", "裂甲"), ("wind_thunder", "转霆")]),
    "REINCARNATION": ("ghost", [("yin", "记招"), ("yin_yang", "转式"), ("wood_water_fire_earth", "先定"), ("five_elements", "循序")]),
}

UPPER_ROLES = {
    "MAIN": ("main", "先运转后兑现，费用不得借原修炼收益抵销，战斗中不增加永久机缘。"),
    "COMBAT": ("combat", "须本人对原目标实际造成普通损耗后准备，派生损耗不递归触发。"),
    "BODY": ("body", "须原肉身资格有效；暂时护持和恢复不提升永久炼体层数，不取消持久伤势。"),
    "SENSE": ("divine_sense", "只依据本人可见的招式记录；神识禁制仍有效，不读取隐藏身份和配置。"),
}

RULE_LIFECYCLE = [
    "读取本人的真实事件，核验既有资格与本书准备条件；不满足则不产生机会。",
    "建立至多一个本书待用机会并锁定必要的来源/目标；特殊说明需要两笔或两次证据时只保存有界记录。",
    "依次满足道途代价、专属附加条件与时序前置，再选择合法兑现窗口；没有合法目标和用途不扣费。",
    "足额支付本书法力与其他明确代价；一次施展次数在真实付款时扣除，失败也不刷新次数。",
    "按本书时序派发一份有界效果包，分期、回响、护持与转换都消费同一份预算。",
    "真实付款即开始本书冷却；实际兑现后更新额度。取消、目标退出或到期清除剩余效果，只有明确允许的退款可退本人实付费用。",
]

EFFECT_CHANNELS = {
    "self_cost_rebate": ["guard", "mana_refund"],
    "bound_breach": ["breach"], "interruptible_restore": ["restore"],
    "receipt_shield": ["prevention"], "budgeted_afterburn": ["extra_damage"],
    "finite_shield": ["prevention"], "initiative_switch": ["mobility"],
    "charge_release": ["extra_damage"], "repeat_source_response": ["received_reduction"],
    "cleanse_temporary": ["cleanse"], "barrier_followup": ["breach"],
    "delayed_loss_recovery": ["restore"], "offense_restore_choice": ["extra_damage", "restore"],
    "damage_to_shield": ["prevention"], "broken_shield_breach": ["breach"],
    "initiative_charge": ["extra_damage"], "alternating_choice": ["extra_damage", "restore"],
    "repeat_initiative_breach": ["breach"], "initiative_cleanse": ["cleanse"],
    "initiative_choice": ["breach", "guard"], "repeat_paid_cast": ["breach"],
    "four_way_choice": ["breach", "guard", "mobility", "cleanse"],
    "breach_then_restore": ["restore"], "cancel_afterburn_for_shield": ["extra_damage", "prevention"],
    "shield_then_breach_or_restore": ["prevention", "breach", "restore"],
    "forecast_choice": ["extra_damage", "restore", "prevention"],
    "five_step_rotation": ["breach", "restore", "prevention", "extra_damage", "mobility"],
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def source_role(book):
    category = book.get("category", "spiritual")
    return category if category in {"body", "divine_sense", "transformation"} else book.get("growth_preference", "balanced")


def resolve_design(book, source_index):
    identity, title = book["id"], book["name"]
    role = source_role(book)
    if identity.startswith("TECH_OPEN_"):
        # Stem names are stable identifiers, not title-based semantic guesses.
        parts = identity.removeprefix("TECH_OPEN_").split("_")
        family = "_".join(parts[1:-1]).lower()
        role = parts[-1].lower()
        form = book["grade"] - 1
        return family, role, form, None, "open_catalog"
    if title in SPECIAL:
        family, trigger, label, clause = SPECIAL[title]
        form = (source_index + book["grade"] - 1) % len(FORMS)
        return family, role, form, dict(name=label, condition=clause, trigger_override=trigger,
                                       origin="named_book_authoring"), "named_fixed"
    if identity.startswith("TECH_GUIXU_"):
        tail = identity.removeprefix("TECH_GUIXU_")
        group, number = tail.rsplit("_", 1)
        family, label, clause = GUIXU[group][int(number) - 1]
        form = (int(number) + list(GUIXU).index(group) - 1) % len(FORMS)
        return family, role, form, dict(name=label, condition=clause,
                                       origin="guixu_named_book_authoring"), "guixu_fixed"
    if identity in EXTRA_FOUR:
        family, label, clause = EXTRA_FOUR[identity]
        form = list(EXTRA_FOUR).index(identity) + 3
        return family, role, form, dict(name=label, condition=clause,
                                       origin="reincarnation_named_book_authoring"), "reincarnation_fixed"
    if "_HERITAGE_" in identity:
        group, number = identity.removeprefix("TECH_").split("_HERITAGE_")
        theme, witness, context = HERITAGE_STYLES[group]
        family, role, label, clause = HERITAGE_ROLES[int(number) - 1]
        form = (int(number) + list(HERITAGE_STYLES).index(group) - 1) % len(FORMS)
        return family, role, form, dict(name=theme + label, condition=context + clause,
                                       witness=witness, origin="regional_lineage_authoring"), "heritage_fixed"
    for group, (_, profiles) in UPPER_PROFILES.items():
        prefix = f"TECH_{group}_"
        if identity.startswith(prefix):
            rank, part = identity.removeprefix(prefix).split("_")
            family, titlepart = profiles[int(rank) - 9]
            role, clause = UPPER_ROLES[part]
            form = (int(rank) - 9) * 3 + list(UPPER_ROLES).index(part)
            form %= len(FORMS)
            return family, role, form, dict(name=titlepart + ROLES[role][0], condition=clause,
                                           origin="upper_lineage_authoring"), "upper_fixed"
    raise ValueError(f"Unreviewed fixed book: {identity} / {title}")


def make_entry(book, source_index):
    family_key, role_key, form_index, special, kind = resolve_design(book, source_index)
    family = FAMILIES[family_key]
    role = ROLES[role_key]
    path = PATHS[book["path"]]
    form = FORMS[form_index]
    p, h = role[4:6]
    casts = 5 if family_key == "five_elements" else 3
    cooldown = 0 if casts == 5 else 2
    packet_scale = 0.6 if casts == 5 else 1.0
    p, h = round(p * packet_scale, 4), round(h * packet_scale, 4)
    # Broad tools pay more, never obtain simultaneous full benefits.
    cost = role[3] + (0.5 if family_key in {"five_elements", "wind_thunder_yin_yang"} else 0)
    effect = family[3].format(p=f"{p:g}", h=f"{h:g}", g=f"{p * .8:g}", r="5")
    trigger = special.get("trigger_override", role[1]) if special else role[1]
    trigger_text = next((r[2] for r in ROLES.values() if r[1] == trigger), role[2])
    needs = sorted(set(["book_dispatch", "paid_cost_receipt", "budget_ledger", *family[5]] +
                       (["legacy_specialty"] if special else []) +
                       (["budget_split", "finite_shield"] if form_index in {3, 8, 10, 11} else [])))
    active_channels = set(EFFECT_CHANNELS[family[2]])
    if form_index in {8, 11}:
        active_channels.add("prevention")
    if form_index == 9:
        active_channels.add("mana_refund")
    caps = dict(
        ordinary_modifier_fraction=p / 100,
        extra_damage_fraction_of_frozen_ordinary_baseline=p / 100,
        prevention_fraction_of_initial_max_state=h / 100,
        recovery_fraction_of_initial_max_state=h / 100,
        mana_refund_fraction_of_own_paid_cost=0.25,
        mana_refund_fraction_of_initial_capacity_per_cast=0.01,
        mana_refund_fraction_of_initial_capacity_per_battle=0.02,
        cleanse_count_per_cast=1,
        active_channels=sorted(active_channels),
    )
    name = (special["name"] if special else family[0]) + "·" + form[0]
    description = (
        f"{family[1]}。此为{path[0]}{role[0]}之法，修习重在“{special['name'] if special else family[0]}”。"
        f"临阵采用{form[0]}之势：{effect}"
        f"其短处是{family[4]}。"
    )
    # All numbers in the growth table are explicit. Strength stays flat; higher
    # study only lowers this book's actual payment by at most 16 percent.
    levels = [dict(level=lv, mp_cost_percent_of_initial_capacity=round(cost * (1 - .02 * (lv - 1)), 3),
                   ordinary_modifier_percent=p, prevention_or_recovery_percent=h,
                   casts_per_battle=casts, strength_multiplier=1.0)
              for lv in range(1, 10)]
    family_lifecycle = (
        "本书作用分支、标记、记录和轮式按原人物+本书+本场战斗隔离。"
        "单个叶效果最长两轮；准备含暂停最多四轮，付款后整条分期链最多四轮，从首次准备起总计最多八轮。各阶段若另有更短期限则从严，不能无限续期。"
        "分期、轮式和本书次数在原战斗续战中保留，目标变化按绑定规则处理。"
    )
    mechanic = dict(
        rule_name=name,
        preparation=dict(event=trigger, rule=trigger_text),
        path_covenant=dict(code=path[4], rule=path[2], drawback=path[3]),
        delivery=dict(code=form[1], rule=form[2], drawback=form[3]),
        payload=dict(code=family[2], rule=effect, channels=sorted(active_channels)),
        exclusive_clause=special,
        cost=dict(resource="原人物普通法力/原规则下对应法力账本", basis="开战时原实际最大容量，不含本稿新增专属效果",
                  level_1_percent=cost, level_9_percent=levels[-1]["mp_cost_percent_of_initial_capacity"],
                  state_sacrifice_percent=0.2 if book["path"] == "demonic" else 0.0,
                  failure="付款后中断不自动退款；只有本书明确退款分支可退，预览和无合法用途不扣款"),
        intrinsic_limits=dict(per_round=1, casts_per_battle=casts, cooldown_full_rounds=cooldown,
                              pending_packets=1, record_keys_max=2, opportunity_absolute_ttl_rounds=4,
                              effect_ttl_rounds=2, effect_chain_ttl_rounds=6 if casts == 5 else 4,
                              invocation_absolute_ttl_rounds=8, recursive_dispatch=False),
        caps=caps,
        budget_rule=f"一次付款建立1份本书预算；同次效果中各通道实际使用的比例之和≤1。拆分、转换、让渡和回响均从此扣除；整战至多{casts}份，不能各通道分别领满。" +
            ("五式每份额度已缩至普通同类的60%，五次总额不超过三份普通预算，费用不随之返还；仅开轮使用准备/时序，后续同一轮式链每轮最多付费推进一次、无额外两轮冷却，最长六轮且仍受整次八轮上限。各次仍检查原资格和绑定，并支付道途明确的资源代价。" if casts == 5 else ""),
        discrete_rule="驱散等不可分操作须使用完整1份预算；分包时前段只完成合法观察，视作时序前段完成但不是战果；末阶段执行一次，不发半次驱散。若时序附带自护，选择驱散即舍弃附带自护，将整份预算合回驱散；不得两者兼得。",
        lifetime=family_lifecycle + ("五式为例外：轮式链最多六轮，阶段不重新触发开轮前置，仍不得超过整次八轮期限。" if casts == 5 else ""),
    )
    signature_body = copy.deepcopy(mechanic)
    signature_body.pop("rule_name")
    if signature_body["exclusive_clause"]:
        signature_body["exclusive_clause"].pop("name")
        signature_body["exclusive_clause"].pop("origin")
    core = dict(trigger=trigger, covenant=path[4], delivery=form[1], payload=family[2],
                exclusive_condition=special["condition"] if special else None)
    source = copy.deepcopy(book)
    changes = dict(id="保留", name="保留", original_base_stats="原样附录，本稿不额外加战力/HP/MP/机缘",
                   original_growth="不在本次设计中重算原基础数值；新增机制不乘原功法等级倍率",
                   original_special_fields="原炼体、神识、变身、道统、领域与介入字段保留，新增机制不替代原权限",
                   runtime_status="未接入游戏；description是拟新增展示文本，不代表现行效果",
                   activation_selection="按用户要求留待后续，不指定槽位数和同时生效数量")
    examples = dict(
        success=f"本人满足“{trigger_text}”及本书附加前置，按{form[0]}方式实际付费并兑现；战报须记录目标、付款、使用额度和{family[0]}结果。",
        counterplay=f"针对窗口采取应对：{family[4]}；{form[3]}。",
        exploit_rejection="同一事件重复提交、读档续战、换目标、派生损耗和取消再开都不能刷新本书已付费用、次数或预算。",
    )
    return dict(
        index=source_index + 1, id=book["id"], name=book["name"], design_status="完整条目设计稿；未实装、未完成实战数值校准",
        path=book["path"], grade=book["grade"], original_category=book.get("category", "spiritual"),
        original_growth_preference=book.get("growth_preference", "balanced"), design_role=role_key,
        required_affinities=book.get("required_affinities", []), source_group=kind,
        description=description, battle_description=f"{name}。准备：{trigger_text}道途运转：{path[2]}时序：{form[2]}效果：{effect}" +
            (f"专属附加规则：{special['condition']}" if special else "") +
            f"Lv.1费用为初始法力容量的{cost:g}%，每战至多{casts}次；完整费用和额度见本条规则。",
        signature=sha(signature_body), nonnumeric_mechanic_signature=sha(core),
        uniqueness=dict(family=family_key, distinguishing_behavior=core,
                        statement="同系保留传承关系，但本条完整触发/时序/代价/转换组合独立登记；不是仅改名字或倍率。"),
        rule=mechanic, levels=levels, interactions=INVARIANTS,
        implementation_dependencies=[dict(id=k, description=DEPENDENCIES[k]) for k in needs],
        acceptance_examples=examples, preservation=changes, original_definition=source,
    )


def coverage_summary(entries):
    return dict(total=len(entries), by_source_group=dict(collections.Counter(e["source_group"] for e in entries)),
                by_role=dict(collections.Counter(e["design_role"] for e in entries)),
                by_path=dict(collections.Counter(e["path"] for e in entries)),
                by_grade={str(k): v for k, v in sorted(collections.Counter(e["grade"] for e in entries).items())})


def validate(document, original):
    entries = document["techniques"]
    errors = []
    def require(ok, message):
        if not ok:
            errors.append(message)
    require(len(entries) == len(original) == 4258, "目录必须一一覆盖4258部")
    require([x["id"] for x in entries] == [x["id"] for x in original], "原ID、顺序与覆盖必须一致")
    require(len({e["id"] for e in entries}) == 4258, "ID重复")
    signature_groups = collections.defaultdict(list)
    nonnumeric_groups = collections.defaultdict(list)
    for entry, source in zip(entries, original):
        key = entry["id"]
        require(entry["original_definition"] == source, f"{key}: 原定义不完整")
        require(entry["name"] == source["name"], f"{key}: 原名变化")
        require(len(entry["description"]) >= 65 and len(entry["battle_description"]) >= 100, f"{key}: 描述缺失")
        for bad in ["TODO", "TBD", "待填写", "待设计", "同上", "略同", "示例占位", "�"]:
            require(bad not in canonical(entry), f"{key}: 占位/编码异常 {bad}")
        require(entry["rule"]["payload"]["channels"], f"{key}: 无战斗用途")
        require(entry["rule"]["intrinsic_limits"]["recursive_dispatch"] is False, f"{key}: 允许递归")
        require(entry["rule"]["caps"]["ordinary_modifier_fraction"] <= .10, f"{key}: 单次修正越界")
        require(entry["rule"]["caps"]["recovery_fraction_of_initial_max_state"] <= .015, f"{key}: 恢复越界")
        require(entry["rule"]["caps"]["prevention_fraction_of_initial_max_state"] <= .015, f"{key}: 护持越界")
        casts = entry["rule"]["intrinsic_limits"]["casts_per_battle"]
        require(casts * entry["rule"]["caps"]["recovery_fraction_of_initial_max_state"] <= .04500001, f"{key}: 整战恢复越界")
        require(casts * entry["rule"]["caps"]["extra_damage_fraction_of_frozen_ordinary_baseline"] <= .30000001, f"{key}: 整战额外伤害越界")
        if entry["rule"]["payload"]["code"] == "five_step_rotation":
            require(casts >= 5, f"{key}: 五式无法完整轮转")
            require(entry["rule"]["intrinsic_limits"]["cooldown_full_rounds"] == 0, f"{key}: 五式被重复冷却截断")
        if entry["rule"]["payload"]["code"] == "self_cost_rebate":
            require("guard" in entry["rule"]["payload"]["channels"], f"{key}: 只付费退款没有实际战斗收益")
        require(len(entry["levels"]) == 9, f"{key}: 等级不完整")
        require(all(l["strength_multiplier"] == 1 for l in entry["levels"]), f"{key}: 新机制乘等级膨胀")
        require(entry["levels"][-1]["mp_cost_percent_of_initial_capacity"] >= 1.68, f"{key}: 费用过低")
        require(entry["levels"][-1]["mp_cost_percent_of_initial_capacity"] < entry["levels"][0]["mp_cost_percent_of_initial_capacity"], f"{key}: 等级成长无效")
        signature_groups[entry["signature"]].append(key)
        nonnumeric_groups[entry["nonnumeric_mechanic_signature"]].append(key)
    duplicates = [v for v in signature_groups.values() if len(v) > 1]
    nond = [v for v in nonnumeric_groups.values() if len(v) > 1]
    require(not duplicates, f"完整机制重复: {duplicates[:5]}")
    require(not nond, f"排除数值、书名、ID后仍重复: {nond[:5]}")
    # Conservative independent per-book ceilings; no runtime simulation claim.
    bounds = dict(max_single_cast_extra_damage_fraction=.10,
                  max_three_cast_extra_damage_fraction_of_one_frozen_baseline=.30,
                  max_single_cast_recovery_fraction=.015,
                  max_battle_recovery_fraction=.045,
                  max_battle_mana_refund_fraction=.02,
                  minimum_level_9_cost_percent=1.68,
                  level_9_strength_multiplier=1.0,
                  shared_branch_budget=1.0)
    return dict(status="passed" if not errors else "failed", coverage=coverage_summary(entries),
                duplicate_rule_groups=duplicates, duplicate_nonnumeric_behavior_groups=nond,
                unique_descriptions=len({e["description"] for e in entries}),
                numeric_envelopes=bounds, errors=errors,
                drafting_corrections=["吐纳类加入实际防护作用，避免只付费再退少量费用的无效循环",
                                      "五式允许五次、每次额度缩至60%，开轮后逐轮实付推进，不被两轮冷却和重复准备截断",
                                      "分包驱散只在最终窗口执行一次，前段观察不伪造非零战果",
                                      "区分准备期限、叶效果期限与整条效果链期限，避免分期被统一短期限截断",
                                      "无方向性准备可绑定已见在场敌人，避免主修追源式永远没有目标"],
                checks=["原ID/名称/顺序/字段一一保留", "4258条均有描述与战斗作用", "9级逐级费用",
                        "每条机制自身额度、次数与不可递归约束", "排除ID、名称和数值后的行为组合去重",
                        "不存在占位词、乱码与遗漏固定功法"],
                not_proven=["4258条全部组合的总体平衡", "全部条件在实际战斗驱动器中的可达性",
                            "每部在同境实际对手分布中的使用价值", "语义相近但文字不同的附加条款是否仍应进一步合并或深化"],
                runtime_tests="未运行新增机制的游戏战斗测试：本交付是设计数据，不是游戏补丁。")


def markdown_entry(entry):
    r = entry["rule"]
    original = entry["original_definition"]
    roots = "、".join(entry["required_affinities"]) or original.get("element", "neutral")
    lines = [f"## {entry['index']:04d} · {entry['name']}", "",
             f"- ID：`{entry['id']}`；原品阶：{entry['grade']}；道途：{PATHS[entry['path']][0]}；设计用途：{ROLES[entry['design_role']][0]}；原属性要求：{roots}。",
             f"- **描述文本：**{entry['description']}",
             f"- **专属规则：{r['rule_name']}。**{r['preparation']['rule']}",
             f"- **运转与代价：**{r['path_covenant']['rule']}",
             f"- **兑现时序：**{r['delivery']['rule']}",
             f"- **实际作用：**{r['payload']['rule']}"]
    if r["exclusive_clause"]:
        lines.append(f"- **本书独有附加条款：**{r['exclusive_clause']['condition']}")
    levels = "／".join(f"{lv['mp_cost_percent_of_initial_capacity']:g}%" for lv in entry["levels"])
    lines += [f"- **Lv.1—9法力费用：**{levels}，均按开战时原最大容量计；新增效果强度不再乘等级倍率。",
              f"- **单书边界：**每战至多{r['intrinsic_limits']['casts_per_battle']}次、每轮至多1次、施展后冷却{r['intrinsic_limits']['cooldown_full_rounds']}个完整轮；至多1份待用包；准备最长4轮、付款后效果链最长{r['intrinsic_limits']['effect_chain_ttl_rounds']}轮、整次过程最长8轮，具体阶段可更短。",
              f"- **数值上限：**普通交锋修正或额外伤害至多{r['caps']['ordinary_modifier_fraction']*100:g}%；恢复/有限护持至多初始最大态势的{r['caps']['recovery_fraction_of_initial_max_state']*100:g}%；仅对本条列明的实际通道生效。",
              f"- **预算：**{r['budget_rule']}{r['discrete_rule']}",
              f"- **弱点：**{entry['acceptance_examples']['counterplay']}",
              f"- **验证场景：**{entry['acceptance_examples']['success']}",
              f"- **接口状态：**" + "；".join(f"`{d['id']}`" for d in entry["implementation_dependencies"]) + "。定义见总说明；不能将设计文案直接当作现有战斗脚本。",
              ""]
    return "\n".join(lines)


README = """# 4258部功法逐条设计稿

日期：2026-11-12。状态：设计交付，未修改游戏运行目录、存档和版本，未接入战斗。

后续实施：2026-11-13已按用户要求将此冻结设计编译为固定目录V3效果，实际结算、太元归墟剑升级特例与验收入口见[固定功法实战接入](../fixed-technique-combat.md)。本目录保留原设计稿，不把后续运行元数据反写成最初设计。

## 交付范围

固定目录 `content/techniques.json` 的全部4258部，保持原顺序、ID、书名和原定义。3888部通用功法及370部其他固定功法均逐条展开，不是只交一个模板或生成器。运行时自创功法、动态道统书目及此固定目录之外的扩展条目不伪计入4258。

- [完整JSON](techniques.json)：每条含原定义、描述、完整机制、代价、成长、边界、依赖与验证场景。
- [完整Markdown](techniques.md)：4258条逐条可读说明，可按ID或书名查找。
- [分册索引](volumes.md)：每册最多250部，便于桌面预览；与完整目录逐条一致。
- [校验报告](validation.json)：覆盖、字段保留、去重与数值边界检查。

## 按用户要求暂不决定的部分

不确定生效槽位数、同时生效数量、跨书叠加方式、自动选招优先级及全角色主动行动配额。文中的次数、冷却、费用和额度只约束单部功法自身。

因此本稿只给出单书有界设计，不能声称4258部同时生效仍然平衡。跨书组合与整体战斗节奏必须在生效规则明确后另行校准。主修/辅修/杀伐等在本稿表示设计长项，不新增使用槽位限制；修炼、炼体、神识和变身功法同样有战斗用途。

## 专属规则的设计方式

每部拥有完整展开的准备事件、运转代价、兑现时序和效果转换；固定名篇还有逐书附加条款。可以共享引擎能力和传承语汇，但不以书名、ID或倍率差异通过唯一性检查。

通用功法以27种属性运转、4种道途代价、12种不同兑现时序及3种准备方式组合成3888条独立登记规则。12阶采用不同等待/分包/改绑/取舍，不单纯递增倍率。这是明示的组合式内容创作，不声称4258套底层机制互不相关。370部其他固定功法另有具名、归墟、地区传承和上界传承专属条款。

排除数值、ID和规则名后的去重验证的是行为配置不同，并不能代替人工游玩对“是否好玩、是否足够不同”的判断。特别是固定条款中的相似约束需要在内容审阅中继续比较。

## 规则执行顺序

准备事件 → 本书专属前置 → 道途运转 → 真实付款 → 兑现时序 → 效果窗口 → 归属与额度结算。若不同条款并存，采用共同满足条件和最早期限；不能以一条描述绕过另一条。没有合法用途时不付款，付款后的风险与失效照本书执行。

触发可在费用提交前记录，但不提前产生收益。道修的先登记后确认、妖修的先承载后兑现、魔修的实际自损、鬼修的原敌绑定均为设计中的新行为，不能假定当前已经可执行。

## 数值口径

1. 原有机缘、HP、MP、战力和原等级曲线完整保留在JSON附录，本稿没有批量增加基础数值。
2. 新机制以开战时的原法力容量、最大战斗态势与排除本稿新专属效果的普通交锋基线为基准；新效果不得互相放大基准。
3. 单次普通修正/追加伤害最高10%；单次恢复/有限护持最高初始最大态势的1.5%。各书按自身长项有更低值。
4. 每次付费只建立1份效果预算。攻守转换、分包、回响、让渡共用这一份；不同通道不分别领满。通常每书每战至多3份；五式轮转功法允许5次，但每次额度缩至60%，整战总额不增加，且需要更多实际付款。五式只在开轮时经历准备，之后每轮实付推进至多一次，不重复附加两轮冷却。
5. 法力返还只能退本人本书实际付费的一部分，整战最多原初容量2%；任何退款不能恢复已消耗施展次数与额度。
6. Lv.1—9只逐级减少本书费用，最大减少16%；新增机制强度不乘旧功法最高等级倍率、不乘品阶或多灵根溢价。
7. 回响、余焰、自损、退款、护持与恢复不递归提供本书的新触发。单书态势恢复总上限4.5%，不能形成自激永动。
8. 清除一项减益是不可分的离散操作，占完整预算；分期时仅末阶段执行一次，不能拆成多次驱散。若时序原本附带自护，选择驱散须舍弃自护并合回预算。
9. “恢复态势”不是HP治疗、肉身修复、复活、解控或高阶储量补充。攻击资格、世界、人物、地点和原有所有权规则不变。

## 现有架构与待补能力

现有战斗语义支持轮次、条件、状态、计数、目标绑定与部分修正通道；普通NPC法力、有限护持余额、驱散注册、付款回执和新功法调度仍需本体接口。JSON每条列出依赖，不能直接导入当前游戏目录。

原功法已有的炼体、神识、变身、道统、领域、特殊介入和修炼作用保持。标题包含“不灭”“裂界”“轮回”等词不构成新增复活、传送、越界或灭魂权限。

NPC使用同一书目和单书规则，但不在此稿给NPC免费补功法、器物或资源。生成、学习与配置由后续统一接入设计处理。

当前玩家普通交战默认5轮、最多8轮，碾压快捷战斗可仅1轮；后台NPC也存在短轮次路径。本文不修改这些规则。延迟、分期和五式不保证每场都完整兑现，1轮快捷战斗不会得到长期收益。后续实装必须验证默认5轮的首个收益可达性，且不能为了让新功法触发而自动延长已经结束的战斗。五式逐轮付费推进的修正专门避免“允许五次却被冷却截断到永远只能三次”的设计错误。

## 文件与检验

设计生成/展开脚本：`tools/design_techniques_4258.py`。执行 `python tools/design_techniques_4258.py --write` 生成文件；不带参数执行逐字一致性与内容校验。脚本不被游戏导入，不读取或写入玩家存档。

校验属于设计数据审计，不是新增机制的实战回归。未声称已证明所有条件可达、所有组合平衡或4258部均有足够出场价值。
"""


def render_files():
    raw = SOURCE.read_bytes()
    original = json.loads(raw)["techniques"]
    source = dict(path="content/techniques.json", sha256=hashlib.sha256(raw).hexdigest(), entries=len(original))
    if any((row.get('combat_effect') or {}).get('version')==3 for row in original):
        frozen=json.loads((OUT/'techniques.json').read_text(encoding='utf-8'))
        prior=[row['original_definition'] for row in frozen['techniques']]
        strip=lambda row:{k:v for k,v in row.items() if k not in {'combat_effect','description'}}
        if [strip(row) for row in original]!=[strip(row) for row in prior]:
            raise ValueError('固定目录基础定义已变化，须审阅设计，不能用已编译效果反向生成设计')
        original=prior;source=frozen['source']
    entries = [make_entry(book, index) for index, book in enumerate(original)]
    document = dict(
        schema="cultivation-life-technique-design", schema_version=1, design_version="0.1.0",
        status="design_only_not_game_content", date="2026-11-12", language="zh-CN",
        source=source,
        scope="固定目录4258部，全部逐条展开；不含运行时动态生成的书目；生效数量限制留后续",
        units=dict(percent="百分比数值，例如2表示2%；fraction字段为比例，例如0.02表示2%",
                   state="战斗态势，不等于HP或肉身完整度", baseline="排除本稿新增专属机制后的原战斗基线"),
        invariants=INVARIANTS, lifecycle=RULE_LIFECYCLE, dependency_catalog=DEPENDENCIES,
        coverage=coverage_summary(entries), techniques=entries,
    )
    report = validate(document, original)
    if report["errors"]:
        raise ValueError(json.dumps(report["errors"][:20], ensure_ascii=False))
    header = "# 全部4258部功法：描述与专属规则\n\n设计稿，不是已实装效果。完整口径与接口边界见[总说明](README.md)，机器可读版本见[JSON](techniques.json)。\n\n原目录顺序；每条均含完整描述、触发、代价、作用和成长。生效槽位及跨书限制留待后续。\n\n"
    rendered = [markdown_entry(e) for e in entries]
    md = header + "\n".join(rendered)
    # Full entries on individual lines keep the 4258-entry JSON below the
    # needless whitespace overhead of deeply indented repeated records.
    metadata = {k: v for k, v in document.items() if k != "techniques"}
    json_text = json.dumps(metadata, ensure_ascii=False, indent=2).rstrip()[:-1].rstrip()
    json_text += ',\n  "techniques": [\n' + ',\n'.join("    " + canonical(e) for e in entries) + '\n  ]\n}\n'
    assert json.loads(json_text) == document
    texts = {"README.md": README, "techniques.md": md, "techniques.json": json_text}
    index = ["# 功法设计分册索引", "", "全部4258部；[总说明](README.md) · [完整Markdown](techniques.md) · [JSON](techniques.json)", "",
             "| 分册 | 原目录序号 | 首部—末部 |", "| --- | --- | --- |"]
    for start in range(0, len(entries), 250):
        stop = min(start + 250, len(entries))
        name = f"volumes/{start + 1:04d}-{stop:04d}.md"
        prefix = f"# 功法设计 · {start + 1:04d}—{stop:04d}\n\n[总说明](../README.md) · [分册索引](../volumes.md)\n\n本册是完整设计目录的原样分段，不是额外功法。\n\n"
        texts[name] = prefix + "\n".join(rendered[start:stop])
        index.append(f"| [第{start // 250 + 1}册]({name}) | {start + 1}—{stop} | {entries[start]['name']}—{entries[stop-1]['name']} |")
    texts["volumes.md"] = "\n".join(index) + "\n"
    report["artifact_sha256"] = {name: hashlib.sha256(value.encode("utf-8")).hexdigest() for name, value in texts.items()}
    texts["validation.json"] = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    return texts, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    texts, report = render_files()
    if args.write:
        OUT.mkdir(parents=True, exist_ok=True)
        for name, text in texts.items():
            (OUT / name).parent.mkdir(parents=True, exist_ok=True)
            (OUT / name).write_bytes(text.encode("utf-8"))
    else:
        for name, text in texts.items():
            if not (OUT / name).is_file() or (OUT / name).read_bytes() != text.encode("utf-8"):
                raise SystemExit(f"Design artifact differs: {OUT / name}")
    print(json.dumps(dict(status=report["status"], coverage=report["coverage"],
                          unique_descriptions=report["unique_descriptions"], output=str(OUT)), ensure_ascii=True))


if __name__ == "__main__":
    main()
