# DLC 内容包

自本体 v1.34.0 起，官方 DLC 不再提供界面或地域地图；全部地理内容位于本体 `content/world.json` 与 `content/maps.json`。专属副本、剧情、道途与特色功能仍由各 DLC 独立提供。

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
`monster_bloodlines.json`、`sage_way.json` 与 `guixu_tide.json`。具体物种、
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
