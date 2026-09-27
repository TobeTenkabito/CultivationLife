# 统一跨界系统（v1.41.0）

界面等级来自 `content/world.json` 的 `systems.world_profiles`。方向只表达地理关系：目标等级更高为飞升、相同为平移、更低为下界。人界到魔界属于平移，但依然使用原本魔道进阶流程与门槛。

`system/world_transition_system.py` 不导入引擎、商盟或 DLC。`WorldTransitionRequest` 不接受客户端提供方向；纯函数 `plan_world_transition` 校验路线、开放状态、落点和封印，返回计划，不更改存档、不消耗随机数。`apply_world_transition` 检查计划是否过期，统一取消原界拍卖、处理迁居和封印、提交同行人员、写入世界与落点、清空失效坊市。

## 路线与权限

- `systems.world_transition_routes` 显式登记每一条路线，标识来源、目的地、模式和开关。仅 `generic_cross_world` 为真的封印下界路线向普通跨界入口开放；不能用它绕过劫关或商盟费用。
- `PROGRESSION`：永久迁居，调用已有宗门交接和社会关系清理。空间节点、魔道进阶、仙界与修罗劫关、妖修幽冥祖路分别保留自身资格判定。
- `SEALED_DESCENT` / `SEALED_RETURN`：临时往返，不重做永久迁居清理。返回路线只来自当前封印，不公开反向通用飞升路线。
- `PASSAGE`：原商盟身份、总部地点、任务状态、通道范围和费用照常校验。商盟的旧访客封印保留原真实道果，不叠加封印；既有封印可由商盟通道恢复。
- `STORY`：目前只登记撤销旧商盟路线后的免费护送，未开放轮回界或其他新通道。

界面法则使用 `cultivation_ceiling`，与 `npc_realm_cap` 分离。一级界面压制至化神初期三层，二级至大乘九层，三级不设来访压制。妖界旧商盟访客的特殊上限使用单独的 `passage_ceiling`。旧内容缺少新字段时仍可读取原 `world_travel` 压制配置。

封印同时记录新字段 `return_world`、`suppressed_world` 和旧字段 `upper_world`、`lower_world`，兼容其他既有读者。最早缺少上下界字段的封印按灵界—人界处理。返界按当时生命、法力比例复原，恢复原寿元和离界时剩余的雷劫时间。

## 随机顺序与事务边界

永久跨界的同行抽签先形成 `EntourageManifest`，抽签只修改影子状态；公共提交才移动真实 NPC 并更新道侣、道友记录。旧空间节点与九重劫关不同的资格条件、抽签顺序保留。

坊市失效在提交时统一处理。为了保持天庭初始化、寻觅祖师和事件效果的随机顺序，实际生成仍在原行动结束处由 `finish_world_transition` 调用市场适配器；不提前抽取坊市随机数。商盟行动补上了抵达后的即时坊市结算。该延后结算只存在于单次引擎操作内部，没有新增外部执行 API。

`tests/test_world_transition_system.py` 验证所有往返路线、纯规划、旧封印、资源比例、拒绝未授权路线、失效计划、数据校验和玩家世界写入边界。`scripts/probe_transition_rng.py` 可分别运行于旧发布树与新树：12 个固定场景比较随机状态、市场内容、历史事件和同行结果；v1.40.0 基准保存在 `tests/fixtures/transition_rng_1400.json`。

## 后续交付范围

本次同步 Windows、六套独立主题及 Android 12。此后用户未另行指定时，只更新 Windows 端并默认适配 A；B–F 与安卓暂停同步。保留其独立布局，不能用 A 的换色模板替换。
