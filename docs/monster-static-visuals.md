# 妖修四族像素头像与静态立绘

2026-10-24，按用户“从狐狸到猿属……原稿进行像素缩略化……真正能在游戏里显示的那种头像，请补上”补齐静态资源。本体仍3.0.0-alpha.3、DLC1仍4.18.0、结构10，不打包。本次仅静态素材接入，羽属与猿属已绘动作仍为独立审阅稿，普通战报保持原回退。

## 覆盖与规格

| 种族 | 套数 | 本次处理 |
| --- | --- | --- |
| 狐 | 20 | 已有头像、详情、缩略60张，原字节保持 |
| 蛇 | 11 | 已有静态33张，原字节保持；元婴至炼虚没有原稿，保持回退 |
| 羽 | 17 | 练气1、结丹6、元婴男女6、合体男女4；新增51张 |
| 猿 | 23 | 练气1、结丹男女12、元婴男女6、合体男女4；新增69张 |

合计71套、213张静态PNG。每套头像128×128、详情全身256×288、全身缩略128×144，原稿主体分离后按最近邻等比缩放；透明画布保留边距与原始多级alpha，不拉伸、不重绘、不用待机动作代替头像。羽属元婴劫羽雷皇女版有淡光晕连接，alpha32仅用于识别两个主体，像素仍用原透明值；其余主体识别阈值8。完整来源、修订选择和SHA256在 `scripts/monster_static_sources.json`。

新资源位于 `dlc/monster-bloodlines/assets/visual/avian` 和 `ape`。各族manifest记录静态身份与节点映射；registry登记羽属51张图片加1份静态清单、猿属69张图片加1份静态清单。静态清单也进入DLC白名单，内部读取与图片请求均服从真实启用状态。`scripts/prepare_visual_release.py`原有registry扫描会保留登记；游戏和发行包不依赖design。

## 选图与显示

继续使用 `monster_visuals.monster_appearance` 与临时公开 `visual_actor`，主界面头像、人物详情和宗门自己的头像沿原VisualAssets入口显示。玩家须启用“新版界面”；桌面HUD头像显示64像素，窄屏沿原56像素样式。旧版文字界面不加载新图。

羽／猿凡境至筑基沿练气图；结丹分别采用现用六支。猿结丹已按用户确定的方向分男女。元婴采用对应三脉男女，化神与炼虚仅从当前节点的真实祖先列表中查找已有元婴进化历史，继续沿用该形象；没有合法历史不猜分支，回退无图。合体两脉男女分别沿用到对应大乘节点。明确节点优先，不因封印下界后的显露境界变回幼体。

新两族静态投影返回combat为空，战前适配器因此保持既有战斗示意，避免把只有静态资源的身份写入战报。狐／蛇既有战斗身份、成品与图集不改。宿身、附身、变化形态、未知节点、九阶以上、未覆盖物种和DLC禁用均保留回退。不新增Player/GameState字段、人物、能力、移动、时间或游戏RNG调用。

## 重导与验收

- `python scripts/prepare_monster_static_assets.py`：需本机有效原稿，只新增／重导羽猿静态PNG，校验狐蛇所有文件保持；源图不修改。
- `python -m pytest tests/test_monster_static_assets.py tests/test_monster_fox_visuals.py tests/test_monster_serpent_visuals.py tests/test_visual_release.py tests/test_combat_replay.py -q`。
- `python tests/browser_monster_static_assets.py`：隔离存档真实创建与加载，71种形象HUD头像、实际点击详情并逐像素对照正式PNG、窄屏、浏览不写档、新版界面关闭、DLC资源404与无图回退。
- 三项仓库门禁：跨界状态合同、模块依赖、文档检查。无跨界或事件提交改动，不做无关全仓回归。

实际浏览器证据在 `build/monster-static-visuals/validation.json` 与同目录截图。四族素材对照入口为本机 `design/monster-static-pixels-20261024/index.html`。已运行的旧游戏进程需要重启，才能重载Python选图代码和资源清单；本次未更新旧发行安装包。

## alpha.4 正式动作接入

此前羽属／猿属仅静态的限制已解除：全部40套已采用动作现已提升到DLC运行目录，战报使用相应真实身份。资源声明统一由DLC的visual/registry.json提供，本体图录不再硬编码这些可选素材。详见[alpha.4说明](alpha4-release.md)。
