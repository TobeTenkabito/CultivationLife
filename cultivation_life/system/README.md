# 系统目录与兼容边界

经济、神机、内政三个系统按职责拆分了方法源码。经济系统进一步改为显式依赖的普通函数；神机、内政暂保留动态装配。外部仍通过原来的 `*_system.py` 模块导入原类及模块级函数。

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

没有修改 `GameEngine` 的继承顺序，也没有为拆出的文件增加 Mixin 基类。战斗、阵法、商盟、鬼修、归墟等其他系统没有参与本轮拆分。

## 经济系统的显式依赖

`economy/` 的 47 个算法是可独立调用的普通模块函数，使用各自模块的真实全局命名空间。`dependencies.py` 按七组职责声明所需回调和资源接口；`wiring.py` 逐项连接依赖，算法不导入装配模块、兼容入口或引擎。

`EconomySystemMixin` 保留原签名的转发方法和 13 个静态辅助函数。`_economy_dependencies` 首次使用时缓存契约，回调及资源 getter 在调用时查找当前对象，因此构造后替换方法或存档服务仍然生效。静态配置辅助函数仍使用入口模块的 `WORLD_SYSTEMS`，兼容既有配置替换；算法直接导入的其他符号应在实际定义或使用模块维护，不再依赖入口的隐式全局变量。

## 神机与内政的方法装配

`_assembly.py` 将方法容器中的函数挂回原系统类，使用该原模块传入的 `globals()` 作为执行命名空间，并保留描述符、参数默认值、注解和函数元数据。

因此，神机与内政原模块符号的替换继续生效。系统方法不会被绑定到 `cultivation_life.engine` 的命名空间。

这两个子目录中的类只存放方法源码，不能独立实例化使用。其依赖通过 `TYPE_CHECKING` 声明，以避免组件在导入时反向加载原模块；实际调用必须经过原系统类。方法默认值若需要运行时求值，必须明确保证初始化环境一致；引用模块常量默认值的方法留在原模块。

神机与内政原模块的导入为移出的方法提供运行时符号，即使原文件中已没有直接调用，也不能当作未使用导入删除。这一约束不再适用于经济系统。

## 跨模块依赖边界

- `npc_contacts.act` 接收 `NpcContactDependencies`，师徒操作由 `engine/composition/contacts.py` 注入，不再反向导入引擎动作实现。
- `system/combat_adapter.py` 为引擎试炼和修罗王庭共用的战斗适配层，位于纯战斗规则目录 `combat/` 之外；旧 `engine/combat_capabilities.py` 仅兼容导出。
- 存档、地图、成就接口定义在 `cultivation_life/ports.py`，旧 `engine/ports.py` 保留兼容导出。
- 道统随机流定义在 `doctrine/randomness.py`，商盟委托种类定义在 `merchant_definitions.py`，原入口继续导出同一符号，避免消费方互相导入。

新增系统代码不得运行时导入 `engine/`；旧修罗适配器 `asura_system.py` 是保留的兼容例外。依赖检查包含函数内延迟导入，忽略仅供类型检查的导入，不模拟动态导入或 Python 隐式执行的包初始化。当前显式导入图仍有四组循环：模型/规则/内容注册等核心模块、战斗适配相关模块，以及战斗规则与血脉、新手引导两个互引组。应逐组拆解，不能把检查通过理解为全项目无循环。

## 行为保持约束

本轮整段移动方法，保持方法体、调用顺序、随机数消费顺序、存档保存时机与展示副作用。不会因方法名带有 `public`、`ensure` 或 `state` 就改变其行为。

验证采用迁移前后方法源码与语法树对比、运行时代码与全局命名空间比对、继承关系比对，并运行完整测试：

```powershell
python tools/check_module_dependencies.py
python -m pytest -q tests/test_module_dependencies.py tests/test_system_layout.py
python -m pytest -q
```

`tests/test_system_layout.py` 覆盖原模块配置替换、辅助函数替换和拍卖取消中的延迟导入兼容性。

`tests/test_module_dependencies.py` 检查上述导入边界、经济算法真实命名空间和契约完整性，并验证无引擎调用、资源替换、人物交往注入和旧路径兼容导出。
