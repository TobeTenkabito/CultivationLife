# 修罗 DLC 男女主角立绘与动作

2026-10-25，修罗显圣：无法无天 1.3.0；本次只更新源码与 DLC，不升级本体 alpha、不重打 EXE／APK。

两套主角重新设计为寂灭战尊、红莲修罗：残日冠／红莲冠、不对称黑白朱红衣装及赤色法纹形成各自轮廓。最初制式战甲版本被用户要求重设计，未作为运行素材。此批是通用修罗人形，不代表玩家已经选择某一八部本命；三头六臂、龙躯等本命差异不由立绘授予。

男女各包含头像 128×128、详情立绘 256×288、缩略立绘 128×144；共 6 张静态 PNG。各九个完整关键姿势（待机、蓄势、发招、防御、承击、受击、失衡、跪撑、倒地），编排待机、修罗煞印、受击恢复、防御、承击、倒地及施域共 14 组动画。动作采用关键帧与既有渲染微动，不宣称逐帧手绘。女主动作补清楚裙摆遮挡的双腿与靴子。

## 选取与隔离

本体 `character_visuals.character_appearance` 读取已加载扩展的 `character_forms`，增加可选 `min_realm_index` 下限。此包声明人族出身魔修、男女主角、第九阶及以上使用对应素材。外观跟随已达到的修为，封印下界读取既有 `sealed_cultivation.realm_index`，不因临时压制变回低境形象；仅到访修罗界不授予外观。宿身、附身、变化形态、未知性别／身份仍按原回退。此次不新增 NPC 套图。

前端接受服务器已选择的合法主角素材标识；不再假定素材名称必然等于道途名称。头像、详情、事件与战斗使用相同投影；心魔等依法沿用战前主角快照的变色版本。新资源全部位于 `dlc/asura-manifestation/assets/visual/`，关闭 DLC 时注册清单与资源 HTTP 访问均不可用。无新持久字段、人物副本、世界改写、迁移、时间／代价或 RNG 消耗。

回放检查修复了字符串姿势的坐标读取：JavaScript 字符串的 `anchor` 方法不是角色锚点，误读会产生 NaN 并使人物不可见。渲染器现在只从对象姿势读取坐标，否则使用角色锚点、再回退基础锚点；兼容原有对象姿势和三道途字符串姿势。浏览器验证检查有限坐标与实际截图，不只验证清单加载成功。

## 来源与验证

内置 OpenAI image_gen 生成；原稿、动作及最终提示词在本机 `design/asura-characters-20261025/redesign-prompts.json`，预览 `index.html`。最近邻导出保留软透明，统一动作比例和脚底锚点；来源哈希随 DLC 的 `characters/provenance.json` 保存。运行环境无需 design 文件夹。

导出：`python -m scripts.prepare_asura_character_assets`。

专项：`tests/test_asura_character_visuals.py`、`tests/test_path_character_visuals.py`、`tests/test_asura_manifestation.py`、`tests/test_asura_dependencies.py`；覆盖境界边界、封印外观、其他身份回退、包隔离、图集哈希、帧界限、真实开局与战斗快照。浏览器 `python tests/browser_asura_characters.py` 使用真实临时服务器和隔离存档，点击头像与战报，检查桌面／手机尺寸和心魔回放全时段；既有三道途页面同时回归。并运行状态合同、模块依赖、文档三项仓库门禁。未执行新一轮 EXE／APK 成品验收，本次不是本体发行。

最终结果：上述四组专项 59 项及 `tests/test_combat_replay.py` 42 项，共 101 项通过；修罗人物、三道途人物、基础战斗回放三组真实浏览器检查通过，三项仓库门禁通过。修罗页面截图与有限坐标诊断存于本机 `build/asura-characters/`。
