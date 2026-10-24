# 蛇族 DLC 形象与动作

2026-10-23，万妖归宗 DLC1 源码更新至 **4.18.0**；本体仍为3.0.0-alpha.3、存档结构10，不打包。用户授权补齐先前境界动作，并将素材放入 DLC、更新 DLC 版本。元婴六版基础立绘尚缺，本轮仅接入已有7套兽形及4套合体男女形象。

## 资源与阶段

正式资源位于 `dlc/monster-bloodlines/assets/visual/serpent`。11套静态形象，各含头像128×128、全身256×288、缩略128×144，共33张；11套战斗图集，99个绘制关键姿态、70组有限关键帧动画。7套兽形各六类动作：待机、吐息进攻、受击、防御、承击、倒地；4套合体各七类，增加施域。时间采样不等于逐帧高帧率手绘。兽形待机保持完整原姿态，不套人形骨架或呼吸变形。

| 阶段 | 采用方式 |
| --- | --- |
| 凡境、练气、筑基 | 复用灵蛇，男女共用；保持真实血脉节点不变 |
| 结丹 | 大妖玄蛇、岩甲巨蟒、沧渊玄蛇、青蛟、雷虺、腾蛇分别选图 |
| 元婴、化神、炼虚 | 尚缺专绘，保留既有回退，不提前展示合体人形 |
| 合体 | 太古祖龙、寰宇蛇祖各男女，完整人身且保留实体族征 |
| 大乘 | 万界龙皇沿祖龙，无始天蛇沿蛇祖，性别分别对应 |

源选择：龙男全身与头像均使用额颞双角修正版v2；龙女合体动作使用分离底排人物的v2；沧渊玄蛇静态使用单尾修正版v2。其余已列明原稿保持。`provenance.json`记录授权、来源与SHA256，`registry.json`登记45项DLC专属资源（33静态、11图集、1动作清单）。既有狐族成品文件不重新导出。

离线导出入口为 `python scripts/prepare_monster_serpent_assets.py`，机械分图、最近邻缩放并保留原始多级透明。龙男修正版全身与头像之间的淡透明连接沿最低透明间隙分离，要求接缝不切不透明身体；不修改原稿。运行游戏不读取design，设计源只用于离线重导。

## 运行边界

`monster_visuals.monster_appearance`只读已加载DLC、真实血脉节点和性别，狐族仍沿原规则，蛇族通过明确节点映射选择。`fox_appearance`兼容入口保留。封印下界的显露境界不改图；未知节点、未绘阶段、其他种族、宿身／附身与变化形态沿原回退。`public_player.visual_actor`为临时投影，战前形象沿既有战报快照保存；没有新增Player/GameState持久字段。

静态头像、详情和宗门自己头像沿现有VisualAssets入口。战报按权威快照加载蛇族DLC动作清单，与本体图集按同一回放接口合并；使用真实命中时序和结果，不增加技能、能力、伤害、时间、移动或游戏RNG调用。低阶清单不含邻域动作；展示能力不授予邻域玩法资格。

关闭DLC后，公开目录过滤和HTTP权限检查阻止专属资源，既有专属战报回退文字。新版界面关闭不加载本批图片。缓存按资源URL与哈希选择，不把狐族清单用于蛇族。

## 专项验证

- `python -m pytest tests/test_monster_serpent_visuals.py tests/test_monster_fox_visuals.py tests/test_visual_release.py tests/test_combat_replay.py -q`
- `python tests/browser_monster_serpent_visuals.py`：真实创建／加载、11套头像与详情、实际结算后的战报、合体施域、窄屏、重播不写档、关闭DLC回退。
- `python tests/browser_monster_fox_visuals.py` 与 `python tests/browser_combat_replay.py`：共用回放入口与旧资产回归。
- 三项仓库门禁：跨界合同、模块依赖、文档检查。

证据在 `build/monster-serpent-visuals/`。按用户要求不做全仓回归，不生成EXE、APK或发行包。已有运行进程需重启以加载更新后的代码与DLC目录。
