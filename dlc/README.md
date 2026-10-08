# DLC 内容包

> 源码维护基线：本体 v1.58.0，2026-10-04；存档结构 8 支持 6→7，结构 1–5 不再加载。扩展版本以各包目录的 manifest.json 为准；旧档字段补全不扩大本体兼容范围。

官方 DLC 不再提供界面或地域地图；全部地理内容位于本体 `content/world.json` 与 `content/maps.json`。专属副本、剧情、道途与特色功能仍由各 DLC 独立提供。

通用功法、装备、法宝、丹药、药材、炼器及阵法材料、补灵根书卷及其常规交易来源也由本体提供。官方 DLC 负责专属功能与特殊剧情；剧情信物、鬼修魂器、夺舍专法、神机专材等特色系统必需品可留在包内。归墟副本宝池仍由 DLC 配置，但通用奖品引用本体定义，并可从本体市场获取；其条目归属为 `exclusive_source=base`。

每个 DLC 使用独立子目录，删除整个 `dlc` 目录不会影响本体启动。DLC 只通过 JSON 内容层接入，不应修改本体 Python 或前端文件。

目录示例：

```text
dlc/
  ghost-cultivation/
    manifest.json
    content/
      items.json
      techniques.json
      ghost_events.json
```

系统型 DLC 还可以提供本体已声明为可选扩展点的内容表，例如
`monster_bloodlines.json`、`sage_way.json`、`guixu_tide.json` 与 `buddhist_way.json`。具体物种、
圣道条目与归墟副本/宝池仍属于 DLC；本体只保留
通用的读取、存档兼容与运行时接口。

`manifest.json`：

```json
{
  "schema_version": 1,
  "api_version": 1,
  "id": "official.ghost-cultivation",
  "name": "鬼修道途",
  "version": "1.0.0",
  "kind": "dlc",
  "enabled": true,
  "load_order": 100,
  "requires": [],
  "description": "独立的鬼修功法与事件线"
}
```

扩展内容文件采用与 `content/` 相同的 `schema_version: 1` 格式。带 `id`、`event_id` 或坊市复合键的数组按键合并；同键内容覆盖旧字段。普通数组默认整体替换，也可显式使用 `{"$replace": [...]}`。在带键数组中写入同键条目并增加 `"$delete": true` 可以移除该条目。

加载顺序固定为：本体 → DLC → MOD；同类扩展按 `load_order` 和 ID 排序。未启用、依赖缺失或内容校验失败的 DLC 会被跳过，本体继续运行。

玩家可以在初始主界面右上角展开“DLC / MOD”管理器。开关保存在程序目录的
`data/extension_preferences.json`，优先于清单中的默认 `enabled`，并在下次启动时生效；
扩展包的 `manifest.json` 不会被改写，更新或替换内容包时也不会丢失玩家选择。

诸法无我：众生为镜提供愿力、清净持守、涅槃与高阶弘法威慑。轮回界地图、宗门、商货和通用飞升入口属于本体，关闭 DLC 后仍然存在。

## 当前官方包

八个包的默认启用状态、加载次序和版本以清单为准。

| 包 | 版本 | ID |
| --- | --- | --- |
| [修罗显圣：无法无天](asura-manifestation/README.md) | 1.2.0 | `official.asura-manifestation` |
| [诸法无我：众生为镜](buddhist-dharma/README.md) | 1.0.0 | `official.buddhist-dharma` |
| [百鬼夜行：往生轮回](ghost-reincarnation/README.md) | 3.8.0 | `official.ghost-reincarnation` |
| [归墟之潮：九死一生](guixu-tide/README.md) | 2.6.0 | `official.guixu-tide` |
| [明争暗斗：合纵连横](intrigue-coalitions/README.md) | 1.3.0 | `official.intrigue-coalitions` |
| [万妖归宗：血脉进化](monster-bloodlines/README.md) | 4.14.1 | `official.monster-bloodlines` |
| [圣人之道：内圣外王](sage-way/README.md) | 1.4.0 | `official.sage-way` |
| [神机百变：巧夺天工](tianji-artifacts/README.md) | 2.2.0 | `official.tianji-artifacts` |
