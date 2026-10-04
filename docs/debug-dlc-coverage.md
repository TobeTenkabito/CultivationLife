# Debug DLC 指令与验证范围

维护基线：本体 **1.57.0 开发源码**，存档结构 **8**。当前共 **178 个控制台命令 / Agent 工具**，具名接入全部 **135 个角色 POST 操作入口**。本轮补齐此前剩余的 **17 个入口**；其中 15 个是正式玩法入口，2 个是已有 Debug 捷径。这里的“覆盖”指可调用入口，不能等同于穷举所有玩法分支。当前安装包需另行打包才会包含这些源码功能。

## 调用约定

控制台、结构化 HTTP、CLI 和 MCP 共用注册表，无须 AI 编写脚本来替代游戏逻辑。先执行 `help`、`capability list` 和 `scenario list` 发现指令、内容可用性及开局配置，再用 `game view` 获取当前面板和真实 ID。`capability list` 新增 `dlc`、`content_available`、`shortcut`：`content_available` 仅表示已声明的内容要求满足，不代表角色境界、道途、事件或资源已满足；`dlc: null` 表示此条没有额外声明内容门禁，仍须通过正式引擎检查。

新增 DLC 命令在内容未启用时拒绝执行，不会自动启用 DLC。普通命令沿用正式消耗、资格、事件和三组操作守卫；变更、RNG 与成就只提交到隔离会话。失败不提交游戏状态，写命令仍记录失败日志并递增会话版本，下一次调用须重新读取版本。Debug 关闭时工具接口返回 404。

`tianji preview` 和 `custom lineage prepare` 是一次性副本预览：不改游戏、随机数、会话版本、日志或快照，也不接受 `request_key`。后者直接返回正式接口的 `monster_bloodline.custom_lineage_editor`，包含可选组件、槽位与功业预算。实际炼制 / 确认仍重新校验正式规则。

文本指令参数按 `help` 顺序填写，省略末尾可选参数，中间使用 `null` 占位。复杂命令优先用具名结构化参数。命令和字段使用源码语义，如 `target_layer_id`、`body_ids`、`forge_kind`，不接受拼音或近义别名。所有 ID 均应来自当前会话面板。

## 新增入口

| 指令 | 正式入口 | 操作 / 参数要点 | 选项来源 |
| --- | --- | --- | --- |
| `buddhist action` | `buddhist-action` | `action`；可选 `blessing`、`authority`、`technique` | `game view /buddhist_system`、已学功法 |
| `guixu action` | `guixu-action` | `action`；可选 `dungeon_id`、`target_layer_id`、`actor_id`、`pool_entry_id`、`confirm_betrayal`、`offer_stones` | `game view /guixu_tide` |
| `asura action` | `asura` | `action`；可选 `target_id`、`body_ids`、`name` | `game view /asura` |
| `tianji action` | `tianji-action` | `action` 为 `activate` / `deactivate`，必填 `artifact_id` | `game view /tianji_artifacts` |
| `tianji preview` | `tianji-preview` | 目标、胎模、四个材料实例 ID，可选 `forge_kind` | 同上及 `game view /crafting_system` |
| `tianji forge` | `tianji-forge` | 同预览参数；实际消耗材料 | 同上 |
| `tianji reveal all` | `tianji-debug-reveal-all` | **调试捷径**：副本内全部神机情报升为 Lv5 | 同上 |
| `sage doctrine` | `sage-doctrine` | `join` / `leave` / `found`；可选 `doctrine_id`、`combo`、`name` | `game view /sage_system` |
| `sage recruitment` | `sage-recruitment` | 可选 `enabled`，省略按正式接口为 `true` | 同上 |
| `sage worship` | `sage-worship` | 必填 `sage_id` | 同上 |
| `sage debate` | `sage-debate` | 必填 `doctrine_id`、`member_id` | 同上 |
| `sage refine manual` | `sage-refine-manual` | 必填 `item_id`，消耗实际玉简 | 同上及 `inventory` |
| `sage outer king` | `sage-outer-king` | `advance` / `combat` / `spirit_stone` / `opportunity` | 同上 |
| `monster evolve` | `monster-evolve` | 必填 `evolution_id` | `game view /monster_bloodline` |
| `custom lineage prepare` | `custom-lineage-prepare` | 必填 `evolution_id`，返回只读立祖编辑器 | 同上 |
| `custom lineage confirm` | `custom-lineage-confirm` | 必填 `evolution_id`、`name`、`rules` | prepare 返回的编辑器 |
| `merchant debug hq` | `merchant-debug-hq` | **调试捷径**：必填 `alliance_id`，副本内获得总部特使身份与影响力 | `game view /merchant_system` |

鬼修与《明争暗斗》的角色操作此前已接入，继续使用 `ghost ...` 和 `intrigue ...` 命令，具体签名见 [完整入口清单](debug-base-coverage.md)。鬼修轮回、依附、魂魄等以及内政任职、客卿、议案、招募无需另一套调用接口。

佛修 `action`：`nirvana`、`blessing`、`temple`、`permission`、`start`、`continue`、`cancel`。常规年度弘法等行动仍通过 `action advance` 调用。

归墟 `action`：`enter`、`team_accept`、`team_decline`、`gift_treasure`、`threat_surrender`、`threat_resist`、`move`、`search`、`return`、`rest`、`fight`、`flee`、`recruit`、`negotiate`、`trapped_cultivate`。关系背叛仍须先请求，再携带 `confirm_betrayal: true` 确认；布尔 `false` 不会被当成 `true`。

修罗 `action`：`purify`、`convert`、`train_body`、`open_vein`、`condense`、`fuse`、`rename`、`train_route`、`choose_branch`、`train_branch`、`train_domain`、`nourish_domain`、`lock_power`、`reroll_power`、`learn_power`。融合的 `body_ids` 为最多两个字符串 ID，重复与资格由正式规则检查；洗练必须整批处理未锁定属性，不能指定单条 `target_id`。

## 示例

可直接在控制台执行的天机调试发现流程：

```text
debug start
capability list
tianji reveal all
game view /tianji_artifacts
game view /crafting_system
```

这会在副本中解锁情报，但不会赠送材料。取得目标和实际材料 ID 后，调用：

```text
tianji preview <target_artifact_id> <mold_id> <primary_id> <secondary_a_id> <secondary_b_id> <quench_id> replica
tianji forge <target_artifact_id> <mold_id> <primary_id> <secondary_a_id> <secondary_b_id> <quench_id> replica
tianji action activate <artifact_id>
```

`forge_kind` 也可为 `true_body`，但必须满足真方、材料、唯一真体和世界法则条件。上述 `<...>` 为占位符，不应原样发送。

儒修开局和创建学说示例：

```text
scenario create "Sage Test" supreme_metal confucian 7301 confucian_core
game view /sage_system
sage doctrine found null '{"classic":"guliang","philosophy":"mind","practice":"statecraft","script":"old_text"}' "New School"
sage recruitment false
```

学说组合必须在当前世界可创立且满足正式条件。`combo` 的四个键固定，值由 `sage_system.combination_choices` 提供。

结构化归墟移动请求（替换会话 ID、版本及实际层 ID）：

```json
{
  "command": "guixu action",
  "arguments": {"action": "move", "target_layer_id": "inner"},
  "session_id": "<session_id>",
  "expected_revision": 12,
  "request_key": "guixu-move-001"
}
```

MCP 工具名为 `cultivation_guixu_action`，参数为上面除 `command` 外的字段。CLI 同样复用具名命令和 JSON 参数；连接及完整用法见 [Debug 开发规范](debug-development.md)。请求超时后仅可使用相同版本、键和参数重试，防止重复消费或重复结算。

自成血脉流程：先 `custom lineage prepare <evolution_id>` 读取编辑器，再提交 `custom lineage confirm`。`rules` 为对象数组，每项只接受 `phase`、`schedule`、`condition`、`target`、`effect`、`value` 六个必填字段；不接收 Python 表达式或任意战斗代码。`value` 必须是真正的数字。已有规则的 `cost`、`description` 是输出字段，重新确认时只提交上述六个输入字段。

```json
{
  "evolution_id": "FOX_NETHER_SELF_1",
  "name": "Test Lineage",
  "rules": [{
    "phase": "round_start", "schedule": "every", "condition": "always",
    "target": "player", "effect": "might", "value": 0.03
  }]
}
```

此例是 `arguments` 对象，适用于已符合立祖条件的狐族角色。组件、档位、槽位、预算及后续阶段旧规则不可修改的限制由原系统校验；旧档补刻沿用正式 ID `__retroactive__`。

## 后续开发与验证

- 继续在 `capabilities.py` 显式登记正式操作、类型化参数、预览属性和 DLC 要求；不新增 Mixin，不往正式引擎添加 Debug 分支。内容判定复用 `debug/dlc.py` 中引用的正式可用性函数。
- 新增 DLC 字段应同步 JSON Schema 与使用文档，不能用任意 `payload` 或方法反射绕过登记。正式模块新增角色 POST 入口时，入口分类测试必须随之通过。
- 新增预览必须能完整返回一次性的业务结果，同时验证成功和失败都不修改会话。普通写操作使用现有隔离事务、版本冲突和幂等重试，不另建存档写通道。
- 本轮验证包括每个新增入口的真实方法签名、DLC 禁用拒绝、纯本体无 DLC 安装、六类 DLC 实际工作流、两条 Debug 捷径、HTTP / Agent 元数据和重试、前置条件拒绝、预算失败与原存档隔离。测试文件为 `tests/test_debug_dlc.py` 与既有 Debug 测试集。

本轮实际验证记录（2026-10-04）：

- 完整 Python 回归分八个独立批次执行：**2,263 通过，0 失败、0 跳过，200.11 秒**。证据：`build/debug-dlc-tests.log`、`debug-dlc-part-*.xml`。
- 新增 DLC 专项 **26 通过，36.95 秒**，包含全部新增入口的实际调用与内容禁用检查。专项用例也包含在完整回归中，不重复累计。证据：`build/debug-dlc-workflows-final.log`。
- 浏览器六主题、桌面 / 竖屏 / 横屏通过，包含新增天机情报指令、DLC 面板读取、能力清单，以及原有快照、补全、导出、双标签页隔离和关闭恢复流程。证据：`build/debug-dlc-browser.log`。
- 依赖检查 **336 个模块、1,842 条边，0 循环、0 边界违规**。证据：`build/debug-dlc-dependencies.json`。静态未定义名称、52 份 Markdown 链接与版本检查、差异空白检查通过。
- 未修改正式玩法实现、存档结构或发行版本；未进行 Android 设备验收或重新打包。验证结论限定于以上源码与测试范围。
