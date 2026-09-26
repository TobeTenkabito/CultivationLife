# 浮生问道

《浮生问道》是一款本地运行、以浏览器为界面的修仙人生模拟游戏。玩家从凡人或快速开局踏入不同道途，在修炼、游历、战斗、关系与势力经营中推进人生；NPC 同时经历成长、寿尽、争斗和世界变迁。

**当前本体版本：v1.37.0**，以 [version.py](cultivation_life/version.py) 为准。发行版本、存档结构、内容 schema 与 DLC/MOD 版本独立管理。逐版本变更见 [更新日志](CHANGELOG.md)。

## 开始游戏

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
| 修行与道途 | 道修、魔修、鬼修、妖修与儒修相关路线；功法配置与升级、四气环境和经验、炼体、神识、收敛/压制修为、手动突破与天劫；部分道途内容由 DLC 扩展 |
| 世界与时间 | 十一界地域地图、路径旅行、境界限制、地域资源与事件；年度世界演化、NPC 成长与寿尽、飞升及跨界往返 |
| 人物与关系 | 师徒、道侣、道友、后代、侍妾与 NPC 队伍；交谈、关系事件、联合突破、俘虏、傀儡与夺舍 |
| 势力与战争 | 宗门、家族、种族、外交、通缉与追捕、监禁、势力战争与和谈；内政职位及重大议案由相关 DLC 扩展 |
| 经营与交易 | 坊市、材料市场、拍卖、私下交易、黑市、匿名交换会、灵田和炼丹；商盟身份、任务、玩家委托及跨界商路 |
| 装备与阵法 | 五槽组合炼器、本命法宝温养与镶嵌、变身、九宫阵法、镇地阵与护山阵；神机与动态材料由相关 DLC 扩展 |
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

未提供配置时默认关闭。改为 `Debug=True` 可启用受此开关控制的调试入口，例如商盟的一键总部特使；刷新页面后读取当前配置。DLC/MOD 的开关另行保存，需要**停止并重新启动游戏服务**才生效，仅刷新网页不会重新加载内容包。

## DLC 与 MOD

启动时按 **本体 → DLC → MOD** 加载内容。同类扩展按 `load_order` 和 ID 排序。每个包放在 `dlc/` 或 `mods/` 下的独立目录，包含 `manifest.json` 与 `content/`；扩展只提供 JSON 数据，不执行其中的 Python 或 JavaScript。

当前仓库包含以下六个可选官方包，版本以各包清单为准：

| 内容包 | 版本 | 主要内容 |
| --- | --- | --- |
| [万妖归宗：血脉进化](dlc/monster-bloodlines/manifest.json) | 4.13.0 | 妖修本源、血脉进化、族血规则与高阶路线 |
| [百鬼夜行：往生轮回](dlc/ghost-reincarnation/manifest.json) | 3.7.0 | 鬼修魂魄、魂蚀、往生与轮回 |
| [明争暗斗：合纵连横](dlc/intrigue-coalitions/manifest.json) | 1.3.0 | NPC 性格、势力职位、客卿、议案与内政 |
| [圣人之道：内圣外王](dlc/sage-way/manifest.json) | 1.3.1 | 学说、教化、门人、经典、外王之策与儒修剧情 |
| [归墟之潮：九死一生](dlc/guixu-tide/manifest.json) | 2.4.0 | 十一界归墟副本、探索、宝物与 NPC 争夺 |
| [神机百变：巧夺天工](dlc/tianji-artifacts/manifest.json) | 2.2.0 | 天工神机榜、分层情报、动态材料、仿制与重铸 |

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
| `docs/` | 游戏设计与历史架构资料 |
| `data/`、`dist/` | 本地持久化数据与打包产物 |

### 引擎与系统边界

外部继续通过 `from cultivation_life.engine import GameEngine` 使用引擎。第二轮重构后，`engine/` 的实现采用普通模块函数：`dependencies.py` 声明协作能力，`ports.py` 定义资源接口，`wiring.py` 显式连接依赖，入口类保留签名明确的转发方法。该目录不再依赖动态方法安装或入口全局命名空间重绑定。

`system/` 中的经济、神机和内政已按职责拆分，原 `*_system.py` 模块继续作为兼容入口。这些系统仍使用原有 Mixin 和装配机制，不能套用引擎的新装配方式。读档补全、展示副作用、随机数调用和年度结算顺序也仍有行为兼容约束。

修改前请阅读 [引擎架构与保留项](cultivation_life/engine/README.md) 和 [系统目录与兼容边界](cultivation_life/system/README.md)。`docs/v2/` 保留历史设计和迁移记录，但当前源码树没有 `cultivation_life/v2/`；这些文档不代表现行运行架构或已接入的功能。

## 开发与验证

### 自动回归

安装测试依赖后，在项目根目录运行：

```powershell
python -m pip install pytest
python -m pytest -q
```

测试同时包含 `unittest` 风格用例和 pytest 函数/fixture。仅运行 `unittest discover` 会遗漏部分依赖边界测试，因此完整回归统一使用 pytest。

修改引擎或已拆分系统时，可先运行相关兼容性测试：

```powershell
python -m pytest -q tests/test_engine_dependencies.py tests/test_system_layout.py
```

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
