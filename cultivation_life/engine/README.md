# 引擎架构与行为兼容说明

第二轮重构将 25 个方法容器中的 251 个实现改为普通模块函数，通过显式依赖调用其他能力。算法不再通过 `FunctionType` 重绑定全局命名空间或动态安装到入口类；`transactions.serialized_commands` 仍为公开操作统一包装存档锁。此前各组 Mixin 迁移保持游戏规则、结算顺序、随机数调用顺序和存档格式；当前存档结构为 8，支持纯数据的 6→7→8 迁移，结构 1–5 停止支持；当前架构边界见 [项目诊断](../../docs/project-diagnosis.md)。

外部入口保持不变：

```python
from cultivation_life.engine import GameEngine, encode_rng
```

`GameEngine` 保留原方法签名、默认值及静态方法/类方法性质。入口类中的转发方法静态声明，算法在对应职责模块中实现；保留这些转发方法是为了让现有调用方及子类继续使用原接口。当前已将修罗养成、天庭、瑶池、神机、内政、经济／交换会、炼器、阵法、归墟、战争、地图／传送、商盟、道统／仙界养成及关系处置移出继承列表。鬼道、魔道、侍妾和佛门的关键流程也已迁出，其余直接基类的相对顺序保持不变。

`actions/asura.py` 接收 `AsuraActionDependencies`，修罗试炼接收 `AsuraTrialDependencies`；两者均不接收整个引擎。旧 `system/asura_system.py` 保留薄适配器供既有调用方使用，引擎不再继承它。

第二阶段将天庭与瑶池的 34 个方法迁入 `system/court/`，直接基类从 22 个减为 20 个。其中 29 个方法使用状态、政务、任期和瑶池四组显式依赖，5 个静态辅助函数无需依赖。`system/court/wiring.py` 连接具名能力，由引擎统一装配；旧四个 Mixin 类仅用于兼容原调用方，不再出现在引擎继承链中。

第三阶段将神机与内政的 74 个方法改为引擎显式转发，直接基类从 20 个减为 18 个。63 个既有算法保持原实现，内政议事权限方法迁入 `system/intrigue/governance.py`，另外 10 个静态辅助实现改为原模块中的普通函数。`composition/systems.py` 连接神机六组、内政七组依赖及原配置钩子，`EngineDependencies` 持有完整契约；两组旧 Mixin 仅兼容独立消费者。引擎保留 `_tianji_dependencies`、`_intrigue_dependencies` 属性供既有代码读取组合后的契约。

第四阶段将经济／交换会、炼器与阵法的 120 个方法改为引擎显式转发，直接基类从 18 个减为 15 个，同时移除间接继承的 `ExchangeSystemMixin`。经济已有的 47 个算法继续复用，补齐跨界拍卖取消与黑市搜索；7 个交换会算法进入 `system/economy/exchange.py`。炼器按市场、选材、预览、炼制、器物交易和展示六组连接依赖，阵法按市场、预设与启阵、镇地阵、NPC 和展示五组连接依赖。原 28 个静态辅助实现保留在原模块，由旧类及引擎分别转发。

本阶段没有合并或延后保存，也没有调整预览、扣料、随机数、退款、撤阵或失败回滚的执行顺序。神机市场与购入回调仍可缺省，通过具名 getter 在调用时读取；兼容消费者缺少这些回调时保持原行为。旧四个 Mixin 保留独立消费者接口，引擎改用 `EngineDependencies` 中的四组系统契约。

## NPC 与关系记录（第 8 项）

师父、弟子、待决拜师帖、道侣、道友和非俘虏来源的侍妾，以 NPC ID 关联人物状态。`relationship_records.RelationshipRecord` 提供具名字段的字典式读写接口；人物事实不存放在关系字典底层，而是在每次访问时按 ID 查找权威 `SectNpc`。NPC 死亡、改名、转宗、跨界或境界变化立即反映到关系视图；通过关系操作修改好感、主修或寿元也直接写入同一人物，后续同步不会再覆盖这些修改。

| 数据 | 归属 |
| --- | --- |
| 姓名、生死、年龄、寿元、境界、道途、世界、宗门、好感、主修、天劫及超脱状态 | NPC 对象；已有家族、世界、留名或宗门人物沿用原对象与年度安排 |
| 没有既有 NPC 的事件生成人物 | `GameState.relationship_npcs`，保留关系系统的年度推进；不会自动进入自由 NPC 的年度、随机遭遇或社交生成流程 |
| 人物 ID、关系来源、加入时间、互动／索取冷却、赠与和传授记录、关系加成 | 关系记录 |
| 境界、道途、种族、性别等显示名称 | 按当前人物事实生成的展示投影，不写入关系存档 |
| 队伍成员 | 仅人物 ID；成员有效性以权威人物的生死和世界为准 |

新增关系使用 `game.link_relationship(seed)`，然后放入 `player.master`、`dao_companion` 或相应列表；不要将临时展示字典长期作为人物状态使用。已有 NPC 始终优先于传入快照，只有不存在权威人物时才根据种子建立事件人物。身份 ID 不允许通过关系字段重绑。`dict(record)`、`record.copy()` 与 `copy.deepcopy(record)` 生成临时展示副本；`record.reference()` 返回持久化形态。游戏整体深拷贝重新关联克隆内部的人物，不调用读档解码、不写回原游戏。

`_sync_relationship_records` 现在只负责关联及关系默认字段，不再逐项复制 NPC 状态。事件人物在多个关系槽位出现时每年只推进一次；明确进入宗门或自由名册时，将同一个 NPC 从关系人物表转入 `notable_npcs`，避免重复年度结算。家族解散后查找优先使用已经转入新宗门的实际成员，旧家族残留名册不能覆盖现任人物。跨界移动也避免对关系视图和底层 NPC 重复执行同一移动。

关系引用阶段的存档结构为 **7**，`relationship_schema.migrate_relationships_v6` 提供 **6→7** 的纯文档迁移：以已有 NPC 为准剥离关系快照，保留关系字段，为孤立的完整旧关系建立人物记录，并将队伍旧别名换成 NPC ID。迁移不抽随机数、不执行养成，也不直接写文件；完整迁移和模型校验成功后才原子提交。缺失目标且没有人物种子的引用明确拒绝，不凭空复活人物。结构 1–5 的拒绝政策不变。

后续已完成俘虏状态拆分：`alive` 只表示实际生存，`custody` 表示受控身份，`roster_state` 表示自由活动、受控或离册。被俘人物以原 ID 转入 `inactive_npcs`，俘虏与俘虏来源侍妾关联同一人物；活傀资源记录保留专用培养字段并记录 `source_npc_id`。释放不复活，实际处决、炼尸、夺舍等结束原人物生命。当前结构为 8，登记 7→8 纯迁移，转换表、旧档边界及验证见 [人物拘禁契约](../../docs/npc-custody.md)。拘魂、机构监禁和后代家庭成长的专用流程仍保留；后代受控期间不能自动重新入族或重复年度推进。

验证位于 `tests/test_relationship_records.py`，覆盖即时双向更新、死亡与跨界后的队伍清理、转宗后同 ID 解析、无重复年度推进、复制隔离、纯迁移、存档回读和特殊俘虏边界。

## 统一时间推进（第 9 项）

普通行动与地图旅行共用 `time_flow.py` 的年度收尾和行动单位结算。`orchestration/world_time.py` 继续提供唯一的公共年度系统调度；`advancement.py` 与 `map_runtime.py` 只保留活动本身的年收益、路线、结果和提交位置，不再分别实现行动单位系统的结算顺序。

推进分为明确的阶段：

1. 活动增加年龄并执行当年操作。普通行动通过 `ActionUnitLedger` 保持每个单位只扣一次资源、只触发一次主动战斗；这里可能在公共年度处理前死亡。
2. `advance_elapsed_year` 调用 `_advance_world_year`，再对仍存活的玩家结算当年魂蚀。年度因事件中断不取消这一年的魂蚀；年度死亡则跳过魂蚀，魂蚀死亡也阻止下一年。该函数不再次增加年龄。
3. 活动处理完成／中断结果、机构工作、到达地点与行动历史。原有位置影响事件及随机数，暂时保留各自流程。
4. `settle_elapsed_time` 统一执行本命法器、行动单位系统、依附消耗、悬赏、行动事件、纪要与拍卖时钟。单位系统固定顺序为：外交 → 侍妾后续 → 天庭 → 内政 → 可选的神机情报。
5. 活动在原有位置刷新市场、压缩历史、保存 RNG 与存档。共用时间流程不加载、不保存，不创建新的随机数生成器。

公共年度顺序仍为：时间事件 → 佛门 → 商盟 → 儒道 → 鬼道 → 妖族血脉 → 突破／天劫／寿元 → 宗门与世界 NPC → 魔道 → 灵田 → 再次突破 → 归墟日历 → 可选遭遇。中断检查仍在原来的阶段边界，例如魔道反噬后先结算灵田，再检查死亡。

`TimeSettlementPolicy` 的两个冻结配置明确保留已有差异，不能为了统一代码而直接统一数值或行为：

| 规则 | 普通行动 `ACTION_TIME` | 旅行 `TRAVEL_TIME` |
| --- | --- | --- |
| 单位年数 | 行动开始时的境界 | 旅行结束时的境界；机构计时仍用出发时的单位 |
| 本命法器 | 单位系统之前 | 单位系统之后 |
| 神机情报 | 每单位处理 | 不额外触发 |
| 依附消耗提示 | 追加纪要文本 | 保留原来的静默结算 |
| 行动事件 | 悬赏之后、纪要之前，保持优先级且不覆盖待处理事件 | 不额外触发普通行动事件 |
| 拍卖与交换会 | 每单位各推进一次 | 整次旅行各推进一次 |
| 年度或到达时死亡 | 不进入行动单位结算 | 已耗时间继续结算，死亡后不推进拍卖时钟 |

进入单位结算之后，单位回调产生事件或死亡不会新增提前退出；普通行动也保留此时继续结算时钟的原行为。零年旅行不产生单位结算，不足一个单位按一个单位处理。以上差异影响随机数、奖励、死亡后状态和跨境界成本，目前没有足以证明玩法等价的规则替代方案，因此保留。

商盟工作、佛门法会、鬼道等待和魔道闭关继续接入同一个 `_advance_world_year`，但保留各自的进度提交、魂蚀和中断规则；不会自动给它们追加普通行动的拍卖、情报或外交结算。归墟被困修炼、即时传送及其他专属时钟也不强行换算成普通行动单位。

新增普通行动或旅行类玩法应复用 `advance_elapsed_year`、`completed_action_units` 和 `settle_elapsed_time`，通过明确依赖与配置接入；新增年度系统只在 `_advance_world_year` 登记，新单位系统只在共用结算处登记，并验证两种配置的顺序与中断。新增专属计时规则需要先说明其单位和结算边界，不通过复制循环接入。共用模块不能反向导入引擎、地图或具体玩法。

`tests/test_time_flow.py` 覆盖阶段顺序、事件优先级、死亡、部分单位、零年数、途中突破后的单位基准、晚绑定回调和单次保存。`tools/replay_time_flow.py` 固定时间、UUID 和哈希种子，比较三个种子的 78 个完整结果与存档检查点：

```powershell
python tools/replay_time_flow.py --output build/time-flow-before.json
# 修改前捕获基线，修改后执行：
python tools/replay_time_flow.py --output build/time-flow-after.json --compare build/time-flow-before.json
```

## 依赖如何连接

Step 2 提取五个系统的关键流程，共 44 个原方法（含两个人物辅助方法）。`RelationshipViolenceMixin` 删除，直接基类从 10 个减为 9 个；鬼道、魔道、侍妾与佛门保留局部规则、培养操作和查询，不以清空 Mixin 为目标。迁出的入口均由 `GameEngine` 显式转发，原四个 Mixin 不再承载这些方法。

| 依赖组 | 装配位置 | 关键流程 |
| --- | --- | --- |
| `ghost_flows` | `composition/ghost_flows.py` | `system/ghost/identity.py` 战陨夺舍、拘魂等待／反抗、离舍；`calendar.py` 年度夜行与魂仆易主；`erosion.py` 侵蚀与判死；`reincarnation.py` 轮回准备和提交 |
| `demonic_flows` | `composition/demonic_flows.py` | `system/demonic/refinement.py` 耗时闭关；`annual.py` 活傀失控、外魂反噬和死亡衔接 |
| `relationships` | `composition/relationships.py` | `system/relationships/captivity.py` 生擒、释放、夺舍与傀儡转换；`concubines.py` 纳入／遣散／转炼尸；`dependents.py` 依附转移、年度解除、提议、追索与脱身；`sanctions.py` 关系制裁；`violence.py` 战斗／处决与关系清理 |
| `buddhist_flows` | `composition/buddhist_flows.py` | `system/buddhist/actions.py` 操作入口；`assembly.py` 法会推进、事件恢复、战斗评分和奖励；涅槃仅接受突破完成与历史记录两个回调 |

四组聚合契约下共有 14 个叶级契约，均为冻结数据类。流程接受明确的存档、事件、时间、战斗和死亡能力，不接收整个引擎；调用时仍解析最新资源与方法。耗时活动通过 `_advance_world_year` 进入公共年度流程，保留各玩法已有的进度提交和中断位置：例如闭关在年度结算返回中断后不增加炼魂进度，法会先记该年耗时，存活时再结算魂蚀。

`system/relationship_rules.py` 承担稳定性别和境界比较，其他玩法不再为了这两个工具依赖侍妾 Mixin。鬼道 11 个成长／侵蚀规则函数及佛门 8 个账本／修正规则函数分别位于 `ghost/progression.py` 与 `buddhist/rules.py`，原模块继续导出同一函数对象。佛门修正器仍在原入口注册一次，不在流程模块重复注册。

本次不统一或改变 NPC 的既有 `alive` 标记含义：俘虏退出自由 NPC 名册、夺舍销毁原魂、转傀儡和释放的写入顺序均保留。关系清理范围、随机数消费、扣费、保存与事件恢复也保持原行为。将这些状态进一步统一为新模型属于另一项改动，需要单独设计存档及结算规则。

`tests/test_key_flow_dependencies.py` 验证独立调用、死亡／中断顺序、身份名册清理、失败分支、单次提交、法会恢复、资源替换和禁止反向引用。五系统回放覆盖三个种子的 90 个完整结果／存档检查点：

```powershell
python tools/replay_key_flows.py --output build/key-flows-before.json
python tools/replay_key_flows.py --output build/key-flows-after.json --compare build/key-flows-before.json
```

上一阶段地图／时间、商盟、道统／仙界养成将直接基类从 13 个减为 10 个，连同间接基类共移除 10 个 Mixin。原 61 个方法成为普通函数，新增 `_finish_travel_time` 承接从旅行中抽出的行动单位结算。原有引擎方法签名不变；这三组的旧 Mixin 类不再保留，调用入口是 `GameEngine` 或带明确依赖参数的模块函数。

| 依赖组 | 装配位置 | 实现边界 |
| --- | --- | --- |
| `EngineDependencies.time` | `composition/travel.py` | 年度阶段、旅行后结算、路线旅行、即时传送四组契约 |
| `EngineDependencies.merchant` | `composition/merchant.py` | 状态、目录、年度推进、交付退款、玩家工作、跨界、操作、展示、委托报价、NPC 执行十组契约 |
| `EngineDependencies.cultivation` | `composition/cultivation.py` | 道统学习／操作／展示、融合、修持读取、提交、仙道操作／展示、仙体、仙窍十组契约 |

年度公共调度位于 `orchestration/world_time.py`，不再由地图 Mixin 提供。商盟工作、鬼道等待、魔道闭关、佛门法会等现有调用方仍经 `_advance_world_year` 进入同一流程。旅行到达、市场更新、历史记录与旅行后结算的先后顺序保持不变，所有阶段共享原来的 RNG 对象；死亡与待处理事件的中断位置也保留，包括魔道年度处理后的灵田结算位置。

`system/cultivation_session.py` 分开提供修持读取与提交。仙体、金光和融合使用只含保存／呈现能力的 `CultivationCommitDependencies`，不再回调一个继承它们的修持父类。道统先保存学习目标再调用 `advance` 的现有顺序保持不变。本轮不合并保存、不改数值、不升存档结构版本。

新增依赖应进入对应叶级契约，并在装配模块逐项连接；不要向算法传递整个引擎或加入任意属性代理。`tests/test_three_group_dependencies.py` 检查脱离引擎执行、阶段中断、订单结算、独立修持提交、资源替换和反向导入边界。

三组固定种子回放比较完整返回值与存档（含 RNG 和历史），应在修改前捕获基线，再在修改后对比：

```powershell
python tools/replay_three_groups.py --output build/three-groups-before.json
python tools/replay_three_groups.py --output build/three-groups-after.json --compare build/three-groups-before.json
```

```text
GameEngine ── wiring.py ── composition/ ── dependencies.py ── ports.py
    │                                        │
    └── 普通模块函数(deps, ...) ────────────────┘
             │
             └── 显式导入模型、配置与规则函数
```

- `dependencies.py` 为每个职责模块声明冻结的数据类，所有协作能力都有名称，构造时必须提供。算法只能访问其契约列出的能力，不接收整个引擎对象。
- `cultivation_life/ports.py` 定义共用的存档、地图和成就资源接口；`engine/ports.py` 保留兼容导出，其他系统无需为了接口导入引擎。
- `wiring.py` 是装配入口，按职责调用 `composition/` 中的具名构建函数。这两个位置是知道 `GameEngine` 的装配边界；每个构建函数逐项连接回调与资源，不使用兜底属性代理，也不把任意属性查找暴露给算法。
- 没有实例依赖的静态辅助函数直接运行；NPC 类方法使用单独的 `NpcClassDependencies`，保留子类对寿元计算的覆盖能力。
- 回调在调用时查找引擎方法，资源通过显式 getter 获取。构造引擎后替换方法、存档服务或其他资源，仍按原行为生效；不能随意改为缓存绑定方法或资源快照。

原入口的 `bloodline_content_available` 兼容钩子通过命名回调注入，保留调用时替换该钩子的行为。算法不反向导入入口模块。其他内部规则符号改为从定义它们的模块导入；`GameEngine` 与现有调用方使用的 `encode_rng` 继续从入口导出。第一轮使用的内部 `Engine*Mixin` 方法容器已删除。

## 目录职责

| 位置 | 职责 |
| --- | --- |
| `__init__.py` | 引擎入口、资源初始化与显式转发方法 |
| `dependencies.py` | 各职责模块所需的命名依赖契约 |
| `ports.py` | 共用资源接口的兼容导出，定义位于 `cultivation_life/ports.py` |
| `wiring.py` | 选择各职责的依赖构建函数，组装完整引擎依赖 |
| `composition/` | 生命周期、动作、事件、战斗、世界、展示、修罗、人物交往以及神机、内政、经济／交换会、炼器、阵法的显式依赖构建 |
| `engine_constants.py` | 引擎共享常量 |
| `orchestration/session.py` | 创建游戏 |
| `orchestration/advancement.py` | 行动推进、年度收益、行动单位结算与记录 |
| `actions/cultivation.py` | 秘术管理及玩家主动突破 |
| `actions/asura.py` | 修罗养成操作、资源消耗、历史记录与保存 |
| `progression/asura_trials.py` | 通过明确契约执行修罗转化、融合与破境试炼 |
| `actions/world_travel.py` | 永久飞升、跨界、随行人员与下界身份清理 |
| `actions/factions.py` | 势力创建、外交、人员调动、退出与继承 |
| `actions/encounters.py` | 监禁、悬赏、拦截与主动战斗 |
| `actions/inventory.py` | 物品、购买、功法与变身材料 |
| `actions/relationships.py` | 师徒、道侣、好友与队伍操作 |
| `events/choices.py` | 事件选择与后续事件排队 |
| `events/encounters.py` | 遭遇目标、缓存与世界剧情触发 |
| `events/effects.py` | 事件效果结算 |
| `progression/breakthroughs.py` | 突破与进阶规则 |
| `progression/trials.py` | 渡劫及相关试炼 |
| `world/npcs.py` | NPC 生成、境界、寿元与更新 |
| `world/relationships.py` | 关系记录与队伍状态维护 |
| `world/factions.py` | 势力及种族关系维护 |
| `world/hostility.py` | 敌意、通缉与追捕 |
| `presentation/character.py` | 角色展示数据 |
| `presentation/world.py` | 世界、种族与关系展示数据 |
| `presentation/factions.py` | 势力展示数据 |
| `engine_world_runtime.py` | 世界年度更新协作 |
| `engine_event_runtime.py` | 事件选择与执行协作 |
| `engine_combat_runtime.py` | 战斗、击杀后果与死亡处理 |
| `engine_presentation.py` | 对外状态汇总 |
| `engine_persistence.py` | 读取、按顺序调用会话准备阶段、统一提交 |
| `persistence/` | 内容基础、魂基结算、角色、世界、服务和事件六组准备算法及窄依赖契约 |
| `../save_schema.py` | 与游戏运行时隔离的结构版本政策及逐级迁移 |

## 读档与版本迁移

结构版本由 `save_schema.SAVE_SCHEMA_VERSION` 定义，当前为 8，支持结构 6→7→8 的关系与拘禁状态迁移，与本体发行版本、内容版本及 DLC 版本独立。结构 1–5 不提供迁移路径；读取与存档码导入均明确拒绝，原文件保持不动，不会把旧版本号直接改为新版本。存档列表仅列出有完整支持路径的文件。

处理分为三个边界：

1. `SaveStore.load` 在锁内读 JSON，先执行结构版本检查及已登记迁移，再构造 `GameState`。当前结构直接解码，不写文件、不调用会话准备；存档编号必须与请求的文件名一致。
2. `engine_persistence._load` 按固定顺序运行六组准备阶段。它仍是有副作用的会话入口，可能补全 DLC 状态、消耗市场随机数或执行魂基判死，不能作为纯查询接口。
3. 准备阶段不持有存档服务；有变化时由协调器统一保存一次。HTTP 请求仍缓存本次准备好的对象，请求结束即释放。

| 阶段 | 职责与副作用 |
| --- | --- |
| `foundations.py` | 当前内容中的机构、地点、修罗与商人基础状态；上境突破标记及固定人物关系一致性 |
| `vitality.py` | 夺舍时间线、鬼修魂基与成长水位；低于魂基生存界限时调用死亡结算 |
| `character.py` | 界面与地域、功法、血脉、寿元和修炼标记；不再换算旧结构的累计神识经验 |
| `world.py` | 宗门与 NPC、境界限制、阵法、DLC 子系统、阵营、战争、队伍与关系同步 |
| `services.py` | 本命法宝、天庭与市场；在原位置提交消费后的 RNG，检测佛修补全是否需要保存 |
| `events.py` | 当前内容与境界下的事件有效性，以及失去对应事件的试炼清理 |

部分系统辅助函数沿用 `migrate_*` 名称，但仍承担当前内容下的初始化或一致性维护，例如 DLC 重启切换、机构身份和夺舍时间线。它们属于会话准备，不代表支持结构 1–5。模型解码中的默认值与字段规范化也仍保留，不能据此绕过存档版本入口。

以后修改持久化结构时，提高 `SAVE_SCHEMA_VERSION`，在 `SAVE_MIGRATIONS` 登记从 N 到 N+1 的纯文档变换。执行器先检查完整路径，再复制文档逐步转换；版本号由执行器推进，步骤不得改存档编号、调用玩法、抽随机数或写文件。全部转换及模型解码成功后才原子提交，保留模型未识别的扩展字段；任一步失败都不覆盖原文件。迁移以新的结构版本为基线运行一次，不进入每次 `_load` 的业务分支。

当前没有为 1–5 登记兼容转换，也不预先编造未来版本迁移。测试使用临时的 6→7→8 转换验证顺序、缺步拒绝、失败隔离及重复读取；实际支持范围为结构 6、7 和 8，当前写入结构 8。存档码使用同一迁移入口，在副本上校验，预览不写入，导入仍保留原有确认与备份流程。

新增系统应把运行时补全放进对应阶段并显式声明能力；结构字段转换则放入版本迁移。不得让准备算法直接读写存档，也不得让结构迁移依赖模型、内容注册或引擎。边界检查与 `tests/test_persistence_pipeline.py` 持续约束这些规则。

## 系统与引擎之间的依赖

人物交往由 `composition/contacts.py` 注入明确的操作契约，系统不再导入引擎内部的师徒实现。经济、神机、内政、炼器、阵法、归墟和战争分别通过各自目录的 `dependencies.py` 和 `wiring.py` 声明、连接协作能力，并由 `composition/systems.py` 直接接入引擎。配置钩子和具名常量仍从原模块延迟读取，各系统算法不反向导入自身的兼容入口。

战斗能力适配已移至 `system/combat_adapter.py`，供引擎与王庭共同调用。`engine/combat_capabilities.py` 保留同一对象的兼容导出。适配器仍承担规则、模型与持久化对象之间的连接，不能视作纯战斗规则。

战斗适配、预案和能力提供者使用 `system/aperture_resources.py` 查询、提交元力；灵域与道统共用 `system/doctrine/state.py`，本界战斗能力由 `system/upper_voisinage_rules.py` 提供。王庭使用 `system/institution_state.py` 维护账本和政策，避免战斗能力读取沿政务调用链返回王庭评估。原展示和操作入口保留兼容导出，战斗结算、资源归属与提交顺序保持原样。

运行 `python tools/check_module_dependencies.py` 检查已建立的模块边界；任何显式导入循环或边界违规都会返回失败。目前包括核心模型在内的所有显式导入循环均已拆开，检查包含函数内延迟导入，不模拟动态导入与隐式包初始化。模型默认值和旧档转换依赖基础定义，内容注册调用独立校验器，鬼修/装备/NPC 数值投影不再导回玩法入口，详见系统目录说明。

## 为保持游戏性而保留的实现

以下实现已经接入显式依赖，但没有改写算法或副作用。它们并非永远不能调整；本轮没有能够直接证明行为等价的替代方案，因此保留现状。

| 代码或函数 | 保留原因与后续修改边界 |
| --- | --- |
| `engine_persistence._load` | 已拆分版本入口和六组准备阶段；会话准备仍可能消耗随机数、记录历史及结算死亡。有变化时统一保存，不是纯读接口；进一步迁移到行动生命周期需要单独验证触发时机。 |
| `engine_presentation.present`、`presentation.world._public_race_system` 及其调用链 | 展示链仍会补全本命法宝、种族关系和成就元数据。移到其他生命周期可能改变首次查询结果和状态，故保留调用顺序与副作用。 |
| `orchestration.advancement.advance` | 已与旅行共用年度收尾和行动单位结算；逐年收益、单位扣费、机构工作及最终提交位置保留，两个结算配置的规则差异见第 9 项说明。 |
| `events.effects._effect` | 保留效果分支顺序、提前返回和共享状态写入。改成异步事件总线可能改变同次行动内的可见状态。 |
| `engine_combat_runtime._combat`、`_apply_cultivator_kill`、`_die` | 保留战斗、奖励、击杀后果、夺舍及死亡处理的先后关系，以及玩家战斗与后台战斗边界。 |
| `actions.world_travel._prepare_permanent_world_transition` 及飞升/返回流程 | 保留势力继承、监禁、拍卖、随行人员、关系及傀儡的清理范围与顺序，避免跨界结果变化。 |
| `world.relationships._sync_relationship_records`、`_sync_party_state` | 普通关系已通过 ID 读写权威 NPC，关系存档仅保留特有字段；俘虏来源侍妾等特殊生命周期暂不合并，见第 8 项。 |
| `progression/breakthroughs.py`、`progression/trials.py` | 保留概率、保底、消耗、联合结算和随机数调用顺序，不顺手修正规则。 |
| `GameEngine` 仍保留的 9 个直接基类 | 上界机构、佛门、家族、儒道、侍妾、鬼道、妖族血脉、本命法宝和魔道仍使用 Mixin；其中鬼道、魔道、侍妾、佛门的关键跨系统流程已移出，其他局部规则、培养和查询继续保留。 |
| `orchestration/world_time.py` 的 `_advance_world_year` | 已从地图 Mixin 移出，通过明确的年度契约调用各系统；阶段顺序与中断语义保持原样，不等于已统一所有活动的计时规则。 |
| `GameState`、`Player` 与现有存档模型 | 保留共享可变对象与 JSON 存储；结构版本为 8，提供 6→7→8 纯文档迁移，1–5 不支持；没有引入实体数据库。 |

本轮解决的是 `engine/` 实现对入口全局变量和未声明引擎能力的隐式依赖。外部玩法 Mixin 的内部耦合，以及上表中的共享状态和副作用，仍是兼容边界；不能据此认为整个项目已完成解耦。

## 后续维护约定

1. 新增规则调用时，从实际定义模块导入；需要其他引擎能力时，先在依赖契约中声明，再在 `composition/` 对应职责中显式连接。新增职责由 `wiring.py` 注册构建函数。
2. 对外保留或新增方法时，在 `GameEngine` 中声明签名明确的转发方法；模块别名不得与方法参数同名。
3. 不再通过动态安装方法、替换函数全局命名空间或通用引擎属性代理建立依赖。
4. 移动存档写入、随机数调用、状态补全与结算顺序，属于行为变更，不能混入仅调整架构的重构。
5. 每组 Mixin 迁移前保存方法接口与固定种子回放基线；迁移后检查方法覆盖、子类 `super()`、配置替换、资源替换及公开命令的存档锁。保留其他基类的相对顺序，避免顺手合并生命周期或展示副作用。

Mixin 迁移改善依赖可见性与独立测试能力，不代表游戏性能必然提升。接口、方法体和回放等价检查能降低玩法回归风险，但无法覆盖所有历史存档、随机分支、外部扩展和设备组合；发行前仍需用当前源码构建安装包，执行相应平台验收。

## 验证

HTTP 请求体读取和响应网络写入位于存档锁之外；状态读取、补全、操作与响应数据序列化仍在请求作用域内完成。桌面与 Android 共用这条边界，慢连接不再持有全局存档锁。成就元数据仅在文件不存在时初始化；读取失败或结构损坏会报错并保留原文件，禁止将失败当作空记录覆盖。

```powershell
python -m pytest -q tests/test_engine_dependencies.py tests/test_asura_dependencies.py tests/test_court_dependencies.py tests/test_priority_fixes.py
python -m pytest -q tests/test_system_composition.py tests/test_system_layout.py
python -m pytest -q tests/test_production_dependencies.py tests/test_crafting_system.py tests/test_formation_system.py tests/test_auction_update.py
python -m pytest -q tests/test_expedition_dependencies.py tests/test_guixu_tide.py tests/test_guixu_companions.py tests/test_war_performance_update.py
python -m pytest -q tests/test_module_dependencies.py
python -m pytest -q tests/test_persistence_pipeline.py tests/test_save_transfer.py tests/test_audit_regressions.py
python tools/check_module_dependencies.py
python -m pytest -q
```

依赖边界测试检查模块全局引用、依赖声明、转发名称冲突、独立调用、构造后的方法覆盖与资源替换、类方法继承分派及兼容钩子。

## 空间操作

`actions/exploration.py` 使用冻结的 `ExplorationDependencies` 接入符箓与空间玩法，不增加继承层级。串行操作上下文为独立空间提供服务端隔离白名单；请求内读档缓存仍然生效。界面排斥在展示提交及突破边界统一协调，不能由客户端设置目的界面。实例年度只推进自身人物及玩家结算，复用公共年度与魂蚀流程。设计及验证见 [空间规则](../../docs/spatial-talismans.md)。
