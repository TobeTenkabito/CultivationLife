# 浮生问道

《浮生问道》是一款本地运行、以浏览器为界面的修仙人生模拟游戏。玩家从凡人或快速开局踏入不同道途，在修炼、游历、战斗、关系与势力经营中推进人生；NPC 同时经历成长、寿尽、争斗和世界变迁。

**当前本体版本：v2.5.1**，以 [version.py](cultivation_life/version.py) 为准。发行版本、存档结构、内容 schema 与 DLC/MOD 版本独立管理。逐版本变更见 [更新日志](CHANGELOG.md)。

v2.5.1 改善自定义数值输入并补齐高阶开局仙脉／魔脉；失落界面增加独立宗门、家族入口。主动开辟空间裂缝须合体起，秘境界壁随机取化神至大乘后期。鬼修曾达九阶后魂蚀率永久停止增长，新增 33 个主要界面专属通用事件与 12 个全界面共有事件。

v2.1.0 在十一界地方事务之外，再加入每界独立的异象与战地档案，共 33 案、66 个分支；消息按所在界层分为详报、传闻、征兆，跨界商盟可受托核实并保存情报。系统发起战争限于同层级界面，玩家主动行动不受此限制。诸天偏好移入设置；外观仅保留松烟书院、月下观星、丹砂金阙、竹简纪年，移除名称字母前缀。

v2.1.1 修复威名／族群敌意串界、即时交互耗时与炼体超额扣年；新增祖兽梦径，情报细分五级，提高百层炼体成功率，落实[跨界开发规范](docs/world-transition-development.md)与[全量审计](docs/world-transition-audit.md)。

当前开发源码使用存档结构 **9**，支持结构 **8 → 9**（8→9） 的纯数据迁移；结构 1–7 不再加载或导入，需要新建角色。诸天地方事务已覆盖十一主要界面，每界各有独立的求证、两种现场处理与返程复核事件；以界域选择器和独立档案页呈现，详见[诸天实装进度](docs/heavens-implementation.md)。原有联系覆盖仙界、修罗界、幽冥界和轮回界四个最高界面的本地调查、合作、有限参悟与维护，并提供校订旧录后续任务；人界穆陵沙漠的镜律场域支持试探、破解、隔断与强攻，无棣原的因果遗址支持读取、唯一阵芯取用／替换／归还、两端阵眼通信和有限抹迹，均可持久重访。新档默认开启、旧档可在设置的诸天偏好中启用，见[实装进度](docs/heavens-implementation.md)。新增人界两处低阶征兆与当地对照，诸天界面采用见闻、诸界、异象、行程、战局独立导航。新增四界个人访学往返，校订后可实际启程、研读并凭预留路费返乡；访学设独立子页。新增原合作 NPC 的有经费回访、异界交往与实际返乡，入口为独立“同道”页。新增四界同道的有限阵材运输，原物资实际交货、项目经费支付，提供独立“运材”详情与“货运”目录。新增四界居民的有限接引与长期迁居，原人物实际通行、安置并留在目的界面，入口为“行程 → 迁居”。双异象已支持邀约与自主同勘，四界具备真实设施托管。M3 固定人界—魔界案例已接通先遣、两端界门、有限输送、实际交锋、当地占领、停战／限期附约、救护与沿路撤离，并有有限灵界物资援助。战局按军情、界门、交锋、援助、地方分开查阅；地方再分秩序、文书和救护档案。任意路线的自主人口迁徙、通用商贸货运、全界征服与通用军队 AI 仍为后续扩展；现有诸天与十一界地方事务一并纳入当前双端发行。

当前源码已完成显式依赖拆分、关键时间流程统一，以及普通关系按 NPC ID 关联权威人物。俘虏、侍妾与活傀已经区分生存、拘禁和名册状态；九个局部 Mixin 仍有明确保留边界。玩法包含四套主题、十一界、八个可选官方 DLC；修罗专属 UI 按境界开放，神通整组洗练可锁属性。

完整资料入口：[文档索引](docs/README.md)、[项目诊断](docs/project-diagnosis.md)、[引擎说明](cultivation_life/engine/README.md)、[Debug 开发规范与控制台](docs/debug-development.md)。当前发行说明见 [更新日志](CHANGELOG.md)。

## 开始游戏

### Android 12

当前安卓发行版本为 2.5.1-android.41，携带四套独立主题与八个 DLC，可离线运行。支持 64 位 ARM 手机及 x86_64 模拟器；最近发行的设备验收范围为 Android 12 模拟器。支持离线存档码导入、导出与分段复制，可在支持相同存档结构的 Windows 与 Android 版本间互通。发行包及验收范围以 `dist/` 内当前发行清单为准。使用与构建说明见 [安卓说明](android/README.md)。

### Windows 启动器

双击项目或发行目录中的 `launcher.exe`，启动器会运行本地服务并打开浏览器。默认在 `127.0.0.1:8000–8010` 中查找已有游戏服务或可用端口；再次启动会打开已运行的游戏页面。

`launcher.exe` 是打包产物，不会自动执行刚修改的 Python 源码。开发、调试或验证源码改动时，请使用下面的源码启动方式；更新发行程序需要重新打包。

### 从源码启动

在项目根目录执行以下命令。当前验证环境为 **Python 3.13**；游戏后端运行使用 Python 标准库，前端为原生 HTML/CSS/JavaScript，无需 npm 或前端构建。

```powershell
python -m cultivation_life.server
```

浏览器打开 <http://127.0.0.1:8000>。在终端按 `Ctrl+C` 停止服务。端口被占用时可指定其他端口：

```powershell
python -m cultivation_life.server --port 8001
```

此时访问 <http://127.0.0.1:8001>。首次进入可创建角色、选择快速开局，或读取已有存档；主页还提供跨存档的「功业录」和 DLC/MOD 管理器。

## 当前玩法

| 方向 | 已有内容 |
| --- | --- |
| 修行与道途 | 道修、魔修、鬼修、妖修、儒修与佛修相关路线；功法配置与升级、四气环境和经验、炼体、神识、收敛/压制修为、手动突破与天劫；部分道途内容由 DLC 扩展 |
| 世界与时间 | 十一界地域地图、空间裂缝、不世秘境与惰性生成的多个失落界面；年度演化、界面排斥及秘法下界 |
| 人物与关系 | 师徒、道侣、道友、后代、侍妾与 NPC 队伍；交谈、关系事件、联合突破、俘虏、傀儡与夺舍 |
| 势力与战争 | 宗门、家族、种族、外交、通缉与追捕、监禁、势力战争与和谈；内政职位及重大议案由相关 DLC 扩展 |
| 经营与交易 | 坊市、材料市场、拍卖、私下交易、黑市、匿名交换会、灵田和炼丹；商盟身份、任务、玩家委托及跨界商路 |
| 装备与阵法 | 四维符箓、五槽组合炼器、本命法宝、变身、九宫阵法及镇地阵；神机与动态材料由相关 DLC 扩展 |
| 剧情与记录 | 各界事件与连续剧情链、战斗记录、世界消息、角色历史、成就和本地存档 |

地图已全部归入本体；关闭对应 DLC 不会删除地图，但专属系统、剧情与道途解锁仍受内容包和游戏条件控制。拥有某界地图不代表新角色可以直接进入该界。

一个行动单位可能跨越多年，引擎仍按年结算世界变化；行动成本、主动遭遇和剧情推进有各自的结算粒度。具体数值和条件以当前加载的内容及游戏内显示为准。

## 存档与本地配置

通常以源码项目根目录或发行版启动器所在目录作为持久化根目录：

| 路径 | 用途 |
| --- | --- |
| `data/saves/<角色ID>.json` | 角色状态、世界状态、历史与随机数状态 |
| `data/saves/global_metadata.json` | 跨存档成就、解锁时间与角色记录 |
| `data/extension_preferences.json` | 玩家选择的 DLC/MOD 启用状态 |
| `game_config.txt` | 启动器旁或源码根目录下的运行配置 |

开发仓库中的 `dist/launcher.exe` 会在识别到完整项目结构时共用根目录 `data/`，避免产生第二套存档；将发行程序放到独立目录后，则使用其自身目录。路径规则见 [runtime.py](cultivation_life/runtime.py)。迁移游戏数据时应同时保留角色存档、全局成就和扩展偏好。

调试功能通过 `game_config.txt` 控制，例如：

```ini
Debug=False
```

旧 Debug 配置默认关闭；它不再控制控制台入口。PC 按 **~ / Backquote**，Android 在设置中打开“开发者控制台”，执行 `debug start` 创建独立副本后再修改数据或测试。神机、商盟的旧调试操作也仅允许在副本中执行。使用方法与后续开发规范见 [Debug 文档](docs/debug-development.md)。DLC/MOD 的开关另行保存，需要**停止并重新启动游戏服务**才生效，仅刷新网页不会重新加载内容包。

开发自动化可复用项目自带的 CLI、Python 客户端和 stdio MCP 工具。启动服务后执行 `python scripts/debug_agent.py tools` 查看命令及参数 Schema；`python scripts/debug_agent.py mcp` 启动 Agent 桥。工具沿用独立副本、版本校验和请求去重，接入配置及完整示例见 [Agent 使用规范](docs/debug-development.md#9-agent-工具与结构化调用)。

当前控制台共 180 个命令，覆盖本体与当前全部 DLC 的 137 个角色操作入口。`scenario create` 可直接新建隔离测试角色；`game view` 提供与界面同源的选项和 ID，市场、功法、生产、关系、组织、战争及跨界操作均沿用正式规则。完整映射见 [角色入口清单](docs/debug-base-coverage.md)，专属玩法、调试捷径和示例见 [DLC 指令清单](docs/debug-dlc-coverage.md)。

Windows ZIP 附带 `scripts/debug_agent.py` 及最小标准库客户端。CLI／MCP 桥需要另备 Python 3.13；正常双击游戏启动器无需安装 Python。使用工具前须启动游戏服务，无需配置 Debug。

## DLC 与 MOD

启动时按 **本体 → DLC → MOD** 加载内容。同类扩展按 `load_order` 和 ID 排序。每个包放在 `dlc/` 或 `mods/` 下的独立目录，包含 `manifest.json` 与 `content/`；扩展只提供 JSON 数据，不执行其中的 Python 或 JavaScript。

当前仓库包含以下八个可选官方包，版本以各包清单为准：

| 内容包 | 版本 | 主要内容 |
| --- | --- | --- |
| [修罗显圣：无法无天](dlc/asura-manifestation/README.md) | 1.2.0 | 煞元转化、魔脉、八部凝身、魔域神通与心魔劫 |
| [诸法无我：众生为镜](dlc/buddhist-dharma/README.md) | 1.0.0 | 三阶段法会、地图信众、寺庙、正负业力、六项加持与佛修双飞升路线 |
| [万妖归宗：血脉进化](dlc/monster-bloodlines/README.md) | 4.14.1 | 妖修本源、血脉进化、族血规则与八源本相铸域 |
| [百鬼夜行：往生轮回](dlc/ghost-reincarnation/README.md) | 3.8.0 | 鬼修魂魄、魂蚀、往生与轮回 |
| [明争暗斗：合纵连横](dlc/intrigue-coalitions/README.md) | 1.3.0 | NPC 性格、势力职位、客卿、议案与内政 |
| [圣人之道：内圣外王](dlc/sage-way/README.md) | 1.4.0 | 学说、教化、门人、经典、外王之策与儒修剧情 |
| [归墟之潮：九死一生](dlc/guixu-tide/README.md) | 2.6.0 | 十一界归墟副本、探索、宝物与 NPC 争夺 |
| [神机百变：巧夺天工](dlc/tianji-artifacts/README.md) | 2.2.0 | 天工神机榜、分层情报、动态材料、仿制与重铸 |

主页右上角可管理启用状态，游戏内「拓」面板可查看本次启动的加载情况。被禁用、依赖缺失或校验失败的扩展会被跳过；玩家开关不会改写包内清单。扩展格式、合并规则和依赖声明分别见 [DLC 说明](dlc/README.md) 与 [MOD 说明](mods/README.md)。

## 项目结构

| 位置 | 职责 |
| --- | --- |
| `launcher.py`、`build/launcher.spec` | Windows 单实例启动器与 PyInstaller 打包配置 |
| `cultivation_life/server.py` | HTTP API、静态资源服务及应用初始化 |
| `cultivation_life/engine/` | `GameEngine` 入口、行动编排、事件、成长、世界维护、展示与读档 |
| `cultivation_life/system/` | 战斗、经济、地图、商盟、阵法、各道途及 DLC 运行时系统 |
| `cultivation_life/models.py`、`rules.py` | 存档模型与核心规则计算 |
| `cultivation_life/content_registry.py`、`event_repository.py` | 内容加载、定义构建、事件和跨表引用校验 |
| `cultivation_life/combat_rule_engine.py` | 公共战斗规则与战斗期间的运行状态 |
| `cultivation_life/simulation.py`、`map_runtime.py` | 行动账本、旅行流程与年度推进协作 |
| `cultivation_life/storage.py`、`runtime.py`、`achievements.py` | JSON 存档、随机数状态、持久化路径与成就 |
| `content/` | 本体世界、地图、功法、物品、势力、商盟与事件等 JSON 数据 |
| `dlc/`、`mods/` | 可选扩展包 |
| `web/` | 无需构建的前端页面、样式和交互脚本 |
| `tests/` | 规则、系统、兼容性回归和手动浏览器烟雾测试 |
| `scripts/`、`tools/` | 发行验收与内容生成、维护脚本 |
| `docs/` | 当前规则、开发文档、诊断及注明版本的历史校准数据 |
| `data/`、`dist/` | 本地持久化数据与打包产物 |

### 引擎与系统边界

外部继续通过 `from cultivation_life.engine import GameEngine` 使用引擎。第二轮重构后，`engine/` 的实现采用普通模块函数：`dependencies.py` 声明协作能力，`ports.py` 兼容导出共用资源接口，`wiring.py` 显式连接依赖，入口类保留签名明确的转发方法。算法不再依赖动态方法安装或入口全局命名空间重绑定；公开操作仍由事务包装器统一加锁。

当前引擎整理已将装配细节归入 `engine/composition/`，多组玩法使用显式依赖，归墟、战争、地图／传送、商盟、道统／仙界养成及关系处置均已移出 Mixin 继承列表，剩余 9 个直接基类。鬼道、魔道、侍妾与佛门的关键时间、身份变更和生死流程也已独立装配，局部规则和培养操作继续保留。世界年度推进位于引擎公共流程；普通行动与旅行共用年度收尾及行动单位结算，通过明确配置保留原有计时和中断差异。仙体与融合共用独立修持提交接口。现有操作接口保持稳定；存档结构 8 在 NPC ID 引用基础上区分生存、拘禁与名册状态，结构 9 增加诸天空容器，支持结构 8 到 9 的纯数据迁移；当前版本的会话准备分为六个阶段。

`system/` 中的经济、神机和内政均已改为显式依赖的普通函数，原 `*_system.py` 模块保留签名明确的转发方法与静态辅助方法，旧动态装配工具已删除。人物交往通过注入操作调用引擎，王庭与引擎共用战斗适配层。读档补全、展示副作用、随机数调用和年度结算顺序仍有行为兼容约束。

修改前请阅读 [引擎架构与保留项](cultivation_life/engine/README.md) 和 [系统目录与兼容边界](cultivation_life/system/README.md)。当前源码树没有 `docs/v2/` 或 `cultivation_life/v2/`；请勿依赖已移除的旧设计路径。

## 开发与验证

经济 V2 前两轮规则及验收入口见 [经济专题](docs/economy-v2.md)。地图展示本地市场与物流，坊市保留精选货架；商盟面板展示真实商队经营，组织财政继续在后续轮次接入。

HTTP 请求在存档锁内共用一次加载、完成会话准备后的角色状态；状态限制检查和实际操作读取同一对象，请求结束即释放，不跨请求缓存。请求之外的直接引擎调用不使用该缓存。结构迁移在解码模型前执行，会话准备中的结算和随机数操作不能放入结构迁移步骤。

API 参数或业务条件错误返回 400，权限错误返回 403，明确的资源不存在返回 404；其余内部异常返回 500 和请求编号。异常堆栈写入持久化目录下的 `data/logs/server-errors.log`，每份约 1 MB、最多保留三份轮转备份；请求编号可与界面提示对应。日志不主动记录请求正文或完整存档。Android 发布检查使用显式校验，在 `python -O`、`python -OO` 下仍执行。

### 自动回归

安装测试依赖后，在项目根目录运行：

```powershell
python -m pip install pytest
python -m pytest -q
```

测试同时包含 `unittest` 风格用例和 pytest 函数/fixture。仅运行 `unittest discover` 会遗漏部分依赖边界测试，因此完整回归统一使用 pytest。

修改引擎或已拆分系统时，可先运行相关兼容性测试：

```powershell
python -m pytest -q tests/test_engine_dependencies.py tests/test_system_layout.py tests/test_module_dependencies.py
python tools/check_module_dependencies.py
python tools/check_documentation.py
```

依赖检查覆盖显式导入及函数内延迟导入，对禁止的反向引用返回失败；可用 `--json dependency-report.json` 导出完整循环组。此前的战斗循环和核心模型／规则循环均已拆开，当前显式导入图无循环。检查还约束商盟结算、公共时间和修持提交的反向依赖。检查不模拟动态导入及包初始化的隐式执行，不能替代运行时测试。

### 浏览器烟雾测试

浏览器测试需额外安装 Playwright 和 Chromium；脚本自行启动临时服务并使用临时存档：

```powershell
python -m pip install playwright
python -m playwright install chromium
python tests/browser_smoke.py
```

此脚本覆盖带官方内容包的界面，运行时需启用仓库自带的官方 DLC。商盟和特定版本界面的专项脚本位于 `tests/browser_*.py`，不会由默认 pytest 命令自动执行。

### Windows 打包

```powershell
python -m pip install pyinstaller
python -m PyInstaller --noconfirm build/launcher.spec
python scripts/verify_release_exe.py
```

构建输出为 `dist/launcher.exe`，包含本体 `content/` 和 `web/`。DLC/MOD 保持外置，发行时将所需扩展目录放在可执行文件旁；本地配置也由该目录提供。验收脚本在隔离临时目录中分别验证无 DLC 和带官方 DLC 的启动、接口及关键操作。构建不会自动替换项目根目录的 `launcher.exe`。

## 内容扩展与维护

在现有 schema 和规则支持的范围内，新增物品、功法、事件或调整数值优先修改 JSON；新增行为或规则类型仍需实现相应执行逻辑。启动时会校验 schema、重复 ID、世界/种族定义及物品、功法、NPC、势力等跨表引用，本体内容错误会阻止加载，扩展错误则隔离报告。

- 世界、地图与成长条件：`content/world.json`、`content/maps.json`。
- 物品、功法与经济：`content/items.json`、`content/techniques.json`、`content/market.json`。
- 势力与人物：`content/factions.json`、`content/world_npcs.json`、`content/races.json`。
- 事件与成就：`content/events.json`、`content/*_events.json`、`content/achievements.json`。
- 发布变更：同步 [版本定义](cultivation_life/version.py) 与 [更新日志](CHANGELOG.md)；DLC 改动另行更新其清单版本。

架构整理应保持接口、存档格式、随机数消费、状态更新和结算顺序。游戏规则变更应单独说明并验证相关流程，不能混入仅移动或拆分文件的重构。

## 平台与文档维护

Windows 和 Android 共用 Python、JSON 与网页源码；Android 另有移动端桥接和资源准备。四主题保留独立布局，新交互应验证桌面及窄屏，发布时按目标平台分别构建并验收。源码回归不等于发行二进制验收。

当前规则写入对应专题，CHANGELOG 只保留当前发行说明。文档文件名中的 1470、1512 等数字保留用于稳定链接，不再代表适用版本；历史采样表须注明采样版本和边界。发布前运行文档一致性检查，并同步本体版本、DLC 清单及存档结构说明。
