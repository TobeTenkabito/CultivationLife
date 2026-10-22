# v3.0.0-alpha.3 发行范围

本体 v3.0.0-alpha.3，Android versionCode 76，存档结构10。结构1–9仍不兼容；不迁移用户存档，不更改DLC版本。

## 本轮功能与修复

魔修男女头像和详情立绘、43位已采用固定NPC与16套通用NPC社交素材、宗门门人及主角头像进入运行资源。望舒重绘仍待采用，不混入发行包；三位女性美术覆盖仅按此前确认登记，不修改游戏性别。

设置提供13种邻域轮廓和内部意象、6款控制外观、内置取色器及HEX输入。烛时之轮采用烛龙盘轮意象。偏好由本机存档共用，显式保存，NPC按新战斗抽淡色并随战报保存。本版正式接入邻域战报回放：展开／维持、覆盖相持、支配、特殊介入、实际施权、收域以及普通交锋依真实记录顺序播放；纯邻域战斗也可播放，后台战斗不启动动画。

多人场域收域时只淡出实际结束的场，维持中的场与控制保留；六人场景已纳入浏览器检查。

复核修复轮廓相位及边缘装饰误随内部意象变化的问题。预览人物从主角合法公开身份选取道修／魔修男女，未覆盖身份明确为示意；不改身份、属性、时间或战斗能力。

## 发行验收

按用户本轮明确要求，不做全仓回归；采用 `visual --focused-visual` 改动领域与必要上游配置，追加NPC社交、邻域编辑器、真实邻域战报、普通战报及多人战报浏览器验证。Windows同一EXE在有／无DLC隔离环境实际点击头像、人物卡、设置、取色保存与重载；Android 12签名包横竖屏验证同类入口、真实互相支配战报、态势终值、重播释放和布局。最终通过数量、源码摘要、成品哈希以同版 `dist/release-*.json` 为准；模拟器验收不等于实体机验收。

```powershell
python scripts/verify_scoped_release.py --profile visual --focused-visual --shards 3 --workers 3
python -m pytest tests/test_save_transfer.py -q
python -m PyInstaller build/launcher.spec --noconfirm
python scripts/verify_visual_exe.py
./scripts/build_android.ps1 -Configuration Release -IncludeTests
./scripts/verify_android_visual.ps1 -Serial emulator-5580
python scripts/verify_android_scoped.py emulator-5580 --visual
python scripts/package_scoped_release.py
```

## 临时素材清理

仅删除本轮开发预览的可重建截图及中间展示图，按清单核对工作区内绝对路径。保留已采用源图、运行素材、来源哈希、复核脚本和本次最终发行证据，不打包工作区的设计演示或用户存档。实际清单记录于 `build/alpha3-cleanup.json`。
