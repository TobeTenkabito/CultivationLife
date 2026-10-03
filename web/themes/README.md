# 六主题维护

六套主题共享玩法并各自维护布局。新增公共交互应验证六主题及窄屏；不能将 B–F 改造成 A 的换色模板。六套主界面的原始设计来源是本机 `design/main-ui-concepts-20260927-r3`；该目录被 Git 忽略，干净检出不保证带有原稿，对照脚本需要自行具备该资源。`common.css` 定义共享控件、侧栏与对话框，`composition.css` 定义六套原稿共用的文字层级和操作语义，`theme-composition.js` 为各主题独立排列已有节点；`a.css` 至 `f.css` 各自维护配色、主布局、装饰和动效。

新增功能窗口应使用 `--surface`、`--ink`、`--muted`、`--line`、`--pine`、`--on-accent` 等语义颜色；风险使用 `--cinnabar`，法力使用 `--info`。不要直接写白底、黑字或假定所有主题的强调色均为深色。DLC 侧栏使用 `data-dlc` 对应色相并保留标识。

`theme-manager.js` 只移动已有操作节点和呈现玩家数据，不复制游戏行为或修改存档。完整人物卡保留原 ID 并放入原生对话框。新增人物关键资源时同步考虑 HUD、精确数值提示和窄窗口布局。

主题偏好通过 `/api/ui-preferences` 独立存储；浏览器缓存仅用于首次绘制。主题切换不得调用推进时间、消耗资源或重建游戏表单的接口。新动效必须服从系统和游戏内减弱动态设置。

恢复验收：`python tests/browser_composition_1391.py`，输出主界面截图与原 SVG 对照页。

验收：`python tests/browser_themes_139.py`，以及相关功能浏览器回归。完整回归使用 `python -m pytest tests -q`。打包验收使用 `python scripts/verify_release_exe.py`。
