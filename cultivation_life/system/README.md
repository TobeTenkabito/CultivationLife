# 系统目录与兼容边界

经济、交换会、神机、内政、炼器、阵法、归墟、战争及天庭／瑶池采用显式依赖的普通函数，原动态装配工具 `_assembly.py` 已删除。外部仍通过原来的 `*_system.py` 模块导入兼容类及模块级辅助函数。

## 已拆分的系统

| 目录 | 文件与职责 |
| --- | --- |
| `economy/` | `market.py` 坊市与通用价格；`spirit_fields.py` 灵田；`arts.py` 技艺经验与炼丹；`auctions.py` 拍卖与跨界取消；`private_trade.py` 私下交易；`black_market.py` 黑市搜索、购买与出售；`treasure.py` 探宝；`exchange.py` 匿名交换会 |
| `tianji/` | `generation.py` 神机生成；`state.py` 状态补全与名称迁移；`intelligence.py` 情报与交互；`forging.py` 材料、货架与炼制；`npcs.py` NPC 持有与掉落；`presentation.py` 展示与调试信息 |
| `intrigue/` | `state.py` 内政状态与人物性格；`governance.py` 职位、权限与人事；`guests.py` 客卿；`recruitment.py` 招募；`resolutions.py` 议案；`runtime.py` 监禁同步与周期更新；`presentation.py` 展示 |
| `court/` | `state.py` 天庭状态与操作；`governance.py` 政务；`lifecycle.py` 任期与俸禄；`yaochi.py` 瑶池操作；四组依赖契约与显式装配 |
| `crafting/` | `market.py` 炼器材料货架与购入；`materials.py` 材料候选与选材校验；`preview.py` 品质概率、预算与数值预览；`forging.py` 实际炼制与图谱保存；`artifacts.py` 器物处置、出售与寄拍；`presentation.py` 展示 |
| `formation/` | `market.py` 阵材与维护资源交易；`loadouts.py` 材料候选、预设、启阵、收阵与失败回滚；`ground.py` 镇地阵部署、权限、维护与战争磨损；`npcs.py` NPC 阵法生成与投影；`presentation.py` 展示 |
| `guixu/` | `state.py` 周期与会话补全、境界边界、操作权限；`calendar.py` 预告、开放、关闭与天数消耗；`npcs.py` 参赛者、队伍与后台争夺；`rewards.py` 宝物发放与转移；`encounters.py` 威胁、临时同行与战斗；`actions.py` 探索操作与被困修炼；`presentation.py` 展示 |
| `war/` | `state.py` 战争状态、阵营与参战名单；`diplomacy.py` 宣战、盟友与指挥权限；`power.py` 阵势和战力；`combat.py` 交战、先锋与伤亡；`lifecycle.py` 行动单位推进与士气胜负；`peace.py` 条款、和约及结算；`actions.py` 指令与地图遭遇；`presentation.py` 展示 |
| `ghost/` | `identity.py` 拘魂与夺舍；`calendar.py` 夜行与魂仆年度流程；`erosion.py` 侵蚀判死；`reincarnation.py` 轮回操作；`progression.py` 共用成长和魂基规则 |
| `demonic/` | `refinement.py` 闭关推进；`annual.py` 活傀失控、外魂反噬及死亡衔接 |
| `relationships/` | `captivity.py` 生擒、释放、夺舍及傀儡转换；`concubines.py` 纳入、遣散和转化；`dependents.py` 易主、追索与脱身；`sanctions.py` 关系制裁；`violence.py` 战斗／处决与名册清理 |
| `buddhist/` | `actions.py` 佛门操作；`assembly.py` 法会的时间、事件与奖励流程；`rules.py` 账本及修正规则 |

## 关系人物的存储边界

普通关系使用 `GameState.link_relationship` 关联 NPC，个人事实通过 `RelationshipRecord` 按 ID 读取和写回，显示名称只作为投影。事件生成人物在 `relationship_npcs` 中有权威记录，但保持原来的关系年度时序；正式加入自由名册时转移同一对象，不能重复推进。新存档结构为 7，纯文档的 6→7 迁移位于 `relationship_schema.py`。俘虏来源侍妾等特殊身份保留原生命周期，详细边界与验证见 `engine/README.md` 第 8 项。

## 原模块继续负责兼容

- `economy_system.py` 保留 `EconomySystemMixin(ExchangeSystemMixin)`，四组旧经济／交换／炼器／阵法类均为独立消费者保留转发接口。跨界取消和黑市搜索的延迟相对导入按迁移后的算法目录解析。
- `tianji_system.py` 保留 `TianjiSystemMixin`、生成版本、常量和全部模块级辅助函数。
- `intrigue_system.py` 保留 `IntrigueSystemMixin`、常量、模块级辅助函数，以及默认参数引用 `PLAYER_ID` 的权限判断转发方法。

经济、神机与内政最初拆分阶段没有修改 `GameEngine` 的继承顺序，也没有为拆出的文件增加 Mixin 基类。后续分组移除继承；Step 2 处理后，当前引擎直接基类为 9 个，其余基类的相对顺序保持原样。

五系统关键流程直接由 `GameEngine` 转发到上述新模块，依赖契约在各目录的 `dependencies.py`，装配位于 `engine/composition/`。`RelationshipViolenceMixin` 已删除；另外四个 Mixin 仅保留本轮范围外的局部规则、培养操作和查询。不要从旧类调用已迁出的流程；使用原有引擎入口，或显式构造契约后调用新函数。原 `ghost_system.py` 的成长／侵蚀规则、`buddhist_system.py` 的账本／修正规则继续兼容导出同一函数对象。

时间推进的接入规则见 `engine/README.md` 第 9 项：普通行动与地图旅行已共用 `time_flow.py` 的年度收尾和单位结算，年度系统仍集中在 `_advance_world_year`。新增同类玩法应接入共用流程，不能复制年度或单位系统调用清单。商盟工作、法会、拘魂等待、闭关及归墟等专属活动保留原有计时语义，不自动追加普通行动的单位奖励或市场时钟。

稳定性别和境界比较位于 `relationship_rules.py`，傀儡类型名称位于 `demonic_definitions.py`。流程不得反向导入这五个旧入口；共用规则不得导回流程。下层规则或依赖契约也不能运行时导入引擎。`tools/check_module_dependencies.py` 和 `tests/test_key_flow_dependencies.py` 约束这些边界。

## 归墟与战争的显式依赖

归墟的 32 个实例方法和战争的 40 个实例方法分别使用七组、八组冻结契约，通过 `engine/composition/systems.py` 接入引擎。11 个静态辅助实现留在原入口，旧 Mixin 和引擎均显式转发。旧类支持独立消费者，首次使用时缓存依赖；方法、存档、地图与事件目录在实际调用时读取，保留子类覆盖和运行时替换。

归墟开关、移动天数、战争条款和原入口 `decode_rng` 钩子由具名回调或 getter 注入。算法不得反向导入本系统入口或装配模块，也不接收整个引擎。其他直接导入的规则符号应在实际定义或使用模块维护。

本阶段只调整职责边界。`guixu_action` 的操作分支与 `_conclude_war` 的条款结算仍保留原顺序；归墟关闭前分配到期宝物、临时队伍与归属维护、战争伤亡、阵法磨损、盟友名单、组合和约的资源结算和最终停战保持原行为。展示与读档中的状态补全仍有副作用。

`tests/test_expedition_dependencies.py` 验证无引擎调用的潮期截止、士气判负、和约预算与结算顺序，以及资源替换、旧适配器、子类 `super()` 和禁止反向导入。`tools/replay_expeditions.py` 固定时间、UUID 和 Python 哈希种子，三个游戏种子共 85 个检查点比较完整返回值与存档摘要，覆盖组队、搜索、归返、被困养成、DLC 关闭清理、先锋战、战争推进、盟友、AI 和约和停战。可用 `--trace-directory` 输出完整状态排查差异。

```powershell
python tools/replay_expeditions.py --output build/expeditions-before.json
# 完成待验证的改动后运行：
python tools/replay_expeditions.py --output build/expeditions-after.json --compare build/expeditions-before.json
python -m pytest -q tests/test_expedition_dependencies.py tests/test_guixu_tide.py tests/test_guixu_companions.py tests/test_war_performance_update.py
```

## 天庭与瑶池的组合式接入

`court/` 将原有 34 个方法改为普通函数，29 个通过四组冻结依赖契约调用协作能力，5 个静态辅助函数直接调用。算法不接收整个引擎，也不反向导入装配模块或旧 Mixin 入口。引擎显式声明转发方法，保留原签名、默认值及静态方法性质。

`heavenly_court_system.py`、`court_governance.py`、`court_lifecycle.py` 与 `yaochi_system.py` 保留薄兼容类，支持原有独立消费者；引擎不再继承这些类。瑶池模块级规则移到 `yaochi_rules.py`，旧路径导出同一函数对象。回调和存档 getter 在调用时查找当前实例，构造后替换方法或资源继续生效。其他规则符号应在实际定义或使用模块维护。

`tests/test_court_dependencies.py` 覆盖独立依赖调用、方法与资源替换、旧瑶池消费者以及禁止反向导入；`tests/test_module_dependencies.py` 检查算法全局引用和契约完整性。天庭与瑶池新增 78 个固定种子回放检查点，覆盖锁货、购买、兑换、俸禄和任期推进；迁移前后返回数据、存档及随机数状态一致。

## 经济系统的显式依赖

`economy/` 最初的 47 个算法已补齐跨界取消、黑市搜索和 7 个交换会算法，共 56 个普通函数。`dependencies.py` 按八组职责声明所需回调和资源接口；`wiring.py` 逐项连接依赖，算法不导入自身装配模块、兼容入口或引擎。

`EconomySystemMixin` 保留原签名的转发方法和 13 个静态辅助入口。引擎直接装配 `EconomyDependencies` 与 `ExchangeDependencies`，旧类首次使用时缓存契约。回调及资源 getter 在调用时查找当前对象，因此构造后替换方法或存档服务仍然生效。静态配置辅助函数仍使用入口模块的 `WORLD_SYSTEMS`，交换会身份和会址通过具名 getter 延迟读取；原入口的 `decode_rng` 替换通过显式回调保留。算法直接导入的其他符号应在实际定义或使用模块维护。

## 炼器与阵法的显式依赖

炼器的 12 个实例算法按六组契约调用，阵法的 24 个实例算法按五组契约调用。选材和预览独立于实际炼制的存档能力；执行函数仍按原顺序扣料、生成结果、记录历史和保存。启阵失败恢复材料、绑定、当前阵法与缓存的原回滚范围，没有增加材料复制或更改返还规则。

`crafting_system.py`、`formation_system.py` 保留模块级规则函数和 15 个静态辅助实现，以原路径提供兼容。需要保留配置替换的规则由 `bind_*_compatibility` 显式注入；这些函数是连接旧模块钩子的装配边界，各算法不接收完整引擎。市场神机回调使用两个可空的具名 getter，既支持独立消费者缺省回调，也保留构造后的增加、删除与替换。

`tests/test_production_dependencies.py` 验证独立交换、重复扣料拒绝、失败启阵回滚、可选回调、资源与配置替换、子类 `super()` 和旧静态释放入口。新增规则依赖应补入相应契约；不可在算法中重新导入本系统兼容类或装配模块。

## 神机与内政的显式依赖

神机原有的 32 个动态装配方法改为 27 个普通函数与 5 个静态辅助函数；内政原有的 41 个改为 36 个普通函数与 5 个静态辅助函数。后续组合阶段另将 `_intrigue_has_decision_authority` 迁入 `intrigue/governance.py`，通过显式契约检查玩家归属、世界、存活和境界，以及 NPC 存活、境界和监禁。入口保留 `PLAYER_ID` 默认参数的原求值时机，执行时的玩家标识通过 getter 读取。所有转发方法都有明确签名，不在运行时创建函数或安装方法。

两个目录各自提供 `dependencies.py` 与 `wiring.py`，分别按六组、七组职责列出并连接协作能力。算法可使用独立的契约实例调用，不接收整个引擎，也不导入入口或装配模块。

引擎通过 `engine/composition/systems.py` 构造契约，不再继承两组 Mixin；旧入口仍为独立消费者在首次使用时缓存契约。回调、资源及兼容常量 getter 均在调用时解析。`tianji_config`、`tianji_content_available`、`intrigue_rules`、稳定随机流和描述辅助函数仍从原入口显式注入，构造契约后替换配置辅助函数、引擎方法或存档服务仍然生效。10 个静态辅助实现保留在原模块，原类与引擎的静态方法分别转发，继续使用该模块的配置绑定。已声明的常量由具名 getter 提供，不使用任意属性代理。

算法使用自身模块的实际运行时导入。新增依赖必须添加到契约和对应构建函数；算法直接使用的规则符号从定义模块导入，不能再借用入口的全局命名空间。函数内相对导入按算法所在包解析，内政招募与迁址使用 `..combat.npc_lifecycle`。

## 跨模块依赖边界

商盟原三组 Mixin 已删除：状态、目录、年度结算、交付退款、玩家工作、跨界和展示进入 `merchant/`，命令、委托报价及执行函数保留在原 `merchant_*system.py` 模块。它们接收 `merchant/dependencies.py` 中的窄契约，由 `engine/composition/merchant.py` 连接；交付与退款不再依赖执行模块的继承宿主。商盟共用常量统一定义在 `merchant_definitions.py`，下层实现不得反向导入商盟入口或执行模块。

道统、融合、仙脉、仙体、仙窍也已改为普通函数，契约在 `cultivation_dependencies.py`。共享修持读取／提交位于 `cultivation_session.py`；仙体与融合只通过提交契约使用存档及呈现，不再反向依赖 `immortal_system.py`。元府及上界邻域操作仅获得读取、保存和呈现能力。原元力规则辅助函数仍从 `immortal_aperture.py` 兼容导出同一对象。

地图旅行与传送函数分别保留在 `../map_runtime.py`、`teleport_system.py`，公共年度阶段及旅行后结算由引擎 `orchestration/world_time.py` 负责。原三组共 10 个 Mixin 均已离开引擎继承链；这些类本身不再提供兼容入口，外部使用 `GameEngine` 的既有方法。

- `npc_contacts.act` 接收 `NpcContactDependencies`，师徒操作由 `engine/composition/contacts.py` 注入，不再反向导入引擎动作实现。
- `system/combat_adapter.py` 为引擎试炼和修罗王庭共用的战斗适配层，位于纯战斗规则目录 `combat/` 之外；旧 `engine/combat_capabilities.py` 仅兼容导出。
- 存档、地图、成就接口定义在 `cultivation_life/ports.py`，旧 `engine/ports.py` 保留兼容导出。
- 道统随机流定义在 `doctrine/randomness.py`，商盟委托种类定义在 `merchant_definitions.py`，原入口继续导出同一符号，避免消费方互相导入。
- `combat_rule_schema.py` 统一定义新版战斗规则常量和校验，战斗执行器与旧血脉规则均依赖它；旧 `combat_rule_engine.validate_rule` 保留同一函数的兼容导出。
- `tutorial_mentorship.py` 负责师缘条件、状态和操作；教程入口与操作教学共同调用它。师缘操作不再为了判定拜师条件调用完整教学展示。旧教程入口保留 `blocked_reason`、`mentor_action` 与 `MENTOR_STEP` 导出。

新增系统代码不得运行时导入 `engine/`；旧修罗适配器 `asura_system.py` 是保留的兼容例外。依赖检查包含函数内延迟导入，忽略仅供类型检查的导入，不模拟动态导入或 Python 隐式执行的包初始化。此前的战斗循环及最后一组 22 个核心模块循环均已拆开；普通关系关联权威 NPC 后，当前 322 个 Python 模块的显式导入图无循环。检查器对任何新循环或已声明边界违规返回失败；这不等于共享可变状态、Mixin 协作和展示副作用已全部解耦。

存档结构转换统一在 `save_schema.py` 登记；当前版本的系统补全接入 `engine/persistence/` 的相应阶段，通过具名契约装配。准备算法不持有存档服务，结构转换不调用玩法或消费随机数；具体规则见引擎目录的“读档与版本迁移”。结构 1–5 已停止支持，现有模型及系统的补全辅助函数不构成旧文件兼容承诺。

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

`tools/replay_production.py` 是可复用的经济、交换、炼器与阵法回放工具。三个固定种子共 78 个检查点比较完整返回数据和存档摘要，包括随机数状态与历史；同时冻结时间和实例 ID。先在修改前生成基线，再在修改后比较，数值或内容的有意变化需单独审查，不能直接覆盖基线掩盖差异：

```powershell
python tools/replay_production.py --output build/production-before.json
# 完成待验证的改动后运行：
python tools/replay_production.py --output build/production-after.json --compare build/production-before.json
```

经济／交换会、炼器与阵法组合阶段共核对 352 个回放检查点，原方法签名、随机数与保存顺序保持一致。全量 1743 项测试及浏览器冒烟通过。扩展加载测试通过清理钩子恢复其修改的类级报告和文档绑定，避免将临时 DLC 加载状态带入后续游戏测试。

`tests/test_module_dependencies.py` 检查上述导入边界、上述系统算法的真实命名空间与契约完整性，并验证无引擎调用、资源和配置替换、人物交往注入及旧路径兼容导出。

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
