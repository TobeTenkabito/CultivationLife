# 项目文档索引

维护基线：**本体 v2.1.1 / 开发源码存档结构 9**，2026-10-07。当前支持 8→9，结构 1–7 停止支持。诸天 M2 已实装四界联系、和平协作、两个异象与人界本地征兆，界面采用独立导航，尚未打包发行，当前发行说明见根目录更新日志。

文档文件名中的历史版本编号用于稳定链接，当前规则看正文。数值校准保留必要的采样条件；更新日志只记录当前发行说明。资料中涉及“旧档”的补全仅适用于允许载入的结构。

## 项目与开发

- [经济 V2 第一轮](economy-v2.md)：本地市场、增长、货架预留、资金去向和后续商队／组织边界。

| 文档 | 用途 |
| --- | --- |
| [项目入口](../README.md) | 当前版本、玩法、启动、测试与构建 |
| [完整诊断](project-diagnosis.md) | 当前架构状态、验证方法及开发边界 |
| [产品与系统规格](修仙人生模拟游戏_GDD_V1.0.md) | 已实现系统、世界、时间、数据归属 |
| [引擎架构](../cultivation_life/engine/README.md) | 显式依赖、关系、时间与读档阶段 |
| [Debug 开发规范与控制台](debug-development.md) | 开发范式、隔离会话、CLI/MCP Agent 工具、指令、快照与复现包 |
| [Debug 本体覆盖清单](debug-base-coverage.md) | 通用功能操作链、全部 137 个角色入口映射与验证范围 |
| [Debug DLC 指令清单](debug-dlc-coverage.md) | 剩余 17 个入口、内容门禁、立祖预览、结构化参数与使用示例 |
| [系统边界](../cultivation_life/system/README.md) | 各算法目录、兼容入口与反向依赖约束 |
| [Android](../android/README.md) | 构建、签名、设备和发布证明 |
| [主题维护](../web/themes/README.md) | 四主题与共享控件 |
| [扩展包](../dlc/README.md)、[MOD](../mods/README.md) | 清单、合并与启停 |
| [更新日志](../CHANGELOG.md) | 当前发行说明与兼容信息 |

## 规则与专题

- [人物生存、拘禁与名册契约](npc-custody.md)
- [存档码格式与结构迁移](save-code-format.md)
- [诸天实装进度：十一界事务、四界往来与局部战争](heavens-implementation.md)
- [空间裂缝、符箓与界面排斥](spatial-talismans.md)
- [统一跨界流程](world-transitions.md)
- [战斗内核与资源](combat-domains.md)
- [邻域效果与主战资格](combat-effects.md)
- [战斗语义 V3](combat-semantics.md)
- [仙界道统与养成](doctrines.md)
- [仙窍、灵域与交通](immortal-1470.md)
- [压制与战斗预案](immortal-1471.md)
- [仙境劫战](immortal-1490.md)
- [金光、瑶池与凭证](immortal-1510.md)
- [仙脉费用与校准方法](immortal-vein-balance.md)
- [合练与三尸规则](three-corpses-1512.md)
- [剧情战斗校准方法（含剧透）](luo-spirit-calibration.md)
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

## 待实现策划

- [诸天系统策划案](诸天系统与跨界战争_策划案_V0.1.md)：当前 V0.5 开工基线，保留宇宙整体与有限认知定位，确定首轮顺序、境界参与初值、法则天海分支成本、最小数据与接口、年度中断、短活动结算、事务恢复及分阶段验收；M0、M1 及 M2 的四界求证、和平协作、镜律场域与因果遗址已落地，人界低阶征兆及当地对照已开放，四界个人访学往返已开放，现有合作 NPC 的回访与实际返乡已开放，四界同道单件阵材的真实运输与交货已开放，四界真实居民的有限接引与长期迁居已开放，自主人口迁徙、通用商贸货运与跨界战争尚未开放，文件名保留以维持链接。

## 维护约定

数值依据优先读取 JSON 配置和规则实现，存档结构依据 `save_schema.py`，本体版本依据 `version.py`，扩展版本依据各自清单。修改当前行为时同步相关专题及百科；不要把历史版本号统一替换成当前版本。新专题需进入本索引。

运行 `python tools/check_documentation.py` 检查本地 Markdown 链接、索引覆盖及关键版本声明。该工具不联网验证外部链接，不保证自然语言规则全部正确；新数值与迁移约定仍需人工核对代码。

- [跨界开发规范](world-transition-development.md)
- [v2.1.1 跨界全量审计](world-transition-audit.md)
- [逐字段归属合同](world-transition-state-contract.json)
