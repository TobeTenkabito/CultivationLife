# 狐族 DLC 形象与动作

2026-10-23，万妖归宗 DLC1 更新至 **4.17.0**，本体仍为 **3.0.0-alpha.3**，存档结构仍为10。用户授权补充兽形动作、接入本批素材并更新 DLC；此次不打包，不声称已发布 alpha.4 安装包。

## 素材与阶段

正式资源在 `dlc/monster-bloodlines/assets/visual/fox`，游戏不读取 design。20套头像128×128、全身256×288、缩略128×144；16套战斗图集以384×288逻辑画布和192/256足底锚点规范化，按内容裁切打包。共144个绘制关键姿态和112组有限关键帧动画：待机、进攻、受击、防御、承击、倒地、施域。时间采样不等同于逐帧手绘；兽形待机保持原姿态，人形复用既有局部呼吸。

| 境界 | 静态形象 | 战斗形象 |
| --- | --- | --- |
| 凡境、练气、筑基 | 保留已采用的五种低阶原稿 | 练气灵狐，男女共用 |
| 结丹 | 玄狐王、月梦灵狐、幼生九尾 | 对应三套四足动作，男女共用 |
| 元婴、化神、炼虚 | 玄狐、月梦、九尾各男女 | 对应元婴六套动作 |
| 合体、大乘 | 三脉各男女；九尾女齐胸襦裙、九尾男白发白须仙翁、月梦男羽扇 | 对应合体六套动作，保留半透明灵尾 |

新增结丹苍山玄狐沿玄狐王外观，月轮司夜狐／织梦灵狐沿月梦外观。未专绘的同脉节点复用美术不合并游戏节点。万相狐君、青丘梦皇、虚天九尾这类历史合流节点优先沿最近的明确血脉历史选图；新的明确分支节点优先于旧历史。历史不足、未知血脉、九阶以上、其它本源、宿身／附身或变化形态回退既有显示。按真实血脉节点对应的阶段选图，不因下界显露境界或所在地变回幼狐。

## 权威入口与资源归属

`monster_visuals.fox_appearance`只读已加载 DLC、真实血脉和历史；`public_player.visual_actor`是临时公开投影，不写入 Player。`combat_identity`在战前将形象写入既有战报视觉快照，战后升阶不改旧战报。浏览、切图和回放不消耗游戏 RNG，不新增技能、移动、时间或伤害。进化与跨界继续沿原结算入口，没有新增持久字段或跨界例外。

头像、详情及宗门自己的头像沿原 VisualAssets/NpcArt 入口。关闭新版界面不加载这些图片；关闭 DLC 后目录过滤和 HTTP 白名单均拒绝专属资源，旧专属战报回退文字。普通人族与三类遭遇妖兽的选择、图集和动作参数不变。

`content/visual_assets.json`登记77项DLC受限资源，包含60张静态图、16张图集和1份动作清单。DLC自身`registry.json`使图标／地图重导保留人物资源登记；`provenance.json`记录原稿哈希及采用范围。元婴18份已采用像素文件逐字节复制。合体和低阶采用最近邻缩放，保留原始多级透明；九尾合体女原稿的两人物在半透明边缘相接，导出沿最低透明接缝分离，不切不透明身体。新增灵狐动作v2修正画布边缘裁切，v1不进入运行包。

离线重导：`python scripts/prepare_monster_fox_assets.py`，需工作区有效 design 原稿；运行游戏和安装包不需要设计目录。预览入口：[狐族资源图谱](../design/fox-beast-combat-alpha4-20261023/index.html)。

## 针对性验收

- `python -m pytest tests/test_monster_fox_visuals.py tests/test_visual_release.py tests/test_combat_replay.py -q`
- `python tests/browser_monster_fox_visuals.py`：真实创建／加载和页面点击，16套形象、头像／详情、真实结算战报、施域、窄屏、重播不写档、资源释放和 DLC 禁用回退。
- `python tests/browser_combat_replay.py`：既有人物与三类妖兽回放回归。
- `python tools/check_world_transition_contract.py`、`python tools/check_module_dependencies.py`、`python tools/check_documentation.py`。

执行结果见 `build/monster-fox-visuals/validation.json` 与相应测试输出。本轮按用户要求仅相关领域验证，不做全仓回归，不生成 EXE／APK 或发行压缩包。
