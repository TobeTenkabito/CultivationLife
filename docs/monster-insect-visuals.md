# 虫属四境立绘与战斗动作

2026-10-24，按用户“仿照前面的流程一次性完成虫属”制作并接入19套形象、57张像素静态图、171个绘制姿态与126组有限关键帧动画。合体虫群女采用成年苗疆少女意象，金甲女采用冷艳妩媚的蛇蝎美人气质；“蛇蝎”描述气质，不改变金甲血脉种族。本体3.0.0-alpha.3、DLC1 4.18.0、结构10保持，未打包。

## 形象与节点

| 美术阶段 | 数量 | 形象 |
| --- | --- | --- |
| 练气 | 1 | 灵甲虫，男女共用，凡境至筑基沿用 |
| 结丹 | 6 | 金甲虫王、虚鸣天蝉、群心胚、紫金甲王、惊雷鸣蝉、百窍幻蛾，男女共用 |
| 元婴 | 6 | 百蜕妖君、群心母皇、虚鸣蝉君，各男女；化神、炼虚沿用 |
| 合体 | 6 | 太古金甲祖、百窍祖巢、太古鸣蝉祖，各男女；对应大乘沿用 |

低阶使用六足虫体；元婴开始使用人脸、人身、双腿，保留短触角、复眼光泽、甲纹或薄翼。合体虫群以靛蓝刺绣、银饰、女裙与男袍区分；金甲女采用黑金长裙、暗红衬里和轻量甲饰，男采用黑金甲袍；鸣蝉男女采用银发、玉白衣装和薄翼。

节点描述中的虫体、母巢与虫群视为血脉本相，高阶原稿表现其人形外观；母皇称号不强制改性别。差异已登记于本批direction.json，不修改进化条件、群体能力或原始数据。金甲合体女战斗图采用高领、裙内不透长裤和完整战斗衣装，与静态长裙有明确衣装差分；记录在动作目录armor-battle-adjustment.json。

选图复用 `monster_visuals.monster_appearance`，只读真实血脉节点、性别、既有进化历史和DLC资格。明确分支优先；旧汇合节点 `INSECT_MYRIAD_EMPEROR`、`INSECT_VOID_HIVE` 只从合法金甲／虫群元婴历史沿用，缺失历史不猜测，不能凭无效鸣蝉历史选图。封印下界的显露境界不改变真实血脉形象。九阶以上、未知节点、宿身、附身、变化形态及DLC禁用沿原回退。

## 运行与导出

运行文件位于 `dlc/monster-bloodlines/assets/visual/insect/`，包括57张静态PNG、19张战斗图集及manifest、registry、provenance。77项资源进入现有DLC白名单。运行不读取被忽略的design目录。

静态图从配对原稿分离为128×128头像、256×288详情立绘、128×144缩略小人，最近邻等比缩小，保留多级透明。九姿态为待机、蓄势、发招、防御、承击、受击、失衡、伏低／跪撑、倒地。每套共同缩放比例，使用384×288逻辑画布和192,256落脚锚点；仅保存九个绘制姿势，时间序列复用索引。七套低阶各6组动作，十二套人形各7组，含施域储备；施域图不会授予邻域能力。这是有限关键帧动画，不是逐帧重绘。

HUD和详情沿用“新版界面”的既有入口。战前身份与胜负由原结算入口决定，回放复用既有战报、法术、护体与邻域表现。无新增持久字段，无移动、时间、代价、HP/MP或游戏RNG改动。旧源码进程需重启加载新增映射；安装包本轮未更新。

重导命令：`python -m scripts.prepare_monster_insect_assets`。仅离线重导依赖本机原稿；脚本核对源图哈希并验证已有狐、蛇、羽、猿、龟甲五族文件逐字节保持。静态有效源为群心胚、合体金甲女v2，其余v1；动作全部v1。被替换静态v1只作修正输入，不用于运行导出。

## 验收入口

本批293项相关测试通过；真实浏览器验证19套形象、邻域回放、窄屏和DLC禁用回退通过，页面脚本错误为0。两个独立预览的静态与动画检查均通过。

- `python -m pytest tests/test_monster_insect_visuals.py tests/test_monster_turtle_visuals.py tests/test_monster_static_assets.py tests/test_monster_fox_visuals.py tests/test_monster_serpent_visuals.py tests/test_visual_release.py tests/test_combat_replay.py -q`
- `python tests/browser_monster_insect_visuals.py`：隔离临时存档真实创建／加载，19套HUD、点击详情与战报、播放暂停拖动、胜负端点、邻域回放、窄屏、缓存释放、浏览不写档、DLC禁用404与不请求专属素材。
- 两个本机设计目录分别运行prepare.py与check_preview.py，核对19套静态、57张像素图、171姿态、126组动画和预览控件。
- `python tools/check_world_transition_contract.py`、`python tools/check_module_dependencies.py`、`python tools/check_documentation.py`。

最终结果见 `build/monster-insect-visuals/final-review.json` 与同目录浏览器证据。本轮仅相关领域检查，不进行无关全仓回归或原生发布验收。

本机预览：`design/insect-growth-alpha4-20261024/index.html` 与 `design/insect-combat-alpha4-20261024/index.html`。素材按本次完整流程授权接入供用户验收，不表述为用户已逐张确认。
