# 引擎架构与行为兼容说明

第二轮重构将 25 个方法容器中的 251 个实现改为普通模块函数，通过显式依赖调用其他能力。算法不再通过 `FunctionType` 重绑定全局命名空间或动态安装到入口类；`transactions.serialized_commands` 仍为公开操作统一包装存档锁。此前各组 Mixin 迁移保持游戏规则、结算顺序、随机数调用顺序和存档格式；后续读档阶段按新的兼容要求启用结构版本 6，详见下文。

外部入口保持不变：

```python
from cultivation_life.engine import GameEngine, encode_rng
```

`GameEngine` 保留原方法签名、默认值及静态方法/类方法性质。入口类中的转发方法静态声明，算法在对应职责模块中实现；保留这些转发方法是为了让现有调用方及子类继续使用原接口。当前已将修罗养成、天庭、瑶池、神机、内政、经济／交换会、炼器、阵法、归墟、战争、地图／传送、商盟及道统／仙界养成移出继承列表，其余直接基类的相对顺序保持不变。

当前增量重构的第一阶段将直接基类从 23 个减为 22 个。`actions/asura.py` 接收 `AsuraActionDependencies`，修罗试炼接收 `AsuraTrialDependencies`；两者均不接收整个引擎。旧 `system/asura_system.py` 保留薄适配器供既有调用方使用，引擎不再继承它。

第二阶段将天庭与瑶池的 34 个方法迁入 `system/court/`，直接基类从 22 个减为 20 个。其中 29 个方法使用状态、政务、任期和瑶池四组显式依赖，5 个静态辅助函数无需依赖。`system/court/wiring.py` 连接具名能力，由引擎统一装配；旧四个 Mixin 类仅用于兼容原调用方，不再出现在引擎继承链中。

第三阶段将神机与内政的 74 个方法改为引擎显式转发，直接基类从 20 个减为 18 个。63 个既有算法保持原实现，内政议事权限方法迁入 `system/intrigue/governance.py`，另外 10 个静态辅助实现改为原模块中的普通函数。`composition/systems.py` 连接神机六组、内政七组依赖及原配置钩子，`EngineDependencies` 持有完整契约；两组旧 Mixin 仅兼容独立消费者。引擎保留 `_tianji_dependencies`、`_intrigue_dependencies` 属性供既有代码读取组合后的契约。

第四阶段将经济／交换会、炼器与阵法的 120 个方法改为引擎显式转发，直接基类从 18 个减为 15 个，同时移除间接继承的 `ExchangeSystemMixin`。经济已有的 47 个算法继续复用，补齐跨界拍卖取消与黑市搜索；7 个交换会算法进入 `system/economy/exchange.py`。炼器按市场、选材、预览、炼制、器物交易和展示六组连接依赖，阵法按市场、预设与启阵、镇地阵、NPC 和展示五组连接依赖。原 28 个静态辅助实现保留在原模块，由旧类及引擎分别转发。

本阶段没有合并或延后保存，也没有调整预览、扣料、随机数、退款、撤阵或失败回滚的执行顺序。神机市场与购入回调仍可缺省，通过具名 getter 在调用时读取；兼容消费者缺少这些回调时保持原行为。旧四个 Mixin 保留独立消费者接口，引擎改用 `EngineDependencies` 中的四组系统契约。

## 依赖如何连接

本轮地图／时间、商盟、道统／仙界养成将直接基类从 13 个减为 10 个，连同间接基类共移除 10 个 Mixin。原 61 个方法成为普通函数，新增 `_finish_travel_time` 承接从旅行中抽出的行动单位结算。原有引擎方法签名不变；这三组的旧 Mixin 类不再保留，调用入口是 `GameEngine` 或带明确依赖参数的模块函数。

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

本轮验证：全量 1848 项测试按完整模块分为八批通过，新增 45 项独立执行与边界检查；浏览器烟雾测试通过。生产 78 个、归墟／战争 85 个及本轮三组 57 个检查点，共 220 个完整状态摘要与修改前一致。61 个原方法体经依赖参数、相对导入和旅行阶段抽取归一化后语法树一致，原引擎方法签名未变。当前 290 个模块、1624 条显式导入边无循环或边界违规。本轮未重新打包或执行 Android 安装包验收。

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

结构版本由 `save_schema.SAVE_SCHEMA_VERSION` 定义，当前为 6，与本体发行版本、内容版本及 DLC 版本独立。结构 1–5 不提供迁移路径；读取与存档码导入均明确拒绝，原文件保持不动，不会把旧版本号直接改为新版本。存档列表仅列出有完整支持路径的文件。

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

当前没有为 1–5 登记兼容转换，也不预先编造未来版本迁移。测试使用临时的 6→7→8 转换验证顺序、缺步拒绝、失败隔离及重复读取；实际支持范围仍只有结构 6。存档码使用同一迁移入口，在副本上校验，预览不写入，导入仍保留原有确认与备份流程。

新增系统应把运行时补全放进对应阶段并显式声明能力；结构字段转换则放入版本迁移。不得让准备算法直接读写存档，也不得让结构迁移依赖模型、内容注册或引擎。边界检查与 `tests/test_persistence_pipeline.py` 持续约束这些规则。

本阶段新增 40 项测试，覆盖旧版及畸形版本拒绝、只读解码、逐级迁移、失败时原文件保留、扩展字段保留、编号一致性、准备顺序、一次提交，以及五条道途的新建与重复读取。全量八批次首次为 1802 通过、1 失败；失败项是世界归属写入位置的架构检查仍指向旧文件，更新到角色准备模块后，该模块 19 项测试全部通过，合计 1803 项已通过验证。浏览器冒烟完整通过。六组 437 个回放检查点在仅归一化顶层游戏结构版本 5→6 后一致，实际存档始终写入结构 6；没有过滤玩法、随机数或历史差异。另修正了神识初始功法补全的变化标记，以及佛修补全在提交之后运行导致未持久化的问题。本阶段未重新打包。

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
| `orchestration.advancement.advance` | 年度推进与行动单位结算有不同粒度，包含中断、市场刷新、随机数状态保存。没有改用新的调度器，也没有重排年度处理。 |
| `events.effects._effect` | 保留效果分支顺序、提前返回和共享状态写入。改成异步事件总线可能改变同次行动内的可见状态。 |
| `engine_combat_runtime._combat`、`_apply_cultivator_kill`、`_die` | 保留战斗、奖励、击杀后果、夺舍及死亡处理的先后关系，以及玩家战斗与后台战斗边界。 |
| `actions.world_travel._prepare_permanent_world_transition` 及飞升/返回流程 | 保留势力继承、监禁、拍卖、随行人员、关系及傀儡的清理范围与顺序，避免跨界结果变化。 |
| `world.relationships._sync_relationship_records`、`_sync_party_state` | 继续使用现有 NPC 与关系对象并保持同步顺序。统一关系存储需要模型与存档迁移，超出等价拆分范围。 |
| `progression/breakthroughs.py`、`progression/trials.py` | 保留概率、保底、消耗、联合结算和随机数调用顺序，不顺手修正规则。 |
| `GameEngine` 仍保留的 10 个直接基类 | 上界机构、关系处置、佛门、家族、儒道、侍妾、鬼道、妖族血脉、本命法宝和魔道仍使用 Mixin；维持相对继承顺序，按实际跨系统职责决定后续拆分范围。 |
| `orchestration/world_time.py` 的 `_advance_world_year` | 已从地图 Mixin 移出，通过明确的年度契约调用各系统；阶段顺序与中断语义保持原样，不等于已统一所有活动的计时规则。 |
| `GameState`、`Player` 与现有存档模型 | 保留共享可变对象与 JSON 存储；结构版本已升为 6，旧结构不再支持，没有引入实体数据库。 |

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

第二轮重构的历史验证包括 251 个实现函数语法树、717 个引擎方法接口、七条路线回放及 NPC 辅助函数核对，不代表后续版本未发生变化。

当前第一阶段另行核对了迁移前后 797 个引擎方法签名，以及原有 26 组依赖构造表达式；两者保持一致。三个固定种子的 81 个回放检查点覆盖转化事件、炼体、开脉、凝练、融合战、养成和神通操作，比较完整返回数据、存档、随机数状态与历史记录。独立依赖测试还覆盖无引擎调用、实例资源替换、方法和子类覆盖、旧 Mixin 适配器。

天庭与瑶池阶段核对了 34 个迁移方法体（仅归一化 `self` 到依赖参数的替换）与 797 个方法签名。新增 78 个天庭／瑶池检查点，连同修罗、神机／内政与战斗回放，共 274 个检查点与迁移前一致。全量 1710 项测试及浏览器冒烟通过；依赖图的 225 个模块无显式导入循环。

神机与内政组合阶段核对了既有方法签名、63 个转发方法体、10 个静态辅助实现，以及权限判断迁移前后的语法树；其余基类顺序保持不变。四组 274 个回放检查点与本阶段迁移前一致。新增 16 项回归覆盖玩家／NPC 权限边界、配置延迟替换、资源与方法替换、子类 `super()` 及旧 Mixin 独立消费者。全量 1726 项测试和浏览器冒烟通过，226 个模块无显式导入循环。本阶段未进行新的 Android 安装包验收。

经济／交换会、炼器与阵法阶段保持原有 800 个非双下划线可调用成员的签名，45 个迁移算法仅替换依赖访问及相对导入，28 个静态辅助函数保持原实现（比较时归一化文档字符串缩进）。新增 78 个经济与生产回放检查点，连同原四组共 352 个检查点与迁移前一致。新增 17 项依赖与行为检查，全量 1743 项测试和浏览器冒烟通过，244 个模块无显式导入循环。扩展加载测试恢复其修改的全局报告，消除批次顺序造成的污染；交换会旧随机数替换钩子继续生效。本阶段没有重新打包或进行新的 Android 安装包验收。

归墟与战争阶段保留 800 个可调用成员签名，核对了 72 个迁移算法与 11 个静态辅助实现，引擎直接基类从 15 个减为 13 个，其余顺序不变。新增 18 项行为与依赖检查，并将两组算法纳入模块契约检查；全量 1763 项测试按完整模块分为八个隔离批次通过。新增 85 个归墟／战争回放点，加上既有五组共 437 个检查点与迁移前一致。归墟回放中炼器材料标签来自集合，首轮发现跨进程顺序差异；工具固定 Python 哈希种子后，用保留的迁移前源码和当前实现对照一致，没有改动游戏输出。依赖图包含 265 个模块、1489 条显式边，未发现循环或边界违规。

本阶段浏览器冒烟首次在鬼修轮回事件卡显示处超时；增加响应与页面异常日志后完整复测通过，两次轮回响应均包含正确事件，未记录页面脚本异常。超时原因未复现，不能据此归因为本次迁移或认定已修复前端问题。此次没有重新打包或执行 Android 安装包验收。
