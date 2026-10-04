# 浮生问道 · Android

维护基线：2026-10-05，本体 **v1.59.2**。Gradle 配置的版本名为 **1.59.2-android.31**，versionCode **31**，沿用 `com.fusheng.wendao` 包名和正式签名。

**当前源码存档结构为 8，支持 6→7→8 迁移，拒绝结构 1–5。** 同包名、同签名覆盖安装保留原文件；结构 1–5 的角色需要新建，不能因为覆盖安装成功就视为兼容。存档码格式 FSWD1 未变，只能在支持相应结构的版本之间互通。

## 游戏与安装

应用携带 Python、本体内容、八个官方 DLC、六套主题和字体，可离线运行。支持 arm64-v8a 与 x86_64；DLC 开关保存后，使用重启应用入口重新加载。专属 UI 同时受 DLC 实际加载与角色资格控制。

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

`prepareGameAssets` 依赖 `copyGamePython`，核对暂存源码后生成 APK 内 `assets/game-build.json`。证明覆盖后端、内容、网页、DLC、Android 主源码与相关构建脚本。源码变动后旧 APK 证明失效，不能靠历史成功日志重新发布。

正式构建后按 `scripts/package_android.py` 要求准备对应版本的回归、界面、设备、签名、版本、Lint、跨端存档及已安装 APK 哈希日志，再执行：

```powershell
python scripts/package_android.py
```

发布检查使用显式异常，在 `python -O` 和 `python -OO` 下仍有效；发行清单的 `save_schema` 从统一结构版本读取。输出在 `dist/`，不会通过更新 README 自动更新 APK。

控制台原生行为通过 `debug-console` instrumentation 阶段在横竖屏验证；Agent 指令和结构化参数详见 [Debug 文档](../docs/debug-development.md)。

设备专项入口为 `tests/android_acceptance_1392.py --serial <测试模拟器序号>`、`tests/android_dlc_lifecycle_1392.py` 和独立 instrumentation 阶段。脚本历史编号是稳定文件名；运行前核对当前场景与断言。测试只在专用测试模拟器执行，Debug 包名带 `.debug`，与正式存档隔离。覆盖安装验证必须使用相同正式签名。

本地服务绑定随机 loopback 端口，使用进程会话令牌并校验 Host / Origin。WebView 限制同源，不申请存储权限；发布包关闭 WebView 调试。请求串行结算，慢连接读写不占用存档锁。错误处理与日志约定见 [项目说明](../README.md)。
