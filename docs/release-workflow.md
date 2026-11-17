# GitHub Release发行流程

从本体3.10.0起，每次正式打包均发布到GitHub Releases。源码仓库不再新增安装包；`dist`只作为PyInstaller验收中的临时目录，`build/releases/<版本>/`作为忽略跟踪的发行暂存目录。

3.12.0起根目录的本地试玩 `launcher.exe` 也退出Git跟踪并加入忽略；保留工作区文件和已有备份，正式包从Release获取。

1. 更新本体版本、Android版本号、更新说明与游戏百科；DLC有实际版本更新时独立更新其清单。
2. 完成最终源码回归、跨界契约／模块依赖／文档检查和真实浏览器操作。中断重跑必须保留原日志，逐条核对测试身份、最终源码指纹和完整覆盖，不能把未执行、跳过或失败项算成通过。
3. 构建Windows EXE并完成同一文件有／无DLC验收。构建签名Android APK，完成Android 12横竖屏原生验收、lint、签名、ABI和已安装包哈希核对；模拟器验收不得表述为ARM实机验收。
4. 运行`python scripts/package_scoped_release.py`。当前发行输出位于`build/releases/<版本>/`，包括Windows、Android包及验收清单。根目录旧`launcher.exe`不会被新发行脚本替换；玩家使用Release中的新包。
5. 打包与验收结束后清理`dist`中的`.exe`、`.apk`、`.aab`、`.zip`文件，保留源码、存档和验收记录。文件必须先解析为绝对路径并确认位于仓库`dist`内，禁止递归删除未知目录。将源码、说明和旧安装包删除记录提交并推送远程。
6. 以已推送的完整提交SHA执行：`python scripts/publish_github_release.py --version <版本> --target <SHA> --notes docs/release-<版本去点>.md --cleanup`。凭据只读取环境变量或现有Git凭据管理器，不打印、持久化或提交。
7. 发布器先创建草稿，逐个上传包、说明、双端验收清单和`SHA256SUMS.txt`，校验远程资产大小与SHA-256后才公开Release。失败时保留草稿与本地文件，修复后可按同一提交续传；公开资产不同则拒绝覆盖。成功后清理暂存安装包，保留上传回执和验收证据。

发布地址：[GitHub Releases](https://github.com/TobeTenkabito/CultivationLife/releases)。旧版本远程Release保留，不因清理本地`dist`而删除。
