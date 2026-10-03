# 新手百科维护说明

> 维护基线：本体 v1.57.0 开发源码，2026-10-04。存档结构 8，支持 6→7→8；文中“旧档补全”仅适用于允许加载的结构。文件名保留历史编号以维持链接；历史采样不是本轮实测。

玩家入口：设置 → 新手百科与修行指南。百科是查阅资料，32 步操作教程仍单独运行。旧版十课数据保留，保证旧教学概念与阅读进度不被误当成新增百科的章节序号。

`web/handbook-content.js` 从入门说明组装完整百科，`web/tutorial.js` 负责检索、分类、表格和章节展开。`/api/config` 的 `extensions[].status === loaded` 是启用依据，不能改用安装目录是否存在、`enabled` 或 `next_enabled`。后两者不能代表本次实际运行的玩法。配置、待重启提示与当前角色的解锁资格共同决定章节。修罗专属说明须满足魔修、修罗界及修罗境门槛；切换角色时重新核验，不能仅凭 DLC 已加载显示高阶攻略。百科不进入年度结算。

## 核对代码来源

| 说明 | 当前依据 |
| --- | --- |
| 世界等级、普通下界压制、妖界通道例外、时间单位 | `content/world.json` 的 `world_profiles`、`world_transition_routes`、`time_units` |
| 人界各道途目的地 | `engine/world/npcs.py::_ascension_destination`、`engine/__init__.py::_ascension_destination` |
| 魔界通道门槛、九重飞升、离界关系清理 | `engine/actions/world_travel.py`、`system/demonic_system.py` |
| 三关钥匙、85% 气血、1.40 战力倍率 | `content/story_chain_events.json` 的三个 `EVT_SPIRIT_CROSSING`；`engine/events/effects.py` 的属性判定 |
| 血脉启停与大乘妖修祖路 | `engine/progression/breakthroughs.py::_manual_breakthrough_kind`、`system/monster_bloodline_system.py` |
| 鬼修本体上行与 DLC 魂蚀 | `system/realm_ascension.py`、`system/ghost/progression.py`、`system/ghost_resources.py` |
| 佛修分流、业力与愿力 | `system/buddhist/assembly.py`、`system/buddhist_system.py`、`system/buddhist_wish.py`、`dlc/buddhist-dharma/content/buddhist_way.json` |
| 商盟范围、晋升、通道、情报与成品 | `system/merchant_system.py`、`system/merchant_execution_system.py`、`system/merchant_commission_system.py` |
| 家族灌顶、内政与同界收益 | `system/family_system.py`、`system/intrigue/governance.py` |
| 仙界进阶与材料购买 | `system/immortal_cultivation.py`、`system/immortal_body_system.py`、`system/doctrine/`、`content/doctrines.json` |
| 归墟索宝与临时队友 | `system/guixu/` |

表中的 Python 路径相对 `cultivation_life/`。更新规则后也应核对百科，不能仅按历史 README 或策划案继续写旧版本规则。

特别容易写错：妖界为二级；没有血脉 DLC 时不能宣称已有替代的幽冥祖路；人界到魔界是同级平移；轮回界上行属于本体，主动轮回则是鬼修 DLC；佛修分流比较四气经验而非等级；涅槃只升一层，且不适用于仙境。

## 验收

`scripts/verify_handbook_ui.py` 按八个包动态覆盖 256 种官方 DLC 组合、加载错误、待重启状态，并在六主题、桌面和手机横竖屏检查搜索、分类、排版和只读性。`scripts/verify_tutorial_ui.py` 重新走完整 32 步控件引导，防止百科筛选或控件变化挡住教学。后端兼容测试为 `tests/test_tutorial.py` 和 `tests/test_tutorial_walkthrough.py`。

验收脚本是独立浏览器检查，不由 pytest 自动执行；本轮诊断的实际执行项见 [项目诊断](project-diagnosis.md)。
