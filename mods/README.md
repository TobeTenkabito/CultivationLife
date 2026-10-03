# MOD 内容包

> 源码维护基线：本体 v1.56.2，2026-10-04；存档结构 7 支持 6→7，结构 1–5 不再加载。扩展版本以各包目录的 manifest.json 为准；旧档字段补全不扩大本体兼容范围。

把每个 MOD 放在 `mods/` 下的独立子目录。系统会在启动时扫描 `manifest.json`，不执行 MOD 中的 Python、JavaScript 或其他代码，只读取 `content/*.json`，因此 MOD 与本体逻辑保持低耦合。

```text
mods/
  my-balance-mod/
    manifest.json
    content/
      items.json
      market.json
      my_events.json
```

最小清单：

```json
{
  "schema_version": 1,
  "api_version": 1,
  "id": "author.my-balance-mod",
  "name": "我的平衡 MOD",
  "version": "1.0.0",
  "kind": "mod",
  "enabled": true,
  "load_order": 100,
  "requires": []
}
```

支持的文件名为本体同名数据表、`events.json` 或任意以 `_events.json` 结尾的事件表。MOD 在全部 DLC 之后加载，因此可以覆盖本体或 DLC 的同 ID 数据。建议所有新增 ID 使用作者前缀，避免与其他 MOD 冲突。

扩展管理器的选择写入 `data/extension_preferences.json`，优先于清单 `enabled`；变更后需要停止并重启服务。只改清单不能覆盖已保存的玩家选择。依赖项填写其他扩展的 ID。依赖未启用、JSON 损坏或跨表引用不合法时，该 MOD 会显示为“加载失败”并被跳过，不会污染此前已经验证通过的本体及扩展内容。
