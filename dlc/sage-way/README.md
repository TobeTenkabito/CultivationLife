# 圣人之道：内圣外王

当前扩展版本 **1.4.0**，本体维护基线 v1.58.0，2026-10-04。存档结构 8 支持 6→7→8；版本与默认启用状态见 [manifest.json](manifest.json)。

提供儒修教化、学说、门人、经典、内圣外王，以及人界结丹和灵界炼虚的专属剧情。普通物品与功法定义归本体，专属配置和事件由本包提供。

配置入口为 `content/sage_way.json`，规则位于 `cultivation_life/system/sage_system.py`。当前 `SageSystemMixin` 仍是引擎直接基类之一；后续拆分应先界定年度收益、门人更新与操作提交的边界，不能只移动文件并改变结算顺序。

扩展开关在重启后生效，以实际加载状态为准；新规则须通过内容校验、相关系统测试及 [依赖检查](../../tools/check_module_dependencies.py)。
