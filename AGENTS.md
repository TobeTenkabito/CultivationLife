# 开发约定

- 修改前阅读相关领域文档。凡涉及界面、人物移动、远程行为、空间实例、跨界情报，必须先读 [跨界开发规范](docs/world-transition-development.md) 和 [当前跨界审计](docs/world-transition-audit.md)。
- 新玩法必须复用已有权威状态与结算入口。禁止直接改写玩家 `world` 来实现移动；禁止复制 NPC、物资、资源池来模拟迁移。
- 跨界方向、移动方式、参与者、地点、实例、状态归属、时间和代价必须分别明确。普通规则不得被剧情、DLC、Debug 或 UI 分支绕过。例外须先登记具体理由、责任入口、状态差异和针对性测试。
- 修改 `Player` / `GameState` 持久字段时，同步更新 `docs/world-transition-state-contract.json` 的归属分类；禁止将未审阅字段自动归入默认保留。
- 至少运行 `python tools/check_world_transition_contract.py`、`python tools/check_module_dependencies.py`、`python tools/check_documentation.py` 及改动领域测试。跨界改动还需运行 `tests/test_world_transition_system.py`、`tests/test_spatial_talismans.py`、`tests/test_release_211.py`。
- 事件加载、选项提交及旧交互按钮改动，还需运行 `tests/test_release_212.py` 和 `python tests/browser_events_212.py`。必须用真实加载／提交与页面点击验证，不能仅调用内部结算函数；覆盖过期页面恢复、后续奖励、忙碌状态解除及仍应禁用的选项。
- 发布前完成发行脚本要求的回归、浏览器、Windows EXE 与签名 Android 原生验收；验收证据必须对应最终代码。界面动作分组使用现有导航，避免堆叠按钮。
- v2.6.0 按用户明确要求仅支持结构 10；旧结构 1–9 不兼容，不映射、不转换，不把未知界面默认为人界。修复用户存档必须先备份，并限定到明确授权字段。
