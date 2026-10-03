# 系统目录与兼容边界

经济、神机、内政三个系统均采用显式依赖的普通函数，原动态装配工具 `_assembly.py` 已删除。外部仍通过原来的 `*_system.py` 模块导入原类及模块级辅助函数。

## 已拆分的系统

| 目录 | 文件与职责 |
| --- | --- |
| `economy/` | `market.py` 坊市与通用价格；`spirit_fields.py` 灵田；`arts.py` 技艺经验与炼丹；`auctions.py` 拍卖；`private_trade.py` 私下交易；`black_market.py` 黑市购买与出售；`treasure.py` 探宝 |
| `tianji/` | `generation.py` 神机生成；`state.py` 状态补全与名称迁移；`intelligence.py` 情报与交互；`forging.py` 材料、货架与炼制；`npcs.py` NPC 持有与掉落；`presentation.py` 展示与调试信息 |
| `intrigue/` | `state.py` 内政状态与人物性格；`governance.py` 职位、权限与人事；`guests.py` 客卿；`recruitment.py` 招募；`resolutions.py` 议案；`runtime.py` 监禁同步与周期更新；`presentation.py` 展示 |

## 原模块继续负责兼容

- `economy_system.py` 保留 `EconomySystemMixin(ExchangeSystemMixin)`，以及含延迟相对导入的拍卖跨界取消、黑市搜索方法。
- `tianji_system.py` 保留 `TianjiSystemMixin`、生成版本、常量和全部模块级辅助函数。
- `intrigue_system.py` 保留 `IntrigueSystemMixin`、常量、模块级辅助函数，以及默认参数引用 `PLAYER_ID` 的权限判断方法。

没有修改 `GameEngine` 的继承顺序，也没有为拆出的文件增加 Mixin 基类。其他玩法的继承关系保持原样。

## 经济系统的显式依赖

`economy/` 的 47 个算法是可独立调用的普通模块函数，使用各自模块的真实全局命名空间。`dependencies.py` 按七组职责声明所需回调和资源接口；`wiring.py` 逐项连接依赖，算法不导入装配模块、兼容入口或引擎。

`EconomySystemMixin` 保留原签名的转发方法和 13 个静态辅助函数。`_economy_dependencies` 首次使用时缓存契约，回调及资源 getter 在调用时查找当前对象，因此构造后替换方法或存档服务仍然生效。静态配置辅助函数仍使用入口模块的 `WORLD_SYSTEMS`，兼容既有配置替换；算法直接导入的其他符号应在实际定义或使用模块维护，不再依赖入口的隐式全局变量。

## 神机与内政的显式依赖

神机原有的 32 个动态装配方法改为 27 个普通函数与 5 个入口静态辅助方法；内政原有的 41 个改为 36 个普通函数与 5 个入口静态辅助方法。原生的 `_intrigue_has_decision_authority` 仍留在入口，保留 `PLAYER_ID` 默认参数。所有转发方法都有明确签名，不在运行时创建函数或安装方法。

两个目录各自提供 `dependencies.py` 与 `wiring.py`，分别按六组、七组职责列出并连接协作能力。算法可使用独立的契约实例调用，不接收整个引擎，也不导入入口或装配模块。

入口首次使用时缓存契约；回调、资源及兼容常量 getter 均在调用时解析。`tianji_config`、`tianji_content_available`、`intrigue_rules`、稳定随机流和描述辅助函数仍从原入口显式注入，构造契约后替换配置辅助函数、引擎方法或存档服务仍然生效。已声明的常量由具名 getter 提供，不使用任意属性代理。

算法使用自身模块的实际运行时导入。新增依赖必须添加到契约和对应构建函数；算法直接使用的规则符号从定义模块导入，不能再借用入口的全局命名空间。函数内相对导入按算法所在包解析，内政招募与迁址使用 `..combat.npc_lifecycle`。

## 跨模块依赖边界

- `npc_contacts.act` 接收 `NpcContactDependencies`，师徒操作由 `engine/composition/contacts.py` 注入，不再反向导入引擎动作实现。
- `system/combat_adapter.py` 为引擎试炼和修罗王庭共用的战斗适配层，位于纯战斗规则目录 `combat/` 之外；旧 `engine/combat_capabilities.py` 仅兼容导出。
- 存档、地图、成就接口定义在 `cultivation_life/ports.py`，旧 `engine/ports.py` 保留兼容导出。
- 道统随机流定义在 `doctrine/randomness.py`，商盟委托种类定义在 `merchant_definitions.py`，原入口继续导出同一符号，避免消费方互相导入。
- `combat_rule_schema.py` 统一定义新版战斗规则常量和校验，战斗执行器与旧血脉规则均依赖它；旧 `combat_rule_engine.validate_rule` 保留同一函数的兼容导出。
- `tutorial_mentorship.py` 负责师缘条件、状态和操作；教程入口与操作教学共同调用它。师缘操作不再为了判定拜师条件调用完整教学展示。旧教程入口保留 `blocked_reason`、`mentor_action` 与 `MENTOR_STEP` 导出。

新增系统代码不得运行时导入 `engine/`；旧修罗适配器 `asura_system.py` 是保留的兼容例外。依赖检查包含函数内延迟导入，忽略仅供类型检查的导入，不模拟动态导入或 Python 隐式执行的包初始化。战斗规则与血脉、新手引导以及九模块战斗适配循环均已拆开；当前仅剩模型/规则/内容注册等 22 个核心模块组成的一组循环，不能把检查通过理解为全项目无循环。

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

本轮整段移动方法，保持方法体、调用顺序、随机数消费顺序、存档保存时机与展示副作用。不会因方法名带有 `public`、`ensure` 或 `state` 就改变其行为。

验证采用迁移前后方法源码与语法树对比、运行时代码与全局命名空间比对、继承关系比对，并运行完整测试：

```powershell
python tools/check_module_dependencies.py
python -m pytest -q tests/test_module_dependencies.py tests/test_system_layout.py
python -m pytest -q
```

`tests/test_system_layout.py` 覆盖原模块配置替换、辅助函数替换和拍卖取消中的延迟导入兼容性。

`tests/test_module_dependencies.py` 检查上述导入边界、三个系统算法的真实命名空间与契约完整性，并验证无引擎调用、资源和配置替换、人物交往注入及旧路径兼容导出。

神机与内政迁移另行核对了 63 个算法的方法体、10 个静态辅助方法和 797 个引擎方法签名。两个固定种子的 90 个回放检查点比较完整返回数据与存档，覆盖新手教学、师缘、神机生成/情报/炼制/激活，以及内政任职、监禁、议案和弟子招募。

战斗循环拆解核对了 25 个迁移函数的完整语法树和 797 个引擎方法签名。七种世界/DLC 配置的 25 个回放检查点覆盖展示、实战、王庭评估及政务推进，比较完整返回值、角色状态和战斗随机数状态。依赖测试禁止这 13 个原模块及共用模块重新进入循环，并验证旧路径导出、下界封存元力与机构只读查询。
