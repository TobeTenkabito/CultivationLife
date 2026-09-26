# 系统目录与兼容边界

经济、神机、内政三个系统按职责拆分了方法源码。其他系统维持原布局，外部仍通过原来的 `*_system.py` 模块导入原类及模块级函数。

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

## 方法装配

`_assembly.py` 将方法容器中的函数挂回原系统类，使用该原模块传入的 `globals()` 作为执行命名空间，并保留描述符、参数默认值、注解和函数元数据。

因此，对 `cultivation_life.system.economy_system.WORLD_SYSTEMS` 等原模块符号的替换继续生效。系统方法不会被绑定到 `cultivation_life.engine` 的命名空间。

子目录中的类只存放方法源码，不能独立实例化使用。其依赖通过 `TYPE_CHECKING` 声明，以避免组件在导入时反向加载原模块；实际调用必须经过原系统类。方法默认值若需要运行时求值，必须明确保证初始化环境一致；本轮将唯一引用模块常量默认值的方法留在原模块。

原模块的导入为移出的方法提供运行时符号，即使原文件中已没有直接调用，也不能当作未使用导入删除。模块级函数、常量和已有缓存保持原位置与对象共享方式。

## 行为保持约束

本轮整段移动方法，保持方法体、调用顺序、随机数消费顺序、存档保存时机与展示副作用。不会因方法名带有 `public`、`ensure` 或 `state` 就改变其行为。

验证采用迁移前后方法源码与语法树对比、运行时代码与全局命名空间比对、继承关系比对，并运行完整测试：

```powershell
python -m pytest -q
```

`tests/test_system_layout.py` 覆盖原模块配置替换、辅助函数替换和拍卖取消中的延迟导入兼容性。
