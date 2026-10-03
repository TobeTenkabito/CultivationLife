# Debug 系统开发规范与控制台使用

适用基线：本体 **1.57.0 开发源码**、存档结构 **8**。本功能是该发行之后的未发布开发变更，不包含在已经生成的 1.57.0 安装包中。

## 1. 优先遵循的开发范式

Debug 是应用边界装配的开发工具。正式玩法不得为了控制台新增条件分支、模型字段、随机数抽取或模块依赖。新增玩法与调试功能共同遵循以下约定：

1. **先确定权威状态与转换契约。** 找到数据真实来源，列清必须一起更新的字段。NPC 的生死、拘禁、名册不能用单一开关代替；灵石来源是背包 `spirit_stone`，不是新增一个计数器。
2. **正式系统保持单向依赖。** `server → debug → engine / rules / models`；正式引擎、系统、模型和规则不得反向导入 `debug`。`tools/check_module_dependencies.py` 会拒绝这类反向依赖。不增加 Mixin，不进行全局 monkey patch。
3. **先登记命令，再接界面。** 命令名称、参数、枚举、类别、帮助说明只有 Registry 一份来源。新增命令不能新增 HTTP 分支或另写前端解析器。按钮与文本输入都调用 `POST /api/debug/command`。
4. **只读查询从独立文档取值。** 不调用引擎 `_load`、`get_game`、自动补全、迁移写回或 RNG。当前普通游戏 GET 可能准备并写回状态，不能当成纯查询服务。
5. **修改在脱离权威状态的副本上完成。** 先保存执行前状态，执行、校验，再原子提交。多字段修改一旦失败，游戏、RNG、概率覆盖和成就都不提交。输入错误用 `CommandError`；程序错误保留堆栈并返回内部错误，不能伪装成输入错误。
6. **模拟调用正式规则。** 不复制一套年度、战斗、突破算法。首版普通游戏界面已经能驱动调试副本；新增 `simulation` 命令前必须接入具名能力、完成事务和差异检查，不能只增加注册表项后直接写引擎存档。
7. **覆盖只放在调试会话中。** 当前唯一规则覆盖是普通修为突破概率，由 `engine_adapter.SessionEngine` 的单实例适配完成。正式 `GameEngine` 与玩家存档均不新增 Debug 字段。不能因开发需求修改全球规则常量。
8. **命令与自然变量同义同名。** 玩家字段使用 `realm_index`、`layer`、`opportunity`；物品使用真实 ID `spirit_stone`。邻域未来命令必须使用 `voisinage`，禁止 `linyu`、`neighborhood` 等拼音或近义别名。英文空格表达动作：`player set ...`、`snapshot restore ...`；不支持自然语言猜测或模糊纠错。
9. **展示投影不得冒充玩家字段。** `spirit_stones` 是已有灵石总量语义的显式操作，映射到背包条目；`breakthrough_chance` 是已有概率计算语义的会话覆盖。新增类似字段必须说明其真实归属、作用范围与撤销方式。
10. **按行为验证。** 至少验证正常模式不变、查询纯度、失败回滚、原角色和成就隔离、同一场景正常/调试无覆盖时结果一致、非法参数、重复/并发执行。复杂转换还需验证死亡、跨界、待处理事件和读档。

正式系统未来新增数据库、文件或其他持久化副作用时，先提供可替换的存储能力，再明确如何进入 Debug 事务和快照。首版事务明确覆盖角色存档与全局成就，不会自动捕获任意新文件；未适配的新副作用不能直接开放给调试会话。

不支持 `eval`、`exec`、Python REPL、任意属性路径和任意文件路径命令。DLC 的未来调试注册应在 Debug 装配边界按已加载内容注册，不让 DLC 玩法加载过程依赖 Debug。首版未开放第三方可执行注册脚本。

## 2. 代码职责与扩展流程

| 文件 | 职责 |
| --- | --- |
| `cultivation_life/debug/registry.py` | 固定语法、类型元数据、注册、纯查询标记、帮助与补全 |
| `cultivation_life/debug/commands.py` | 首版命令、字段白名单、资源映射、快照操作 |
| `cultivation_life/debug/state.py` | 纯查询、轻量校验、摘要、带上限的状态差异 |
| `cultivation_life/debug/runtime.py` | 会话、原子提交、执行前现场、操作记录、复现包 |
| `cultivation_life/debug/engine_adapter.py` | 唯一引擎适配位置；普通修为概率覆盖 |
| `cultivation_life/debug/gateway.py` | HTTP 与隔离引擎的装配；拒绝逃逸到正式角色的操作 |
| `web/debug-console.js`、`.css` | 控制台、会话标识、命令历史、元数据补全 |

新增一个查询或简单修改命令的流程：

1. 确认真实字段、单位、范围和权威来源；复杂玩法先明确系统契约。
2. 在所属命令模块定义处理函数，接收 `Context` 和显式参数。禁止把完整引擎传给所有处理函数。
3. 登记 `Command(name, kind, description, handler, arguments, requires_session)`。名称重复立即报错；补全、帮助自动从登记信息生成。
4. 在 `tests/test_debug_console.py` 或对应专题测试中验证语义和隔离。新 Query 必须加入查询纯度覆盖；新规则适配必须验证真实消费入口。
5. 同步本文示例；完整可执行命令以运行时 `help` 为准。

支持的类别为 `query`、`mutation`、`session`、`snapshot`、`export`；`simulation` 保留扩展登记类别，首版没有模拟专用命令。会话和快照管理不属于游戏玩法推进。

## 3. 开启和关闭

### PC 源码运行

在项目根目录 `game_config.txt` 写入：

```ini
Debug=True
```

使用 `python launcher.py` 或 `python -m cultivation_life.server` 启动，刷新页面。使用 EXE 时，配置位于 EXE 对应的应用根目录；需要以后重新构建包含本功能的 EXE。

Debug 默认关闭；缺失、无法读取或无效配置不会启用。后端每次请求检查开关，改为 `Debug=False` 后旧会话请求立即返回 404，不会转而操作原存档。页面入口随下次刷新更新。已打开页面可用“断开会话”清除当前标签页的连接并重新加载标题页。

### Android

安装包含本功能的构建后，在游戏设置面板点击“开发者模式设置”，通过原生对话框开启或关闭。它仅写入应用私有目录的 `game_config.txt`，不改变 APK 的 `debuggable` 标志，也不为正式 APK 开启 WebView 远程调试。开关变化后刷新页面。

首版复现包在安卓通过系统文件选择器导出、导入，无需扩大存储权限。普通存档码剪贴板协议保持不变。关闭原生开发者模式会清除当前 WebView 的会话连接，保留本地调试副本。

## 4. 基本操作

选择并进入一个角色，点击“开发者控制台”，或按 **Ctrl + `**。然后执行：

```text
debug start
player fields
player set spirit_stones 100000
give spirit_stone 5000
remove spirit_stone 1000
realm list
player set realm_index 4
player set layer 7
player set opportunity 100000
player set breakthrough_chance 0.8
snapshot create before_test
```

`debug start` 在 `data/debug/` 建立独立副本，角色 ID 保持不变，通过随机会话 ID 和独立存储区区分。顶部持续显示 **DEBUG · 独立副本**。关闭控制台后可用正常游戏按钮修炼、交互和战斗，操作与成就都只提交到副本。另一个没有会话的标签页继续使用原角色。

按 Enter 执行；上下方向键查看最近 100 条命令；Tab 使用注册表补全命令和枚举参数；Ctrl+L 清空屏幕输出。命令按大小写精确匹配。文本参数支持引号，不支持 Shell 运算符、管道或复合脚本。

```text
debug status
debug sessions
debug stop
debug resume <session_id>
```

`debug stop` 返回原角色，副本保留；`debug resume` 可恢复已有副本。`session_id` 取自 `debug sessions`，不是角色 ID。会话保存在磁盘；浏览器连接标识只保存在当前标签页的 sessionStorage。

Debug 关闭、会话丢失、配置变化或服务错误时，不自动回退到正式存档。用“断开会话”显式返回。调试过程中创建/删除角色、普通存档码导入导出及修改扩展启用状态会被拒绝；切换角色前先退出调试。

## 5. 玩家数据与概率的准确含义

| 命令字段 | 类型与范围 | 含义 |
| --- | --- | --- |
| `spirit_stones` | 整数，0–10^15 | 背包 `spirit_stone` 的总量；不在 Player 中增加字段 |
| `opportunity` | 有限数，0–10^15 | 当前机缘；后续正常操作仍遵循本境界的规则 |
| `realm_index` | `realm list` 中的索引 | 设置境界，层数重置为 1，清除等待突破/飞升等标志；不自动跨界或发放晋升奖励 |
| `layer` | 当前境界合法层数 | 设置该境界层数；遵守配置中的当前世界修为上限 |
| `breakthrough_chance` | 有限数，0–1 | 独立会话中的普通修为大/小境界成功概率覆盖 |
| `age` | 整数，0–10^9 | 直接修改年龄，不推进世界，也不结算历年收益 |
| `lifespan` | 整数，1–10^9 | 修改寿元，不自动解除死亡状态 |
| `hp`、`mp` | 有限数，0–10^15 | 原始资源值；后续正式准备/结算仍可能按资源上限修正 |
| `heart_demon` | 有限数，0–10^9 | 当前心魔 |
| `karma` | 有限数，−10^9–10^9 | 当前因果 |
| `sha_qi` | 整数，0–10^9 | 当前煞气 |

境界/层数设置在待处理事件或试炼期间拒绝执行。不同世界和道途仍有正常玩法限制，控制台不会把人界角色硬塞入上界状态；需要上界测试时，从相应快速开局创建源角色。设置境界不是一次自然突破，不增加寿元或保证门槛已满足。

概率覆盖修改 `_breakthrough_chance` 的最终概率，保留原来的随机数抽取和其他结算。它不绕过机缘、丹药、世界、道途和待处理事件的门槛，**也不覆盖炼体、仙界/修罗专属养成、劫战或 NPC 突破**。因此设为 1 不代表任何“突破”按钮都必定完成全部流程。

```text
player get breakthrough_chance
player set breakthrough_chance 1
player set breakthrough_chance 0
player reset breakthrough_chance
```

0 表示对应概率检定失败，1 表示成功；重置后恢复正常计算。覆盖随会话与快照保存，不写入玩家存档或正式规则配置。

## 6. 查询、快照和复现命令

```text
help
help player
help snapshot restore
version
player
player get realm_index
player get spirit_stones
player fields
realm list
npc list
npc inspect <npc_id>
rng state
rng seed 114514
save validate
extensions
```

`npc list` 最多显示 200 条来源记录；`npc inspect` 显示对应 ID 的所有已记录来源，包括世界、宗门、家族、关系和受控人物表。它不复活、迁移或重新绑定人物，也不把重复来源一律判定为错误。

`rng state` 不抽随机数；`rng seed` 只重置副本未来的 RNG，不会重新生成已有世界。`save validate` 仅验证模型解码、境界/层数、世界、基础数字与 RNG；它不是全部 DLC 业务不变量的完整证明。

```text
snapshot create before_test
snapshot list
snapshot diff before_test
snapshot restore before_test
snapshot restore initial
snapshot restore last_before
snapshot delete before_test
repro export
```

命名快照最多 8 个，名称使用英文字母开头的 1–48 位字母、数字、`_` 或 `-`。`initial` 为建会话时的状态；`last_before` 为最近一次被记录操作之前的状态；两者保留，不允许覆盖或删除。快照包含玩家与世界完整数据、RNG、会话覆盖和独立成就。

差异输出最多显示 100 个变化位置；大型集合使用摘要和预览，完整状态仍在快照。日志最多保留最近 100 条；控制台屏幕输出也有上限，不代表复现包丢失完整当前状态。

## 7. 故障复现工作流

1. 开启 Debug，在角色中执行 `debug start`。
2. 配置测试状态，执行 `snapshot create before_test`。
3. 关闭控制台，使用正常界面触发问题；或执行要测试的控制台命令。
4. 出错后立即 `repro export`，下载 JSON；安卓使用“保存复现包到文件”。不要先进行无关操作，以免替换最近的执行前检查点。
5. 在另一环境开启 Debug，使用“导入复现包”。PC 也可粘贴剪贴板 JSON。该操作通过注册命令 `repro import` 接收文件内容，**不接受任意文件系统路径**。
6. 导入生成新会话。检查版本、代码和内容指纹差异，执行 `snapshot restore last_before` 或恢复命名快照，再按记录中的操作手动重试。

复现包含初始状态、当前状态、最近执行前状态、命名快照、临时概率覆盖、独立成就、最近操作的名称/参数、前后摘要、失败堆栈、请求编号、版本、Python 平台、扩展清单、界面偏好和内容指纹。Android 还纳入随包构建来源记录的哈希，避免将虚拟 Python 目录误当成可遍历源码。它包含完整角色信息，应只交给实际需要诊断的人。主题偏好属于应用共享设置；导入复现包不会自动改动目标设备的主题。

首版不自动重放命令序列、不固定运行时时钟和 UUID、不追踪每一次随机数调用。因此保证的是**保留现场并支持隔离重试**，不是跨版本、跨平台逐字节确定性回放。包格式为 `CultivationLife.debug.v1`，会话和导入请求上限均为 64 MiB；快照过多触及上限时应删除旧命名快照或建立新会话。

## 8. 测试与发布边界

```powershell
python -m pytest tests/test_debug_console.py tests/test_audit_regressions.py tests/test_runtime_config.py -q
python tests/browser_debug_console.py
python tools/check_module_dependencies.py
python tools/check_documentation.py
```

Android 的 `debug-console` instrumentation 阶段验证原生 WebView 控制台、六主题、正常操作写入副本、原角色隔离、原生返回和关闭后拒绝旧会话。APK 编译和 Lint 不能替代这些行为检查。正式包必须继续保持默认 `Debug=False` 及原有发布验收，不得将开发测试 APK 当成新正式发行。

首版暂未实现：NPC 生命周期修改、强制跨界、任意事件触发、时间专用命令、RNG trace、批量战斗/概率模拟、自动回放和第三方 DLC 可执行调试插件。这些功能在明确状态转换契约和验证范围后逐项扩展，不通过任意字段写入绕过。

### 本轮验证记录（2026-10-04）

- 完整 Python 回归分八个独立批次执行，**2,071 项通过，0 失败、0 跳过**，其中新增 Debug 专项 40 项；证据为 `build/debug-development-tests.log` 与八份 JUnit XML。
- `tests/browser_debug_console.py` 通过六主题、桌面/手机竖屏/手机横屏、命令补全、资源修改、快照、导出、双标签页隔离和关闭后的恢复；原有 `tests/browser_smoke.py` 也通过。
- Android Debug APK 构建通过，Lint 无问题；专用 Android 12 / API 31 x86_64 模拟器的竖屏和横屏验证通过。覆盖原生 WebView、资源和概率覆盖、快照、原始文件不变、原生返回、关闭后拒绝旧会话，以及通过 instrumentation 注入确定 URI 的实际文件导入导出回调。未验证实体 ARM 手机，也未将系统文件选择器的人工浏览流程作为自动化验收内容。
- Python 静态未定义名称检查通过；显式依赖图 **331 个模块、1,824 条边，0 循环、0 边界违规**；50 份 Markdown 的索引、链接和关键版本检查通过。
- 本轮未升级版本或替换 `dist/` 正式安装包。用于安卓验证的是独立包名的 Debug APK，不能作为原正式 APK 的覆盖更新。
