# 项目文档索引

维护基线：**本体 v1.57.0 开发源码 / 存档结构 8**，2026-10-04。当前支持 6→7→8，结构 1–5 停止支持。本轮双端发布记录见根目录更新日志；旧诊断数字保留其采样背景。

文档文件名中的历史版本编号用于稳定链接，当前规则看正文。历史数值试验注明采样条件，不冒充本轮复测；CHANGELOG 和 dist 中的副本保留其发行时间背景。资料中涉及“旧档”的补全仅适用于允许载入的结构。

## 项目与开发

| 文档 | 用途 |
| --- | --- |
| [项目入口](../README.md) | 当前版本、玩法、启动、测试与构建 |
| [完整诊断](project-diagnosis.md) | 本轮检查、修复及仍保留的风险 |
| [产品与系统规格](修仙人生模拟游戏_GDD_V1.0.md) | 已实现系统、世界、时间、数据归属 |
| [引擎架构](../cultivation_life/engine/README.md) | 显式依赖、关系、时间与读档阶段 |
| [Debug 开发规范与控制台](debug-development.md) | 开发范式、隔离会话、CLI/MCP Agent 工具、指令、快照与复现包 |
| [系统边界](../cultivation_life/system/README.md) | 各算法目录、兼容入口与反向依赖约束 |
| [Android](../android/README.md) | 构建、签名、设备和发布证明 |
| [主题维护](../web/themes/README.md) | 六主题与共享控件 |
| [扩展包](../dlc/README.md)、[MOD](../mods/README.md) | 清单、合并与启停 |
| [更新日志](../CHANGELOG.md) | 真实发行历史及未发布变更 |

## 规则与专题

- [人物生存、拘禁与名册契约](npc-custody.md)
- [存档码格式与结构迁移](save-code-format.md)
- [统一跨界流程](world-transitions.md)
- [战斗内核与资源](combat-domains.md)
- [邻域效果与主战资格](combat-effects.md)
- [战斗语义 V3](combat-semantics.md)
- [仙界道统与养成](doctrines.md)
- [仙窍、灵域与交通](immortal-1470.md)
- [压制与战斗预案](immortal-1471.md)
- [仙境劫战及历史样本](immortal-1490.md)
- [金光、瑶池与凭证](immortal-1510.md)
- [仙脉费用与历史校准](immortal-vein-balance.md)
- [合练、三尸与历史复测](three-corpses-1512.md)
- [剧情战斗历史校准（含剧透）](luo-spirit-calibration.md)
- [仙界修行、选举与经验](experience-1520.md)
- [机构归属](institutions-1513.md)
- [瑶池经济、议政与人物交往](yaochi-governance-1511.md)
- [三界上境及 DLC 分流](upper-worlds-1500.md)
- [三界本体邻域与机构](upper-voisinages-1522.md)
- [修罗王庭](asura-court-1530.md)
- [教程入口](tutorial-1480.md)
- [操作引导](tutorial-1481.md)
- [百科维护](handbook-1481.md)
- [十一界归墟现行规格](归墟之潮_九死一生_DLC策划案_V0.2.md)

## 维护约定

数值依据优先读取 JSON 配置和规则实现，存档结构依据 `save_schema.py`，本体版本依据 `version.py`，扩展版本依据各自清单。修改当前行为时同步相关专题及百科；不要把历史版本号统一替换成当前版本。新专题需进入本索引。

运行 `python tools/check_documentation.py` 检查本地 Markdown 链接、索引覆盖及关键版本声明。该工具不联网验证外部链接，不保证自然语言规则全部正确；新数值与迁移约定仍需人工核对代码。
