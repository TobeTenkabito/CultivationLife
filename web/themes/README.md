# 双像素主题维护

当前仅支持「山海图志」浅色与「沧海夜色」暗色，共用像素布局。内部布局标识固定为 `theme=a`、`pixel_art=true`，只允许通过 `pixel_theme` 选择浅暗配色；旧文字主题及关闭像素界面的请求继续拒绝，旧偏好不能恢复退役布局。规则见[3.5.0发行说明](../../docs/release-350.md)。

`common.css`、`composition.css` 和 `pixel-base.css` 维护共用控件及布局；`theme-manager.js` 与 `theme-composition.js` 呈现玩家数据、排列原有节点；`pixel-home.js`、`pixel-home.css` 与 `pixel-dark.css` 维护像素绘景及浅暗配色。素材来源与限制见[像素素材与主界面](../../docs/visual-assets.md)。

新增功能窗口使用 `--surface`、`--ink`、`--muted`、`--line`、`--pine`、`--on-accent` 等语义颜色；风险使用 `--cinnabar`，法力使用 `--info`。DLC 侧栏使用 `data-dlc` 对应色相并保留标识。验证两套配色及桌面、手机横竖屏，不再添加旧主题 b–f 的选择器。

人物详情沿现有 `.hud-identity` 及资源入口打开。教程定位现有可见控件，不创建备用旧布局按钮。主题组件不复制游戏行为、不修改角色存档；布局调整必须保留操作节点、键盘导航和禁用状态。

主题偏好通过 `/api/ui-preferences` 独立存储；浏览器缓存仅用于首次绘制。切换不得调用推进时间、消耗资源或重建游戏表单的接口。动效服从系统和游戏内减弱动态设置。

2026-11-05清理：移除六份面板样式中31处退役主题选择器、未挂入页面的旧侧栏容器和详情按钮及其备用教程定位；保留存档悬停等共用规则、固定布局标识和两套像素配色。没有玩家移动、持久字段、结算或存档格式改动。

当前验收入口为 `python tests/browser_pixel_only.py`、`python tests/browser_tutorial_interface.py` 和 `python -m pytest tests/test_ui_preferences.py tests/test_tutorial.py tests/test_tutorial_walkthrough.py -q`。旧四主题浏览器脚本仅保留作历史记录，不作为当前验收依据。正式发行仍需完成发行脚本要求的双端验收。
