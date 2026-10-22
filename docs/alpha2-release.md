# v3.0.0-alpha.2 发行范围

本体 v3.0.0-alpha.2，Android versionCode 75；归墟之潮2.7.2、神机百变2.2.1。仅支持结构10，结构1–9不迁移。用户明确要求仅关键测试，不执行全仓回归；实际通过范围、源码摘要和包哈希以 `dist/` 同版发行清单为准。

## 战报表现

可选新版使用24套人物与妖兽素材，每方最多显示三人；优先选择合法且不重复的立绘，再复用已上场素材。普通回合顺序、先手、态势扣减与恢复读取原权威战报；仅邻域阶段不播动画，其后的普通交锋仍播放。六种单／多人战场只读取原地形，不修改地址或结算。

倒地素材采用显式尺寸基准，不将蹲伏或倒地包围盒放大到站姿高度。败方最后出手时，补接胜方本场已有普通动作作为只读收势，接触后倒地；没有胜方普通行动事实时不虚构击倒。关闭释放画布、解码缓存与帧循环，重播不写存档。战报弹窗身份包含原存档与完整报告，避免不同存档的同名战报或同年同轮新交锋被误认成旧报告。

## DLC 修复

归墟440件物品的说明由目录定义与共享公式生成，逐件列出携带属性、服用恢复、机缘与炼器用途。原有服用、炼器数值不变，不额外实现名称暗示的延寿等效果；原目录同步入口更新结构10旧档说明，不改数量或养成。百科同步说明用途，关闭DLC仍保留原物品及中性图标回退。

神机情报只在玩家真实战斗完成后、原死亡与掉落处理前增加。完整实际敌方名单中的真体或仿制品持有者均计入，同一场每件神机增加一级，最高Lv5；击杀掉落的原最低情报等级保留。移除战前注入装备即固定补到Lv2的旧逻辑。预览、刷新、重播、拒绝开战及后台NPC交战不增加。使用原知识与发现日志字段，不新增持久状态，不改NPC所有权、物资、移动、时间、RNG或经济公式。

## 验证与打包

动画使用兼容旧WebView的数组索引与查找，不依赖 `Array.at` 或 `Array.findLast`。浏览器专项显式移除这两个方法再进行真实点击，Android 12原生验收使用WebView 91，避免只在现代桌面浏览器验证。

`combat-alpha` 是独立的相关领域发行配置，不降低原 `visual` 全仓发行门槛。覆盖DLC、战斗、阵法、炼器、素材、前端偏好、跨界上游、旧事件、存档互通及打包守卫。四组浏览器分别验证本轮DLC实操、普通战报、多人战报和旧事件真实加载／提交。

Windows 同一EXE分别在有／无DLC隔离目录点击验收；签名Android 12在隔离模拟器横竖屏验证四主题、真实服用／截杀、真品／仿制品情报、三对三战败与播放器释放。模拟器验收不等于ARM实体机验收。最终凭证必须对应最终源码与最终APK／EXE；不借用alpha.1凭证，不打包用户存档或机器偏好。

```powershell
python scripts/verify_scoped_release.py --profile combat-alpha --shards 3 --workers 1
python -m pytest tests/test_save_transfer.py -q
python -m PyInstaller build/launcher.spec --noconfirm
python scripts/verify_combat_alpha_exe.py
./scripts/build_android.ps1 -Configuration Release -IncludeTests
./scripts/verify_android_combat_alpha.ps1 -Serial emulator-5580
python scripts/verify_android_scoped.py emulator-5580 --combat-alpha
python scripts/package_scoped_release.py
```
