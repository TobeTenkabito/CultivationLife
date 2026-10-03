# 系统目录与兼容边界

经济、神机、内政三个系统均采用显式依赖的普通函数，原动态装配工具 `_assembly.py` 已删除。外部仍通过原来的 `*_system.py` 模块导入原类及模块级辅助函数。

## 已拆分的系统

| 目录 | 文件与职责 |
| --- | --- |
| `economy/` | `market.py` 坊市与通用价格；`spirit_fields.py` 灵田；`arts.py` 技艺经验与炼丹；`auctions.py` 拍卖；`private_trade.py` 私下交易；`black_market.py` 黑市购买与出售；`treasure.py` 探宝 |
| `tianji/` | `generation.py` 神机生成；`state.py` 状态补全与名称迁移；`intelligence.py` 情报与交互；`forging.py` 材料、货架与炼制；`npcs.py` NPC 持有与掉落；`presentation.py` 展示与调试信息 |
| `intrigue/` | `state.py` 内政状态与人物性格；`governance.py` 职位、权限与人事；`guests.py` 客卿；`recruitment.py` 招募；`resolutions.py` 议案；`runtime.py` 监禁同步与周期更新；`presentation.py` 展示 |
| `court/` | `state.py` 天庭状态与操作；`governance.py` 政务；`lifecycle.py` 任期与俸禄；`yaochi.py` 瑶池操作；四组依赖契约与显式装配 |

## 原模块继续负责兼容

- `economy_system.py` 保留 `EconomySystemMixin(ExchangeSystemMixin)`，以及含延迟相对导入的拍卖跨界取消、黑市搜索方法。
- `tianji_system.py` 保留 `TianjiSystemMixin`、生成版本、常量和全部模块级辅助函数。
- `intrigue_system.py` 保留 `IntrigueSystemMixin`、常量、模块级辅助函数，以及默认参数引用 `PLAYER_ID` 的权限判断转发方法。

经济、神机与内政最初拆分阶段没有修改 `GameEngine` 的继承顺序，也没有为拆出的文件增加 Mixin 基类。后续天庭与瑶池阶段移除两个直接基类，神机与内政组合阶段再移除两个；其余基类的相对顺序保持原样。

## 天庭与瑶池的组合式接入

`court/` 将原有 34 个方法改为普通函数，29 个通过四组冻结依赖契约调用协作能力，5 个静态辅助函数直接调用。算法不接收整个引擎，也不反向导入装配模块或旧 Mixin 入口。引擎显式声明转发方法，保留原签名、默认值及静态方法性质。

`heavenly_court_system.py`、`court_governance.py`、`court_lifecycle.py` 与 `yaochi_system.py` 保留薄兼容类，支持原有独立消费者；引擎不再继承这些类。瑶池模块级规则移到 `yaochi_rules.py`，旧路径导出同一函数对象。回调和存档 getter 在调用时查找当前实例，构造后替换方法或资源继续生效。其他规则符号应在实际定义或使用模块维护。

`tests/test_court_dependencies.py` 覆盖独立依赖调用、方法与资源替换、旧瑶池消费者以及禁止反向导入；`tests/test_module_dependencies.py` 检查算法全局引用和契约完整性。天庭与瑶池新增 78 个固定种子回放检查点，覆盖锁货、购买、兑换、俸禄和任期推进；迁移前后返回数据、存档及随机数状态一致。

## 经济系统的显式依赖

`economy/` 的 47 个算法是可独立调用的普通模块函数，使用各自模块的真实全局命名空间。`dependencies.py` 按七组职责声明所需回调和资源接口；`wiring.py` 逐项连接依赖，算法不导入装配模块、兼容入口或引擎。

`EconomySystemMixin` 保留原签名的转发方法和 13 个静态辅助函数。`_economy_dependencies` 首次使用时缓存契约，回调及资源 getter 在调用时查找当前对象，因此构造后替换方法或存档服务仍然生效。静态配置辅助函数仍使用入口模块的 `WORLD_SYSTEMS`，兼容既有配置替换；算法直接导入的其他符号应在实际定义或使用模块维护，不再依赖入口的隐式全局变量。

## 神机与内政的显式依赖

神机原有的 32 个动态装配方法改为 27 个普通函数与 5 个静态辅助函数；内政原有的 41 个改为 36 个普通函数与 5 个静态辅助函数。后续组合阶段另将 `_intrigue_has_decision_authority` 迁入 `intrigue/governance.py`，通过显式契约检查玩家归属、世界、存活和境界，以及 NPC 存活、境界和监禁。入口保留 `PLAYER_ID` 默认参数的原求值时机，执行时的玩家标识通过 getter 读取。所有转发方法都有明确签名，不在运行时创建函数或安装方法。

两个目录各自提供 `dependencies.py` 与 `wiring.py`，分别按六组、七组职责列出并连接协作能力。算法可使用独立的契约实例调用，不接收整个引擎，也不导入入口或装配模块。

引擎通过 `engine/composition/systems.py` 构造契约，不再继承两组 Mixin；旧入口仍为独立消费者在首次使用时缓存契约。回调、资源及兼容常量 getter 均在调用时解析。`tianji_config`、`tianji_content_available`、`intrigue_rules`、稳定随机流和描述辅助函数仍从原入口显式注入，构造契约后替换配置辅助函数、引擎方法或存档服务仍然生效。10 个静态辅助实现保留在原模块，原类与引擎的静态方法分别转发，继续使用该模块的配置绑定。已声明的常量由具名 getter 提供，不使用任意属性代理。

算法使用自身模块的实际运行时导入。新增依赖必须添加到契约和对应构建函数；算法直接使用的规则符号从定义模块导入，不能再借用入口的全局命名空间。函数内相对导入按算法所在包解析，内政招募与迁址使用 `..combat.npc_lifecycle`。

## 跨模块依赖边界

- `npc_contacts.act` 接收 `NpcContactDependencies`，师徒操作由 `engine/composition/contacts.py` 注入，不再反向导入引擎动作实现。
- `system/combat_adapter.py` 为引擎试炼和修罗王庭共用的战斗适配层，位于纯战斗规则目录 `combat/` 之外；旧 `engine/combat_capabilities.py` 仅兼容导出。
- 存档、地图、成就接口定义在 `cultivation_life/ports.py`，旧 `engine/ports.py` 保留兼容导出。
- 道统随机流定义在 `doctrine/randomness.py`，商盟委托种类定义在 `merchant_definitions.py`，原入口继续导出同一符号，避免消费方互相导入。
- `combat_rule_schema.py` 统一定义新版战斗规则常量和校验，战斗执行器与旧血脉规则均依赖它；旧 `combat_rule_engine.validate_rule` 保留同一函数的兼容导出。
- `tutorial_mentorship.py` 负责师缘条件、状态和操作；教程入口与操作教学共同调用它。师缘操作不再为了判定拜师条件调用完整教学展示。旧教程入口保留 `blocked_reason`、`mentor_action` 与 `MENTOR_STEP` 导出。

新增系统代码不得运行时导入 `engine/`；旧修罗适配器 `asura_system.py` 是保留的兼容例外。依赖检查包含函数内延迟导入，忽略仅供类型检查的导入，不模拟动态导入或 Python 隐式执行的包初始化。此前的战斗循环及最后一组 22 个核心模块循环均已拆开；当前 226 个 Python 模块的显式导入图无循环。检查器对任何新循环或已声明边界违规返回失败；这不等于共享可变状态、Mixin 协作和展示副作用已全部解耦。

## 战斗共用规则与状态

战斗适配不再为了查询元力、邻域或道统而导入包含展示、操作和政务推进的入口。原有 25 个函数整段迁入四个共用模块，旧导入路径继续导出同一函数对象：

| 共用模块 | 职责 | 原兼容入口 |
| --- | --- | --- |
| `aperture_resources.py` | 真实境界、投入倍率、元力池初始化、读取与扣除 | `immortal_aperture.py` |
| `doctrine/state.py` | 道统目录初始化、旧档补全、玩家记录 | `doctrine/provider.py` |
| `upper_voisinage_rules.py` | 本界配置、可用条件、等级及战斗能力投影 | `upper_voisinage.py` |
| `institution_state.py` | 机构账本、政策查询与历史记录 | `upper_institutions.py` |

王庭仍可调用战斗适配做评估，但账本和政策查询改用 `institution_state`；战斗道统提供者只读取 `upper_voisinage_rules`，不会经过培养报价返回政务和王庭。灵域目录初始化调用 `doctrine.state`，不再导回战斗能力提供者。元府展示与培养操作仍保留在原入口。

这些共用模块禁止反向导入战斗适配、能力提供者及上述操作入口。共享状态函数并非全部只读：元府迁移、道统初始化、资源扣除和历史写入仍保留原调用时机；重构没有增加刷新、补满或自动培养。不要将 `ensure_*` 当作纯查询，也不要在展示阶段额外调用它们。

## 行为保持约束

重构以整段移动方法为主，保持数值公式、随机数消费顺序、存档保存时机与展示副作用。内容校验改为显式接收目录，突破报价由调用者提供世界策略，肉身采集只投影族属，不再经过无关的修罗路线展示。不会因方法名带有 `public`、`ensure` 或 `state` 就改变其行为。

验证采用迁移前后方法源码与语法树对比、运行时代码与全局命名空间比对、继承关系比对，并运行完整测试：

```powershell
python tools/check_module_dependencies.py
python -m pytest -q tests/test_module_dependencies.py tests/test_system_layout.py
python -m pytest -q
```

`tests/test_system_layout.py` 覆盖原模块配置替换、辅助函数替换和拍卖取消中的延迟导入兼容性。

`tests/test_module_dependencies.py` 检查上述导入边界、三个系统算法的真实命名空间与契约完整性，并验证无引擎调用、资源和配置替换、人物交往注入及旧路径兼容导出。

神机与内政迁移另行核对了 63 个算法的方法体、10 个静态辅助方法和 797 个引擎方法签名。两个固定种子的 90 个回放检查点比较完整返回数据与存档，覆盖新手教学、师缘、神机生成/情报/炼制/激活，以及内政任职、监禁、议案和弟子招募。

后续组合阶段通过 `tests/test_system_composition.py` 验证移除继承后的玩家与 NPC 议事权限、配置替换、实例资源替换、子类覆盖与 `super()`、旧入口独立调用。该阶段重新生成迁移前后基线：神机／内政 90 个检查点与其他三组回放合计 274 个检查点一致；全量 1726 项测试和浏览器冒烟通过。

战斗循环拆解核对了 25 个迁移函数的完整语法树和 797 个引擎方法签名。七种世界/DLC 配置的 25 个回放检查点覆盖展示、实战、王庭评估及政务推进，比较完整返回值、角色状态和战斗随机数状态。依赖测试禁止这 13 个原模块及共用模块重新进入循环，并验证旧路径导出、下界封存元力与机构只读查询。

## 核心模型与内容加载边界

模型、校验器和数值投影不再通过玩法入口相互引用。新增代码应直接使用对应定义模块；原入口保留兼容导出。

| 定义模块 | 职责与约束 |
| --- | --- |
| `../ancestry.py`、`../cultivation_coordinates.py` | 稳定族属、境界坐标和旧神识转换；不依赖内容注册或玩法。模型保留对纯数据转换 `combat/migration.py` 的调用。 |
| `../event_catalog.py`、`../achievement_definitions.py` | 校验事件和成就定义；事件目录必须显式传入。`EventRepository` 保留文件加载、默认目录、冻结数据类和子类校验分派。 |
| `map_definition.py`、`world_transition_schema.py`、`combat/lifecycle_schema.py` | 地图拓扑、跨界定义和 NPC 生命周期配置校验；不加载全局内容，也不执行运行期玩法。地图查询与寻路仍由 `MapCatalog` 提供。 |
| `../errors.py` | 共用 `ContentError`，内容加载器和校验器无需为异常类型互相导入。 |
| `../combat_benchmarks.py`、`../cultivation_costs.py` | 境界战力基准和突破报价；世界策略由调用者传入，仙界/修罗报价与普通境界机缘尺度仍分开。 |
| `crafted_artifact_rules.py` | 装备生效、神机世界上限、属性和战斗效果投影；不导入炼制动作或汇总规则。 |
| `ghost_resources.py` | 鬼修魂魄加成、本源数值、承载比例和旧档初始化；不导入轮回或跨界动作。初始化仍有迁移和寿元写入。 |
| `npc_cultivation.py`、`cultivation_reserves.py` | NPC 稳定培养默认值，以及上下界封存机缘策略；不导回人物展示或血脉养成入口。 |

`content_registry` 直接调用定义校验器，仍按原顺序验证完整本体、DLC 和 MOD 内容，没有取消跨表引用、地图、跨界或生命周期校验。修罗入口保留运行期开关；报价、资源加成和无上限机缘仍在调用时读取该开关。

`tests/test_core_dependencies.py` 在新解释器中验证旧档解码与内容注册不会加载玩法入口，覆盖兼容导出、事件覆盖和子类分派、冻结目录、修罗开关，以及新增循环导致检查命令失败。本轮另行比较 49 个迁移函数的语法树（归一化 NPC 访问器导入位置）、797 个引擎签名和重构前后 196 个固定种子回放检查点。
