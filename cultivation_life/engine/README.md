# 引擎文件布局

本目录按职责组织现有 `GameEngine` 的方法。外部调用仍使用：

```python
from cultivation_life.engine import GameEngine
```

本次为第一轮文件整理：整段移动方法并调整组件导入、装配清单，不改变玩法规则、方法签名、返回数据、存档格式或结算顺序。

## 目录职责

| 位置 | 职责 |
| --- | --- |
| `__init__.py` | `GameEngine` 定义、依赖初始化、公共查询与设置入口、运行时组件装配 |
| `actions/cultivation.py` | 秘术管理及玩家主动突破操作 |
| `actions/encounters.py` | 监禁、悬赏、拦截和主动战斗行动 |
| `actions/factions.py` | 创建势力、外交提议、人员调动、退出与继承 |
| `actions/inventory.py` | 物品、坊市购买、功法和变身材料操作 |
| `actions/relationships.py` | 师徒、道侣、好友和队伍操作 |
| `actions/world_travel.py` | 永久飞升、跨界、随行人员和下界身份清理 |
| `orchestration/session.py` | 创建游戏 |
| `orchestration/advancement.py` | 行动推进、年度收益、行动单位结算与行动记录 |
| `events/choices.py` | 事件选择与后续事件排队 |
| `events/encounters.py` | 遭遇目标生成、缓存及世界剧情触发 |
| `events/effects.py` | 原有 `_effect()` 效果解释器，保持完整方法体 |
| `progression/breakthroughs.py` | 突破判定、概率、消耗与结果结算 |
| `progression/trials.py` | 突破试炼、飞升试炼、仙灵力转换与周期雷劫 |
| `world/npcs.py` | NPC 查询、生成、修炼、寿元、招募及修为感知 |
| `world/relationships.py` | 关系同步、好感、复仇、家庭年度更新及队伍同步 |
| `world/factions.py` | 势力年度更新、外交、战争与势力强度 |
| `world/hostility.py` | 通缉、敌意、追捕、和解与悬赏推进 |
| `presentation/character.py` | 修炼、人物关系、队伍和通缉信息展示 |
| `presentation/world.py` | 世界 NPC、排名、种族与跨界路线展示 |
| `presentation/factions.py` | 家庭、内政、势力、外交和人员调动展示 |

原有文件保留较集中的职责：

- `engine_world_runtime.py`：世界初始数据、兼容补全、境界限制和历史压缩。
- `engine_combat_runtime.py`：战斗组织、击杀后果、死亡和状态快照。
- `engine_event_runtime.py`：事件筛选、实例化、条件判断和剧情战斗检查。
- `engine_presentation.py`：组装完整返回数据以及历史可见性判断。
- `engine_persistence.py`：完整保留现有 `_load()` 流程。
- `engine_constants.py`：现有比较运算表与旧种族映射。

## 第一轮保留的运行机制

`_include_runtime_methods()` 将组件方法挂载到 `GameEngine`，`_runtime_method()` 将函数的全局命名空间绑定到 `cultivation_life.engine`。这两个装配函数及 `GameEngine` 原有的基类顺序保持不变。

因此，子目录中的类仍然是方法容器，不能当作独立服务实例化使用。原有五个运行时组件类也属于内部方法容器；完整调用入口是 `GameEngine`。

入口模块中部分导入的直接调用者已经移到子目录，但这些导入仍提供运行时全局符号。不要将它们当作普通的未使用导入删除。现有针对 `cultivation_life.engine` 符号的替换继续有效。

以下行为原样保留：

- 年度结算与行动单位结算的顺序、随机数消费顺序及状态保存时机。
- `_load()` 中的兼容迁移、状态修复和保存副作用。
- `present()` 及展示辅助方法中的状态维护与成就评估。
- 方法的 `staticmethod`、`classmethod` 描述符、默认值与注解。
- 各玩法方法通过 `self` 调用其他组件和现有 `system/` 模块的方式。

进一步拆解长方法、移除动态绑定或调整这些职责边界属于后续重构，不在本轮范围内。

## 验证

完整测试同时包含 unittest 和 pytest 风格用例，统一执行：

```powershell
python -m pytest -q
```

本轮迁移还对比了原布局与新布局的全部引擎方法语法树，以及 `GameEngine` 的运行时方法、描述符、签名、默认值、注解、全局命名空间和继承顺序。运行时代码对比忽略因文件移动必然改变的源码路径、行号和代码对象限定名，其字节码、常量、名称引用和异常表保持一致。
