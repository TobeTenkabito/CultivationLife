# 浮生问道 · Android

维护基线：本体 **v3.2.1**，Android **3.2.1-android.84**，versionCode **84**。沿用正式包名与签名；本次仅相关领域、浏览器及签名Android 12原生验收。实际验收以同版发行证据为准，见[版本说明](../docs/soul-lifecycle.md)。

本轮验证原四主题、主角与NPC人物卡、30款邻域轮廓素材及按道途开放的编辑器、真实战斗回放、妖修八族分境外观、鬼儒佛角色和主页五种地图视图。签名Android 12横竖屏使用隔离模拟器真实点击，并核对关闭后资源释放；Windows同一EXE有／无DLC分别验收。绘景仍在默认收起的左侧抽屉，不挤占首屏行动；新版界面默认关闭，可由玩家选择启用。

v2.17.2 使用 building-visits 相关领域配置，不做全仓：公共设施、年度城市经营、专属景色故事与有限遗物，以及原建筑、产业、佛寺和旧事件页面；同版 Windows EXE 有／无 DLC，签名 Android 12 的 building-visits / economy-enterprises 横竖屏四主题原生验收。最终范围以同版清单为准。

v2.17.0 使用 buildings 发行配置：全仓回归、十一界城市与建筑真实页面、Windows 同一 EXE 有／无 DLC，以及签名 Android 12 的建筑、产业与旧事件横竖屏原生验收。最终通过范围与包哈希以 `dist/` 同版发行清单为准；玩法见[建筑系统](../docs/building-system.md)。

v2.16.3 使用 architecture 发行配置：全仓回归、人物与事件及地区页面，Windows 同一 EXE 有／无 DLC，签名 Android 12 的上界、佛儒、本命、修罗王庭、地区、组织与既有修复共七阶段横竖屏原生验收。最终源码、包哈希和通过范围以 `dist/` 同版发行清单为准；设计边界见[架构第三阶段](../docs/architecture-stage3.md)。

v2.16.0 的地区历法、归墟通知与续程采用 regional 相关领域发行配置；原生验收覆盖四主题、手机横竖屏及商路操作。见[地区历法](../docs/regional-calendar.md)。

v2.15.1 使用common-goods相关领域发行配置，不运行全仓；通用商品、分级拍卖、事件恢复及双端成品验证见[通用商品与拍卖](../docs/common-goods-2151.md)。

**当前源码存档结构为 11，旧结构 1–10 明确不兼容；不迁移或覆盖原文件。** 同包名、同签名覆盖安装保留原文件；结构 1–10 的角色需要新建，不能因为覆盖安装成功就视为兼容。存档码格式 FSWD1 未变，只能在支持相应结构的版本之间互通。

## 游戏与安装

应用携带 Python、本体内容、十个官方 DLC、四套主题和字体，可离线运行。支持 arm64-v8a 与 x86_64；DLC 开关保存后，使用重启应用入口重新加载。专属 UI 同时受 DLC 实际加载与角色资格控制。

每次操作按后端规则保存。系统返回键依次关闭弹窗、功能窗口或返回初始界面；初始界面确认后退出。横竖屏和窄屏使用移动端桥接与样式适配，玩法结算与 Windows 相同。

存档位于应用私有目录 `files/game/data/saves`。卸载或清除数据会删除本地存档；跨设备可使用存档码及分段复制，详见 [存档码协议](../docs/save-code-format.md)。没有云同步或额外 MOD 安装入口。

## 系统与构建配置

配置来源为 [app/build.gradle](app/build.gradle)、[build.gradle](build.gradle) 和 [环境脚本](../scripts/android_environment.ps1)：

| 配置 | 当前值 |
| --- | --- |
| applicationId | com.fusheng.wendao |
| minSdk / targetSdk / compileSdk | 31 / 31 / 35 |
| ABI | arm64-v8a、x86_64 |
| Gradle / AGP / Chaquopy | 8.11.1 / 8.9.3 / 17.0.0 |
| Python / Java | 3.13 / 17 |

源码没有声明 maxSdkVersion；发布验收使用专用 Android 12 / API 31 x86_64 模拟器。更高系统、16 KB 页设备及实体 ARM 手机需独立验证；当前包的实际验收范围见 `dist/` 发行清单。

本机工具默认位于 `F:\CultivationLife-Android-Tools`，JDK 默认使用 `D:\java\java17`。通过 `CULTIVATION_ANDROID_TOOLS`、`JAVA_HOME` 调整环境；环境脚本将 `CULTIVATION_BUILD_PYTHON` 设为当前 PATH 中的 Python，直接调用 Gradle 时也可显式设置该变量。密钥通过 `CULTIVATION_KEYSTORE`、`CULTIVATION_KEYSTORE_PASSWORD` 或本机专用 signing 目录读取；签名私钥不进入仓库或发行包。

```powershell
./scripts/build_android.ps1 -Configuration Release
```

Gradle 从仓库复制 Python、content、web、dlc；`app/src/main/mobile` 在准备阶段注入移动端资源，不维护另一套玩法逻辑。CSS 混色由 `scripts/android_css.py` 转换，以兼容旧 WebView。Lint 仅排除面向商店目标 SDK 政策的 `ExpiredTargetSdkVersion`。

## 发布证明与验收

v2.15.0 使用secret-arts发行配置执行全仓回归和秘术、通用功法、事件真实页面；Windows同一EXE有/无DLC，以及签名Android 12 secret-arts、common-techniques四主题横竖屏原生阶段。规则见[秘术说明](../docs/secret-arts.md)，最终产物和证据以dist发行清单为准。

v2.14.4 执行通用灵根功法、坊市资格及相关领域专项回归：python scripts/verify_scoped_release.py --profile common-techniques；Windows 同一 EXE 有／无 DLC，以及签名 Android 12 common-techniques 横竖屏、四主题原生验收。本次不是全仓回归。构建限制一个工作进程、512 MiB Java 堆，浏览器与专用 1 GiB 只读模拟器分阶段运行，最终证据见 dist/release-2.14.4*.json。

v2.14.0 按用户要求执行全仓回归和完整发行验收，后端单进程、浏览器单实例；内存余量充足时二者有界重叠，Windows 与 Gradle 构建、专用只读 Android 12 模拟器分阶段单独运行。新战争的 `strategic-war` 原生阶段覆盖四主题横竖屏的真实闲置调度、原军费托管、本部固守和本宗撤回；不操作用户已在运行的其他模拟器。最终成品版本、范围及哈希以 `dist/release-2.14.0*.json` 为准。

v2.13.6 按用户要求串行运行经济、传承及系统修复相关回归，不运行全仓。发行入口为 `python scripts/verify_scoped_release.py --profile bugfix`、`python scripts/verify_android_scoped.py emulator-5580 --bugfix` 和 `python scripts/package_scoped_release.py`。原生阶段覆盖下界与返界、培养寿元、剩余履约、传承承接、监禁、护山及经济托管的横竖屏真实点击；Windows 同一 EXE 验证有／无 DLC。构建限制单工作进程，验收只运行一台专用模拟器；凭据对应最终代码及实际安装 APK，不沿用旧产物哈希。

`prepareGameAssets` 依赖 `copyGamePython`，核对暂存源码后生成 APK 内 `assets/game-build.json`。证明覆盖后端、内容、网页、DLC、Android 主源码与相关构建脚本。源码变动后旧 APK 证明失效，不能靠历史成功日志重新发布。

v2.11.2 按用户明确要求沿用上一轮422项领域／跨界测试及10个浏览器程序，不重复运行，也不标记为本轮全仓回归。新产物另验版本、签名、Lint、源码对应关系、已安装APK哈希，以及横竖屏四主题的市场搜索、实际购买和妖修入口；Windows验收新EXE的带DLC／不带DLC运行。沿用证据与新验收分别记入当前发行清单。

正式构建后按 `scripts/package_android.py` 要求准备对应版本的回归、界面、设备、签名、版本、Lint、跨端存档及已安装 APK 哈希日志，再执行：

```powershell
python scripts/package_android.py
```

发布检查使用显式异常，在 `python -O` 和 `python -OO` 下仍有效；发行清单的 `save_schema` 从统一结构版本读取。输出在 `dist/`，不会通过更新 README 自动更新 APK。

控制台原生行为通过 `debug-console` instrumentation 阶段在横竖屏验证；Agent 指令和结构化参数详见 [Debug 文档](../docs/debug-development.md)。

设备专项入口为 `tests/android_acceptance_1392.py --serial <测试模拟器序号>`、`tests/android_dlc_lifecycle_1392.py` 和独立 instrumentation 阶段。脚本历史编号是稳定文件名；运行前核对当前场景与断言。测试只在专用测试模拟器执行，Debug 包名带 `.debug`，与正式存档隔离。覆盖安装验证必须使用相同正式签名。

本地服务绑定随机 loopback 端口，使用进程会话令牌并校验 Host / Origin。WebView 限制同源，不申请存储权限；发布包关闭 WebView 调试。请求串行结算，慢连接读写不占用存档锁。错误处理与日志约定见 [项目说明](../README.md)。

本体2.13.3按用户要求只执行中心平移、缩放、触屏手势、地图交互与发行相关专项回归；十一界素材、四主题浏览器、横竖屏真实触屏拖动与新签名产物分别验证，原生共28组。专项发行入口为 `python scripts/package_map_release.py`，范围与源码/产物凭据写入发行清单，不标记为全仓回归。
