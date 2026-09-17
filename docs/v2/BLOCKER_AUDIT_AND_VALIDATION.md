# V1/V2 阻断项根因审计与校验基线

## 结论

原有的 44 个阻断项不是 44 个独立回归错误，而是功能矩阵中所有尚未达到 `pass` 的必需功能。第二批迁移完成后阻断数降为 36；第三批第一阶段降为 33，第三批第二阶段继续降为 32。迄今转为完整通过的功能包括：

- `presentation.settings_debug`：Schema 4 持久化界面设置；异界消息继续模拟但默认不投影，Debug 模式才显示全部世界。
- `relations.faction_invitation`：只有当前世界中存活的师父、道侣或道友可被引荐入宗；弟子、侍妾和无关系人物不能借此加入。
- `factions.rewards`：元婴及以上成员可固定年度奖励；每年结算贡献与收益，永久属性在退宗后仍保留。
- `cultivation.body`：炼体训练、圆满、分段概率、失败保留、保底和每层固有气血成长进入独立组件。
- `cultivation.divine_sense`：神识训练与手动升级进入独立组件，突破仅扣当前等级所需经验。
- `cultivation.transformations`：真灵素材直接/提纯/批量炼化、六维圆满度、容量和战斗空间编队闭环完成。
- `cultivation.realm_breakthrough`：概率突破、保底、传统三关、天劫五关和五轮天魔劫均进入可保存读取的统一试炼状态机。
- `world.realm_crossing`：下界飞升、邀请过滤、下界封印/返回、仙界与修罗界九重飞升全部复用六领域清理事务；事件内部发起的跨界由最后一个领域回执提交。
- `economy.spirit_plant_sale`：采收灵植成为带年份、品质和价值的实例资产，出售精确消费该实例并原子结算灵石。
- `economy.spirit_field`：瞬时开垦、播种、统一时钟生长、MP灌溉、造化灵液、采收与五艺经验形成闭环。
- `crafting.alchemy`：堆叠药材和实例灵植共用材料校验与消费路径，MP、随机结果、产物和经验原子提交。
- `economy.auction`：预告、开场、竞价、结拍和黑市阶段进入可保存状态机；竞价与寄拍复用统一托管账本，跨界取消立即退款，匿名身份、交涉和私下买卖均已接入。

另修复两个不属于独立矩阵行、但会污染平价校验的缺陷：V2 新角色缺少初始灵剑；妖修开局没有装配 DLC 指定的 `TECH_MONSTER_BREATHING`，导致修炼行动零收益。

`inventory.item_use`从`missing`推进为`partial`：治疗、突破辅助、劫中恢复、补灵根、永久本源和主动灵植效果已接入；孕育丹仍依赖尚未迁移的家族生命周期，不能提前宣告完成。`economy.black_market`也推进为`partial`：检索、购买、离开以及堆叠物/实例资产出售已完成，但傀儡出售仍等待魔道傀儡与魂魄聚合迁移。

当前矩阵为 53 项：21 项 `pass`、13 项 `partial`、19 项 `missing`。101 个冻结的 V1 公共操作仍被完整且唯一归档，矩阵结构无错误。V2 仍不可正式切换。

## 32 项的共同根因

| 根因组 | 数量 | 阻断项 |
|---|---:|---|
| 共享运行时缺口 | 4 | `core.action_loop`、`story.interactive_events`、`verification.shadow_coverage`、`interface.http_frontend` |
| 实例资产与经济模型 | 5 | `inventory.item_use`、`economy.black_market`、`crafting.artifacts`、`formation.nine_palace`、`artifact.natal` |
| 关系与治理事务 | 10 | `relations.lifecycle`、`relations.dao_companion`、`relations.dao_friend`、`relations.master_disciple`、`relations.concubines`、`relations.capture`、`factions.succession`、`factions.family`、`factions.npc_operations`、`factions.diplomacy` |
| 战斗、战争与魔道聚合 | 6 | `party.management`、`combat.automatic_resolution`、`war.aggregate`、`demonic.prison`、`demonic.captives`、`demonic.puppets_souls` |
| DLC 深层状态机 | 7 | `ghost.reincarnation`、`ghost.soul_ecology`、`ghost.attachment_possession`、`monster.evolution_lineage`、`celestial.court`、`intrigue.personnel`、`intrigue.guests_decisions` |

这些分组揭示了实际瓶颈：不能按页面逐个复制按钮。若先迁移拍卖、炼器或 DLC 页面，却没有通用交互事件、实例资产、托管账本和长期事务，跨系统清理问题会再次出现。

## 校验结果与边界

本轮建立 `tools/audit_v1_v2.py`，同时执行以下检查：

1. 从 V1 HTTP 分派源码重新提取公共操作，与冻结清单逐项比较；当前为 101/101，无新增、遗漏或重复。
2. AST 扫描 V2 包，禁止导入 V1 `engine`、`models`、`storage`；当前违规数为 0。
3. 校验矩阵覆盖、证据文件及具体测试节点。`pass` 不再能仅引用一个存在但无关的测试文件。
4. 使用道修、魔修、妖修、鬼修，多种种子分别执行 `rest` 与 `cultivate` 影子场景。每个命令从全新同源角色开始，避免 V1 待处理事件把下一命令误报为执行失败。
5. 完整运行仓库回归测试；它验证 V1 自身稳定、V2 已迁移切片稳定以及导入/存档迁移安全，但不能替代尚未实现操作的平价测试。

统一剧情运行时接入后，10组影子场景已有9组完全一致，原先所有`pending_event`差异均已消除。仅鬼修`cultivate`仍有一项机缘数值告警，原因是V1创建鬼修时的附加世界初始化会额外消费共享随机流；该差异必须在鬼修专属状态机迁移时消除，不能通过忽略字段掩盖。

当前V2共加载363个基础及DLC剧情定义。效果注册表已迁移20种效果，经过后续事件链闭包检查后有165个事件可安全进入随机池；试炼效果现已接入，其他未迁移的战斗、关系制裁或DLC专属效果仍明确隔离。因此`story.interactive_events`仍为`partial`，尚不能标记为`pass`。

## 后续修复顺序

1. 通用交互队列、条件求值器和类型化效果注册表已经落地；领域专属效果随对应系统迁移注册。
2. 扩展统一行动适配器到V1剩余行动种类，并完成战斗/试炼效果，使`advance`与`choice`达到完整语义覆盖。
3. 实例资产仓库、统一预留/托管账本、物品首批效果、灵田、炼丹和拍卖已经落地；黑市除傀儡外已复用同一账本，下一阶段继续迁移炼器、阵法、本命法宝与魔道傀儡。
4. 永久/临时跨界及全部高阶突破、飞升试炼已经落地；后续跨界玩法必须复用同一回执事务，不得直接清理其他领域状态。
5. 在同一关系与治理模型上完成关系交互、家族、宗门经营、外交和继承，不再保存 NPC 副本。
6. 扩展战斗快照到队伍、地形、阵法和战争；随后迁移魔道聚合。
7. 最后迁移 DLC 深层状态机、正式 HTTP/前端，并把影子适配器扩展到全部 101 个操作。

每一项只能在命令、权威状态、跨领域事件、失败原子性、不变量、存档迁移和具体测试节点全部存在后改为 `pass`。在 32 项真正清零前，Step 10 继续保持禁止状态。
