# 水属四境立绘与战斗动作

锦鲤最新确认：用户保留银发金饰与华丽礼服基础，仅将男性长须改为贴近下颌的短须。女版静态v4／动作v2保持；男版静态v4／动作v4生效。素色阴阳师试稿不采用，相关记录见静态目录koi-short-beard.json。

2026-10-24，按用户“仿照前面的流程一次性完成水属”完成19套形象、57张像素静态图、171个绘制姿态和126组有限关键帧动画，接入妖修DLC源码。天海神鲲路线采用江南水乡风格，鲤鱼路线采用和式锦鲤风格。本体3.0.0-alpha.3、DLC1 4.18.0、结构10保持，本轮不打包。

## 形象与节点

| 美术阶段 | 数量 | 形象 |
| --- | --- | --- |
| 练气 | 1 | 灵潮鱼，男女共用，凡境至筑基沿用 |
| 结丹 | 6 | 沧海龙鲤王、寒渊巨鲸、幼生天鲲、金鳞跃鲤、玄冰巨鲸、蜃潮灵鲸，男女共用 |
| 元婴 | 6 | 四海妖君、天海鲲君、沧渊鲸君，各男女；化神、炼虚沿用 |
| 合体 | 6 | 太古龙鲤祖、太古祖鲲、太古鲸祖，各男女；对应大乘沿用 |

低阶保留鱼、鲸、鲲的完整兽形。元婴起采用人脸、人身、双腿，保留鳍耳、鬓侧鳞纹与血脉衣纹。鲲线使用烟青月白丝衣、柳叶、荷与水纹；锦鲤元婴使用黑发、和服／羽织与袴，合体按用户“没有体现修为差距”反馈重设计为银白祖相：女版金色鳞冠、宽博层叠礼装，男版短须白发长者、乌帽与朱红朝服，均有额心祖纹、金瞳和连接肩衣的鳍形披帛。披帛属于服装，不新增肢体或能力。鲸线使用藏青银纹、肩衣与靴装，合体男保留短银黑胡须。

原始节点的鲲躯、鲸躯及龙鲤本相描述不变，高阶原稿表现其人形外观。风格不改变世界设定、化形能力、进化条件或数值；龙鲤不因美术增加真龙角爪或龙血。差异登记于本批direction.json。

选图复用 `monster_visuals.monster_appearance`，只读真实血脉节点、性别、既有进化历史和DLC资格。明确分支优先；旧汇合节点 `AQUATIC_OCEAN_EMPEROR`、`AQUATIC_WORLD_KUN` 只从合法锦鲤／天鲲元婴历史沿用，缺失历史不猜测，无效鲸脉历史不能选图。明确的 `AQUATIC_WHALE_5` 即便来自四海妖君也使用鲸脉形象。封印下界的显露境界不改变真实血脉形象。九阶以上、未知节点、宿身、附身、变化形态及DLC禁用沿原回退。

## 运行与导出

运行文件位于 `dlc/monster-bloodlines/assets/visual/aquatic/`：57张静态PNG、19张战斗图集及manifest、registry、provenance。77项资源进入既有DLC白名单；运行不读取被忽略的design目录。

静态图由配对原稿分离为128×128头像、256×288详情立绘和128×144缩略小人，最近邻等比缩小并保留多级透明。动作采用384×288逻辑画布，每套九姿态共享缩放比例，时间序列复用九帧索引。七套兽形各6组动作、十二套人形各7组动作，包含待机、施法、受击恢复、防御、承击、败退及人形施域储备。兽形用屈身游动、收鳍、失衡下沉、侧倒表现，不套用人类腿脚动作；施域图不授予邻域能力。这是有限关键帧动画，不是逐帧重绘。

HUD和详情沿用“新版界面”既有入口，战斗复用已有结算和回放播放器。兽形发射点按各自发招姿态的口部高度校准，鱼类与上扬鲸鲲分别处理。无新增持久字段、移动、时间、代价或游戏RNG变化。旧源码进程需重启以加载新增映射；安装包本轮未更新。

重导命令：`python -m scripts.prepare_monster_aquatic_assets`。离线重导核对原稿哈希并验证已有狐、蛇、羽、猿、龟甲、虫六族文件不变。静态有效源为元婴天鲲女v2、合体锦鲤女v4／男v4，其余v1；合体锦鲤女动作v2、男动作v4，其余动作v1。被替换版本仅保留历史来源，不用于运行导出。原稿、实际提示词、参考哈希及生成缓存出处均已存入两个设计目录。锦鲤重设计另见静态目录koi-redesign.json及koi-redesign-history.json；478个无关运行文件逐字节保持。

## 验收入口

- `python -m pytest tests/test_monster_aquatic_visuals.py tests/test_monster_insect_visuals.py tests/test_monster_turtle_visuals.py tests/test_monster_static_assets.py tests/test_monster_fox_visuals.py tests/test_monster_serpent_visuals.py tests/test_visual_release.py tests/test_combat_replay.py -q`：348项相关测试通过。
- `python tests/browser_monster_aquatic_visuals.py`：隔离临时存档，真实创建／加载19套形象、点击HUD详情与战报、播放暂停拖动、胜负端点、邻域、窄屏、缓存释放、浏览不写档、DLC禁用404及不请求专属素材。
- 两个设计目录的prepare.py与check_preview.py：19套静态、57张像素图、171姿态、126组动画、真实控件和四种宽度。
- `python tools/check_world_transition_contract.py`、`python tools/check_module_dependencies.py`、`python tools/check_documentation.py`。

锦鲤重设计后复核水属与视觉发行61项测试、19形象真实浏览器、两个设计预览和三项工程门禁；新增锦鲤男女合体的窄屏与截图覆盖。最终验收结果见 `build/monster-aquatic-visuals/final-review.json` 与同目录浏览器证据。仅运行相关领域检查，不进行全仓回归或原生发布验收。

本机预览：`design/aquatic-growth-alpha4-20261024/index.html` 与 `design/aquatic-combat-alpha4-20261024/index.html`。素材按整批流程授权接入供用户验收，不表示用户已经逐张确认。
