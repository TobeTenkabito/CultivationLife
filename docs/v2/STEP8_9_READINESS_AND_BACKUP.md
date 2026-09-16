# 第8、9步：功能矩阵门禁与导入前备份

## 第8步：可执行功能矩阵

功能矩阵位于`docs/v2/feature_matrix.json`。它不是进度说明的副本，而是正式切换的机器门禁。

当前规则：

1. 冻结清单中的101个V1公开操作必须全部出现；
2. 每个公开操作必须且只能归属于一个功能项；
3. 功能项状态只能是`pass`、`partial`、`missing`或`retired`；
4. `pass`必须提供仓库内真实存在的测试证据；
5. `retired`必须提供明确的废弃决策记录并显式标记为非切换必需项；
6. 任一切换必需项不是`pass`时，正式切换必须失败；
7. 矩阵结构错误、证据路径失效、遗漏或重复操作同样阻止切换。

普通审计：

```powershell
python tools/check_v2_readiness.py --report build/v2-readiness.json
```

正式切换或CI必须使用严格门禁：

```powershell
python tools/check_v2_readiness.py --require-ready
```

当前矩阵包含53个功能项：9项`pass`、11项`partial`、33项`missing`，共44个切换阻断项。矩阵自身结构完整，101个公开操作覆盖率为101/101，但玩法尚未平价，因此本轮没有切换启动器或正式前端。

后续根因审计和两批迁移已将当前状态推进到15项`pass`、13项`partial`、25项`missing`，共38个阻断项；最新结果及分组见`docs/v2/BLOCKER_AUDIT_AND_VALIDATION.md`。本段的44项数字保留为第8、9步完成时的历史快照。

更新矩阵时不能只改状态。对应功能必须先具备行为规格、权威状态、命令/事件/投影、不变量、失败原子性和测试证据，再将状态改为`pass`。影子运行覆盖仍为`partial`，需要随着公共命令适配器扩展逐步转绿。

## 第9步：旧存档导入前强制备份

`V2GameEngine.import_v1_save()`现在按照以下顺序执行：

```text
读取并哈希源文件
  → 校验和构造V2状态
  → 运行全部V2不变量
  → 再次读取源文件并确认哈希未变化
  → 持久化只读备份并fsync
  → 写入V2 SQLite事务
```

默认备份目录是V2数据库旁的`legacy-v1-backups/`。备份名称由安全化的源文件名和SHA-256前缀组成，以`.v1.json`结尾。同一内容已有备份时只校验并复用，不覆盖、不改写时间戳。

命令行可显式指定目录：

```powershell
python tools/import_v1_save.py data/saves/<存档ID>.json `
  --database data/v2/saves.sqlite3 `
  --backup-directory data/v2/legacy-v1-backups `
  --report data/v2/import-reports/<存档ID>.json
```

安全保证：

- 备份失败时不会创建V2目标存档；
- V2数据库写入失败时，已经成功落盘的备份仍然保留；
- 源文件在初次校验与备份之间发生变化时会终止导入；
- 导入报告和V2审计组件记录备份绝对路径、哈希以及本次是否新建；
- V2只读V1 JSON，不提供V2到V1写回、覆盖或降级保存功能。

自动备份保护的是单次导入，不等于已经允许删除整个V1存档目录。只有第8步门禁全绿、正式切换验证完成后，才能另行决定旧运行时和旧存档的保留策略。
