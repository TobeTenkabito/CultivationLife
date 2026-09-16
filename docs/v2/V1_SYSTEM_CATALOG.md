# V1系统与迁移边界目录

本目录记录V1当前的主要权威数据、生命周期依赖和V2目标边界。它用于确定迁移顺序，不代表V2已经实现对应领域。

| 领域 | V1主要实现 | 当前权威状态 | 关键外部依赖 | V2目标边界 |
|---|---|---|---|---|
| 角色生命 | `models.py`、`rules.py`、`engine.py` | `Player`的年龄、寿命、生死、HP/MP | 时间、境界、鬼修、夺舍、战斗 | Character实体的Life/Body组件；年龄由世界时钟推导 |
| 修炼与突破 | `engine.py`、`rules.py`、`demonic_system.py` | `Player`境界、层数、机缘、功法和突破标记 | 时间、物品、天劫、世界路线、流派 | Cultivation领域；突破作为命令和状态机 |
| 世界与地图 | `map_system.py`、`map_runtime.py`、`engine.py` | `player.world/location_id`及地图内容 | 飞升、旅行、市场、消息、势力、NPC | World领域；临时移动和永久迁界分别建模 |
| 时间 | `engine.advance`、`map_runtime.py`及各系统特例 | `Player.age`和多个系统自己的计数器 | 几乎所有领域 | Kernel Clock/Scheduler唯一推进入口 |
| NPC | `npc_system.py`、`world_state.py`、`models.py` | 宗门NPC、世界NPC、知名NPC及多个关系快照 | 寿命、关系、势力、战争、战斗 | 单一EntityStore；人物事实不复制 |
| 人际关系 | `engine.py`、`concubine_system.py` | master、disciples、friends、companion、concubines等不同容器 | NPC、飞升、组队、势力、事件 | RelationStore，以实体ID和有类型的关系边保存 |
| 势力与家族 | `engine.py`、`models.py`、`world_state.py` | SectState、family及Player全局身份字段 | NPC、世界、外交、战争、贡献、控制权 | Faction领域；成员、职位、贡献全部带faction_id |
| 战争 | `war_system.py` | `GameState.wars`字典列表 | 势力、NPC、战斗、时间、世界可见性 | War领域聚合；通过公开势力和战斗端口协作 |
| 内政与客卿 | `intrigue_system.py` | `GameState.intrigue_state` | 势力、NPC、时间、消息 | DLC模块状态；订阅时间和势力事件 |
| 经济与市场 | `economy_system.py`、`engine.py` | 市场字段、auction_state、玩家行囊和灵石 | 位置、世界、时间、NPC、飞升 | Economy领域；报价、冻结资产和拍卖均为实体/账本 |
| 灵田与炼丹 | `economy_system.py`、`Player.spirit_field` | 玩家内嵌字典和物品实例 | 时间、百艺、市场、物品 | Economy/Crafting子域；开垦为瞬时命令，生长由调度器驱动 |
| 战斗 | `combat_system.py`、`engine.py` | Player、NPC快照及last_combat_report | 功法、装备、阵法、队伍、傀儡、战争 | Combat领域服务；输入战斗快照，输出领域事件 |
| 俘虏与傀儡 | `demonic_system.py`、`Player`列表 | prisoners、puppets、foreign_souls | NPC、神识、战斗、时间、飞升 | 有类型的实体关系/状态，不保存人物副本 |
| 炼器与阵法 | `crafting_system.py`、`formation_system.py` | Player内嵌材料、成品、阵图和绑定列表 | 物品、位置、战斗 | Crafting/Formation模块，只通过物品实体ID协作 |
| 鬼修与轮回 | `ghost_system.py`、`possession_system.py` | 大量Player鬼修字段及GameState游魂状态 | 生命、身体、时间、NPC、世界 | DLC模块；身体与灵魂拆为实体/组件，不替换整个Player |
| 妖修血脉 | `monster_bloodline_system.py`及相关规则文件 | Player血脉、进化、适应和自定义谱系字段 | 修炼、战斗、世界、寿命 | DLC组件和注册式进化命令 |
| 天庭 | `heavenly_court_system.py` | `GameState.heavenly_court` | 世界、势力、选举、时间、消息 | DLC模块；选举使用交互队列而非全局事件槽 |
| 本命法宝 | `natal_artifact_system.py` | `GameState.natal_artifact`及Player加成字段 | 修炼、战斗、时间 | DLC实体/组件，派生属性由查询计算 |
| 普通事件 | `event_repository.py`、`engine._effect` | `pending_event`和字典效果DSL | 所有Player/GameState字段 | Story领域；事实事件、交互事件、效果命令分离 |
| 消息与历史 | 各系统直接追加`game.history` | HistoryRecord及手写tags | 世界、势力、debug模式 | 统一History投影服务，作用域为必填类型 |
| 存档 | `storage.py`及`engine._load` | V1 JSON快照和集中式兼容修正 | 所有系统 | SQLite快照、事件日志、核心与模块独立迁移版本 |
| HTTP与界面 | `server.py`、`web/app.js` | 巨型操作分派和前端重复权限判断 | 所有公开系统 | 命令注册表、查询投影、后端能力列表、TypeScript客户端 |

## 必须先迁移的依赖骨架

```text
Clock / Scheduler / EntityStore
             ↓
Character ─ Cultivation ─ World
    ↓             ↓          ↓
Relations      Combat      Faction
    └─────────────┴──────────┘
                 ↓
        Economy / Story / DLC
```

人物、修炼、世界、关系和势力迁移期间，DLC只能等待这些公开端口稳定，不能先复制V1字段进入V2世界状态。

## 迁移判定

一个领域只有满足以下条件才算完成迁移：

1. V1可观察规则已有对应规格或明确记录为废弃；
2. 状态具有单一所有者，不复制其他领域的权威数据；
3. 所有命令、事件、时间任务和投影都有稳定类型；
4. 模块不直接写入其他领域内部状态；
5. 具备单元测试、不变量测试、存档往返测试和失败原子性测试；
6. 已加入后续V1/V2行为对照矩阵。
