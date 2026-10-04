# 归墟之潮：九死一生 · 当前实现规格

维护基线：本体 v1.58.0 / DLC 2.6.0，2026-10-04。沿用旧文件名保持引用；早期“两座副本首版计划”已被十一界实现取代，原策划可从 Git 历史查阅。本页以 `dlc/guixu-tide/content/guixu_tide.json` 和 `cultivation_life/system/guixu/` 为依据。

## 副本与配置

当前十一座副本，每座四个常规层与一个秘层，各六十条宝池条目，共六百六十条。每轮从剩余宝池抽取最多六条，已消耗条目不按开关或读档重生。表中周期、预告单位为年，窗口单位为副本天。

| 副本 | 世界 | 入口地图 ID | 周期年 | 提前年 | 开窗天 | 宝池条目 |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 葬海天渊 | `human` | `lancang_sea` | 100 | 10 | 90 | 60 |
| 诸界尾闾 | `spirit` | `mist_sea_isles` | 200 | 20 | 120 | 60 |
| 血河沉渊 | `demon` | `nine_yin_marsh` | 120 | 12 | 42 | 60 |
| 太古葬魔墟 | `true_demon` | `fallen_god_ridge` | 240 | 24 | 56 | 60 |
| 万兽祖涡 | `phantom_underworld` | `phantom_tide` | 180 | 18 | 49 | 60 |
| 黄泉无底狱 | `hell` | `ninefold_prison` | 210 | 21 | 49 | 60 |
| 妖祖沉庭 | `monster_realm` | `ancestral_mountain` | 180 | 18 | 49 | 60 |
| 天律沉宫 | `celestial` | `law_sea` | 300 | 24 | 56 | 60 |
| 修罗劫海 | `asura` | `destruction_sea` | 300 | 24 | 56 | 60 |
| 太初龙渊 | `nether` | `dragon_origin_sea` | 300 | 18 | 49 | 60 |
| 无时轮回墟 | `reincarnation` | `timeless_grave` | 300 | 21 | 49 | 60 |

可入最高修为 `max_entry_rank` 与突破传出线 `eject_rank` 分开配置；不可将一个上限同时用于两种判定。层级行程、四气、修士数量和奖品由同一 JSON 配置，玩家面板读取当前值。

## 时间、夺宝与退出

生命周期包括预告、开启、闭合及下次开启。开放期使用副本天数预算，探索不按每次点击推进世界年；被困后的苦修才恢复按实际年数进行角色和世界结算。普通行动可被潮期日历中断，不能把归墟时间直接替换为普通行动单位。

当前基础用时：探宝两天，战斗、交涉、事件、休息各一天；跨层用时由层级配置。窗口耗尽会进入被困状态，归返、突破传出、秘层与脱困按各自条件处理。关闭 DLC 时，未结束会话安全送回入口并清除会话，既有周期与宝池保留；不能把“冻结”理解为继续困住玩家。

参与者按副本周期生成，宝物拥有者与到期分配记录属于真实会话状态。NPC 会组队、争夺和交涉；同境索宝须结队，拒绝勒索按防御战结算。返回、关闭与结算之前须处理已经到期的宝物归属，不能提前移除导致复制或丢奖。

临时队友、招募资格、分宝、关系保护与背叛沿实际流程处理；不能将临时队员等同永久队伍关系。宝池耗尽后的静修场不重刷完整夺宝奖池。通用物品与功法定义由本体提供，特殊剧情和副本配置由 DLC 控制，关闭 DLC 不删除本体地图。

## 存档与职责

`GameState.guixu_state` 保存 `cycles`、`entered_cycles`、`external_treasures` 和 `player_session`。容器自身 `schema_version=1` 是归墟子协议，当前角色存档结构为 8，二者不能混用。

| 模块 | 职责 |
| --- | --- |
| `system/guixu/state.py` | 周期及会话补全、扩展关闭后的退出 |
| `system/guixu/calendar.py` | 预告、开启、到期与闭合 |
| `system/guixu/actions.py` | 进入、移动、探索、休息、归返与被困行动 |
| `system/guixu/npcs.py`、`encounters.py` | 参与者、临时团队、交涉与遭遇 |
| `system/guixu/rewards.py`、`presentation.py` | 奖品发放、归属与界面投影 |
| `system/guixu/dependencies.py`、`wiring.py` | 七组冻结依赖及明确装配 |
| `system/guixu_system.py` | 保留旧调用方的薄适配器与静态辅助入口 |

上述 Python 路径相对 `cultivation_life/`。GameEngine 已不继承归墟 Mixin，算法不接收完整引擎。副本日历、随机数、历史写入与奖励顺序必须继续保持；`ensure` 与部分展示仍可能补全状态，不能当作纯查询复制调用。

## 验证与继续开发

```powershell
python -m pytest -q tests/test_guixu_tide.py tests/test_guixu_companions.py tests/test_expedition_dependencies.py
python tools/check_module_dependencies.py
python tools/replay_expeditions.py --output build/expeditions-current.json
```

回放同时覆盖归墟与战争，比较改动前后须先保留同一结构的基线；不能拿不同结构的原始 JSON 哈希直接判为行为回归。本轮执行记录见 [项目诊断](project-diagnosis.md)。

当前没有多人联机或通用副本编辑器。未来扩充地点、层级和宝池先走内容校验；新计时或人物生命周期须单独设计并增加闭合、死亡、DLC 关闭、中断续接和奖励唯一性回归。
