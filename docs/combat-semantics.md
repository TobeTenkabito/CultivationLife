# 战斗语义 V3：条件、状态与邻域／普通交锋

本层只提供可执行的语义，不提供具体 buff、随机词条、修罗之躯培养表或 DLC 内容。
血脉 V1 与巧夺天工 V2 继续走原来的 `combat_rule_engine`；V3 通过
`CapabilitySource.semantic_rules` 或战斗状态的 `semantic_rules` 明确注入。
没有规则的旧角色不创建新的语义运行时，不改变现有随机序列。

## 入口与职责

- `cultivation_life/combat_semantics.py`：有限词汇表、严格解析、条件判断、预览／提交、状态快照。
- `system/combat/semantics.py`：将真实参战人物和战斗结果转换为语义事实，应用结算结果。
- `system/combat/voisinages.py`、`effects.py`：接入魔域／仙域等邻域的费用、对抗、施权和普通伤害。
- `combat_system.py`、`combat/npc_battle.py`、`combat/trials.py`：玩家战斗、后台 NPC、分批劫战共用接口。
- `semantic_catalog()`：返回 JSON 可序列化的完整词汇表，包含每项事实的类型、合法读取阶段、
  修正通道与动作种类。后续内容编辑器可以直接使用该目录，不必另维护一份白名单。

规则字段为 `schema_version=3`、`id`、`source_id`、`trigger`、`actions`；可选
`name`、`when`、`scope`、`schedule`、`limits`、`reset_on_target_change`。
这里只描述语言，不收录具体玩法规则。

## 触发时点全集

| 时点 | 发生位置 | 对象与用途 |
| --- | --- | --- |
| `round_start` | 整个战斗轮开始 | 包括纯邻域回合；处理轮初状态和调整 |
| `field_prepare` | 一项邻域尝试支付展开／维持费之前 | 自身；可预览费用减免，失败不提交 |
| `field_established` | 邻域真正建立、资源扣除后 | 自身；可读取是否续持、实际费用 |
| `contest_prepare` | 一次方向性的侵夺／庇护比较前 | 侵夺者对受护目标；保护者对侵夺者 |
| `contest_resolved` | 本轮所有方向性对抗已经完成后 | 攻方和被攻击者分别收到结果 |
| `pressure_resolved` | 连续支配的态势／战意侵蚀完成后 | 区分侵夺者与受侵蚀者，不冒充肉身伤害 |
| `effect_prepare` | 选择施权能力、检查是否付得起费用时 | 施术者；仅预览，不扣计数、不消耗状态 |
| `effect_before_apply` | 目标合法、特殊介入完成且施权已付费后 | 施术者与承受者；修改实际施权强度 |
| `effect_resolved` | 对一个目标施权／处决完成后 | 可读取实际损耗、恢复和伤害来源 |
| `intervention_resolved` | 抵抗、庇护、扰乱或逃离实际成功后 | 介入者和被阻止的施术者 |
| `ordinary_start` | 确定仍能参与普通交锋的人物之后、算先手之前 | 各有资格的参战者；六维修正 |
| `initiative_resolved` | 普通交锋先后手已确定之后 | 可修正尚未结算的威能／防护／破法，或记录状态；不重算先手 |
| `ordinary_before_damage` | 有合法攻击来源并通过作用层级检查之后 | 实际攻击者／承受者；伤害和损耗上限 |
| `ordinary_after_damage` | 普通交锋双方同时扣除实际损耗后 | 按来源和目标归属，不能用理论伤害冒充受创 |
| `round_end` | 本轮全部普通／邻域结算完成后 | 轮末调整、保存上轮事实、状态到期 |

时点有严格因果关系。例如 `round_start` 不能读取本轮 `event.actual_loss`。
邻域回合没有普通交锋时，不制造先手、普通攻击或受创事件，但仍推进轮初／轮末与持续时间。

`contest_prepare` 中的 `target`：攻击者看到真正被攻击的人物；防守者看到侵夺者。
`contest_resolved` 的 defender 是实际被攻击者，借助同伴庇护也可以抵挡侵夺。
普通交锋的六维修正按人物战力占本方的比例投影到现有团队六维；不创建法宝实例或额外行动。
NPC 简化交锋使用对应的六维修正，但继续保持其简化伤害曲线。

## 条件可以读取什么

以下人物字段都支持 `self.`、`target.`、`previous.self.`、`previous.target.` 前缀。
`target` 仅能在真实存在方向性对象的时点读取；上一轮记录缺失时保持“未知”。

| 类别 | 字段全集 |
| --- | --- |
| 身份与阵营 | `id`、`side`、`rank`、`power` |
| 生存与战意 | `state`、`body`、`morale`、`fighting`、`suppressed`、`escaped` |
| 资源 | `energy`、`capacity`、`energy_ratio`、`mp_ratio` |
| 邻域状态 | `has_field`、`active_field`、`field_id`、`field_sealed`、`stance`、`sustained_rounds` |
| 对抗后果 | `dominated`、`escape_locked`、`pressure`、`strain`、`seal_progress` |
| 攻防资格 | `force_tier`、`ward_tier`、`resource_tier`、`technique_tier`、`artifact_tier` |
| 禁制 | `restricted_artifact`、`restricted_technique`、`restricted_supply`、`restricted_support`、`restricted_communication`、`restricted_voisinage`、`restricted_ordinary` |
| 存续人数 | `ally_count`（不含自己）、`enemy_count` |
| 普通交锋累计 | `ordinary_dealt`、`ordinary_received` |
| 邻域施权累计 | `field_dealt`、`field_received` |
| 连续支配累计 | `pressure_dealt`、`pressure_received` |

说明：`state` 是战斗态势比例，`body` 是肉身完整度，二者不可互换；`energy` 是独立高阶储量，
`mp_ratio` 是驱动器提供的本方法力比例，当前并非每个 NPC 各自独立的法力账本。
玩家普通交锋的 `morale` 同样读取驱动器的实际本方战意；纯邻域／后台 NPC 使用人物的战意状态。
`capacity` 使用实际可调用容量。损耗累计按受害者自身最大态势的比例相加，跨多个目标可能大于 1。
上轮累计是上轮的独立值，不在战斗过程中永久累加。`rank=-1` 表示未知境界；
双方境界均已知才提供 `rank_delta`。

其他事实：

- 通用：`round`、`role`、`rank_delta`。
- 战场：`environment.terrain`、`environment.forbidden_flight`、
  `environment.forbidden_sense`、`environment.formation`。驱动器没有提供时保持未知，
  不替 NPC 简化战斗或劫战编造地形。
- 先后手：`event.first`。没有普通交锋就没有此事实。
- 展域：`event.continued`、`event.cost`。
- 对抗：`event.relation`（`contested`／`pressed`／`dominated`）、`event.incursion`、`event.stability`。
- 施权：`event.effect`、`event.restriction`、`event.terminal`、`event.cost`。
- 损耗：`event.damage_source`（`ordinary`／`field`／`pressure`）、`event.amount`、
  `event.actual_loss`、`event.body_loss`；施权另有 `event.restored`。
- 介入：`event.intervention`（`resist`／`shelter`／`disrupt`／`escape`）。

所有事件事实的具体合法时点以 `FACTS`／`semantic_catalog()` 为准。
`event.amount` 是该事件进入结算的输入值，不代替实际损耗。被护体资格阻挡的普通攻击
不触发“实际受创”；多名攻击者造成的实际损失按贡献分摊，不给每个人重复记一遍总伤害。

## 条件表达式

- `all`、`any`、`not`：有限嵌套的且、或、非。
- 事实比较：`fact` ＋ `op` ＋ `value`。
- 局部计数比较：`counter` ＋ `op` ＋ `value`。
- 局部状态层数比较：`status` ＋ `op` ＋ `value`。
- 比较符：`eq`、`ne`、`lt`、`le`、`gt`、`ge`、`in`、`not_in`。
- `exists`：仅检查事实是否存在，不需要 `value`。

不接受 Python、字符串公式、回调、任意属性路径。数字、布尔和字符串严格区分；
布尔值不能冒充数字。未知事实不会当成 0，`not 未知` 仍然未知，只有明确为真的条件才能触发。
嵌套至多 8 层，条件节点至多 64 个，成员列表至多 32 项。

`schedule` 提供正整数 `start`／`end`／`every`，可表达首轮、奇偶轮、每 N 轮、
从第 N 轮开始、限定轮段。不提供未知战斗长度下的“最后一轮”，也不在解释器内临时掷随机数。
`limits` 提供 `per_round`（默认 1）、`per_battle`、`cooldown`；冷却 N 表示跳过接下来的 N 轮。
次数与冷却按人物＋来源＋规则记录，不会因目标变多而绕过。

## 可执行动作与效果全集

| 动作 | 含义 |
| --- | --- |
| `modify` | 对当前正在结算的合法通道输出临时修正 |
| `counter_add` | 增加计数，受 `max` 限制 |
| `counter_set` | 设置计数；设为 0 即重置 |
| `counter_consume` | 消耗计数；不足时整条规则不能触发 |
| `status` | 添加具有期限、层数和可选修正效果的状态；无修正效果即纯印记 |
| `consume_status` | 消耗指定状态层数；不足时不触发 |
| `clear_status` | 清除本来源指定状态 |
| `adjust` | 仅在轮初／轮末调整自身已存在的战斗资源 |

即时修正通道：

- 普通六维：`ordinary.might`、`guard`、`mobility`、`sense`、`sustain`、`breach`，均带 `ordinary.` 前缀。
- 普通损耗：`ordinary.dealt`、`ordinary.received`、`ordinary.received_cap`。
- 展域费用：`field.opening_cost`、`field.upkeep_cost`、`field.extra_target_cost`。
- 方向对抗：`field.incursion`、`field.stability`。
- 施权费用与权能：`field.effect_cost`、`field.authority`。
- 具体施权：`field.strike`、`field.suppress`、`field.seal`、
  `field.restore_body`、`field.restore_spirit`、`field.restore_field`。
- 承受施权损耗：`field.received`、`field.received_cap`，只作用于非终结性的杀伤／镇压损耗。

相对修正 `value` 在 -0.75 至 1 之间，同一评估中叠加后倍率限制在 0.25 至 2；
带 `_cap` 的通道是 0 至 1 的损耗比例上限，多个取最小值。
普通损耗上限对一名受害者在一次普通交锋中的所有攻击贡献共同生效。
各阶段、攻方／受方或不同六维仍各自有真实作用，不将这些上限宣称为整场总增伤上限。

瞬时 `adjust` 支持 `state`、`body`、`morale`、`pressure`、`strain`、`seal_progress`；
数值按现有真实范围钳制，不能复活死亡或已被制伏的人物。
不提供凭空恢复高阶储量、解除剧情封印、跳过护体层级或制造额外攻击的动作。
二值禁制与隔离没有“强度修正”通道，不能写一个乘数假装已经改变其持续或判定规则。

## 状态生命期与目标隔离

`status` 支持 `key`、`duration`、`delay`、`stacks`、`max_stacks`、`modifiers`、
`consume_on`、`recipient`、`bind_target`、`stacking`。

- `duration=1, delay=0`：到本轮末失效；`delay=1`：下轮才生效。
- `stacking=refresh`：重新计算期限；`extend`：延长期限；`keep`：保持原期限。
- `consume_on`：仅在对应阶段的效果真正用到时消耗一层。没有合法目标、付不起费用、
  被特殊介入取消，都不能提前消耗。多个通道共用一层状态，只消费一次。
- `recipient=self/target`：可以将状态施加给自己或真实事件对象；不将一个敌人的减益广播给整方。
- `bind_target=true`：只对绑定对象生效；不匹配时保留到期，不能作用于其他对象。
- `scope=self`：计数和状态按人物＋来源隔离；`scope=target`：再按真实目标隔离。
- `reset_on_target_change=true`：目标作用域的实际事件更换对象时清掉同来源旧进度；
  即便该事件没有满足奖励条件，也会完成目标切换。预览失败的动作不会执行切换。

默认不递归派发事件：同一事件中的规则统一读取事件前的计数／状态；
新获得的状态可以影响之后的阶段，不追溯修改已经结算的对抗。
显式的状态消耗和自动消耗应由内容作者选择适合的方式，避免对同一状态重复安排消费。

每人最多 128 条规则，每条最多 16 个动作；计数／状态最高 99 层。
战斗计数和状态记录各最多 512 项，状态期限上限有界；事件追踪只保留当前轮末尾 128 条。
这些是运行边界，不是具体 DLC 的培养上限。

## 续战、兼容与检验

`dump_battle`／`load_battle` 保存计数、状态起止轮、绑定目标、次数、冷却、上轮事实、
战场事实及规则来源。分批劫战从下一真实轮继续，不重新发开局奖励。
旧快照缺少该块时维持原行为；畸形、未知或无限数值的语义快照拒绝载入。

战前能力、普通法力、高阶储量、人物培养记录仍各自使用既有账本；语义运行时只保存本场状态。
未新增 NPC 年度遍历。战报附带规则来源、触发时点、人物和目标，以及当前计数／状态。

验证入口：`tests/test_combat_semantics.py`。覆盖词汇表、因果校验、未知值、作用域、期限与消费、
资源不足／介入取消、方向性对抗、普通战斗接入、真实伤害归属、纯邻域回合和 JSON 续战一致性。
测试中的规则仅为合成夹具，不作为玩家可获取的 buff。
