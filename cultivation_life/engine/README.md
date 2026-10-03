# 引擎架构与行为兼容说明

第二轮重构将 25 个方法容器中的 251 个实现改为普通模块函数，通过显式依赖调用其他能力。算法不再通过 `FunctionType` 重绑定全局命名空间或动态安装到入口类；`transactions.serialized_commands` 仍为公开操作统一包装存档锁。游戏规则、结算顺序、随机数调用顺序和存档格式保持原样。

外部入口保持不变：

```python
from cultivation_life.engine import GameEngine, encode_rng
```

`GameEngine` 保留原方法签名、默认值及静态方法/类方法性质。入口类中的转发方法静态声明，算法在对应职责模块中实现；保留这些转发方法是为了让现有调用方及子类继续使用原接口。当前已将修罗养成、天庭与瑶池移出继承列表，其余直接基类的相对顺序保持不变。

当前增量重构的第一阶段将直接基类从 23 个减为 22 个。`actions/asura.py` 接收 `AsuraActionDependencies`，修罗试炼接收 `AsuraTrialDependencies`；两者均不接收整个引擎。旧 `system/asura_system.py` 保留薄适配器供既有调用方使用，引擎不再继承它。

第二阶段将天庭与瑶池的 34 个方法迁入 `system/court/`，直接基类从 22 个减为 20 个。其中 29 个方法使用状态、政务、任期和瑶池四组显式依赖，5 个静态辅助函数无需依赖。`system/court/wiring.py` 连接具名能力，由引擎统一装配；旧四个 Mixin 类仅用于兼容原调用方，不再出现在引擎继承链中。

## 依赖如何连接

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
| `composition/` | 生命周期、动作、事件、战斗、世界、展示、修罗及人物交往的显式依赖构建 |
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
| `engine_persistence.py` | 读取、旧档迁移与状态补全 |

## 系统与引擎之间的依赖

人物交往由 `composition/contacts.py` 注入明确的操作契约，系统不再导入引擎内部的师徒实现。经济、神机、内政分别通过各自目录的 `dependencies.py` 和 `wiring.py` 声明、连接协作能力，保留原入口的转发方法和继承关系。三个系统均已移除旧式动态装配。

战斗能力适配已移至 `system/combat_adapter.py`，供引擎与王庭共同调用。`engine/combat_capabilities.py` 保留同一对象的兼容导出。适配器仍承担规则、模型与持久化对象之间的连接，不能视作纯战斗规则。

战斗适配、预案和能力提供者使用 `system/aperture_resources.py` 查询、提交元力；灵域与道统共用 `system/doctrine/state.py`，本界战斗能力由 `system/upper_voisinage_rules.py` 提供。王庭使用 `system/institution_state.py` 维护账本和政策，避免战斗能力读取沿政务调用链返回王庭评估。原展示和操作入口保留兼容导出，战斗结算、资源归属与提交顺序保持原样。

运行 `python tools/check_module_dependencies.py` 检查已建立的模块边界；任何显式导入循环或边界违规都会返回失败。目前包括核心模型在内的所有显式导入循环均已拆开，检查包含函数内延迟导入，不模拟动态导入与隐式包初始化。模型默认值和旧档转换依赖基础定义，内容注册调用独立校验器，鬼修/装备/NPC 数值投影不再导回玩法入口，详见系统目录说明。

## 为保持游戏性而保留的实现

以下实现已经接入显式依赖，但没有改写算法或副作用。它们并非永远不能调整；本轮没有能够直接证明行为等价的替代方案，因此保留现状。

| 代码或函数 | 保留原因与后续修改边界 |
| --- | --- |
| `engine_persistence._load` | 读取会迁移旧档、补全商人/鬼修/夺舍/种族/NPC/关系/市场等状态，并可能消耗随机数、多次保存、记录历史或结算死亡。改成纯读取或合并保存会改变触发时机，需另行设计迁移协议。 |
| `engine_presentation.present`、`presentation.world._public_race_system` 及其调用链 | 展示链仍会补全本命法宝、种族关系和成就元数据。移到其他生命周期可能改变首次查询结果和状态，故保留调用顺序与副作用。 |
| `orchestration.advancement.advance` | 年度推进与行动单位结算有不同粒度，包含中断、市场刷新、随机数状态保存。没有改用新的调度器，也没有重排年度处理。 |
| `events.effects._effect` | 保留效果分支顺序、提前返回和共享状态写入。改成异步事件总线可能改变同次行动内的可见状态。 |
| `engine_combat_runtime._combat`、`_apply_cultivator_kill`、`_die` | 保留战斗、奖励、击杀后果、夺舍及死亡处理的先后关系，以及玩家战斗与后台战斗边界。 |
| `actions.world_travel._prepare_permanent_world_transition` 及飞升/返回流程 | 保留势力继承、监禁、拍卖、随行人员、关系及傀儡的清理范围与顺序，避免跨界结果变化。 |
| `world.relationships._sync_relationship_records`、`_sync_party_state` | 继续使用现有 NPC 与关系对象并保持同步顺序。统一关系存储需要模型与存档迁移，超出等价拆分范围。 |
| `progression/breakthroughs.py`、`progression/trials.py` | 保留概率、保底、消耗、联合结算和随机数调用顺序，不顺手修正规则。 |
| `GameEngine` 仍保留的 20 个直接基类 | `system/` 的其余玩法 Mixin 与 `MapTravelMixin` 内部仍通过 `self` 调用引擎能力。修罗养成、天庭与瑶池已迁出，其余系统保持相对继承顺序，后续逐个迁移。 |
| `cultivation_life/map_runtime.py` 的 `MapTravelMixin._advance_world_year` | 位于本轮范围之外，年度系统调用顺序保持原样，通过显式回调接入引擎算法。 |
| `GameState`、`Player` 与现有存档模型 | 保留共享可变对象与原 JSON 格式，没有引入实体数据库、状态复制或新的存档版本。 |

本轮解决的是 `engine/` 实现对入口全局变量和未声明引擎能力的隐式依赖。外部玩法 Mixin 的内部耦合，以及上表中的共享状态和副作用，仍是兼容边界；不能据此认为整个项目已完成解耦。

## 后续维护约定

1. 新增规则调用时，从实际定义模块导入；需要其他引擎能力时，先在依赖契约中声明，再在 `composition/` 对应职责中显式连接。新增职责由 `wiring.py` 注册构建函数。
2. 对外保留或新增方法时，在 `GameEngine` 中声明签名明确的转发方法；模块别名不得与方法参数同名。
3. 不再通过动态安装方法、替换函数全局命名空间或通用引擎属性代理建立依赖。
4. 移动存档写入、随机数调用、状态补全与结算顺序，属于行为变更，不能混入仅调整架构的重构。

## 验证

HTTP 请求体读取和响应网络写入位于存档锁之外；状态读取、补全、操作与响应数据序列化仍在请求作用域内完成。桌面与 Android 共用这条边界，慢连接不再持有全局存档锁。成就元数据仅在文件不存在时初始化；读取失败或结构损坏会报错并保留原文件，禁止将失败当作空记录覆盖。

```powershell
python -m pytest -q tests/test_engine_dependencies.py tests/test_asura_dependencies.py tests/test_court_dependencies.py tests/test_priority_fixes.py
python -m pytest -q tests/test_module_dependencies.py
python tools/check_module_dependencies.py
python -m pytest -q
```

依赖边界测试检查模块全局引用、依赖声明、转发名称冲突、独立调用、构造后的方法覆盖与资源替换、类方法继承分派及兼容钩子。

第二轮重构的历史验证包括 251 个实现函数语法树、717 个引擎方法接口、七条路线回放及 NPC 辅助函数核对，不代表后续版本未发生变化。

当前第一阶段另行核对了迁移前后 797 个引擎方法签名，以及原有 26 组依赖构造表达式；两者保持一致。三个固定种子的 81 个回放检查点覆盖转化事件、炼体、开脉、凝练、融合战、养成和神通操作，比较完整返回数据、存档、随机数状态与历史记录。独立依赖测试还覆盖无引擎调用、实例资源替换、方法和子类覆盖、旧 Mixin 适配器。

天庭与瑶池阶段核对了 34 个迁移方法体（仅归一化 `self` 到依赖参数的替换）与 797 个方法签名。新增 78 个天庭／瑶池检查点，连同修罗、神机／内政与战斗回放，共 274 个检查点与迁移前一致。全量 1710 项测试及浏览器冒烟通过；依赖图的 225 个模块无显式导入循环。
