# 引擎架构与行为兼容说明

第二轮重构将 25 个方法容器中的 251 个实现改为普通模块函数，通过显式依赖调用其他能力。`engine/` 已移除 `FunctionType` 全局命名空间重绑定和运行时方法安装。游戏规则、结算顺序、随机数调用顺序和存档格式保持原样。

外部入口保持不变：

```python
from cultivation_life.engine import GameEngine, encode_rng
```

`GameEngine` 保留原方法签名、默认值、静态方法/类方法性质以及原继承顺序。入口类中的转发方法静态声明，算法在对应职责模块中实现；保留这些转发方法是为了让现有调用方及子类继续使用原接口。

## 依赖如何连接

```text
GameEngine ── wiring.py ── dependencies.py ── ports.py
    │                         │
    └── 普通模块函数(deps, ...) ┘
             │
             └── 显式导入模型、配置与规则函数
```

- `dependencies.py` 为每个职责模块声明冻结的数据类，所有协作能力都有名称，构造时必须提供。算法只能访问其契约列出的能力，不接收整个引擎对象。
- `ports.py` 定义存档、地图和成就资源接口，领域实现不依赖这些资源的具体适配器。
- `wiring.py` 是知道 `GameEngine` 的依赖装配边界。它逐项连接回调与资源，不使用兜底属性代理，也不把任意属性查找暴露给算法。
- 没有实例依赖的静态辅助函数直接运行；NPC 类方法使用单独的 `NpcClassDependencies`，保留子类对寿元计算的覆盖能力。
- 回调在调用时查找引擎方法，资源通过显式 getter 获取。构造引擎后替换方法、存档服务或其他资源，仍按原行为生效；不能随意改为缓存绑定方法或资源快照。

原入口的 `bloodline_content_available` 兼容钩子通过命名回调注入，保留调用时替换该钩子的行为。算法不反向导入入口模块。其他内部规则符号改为从定义它们的模块导入；`GameEngine` 与现有调用方使用的 `encode_rng` 继续从入口导出。第一轮使用的内部 `Engine*Mixin` 方法容器已删除。

## 目录职责

| 位置 | 职责 |
| --- | --- |
| `__init__.py` | 引擎入口、资源初始化与显式转发方法 |
| `dependencies.py` | 各职责模块所需的命名依赖契约 |
| `ports.py` | 存档、地图、成就资源接口 |
| `wiring.py` | 引擎与依赖契约之间的装配 |
| `engine_constants.py` | 引擎共享常量 |
| `orchestration/session.py` | 创建游戏 |
| `orchestration/advancement.py` | 行动推进、年度收益、行动单位结算与记录 |
| `actions/cultivation.py` | 秘术管理及玩家主动突破 |
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
| `GameEngine` 原有的 16 个直接基类 | `system/` 的玩法 Mixin 与 `MapTravelMixin` 内部仍通过 `self` 调用引擎能力。保留原 MRO，当前引擎模块通过具名依赖访问这些能力；本轮未继续改造系统内部。 |
| `cultivation_life/map_runtime.py` 的 `MapTravelMixin._advance_world_year` | 位于本轮范围之外，年度系统调用顺序保持原样，通过显式回调接入引擎算法。 |
| `GameState`、`Player` 与现有存档模型 | 保留共享可变对象与原 JSON 格式，没有引入实体数据库、状态复制或新的存档版本。 |

本轮解决的是 `engine/` 实现对入口全局变量和未声明引擎能力的隐式依赖。外部玩法 Mixin 的内部耦合，以及上表中的共享状态和副作用，仍是兼容边界；不能据此认为整个项目已完成解耦。

## 后续维护约定

1. 新增规则调用时，从实际定义模块导入；需要其他引擎能力时，先在依赖契约中声明，再在 `wiring.py` 中显式连接。
2. 对外保留或新增方法时，在 `GameEngine` 中声明签名明确的转发方法；模块别名不得与方法参数同名。
3. 不再通过动态安装方法、替换函数全局命名空间或通用引擎属性代理建立依赖。
4. 移动存档写入、随机数调用、状态补全与结算顺序，属于行为变更，不能混入仅调整架构的重构。

## 验证

```powershell
python -m pytest -q tests/test_engine_dependencies.py
python -m pytest -q
```

依赖边界测试检查模块全局引用、依赖声明、转发名称冲突、独立调用、构造后的方法覆盖与资源替换、类方法继承分派及兼容钩子。

本轮还进行了重构前后核对：251 个实现函数在还原依赖参数改名后语法树一致；717 个引擎方法的签名、描述符、文档和原 MRO 一致；固定随机种子的七条修行路线回放、地图死亡、旧档补全及 104 组 NPC 类辅助函数结果一致。回放比较包含完整返回数据、存档、随机数状态与历史记录。`engine/` 之外的原有 Python 源文件保持不变。
