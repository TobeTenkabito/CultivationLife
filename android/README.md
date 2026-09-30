# 浮生问道 · Android 12

本体 **v1.49.0**，安卓版本 **1.49.0-android.14**（versionCode 14）。以 Android 12 / API 31 为适配目标，包含 arm64-v8a 与 x86_64 两种架构。

v1.49.0 新增邻域四阶段培养、五轮道统反噬、人五衰、天五衰与不限轮数的斩三尸。三尸同时出场，须全部斩灭；战前邻域锁定，长战消耗与状态延续。新增道祖成就与百科突破建议，六主题同步适配。

v1.48.1 的新手教程使用真实界面上的高亮、箭头和文字提示，带玩家亲自修炼、探宝、配置功法、拜师并选择宗门入门。系统返回键可暂停引导，稍后从主界面续接；32 步流程和确定结果操作在六主题中通过原生点按验收。完整说明继续保留在设置中。

初始页和主界面可开启、暂停教程，设置内保留完整十课参考说明。适龄新手亲自完成操作后，会获得预先说明的修炼与探宝收获、结丹师缘和宗门身份。进度与收获保存在角色存档中。独立测试 APK 的 `phase=tutorial` 验证六主题、真实控件原生点按、拜师入门、不耗时演练、续接进度与系统返回键。

本版强化邻域连续压制与两轮修为碾压结算；仙窍容量、追加投入上限随初／中／后期增长。下界恢复蓝色 MP，归返恢复转化条；传送阵先选许可／贿赂／暗杀再选目的地。设置可开启手动预案，左侧配置邻域、爆发、法力保留线、变身和护主，六主题均适配。

保留存档码导入与导出。初始界面可导入，修行卷卡片或设置中可导出；点复制即可保存为文本。长码会分段显示，请逐段保存，导入时可乱序粘贴并点“预览存档”收录。完整存档码即为恢复凭据。替换同一存档前需确认，并保留原文件备份。

六主题均适配修行卷列表、存档弹窗和佛修按钮配色。保留血脉触屏说明、长存档性能优化与浅色图标，包含七个 DLC。使用原正式签名覆盖安装即可保留已有存档，无需卸载。跨设备传递存档不迁移 DLC 文件或应用主题偏好，建议两端启用相同扩展后继续游玩。

独立测试 APK 的 `phase=save-transfer` 验证六主题下大于 10 MB 的 JSON 存档、原生剪贴板、分段乱序收录、确认替换和内容一致性，并进行 Windows 与 Android 的文本码互通。测试代码不包含于正式 APK；Android 12 模拟器之外的实体设备未纳入本轮验收。

## 更高版本系统

Android 12 是最低要求，并非最高限制。`minSdk=31`、`targetSdk=31` 且没有 `maxSdkVersion`；按 [Android 官方 SDK 规则](https://developer.android.com/guide/topics/manifest/uses-sdk-element)，更高系统可采用兼容行为运行旧目标版本应用。因此预计可以在更高版本的 64 位安卓设备上运行，但目前仅完成 Android 12 模拟器验收，未承诺所有新系统及厂商 ROM 均兼容。

Android 15 起部分设备使用 [16 KB 内存页](https://developer.android.com/guide/practices/page-sizes)。本包 132 个原生 ELF 库的载入段对齐均至少为 16 KB；这项静态检查不能代替更高版本、16 KB 设备上的实际运行测试。

## 游戏与安装

- 安装发行 APK 后直接打开；Python、本体内容、七个 DLC 和中文字体全部随包携带，可离线游戏。
- 保留 A–F 六套独立主题，初始界面和游戏设置均可切换。横竖屏保留当前界面，窄屏操作区与双行功能入口支持触摸和滚动。
- 每次行动后自动保存。初始界面可删除指定角色，删除前显示角色名确认。
- 系统返回键优先关闭弹窗／功能窗口，再返回初始界面；初始界面返回会确认退出。
- DLC 在初始界面或扩展管理中开关，使用“重启应用，使 DLC 设置生效”重新加载。
- 存档位于应用私有目录 `files/game/data/saves`；同包名、同签名覆盖安装保留数据。卸载或清除应用数据会删除存档。
- 支持存档码导入、导出和分段传递；没有云同步或额外 MOD 安装入口。

## 构建

当前工作机的 SDK、Gradle、AVD、构建缓存和签名文件位于 `F:\CultivationLife-Android-Tools`。复用现有 `D:\java\java17` JDK 与 Python 3.13，不要求 Android Studio。

```powershell
./scripts/build_android.ps1 -Configuration Release
```

构建版本：Gradle 8.11.1、Android Gradle Plugin 8.9.3、Chaquopy 17.0.0、Python 3.13；compileSdk 35，minSdk / targetSdk 31。Lint 仅排除面向 Google Play 上架政策的 `ExpiredTargetSdkVersion`，其他错误正常阻止构建。

环境脚本为 `scripts/android_environment.ps1`，可通过 `CULTIVATION_ANDROID_TOOLS`、`JAVA_HOME` 覆盖本机路径。正式构建读取 `CULTIVATION_KEYSTORE` / `CULTIVATION_KEYSTORE_PASSWORD`，或读取本机专用 signing 目录中的文件。**保管该签名目录**，后续覆盖升级必须使用同一把密钥；密钥不进入源码和发行包。

Gradle 自动从仓库复制 Python 源码、打包 content / web / dlc，不维护第二套游戏规则。Android 专用呈现在 `app/src/main/mobile`，打包时注入，不改变 Windows 主题。CSS sRGB 混色在打包时转换为通道运算，兼容 Android 12 最初的 WebView 91；各主题、DLC 和资源条的颜色变量继续独立生效。

本地服务只监听随机的 127.0.0.1 端口，使用每次进程启动生成的随机会话令牌，并检查 Host / Origin。WebView 限制在该源，不申请存储权限。游戏请求串行结算，资源更新不触碰 data 目录。发布包关闭 WebView 调试。

## 验收

v1.39.3 增加 `tests/browser_character_layout_1393.py`：六主题、四种宽度、宗门／世界修士／家族／同行／圣贤门人的长文本与多操作布局回归。同一份人物样例由独立测试 APK 的 `phase=characters` 在 Android 12 WebView 中执行；测试样例不进入正式 APK。另验证 v1.39.2 覆盖升级后的离线存档、进度及主题保留。

`tests/android_acceptance_1392.py --serial <本工程的模拟器序号>` 使用原生触摸检查六主题、行动、功能窗口、删除确认、后台／旋转和进程重启。`tests/android_dlc_lifecycle_1392.py` 检查 DLC 冷重载和离线存档。仅在独立测试模拟器运行这些测试。

模拟器名 `WendaoAndroid12`，数据位于专用 F 盘目录。Debug 应用包名以 `.debug` 结尾，与正式版隔离；不会写入桌面存档。发布前另对正式签名 APK 做安装启动和覆盖升级验证。
