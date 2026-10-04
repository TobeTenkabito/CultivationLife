# Debug 本体通用功能覆盖清单

维护基线：本体 **1.58.0**，存档结构 **8**。当前共有 **178 个命令/工具**，其中 **135 个现有角色操作入口**已具名接入。它们覆盖本体通用玩法及当前全部 DLC 的角色操作入口；专属指令详见 [DLC 指令清单](debug-dlc-coverage.md)。使用与开发约定见 [开发规范](debug-development.md)。

## 如何理解覆盖范围

覆盖是“可以通过控制台、结构化 API、CLI 或 MCP 调用同一正式操作”，不是直接写所有模型字段，也不是跳过资格与剧情。读档准备、随机、年龄、费用、死亡、拘禁、关系和跨界都由既有规则处理。

| 系统 | 已覆盖的操作链 | 发现当前选项 |
| --- | --- | --- |
| 开局与现场 | 复制存档、新建隔离角色、固定种子、命名快照、恢复、差异、复现导入导出 | `scenario list`、`save list`、`debug sessions` |
| 玩家与修炼 | 数据修改、正常行动、修为/炼体/神识突破、秘法、道统、元府 | `player fields`、`game view /breakthrough`、`game view /secret_arts` |
| 功法、物品、本命法宝 | 使用、装备、升级、玉简合并、变身、本命法宝绑定与养成 | `game view /player/known_techniques`、`game view /natal_artifact` |
| 地图与跨界 | 普通旅行、传送、跨界、灵界与两类上界飞升 | `game view /map`、`game view /world_travel` |
| 商业 | 坊市购买/锁定、拍卖、寄售、匿名身份、私下交易、交换会、黑市、商盟委托 | `game view /market`、`game view /auction_system`、`game view /merchant_system` |
| 生产 | 灵田开垦/种植/灌溉/收获、灵植使用、炼丹、炼器预览/图谱/制作、阵法与地阵、机械傀儡 | `game view /spirit_field`、`game view /crafting_system`、`game view /formation_system` |
| NPC 与关系 | 交往、道友/道侣、师徒、请求/馈赠、组队、退出关系、真实俘虏及侍妾流程 | `npc find "" 0`、`game view /world_npcs`、`game view /dao_companion` |
| 宗门、家族与政治 | 建立组织、奖励、继承、派遣、关系任职、家族决策、外交、战争、议和、悬赏、内政 | `game view /faction`、`game view /family`、`game view /war_system`、`game view /intrigue_system` |
| 上界通用玩法 | 仙界养成、天庭、瑶池、三界机构及本体 voisinage | `game view /doctrines`、`game view /aperture`、`game view /upper_voisinages`、`game view /upper_institution` |
| 教程、展示、战斗设置 | 教程操作、消息设置、世界纪事开关、手动战斗预案 | `game view /tutorial`、`game view /settings`、`game view /combat_plan` |

`game view` 会像游戏界面一样整理并提交副本状态，属于写入操作。用于查看原始保存数据的 `state get` 是纯查询。六类制作/委托/立祖预览标为 `preview`，只在一次性临时存储内计算，不修改会话文件。

正文中的 `<参数>` 为必填，`[参数]` 为可选，均以运行时 `help` / JSON Schema 为准。文本模式按顺序提供参数；省略末尾可选参数，中间使用 `null` 占位。结构化调用可直接按字段名提供。参数名称保持正式 API/模型语义，完整 JSON 对象字段、数值范围和枚举由 `tools/list` 返回。

## 已接入的角色操作

以下是角色级 POST 入口的逐项映射。普通存档删除、覆盖导入、扩展开关、操作系统文件访问和发布操作不属于角色玩法能力；工具不提供它们。创建测试角色使用 `scenario create`，复制/复现使用独立会话流程。

<!-- The reviewed command mapping below is checked against server routes by tests. -->

| 控制台指令 | 正式操作入口 | 类型 |
| --- | --- | --- |
| `action advance <action> <units>` | `advance` | simulation |
| `event choose <choice_id>` | `choice` | simulation |
| `npc contact <npc_id> <action>` | `npc-contact` | simulation |
| `relationship violence <kind> <target_id> [capture]` | `relationship-violence` | simulation |
| `doctrine action <action> [doctrine_id] [manual_id] [confirm_origin] [npc_id]` | `doctrine-action` | simulation |
| `aperture action <action> [manual_id]` | `aperture-action` | simulation |
| `upper institution <action> [target_id]` | `upper-institution` | simulation |
| `upper voisinage <action> [voisinage_id]` | `upper-voisinage` | simulation |
| `immortal action <action> [doctrine_id] [axis] [supply_id]` | `immortal-action` | simulation |
| `yaochi action <action> [target_id] [amount]` | `yaochi-action` | simulation |
| `item use <item_id>` | `use-item` | simulation |
| `faction reward <reward_id>` | `faction-reward` | simulation |
| `faction succession` | `faction-succession` | simulation |
| `market buy <offer_id>` | `market-buy` | simulation |
| `market lock <offer_id>` | `market-lock` | simulation |
| `market sell plant <item_id>` | `market-sell-plant` | simulation |
| `auction consign <item_id> [start_price]` | `auction-consign` | simulation |
| `auction bid <lot_id>` | `auction-bid` | simulation |
| `auction advance` | `auction-advance` | simulation |
| `auction negotiate <npc_id>` | `auction-negotiate` | simulation |
| `auction identity <alias>` | `auction-identity` | simulation |
| `exchange action <action> [alias] [offer_id] [materials]` | `exchange-action` | simulation |
| `merchant action <action> [alliance_id] [task_id] [destination] [kind] [stars] [quantity] [source_world] [material_category] [definition_id] [target_id] [principal] [material_tier] [mold_id] [metrics] [metric_maxima] [preview_token]` | `merchant-action` | simulation |
| `merchant preview [alliance_id] [task_id] [destination] [kind] [stars] [quantity] [source_world] [material_category] [definition_id] [target_id] [principal] [material_tier] [mold_id] [metrics] [metric_maxima] [preview_token]` | `merchant-preview` | preview |
| `auction private buy <npc_id> <offer_id>` | `auction-private-buy` | simulation |
| `auction private sell <npc_id> <item_id>` | `auction-private-sell` | simulation |
| `auction private bargain <npc_id> <side> <asset_id>` | `auction-private-bargain` | simulation |
| `transformation absorb <item_id> [stat_id]` | `transformation-absorb` | simulation |
| `transformation purify <item_id> [stat_id]` | `transformation-purify` | simulation |
| `transformation batch <item_id> [mode] [stat_id]` | `transformation-batch` | simulation |
| `setting set <setting> [enabled]` | `settings` | simulation |
| `combat plan [stance] [investment] [burst] [mp_reserve] [transformations] [support_guard]` | `combat-plan` | simulation |
| `tutorial <action> [step] [target_id]` | `tutorial` | simulation |
| `black market search <pattern>` | `black-market-search` | simulation |
| `black market buy <result_id> [quantity]` | `black-market-buy` | simulation |
| `black market sell <kind> <asset_id>` | `black-market-sell` | simulation |
| `spirit field reclaim` | `spirit-field-reclaim` | simulation |
| `spirit field plant <plant_id> [slot]` | `spirit-field-plant` | simulation |
| `spirit field irrigate <plot_id> [mp_amount] [booster_id]` | `spirit-field-irrigate` | simulation |
| `spirit field harvest <plot_id>` | `spirit-field-harvest` | simulation |
| `alchemy refine <target_item_id> <materials>` | `alchemy` | simulation |
| `crafting preview <mold_id> <primary_id> <secondary_a_id> <secondary_b_id> <quench_id> <allocations> [name] [blueprint_name]` | `crafting-preview` | preview |
| `crafting forge <mold_id> <primary_id> <secondary_a_id> <secondary_b_id> <quench_id> <allocations> [name] [blueprint_name]` | `crafting-forge` | simulation |
| `crafting blueprint <mold_id> <primary_id> <secondary_a_id> <secondary_b_id> <quench_id> <allocations> [name] [blueprint_name]` | `crafting-blueprint` | simulation |
| `crafted artifact <artifact_id> <action> [start_price]` | `crafted-artifact` | simulation |
| `formation preview <slots> [name] [loadout_id] [activate]` | `formation-preview` | preview |
| `formation save <slots> [name] [loadout_id] [activate]` | `formation-save` | simulation |
| `formation activate <formation_id>` | `formation-activate` | simulation |
| `formation deactivate` | `formation-deactivate` | simulation |
| `formation delete <formation_id>` | `formation-delete` | simulation |
| `formation ground deploy [owner_kind]` | `formation-ground-deploy` | simulation |
| `formation ground withdraw <ground_formation_id>` | `formation-ground-withdraw` | simulation |
| `formation ground repair <ground_formation_id> [supply_id] [quantity]` | `formation-ground-repair` | simulation |
| `spirit plant use <item_id>` | `spirit-plant-use` | simulation |
| `black market leave` | `black-market-leave` | simulation |
| `teleport action <action> [destination]` | `teleport-action` | simulation |
| `map travel <destination>` | `map-travel` | simulation |
| `technique equip <technique_id> <slot>` | `equip-technique` | simulation |
| `technique upgrade <technique_id>` | `technique-upgrade` | simulation |
| `technique manual merge <technique_id> [level]` | `technique-manual-merge` | simulation |
| `transformation <form_id> <action>` | `transformation` | simulation |
| `body breakthrough` | `body-breakthrough` | simulation |
| `sense breakthrough` | `sense-breakthrough` | simulation |
| `secret art <art> <action> [realm_index] [layer]` | `secret-art` | simulation |
| `ghost reincarnate` | `ghost-reincarnate` | simulation |
| `ghost reincarnation prompt` | `ghost-reincarnation-prompt` | simulation |
| `ghost wangsheng [all]` | `ghost-wangsheng` | simulation |
| `ghost parade <soul_id> <action>` | `ghost-parade` | simulation |
| `ghost soul <soul_id> <action> [slot]` | `ghost-soul` | simulation |
| `ghost attachment <action> [item_id]` | `ghost-attachment` | simulation |
| `ghost constraint <action>` | `ghost-constraint` | simulation |
| `ghost leave host` | `ghost-leave-host` | simulation |
| `post battle possession [target_id]` | `post-battle-possession` | simulation |
| `captive action <target_id> <action>` | `captive-action` | simulation |
| `concubine action <target_id> <action>` | `concubine-action` | simulation |
| `concubine status <action>` | `concubine-status` | simulation |
| `relationship capture <kind> [target_id]` | `relationship-capture` | simulation |
| `owned training <target_id> <kind> [axis] [batches]` | `owned-training` | simulation |
| `puppet action <puppet_id> <action> [content_id]` | `puppet-action` | simulation |
| `puppet preview <form> <core> <shell> <energy>` | `puppet-preview` | preview |
| `craft puppet <form> <core> <shell> <energy>` | `craft-puppet` | simulation |
| `refine souls` | `refine-souls` | simulation |
| `secluded refine souls` | `secluded-refine-souls` | simulation |
| `faction dispatch <target>` | `faction-dispatch` | simulation |
| `faction relationship <npc_id> <role>` | `faction-relationship` | simulation |
| `party <npc_id> <action>` | `party` | simulation |
| `dao companion <action> [npc_id] [kind] [content_id]` | `dao-companion` | simulation |
| `dao friend <npc_id> <action>` | `dao-friend` | simulation |
| `relationship faction <npc_id>` | `relationship-faction` | simulation |
| `relationship exit <kind> <npc_id>` | `relationship-exit` | simulation |
| `leave faction` | `leave-faction` | simulation |
| `prison action <action>` | `prison-action` | simulation |
| `disciple request <request_id> [accept]` | `disciple-request` | simulation |
| `master request <kind>` | `master-request` | simulation |
| `disciple gift <disciple_id> <kind> [content_id]` | `disciple-gift` | simulation |
| `spirit crossing` | `spirit-crossing` | simulation |
| `celestial ascension` | `celestial-ascension` | simulation |
| `asura ascension` | `asura-ascension` | simulation |
| `heavenly election [method] [pledge_id]` | `heavenly-election` | simulation |
| `heavenly court <action> [target_id] [enact] [influence_spend]` | `heavenly-court` | simulation |
| `natal artifact <action> [item_id] [slot_index]` | `natal-artifact` | simulation |
| `cross world <destination>` | `cross-world` | simulation |
| `create faction <name>` | `create-faction` | simulation |
| `create family <name>` | `create-family` | simulation |
| `family action <action> [npc_id] [technique_id] [item_id] [enabled] [partner_id] [sect_id] [target_id] [status] [amount]` | `family-action` | simulation |
| `race diplomacy <target_id> <status>` | `race-diplomacy` | simulation |
| `faction diplomacy <target_id> <status>` | `faction-diplomacy` | simulation |
| `vassal transfer <kind> <target_id> <npc_id>` | `vassal-transfer` | simulation |
| `war action <war_id> <action> [ally_id]` | `war-action` | simulation |
| `war peace <war_id> [term] [target_id] [target_power_id] [third_party_id] [third_status] [concede]` | `war-peace` | simulation |
| `issue bounty <npc_id> <authority>` | `issue-bounty` | simulation |
| `faction intercept <npc_id>` | `faction-intercept` | simulation |
| `intrigue personnel <kind> <action> <npc_id> [position_id] [years] [reason]` | `intrigue-personnel` | simulation |
| `intrigue guest <kind> <action> <npc_id>` | `intrigue-guest` | simulation |
| `intrigue resolution <kind> <resolution_type> [target_id] [player_vote]` | `intrigue-resolution` | simulation |
| `intrigue recruitment <action> [filters] [candidate_ids] [player_vote]` | `intrigue-recruitment` | simulation |
| `breakthrough attempt` | `breakthrough` | simulation |
| `world news set [enabled]` | `debug-world-news` | simulation |
| `buddhist action <action> [blessing] [authority] [technique]` | `buddhist-action` | simulation |
| `guixu action <action> [dungeon_id] [target_layer_id] [actor_id] [pool_entry_id] [confirm_betrayal] [offer_stones]` | `guixu-action` | simulation |
| `asura action <action> [target_id] [body_ids] [name]` | `asura` | simulation |
| `tianji action <action> <artifact_id>` | `tianji-action` | simulation |
| `tianji preview <target_artifact_id> <mold_id> <primary_id> <secondary_a_id> <secondary_b_id> <quench_id> [forge_kind]` | `tianji-preview` | preview |
| `tianji forge <target_artifact_id> <mold_id> <primary_id> <secondary_a_id> <secondary_b_id> <quench_id> [forge_kind]` | `tianji-forge` | simulation |
| `tianji reveal all` | `tianji-debug-reveal-all` | simulation |
| `sage doctrine <action> [doctrine_id] [combo] [name]` | `sage-doctrine` | simulation |
| `sage recruitment [enabled]` | `sage-recruitment` | simulation |
| `sage worship <sage_id>` | `sage-worship` | simulation |
| `sage debate <doctrine_id> <member_id>` | `sage-debate` | simulation |
| `sage refine manual <item_id>` | `sage-refine-manual` | simulation |
| `sage outer king <action>` | `sage-outer-king` | simulation |
| `monster evolve <evolution_id>` | `monster-evolve` | simulation |
| `custom lineage prepare <evolution_id>` | `custom-lineage-prepare` | preview |
| `custom lineage confirm <evolution_id> <name> <rules>` | `custom-lineage-confirm` | simulation |
| `merchant debug hq <alliance_id>` | `merchant-debug-hq` | simulation |

当前全部角色操作入口均已接入，`EXCLUDED_OPERATIONS` 为空。两条调试捷径在帮助和能力清单中显式标记；完整参数语义、DLC 门禁、预览约定和示例见 [DLC 指令清单](debug-dlc-coverage.md)。

## 验证与实际边界

自动检查对照全部角色操作分支，拒绝漏记的入口；逐项绑定实际引擎方法签名及参数类型。另有真实工作流、失败回滚、纯本体安装、HTTP/Agent 和浏览器检查。入口级覆盖不替代每个 DLC 与所有玩法分支的专项测试。
