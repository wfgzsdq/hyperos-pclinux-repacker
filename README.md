# 小米 PC 框架 ARM64 Linux 应用封装实验 v0.2

# 现阶段，你的设备需要解锁并获取root权限方可使用该项目，欢迎PR或提交Issues。本项目不保证后续HyperOS版本能够正常使用，不受理由此产生的Issue适配，请自行修改源码并调试

# ARM64 deb → 小米 PC 框架 APK

`deb2apk.py` 是统一入口。它读取 deb 的 control 与 `.desktop`，解析真正的可执行文件、启动参数、应用名称和 PNG 图标，生成独立 Android 包，打包为只读 EROFS 并签名。不会执行 deb 维护脚本，也不需要先在 rootfs 中用 dpkg 安装软件。

**适用范围：可以重定位运行、依赖与平板现有 Ubuntu 22.04 ARM64 环境兼容的 GUI 软件。** “可以接受 ARM64 deb 作为输入”不意味着任何 deb 都能直接运行；纯库包、驱动、系统服务和依赖安装脚本的软件需要额外适配。脚本会输出依赖和兼容性提示，不承诺自动解决这些问题。

## 准备

- Windows、Python 3.11+、Java 17；通过 `python setup_tools.py` 下载并校验 Android 构建工具和 ARM64 erofs-tools。Java 默认使用本次测试的 Microsoft JDK 路径，其他机器设置 `PCLINUX_JAVA_BIN` 指向自己的 JDK `bin`。

- 构建新 EROFS 镜像时需要已连接的 ARM64 小米平板、运行中的 ADB server 和可用的 root ADB shell。`--serial` 是 `adb devices` 显示的序列号。

- 设备已有小米 PC Linux 框架；运行 APK 前先用 WPS PC/CAJ 初始化框架。隐藏 root 模块需要把每个新 APK 的包名加入许可范围。

- gzip/xz/bzip2/未压缩 tar 使用标准库；zstd 压缩的 deb 在 Python 3.14+ 可直接读取，Python 3.11–3.13 先运行 `python -m pip install zstandard`。


示例在脚本目录执行；脚本也支持从其他工作目录传入完整路径。

```powershell

# 默认从桌面入口推断配置，完整封装，不自动安装

python deb2apk.py "D:\Downloads\example_arm64.deb" --serial 898cd909


# 隐藏 root 的设备可以明确指定 ADB 侧 su 路径

python deb2apk.py "D:\Downloads\example_arm64.deb" --serial 898cd909 --adb-su /debug_ramdisk/su


# 安装脚本单独执行，避免在普通构建时中断设备上的应用

python install_apk.py jobs/example/example-pc.apk --serial 898cd909

```


每个应用的资产、图标、镜像、编译文件在 `jobs/<id>/`，不同应用不会互相覆盖。默认包名 `local.pclinux.<id>`。相同应用的配置、版本及运行参数会写入 `app.json`，APK 旁边的 `.build.json` 包含 deb、镜像、APK 和图标来源的校验信息。


同一个工作目录请不要并发执行两次构建。`--work-dir` 可指定独立工作目录；`--output` 指定完整 APK 输出路径。


## 先检查，再编辑配置


```powershell

python deb2apk.py app.deb --inspect

python deb2apk.py app.deb --configure-only

# 修改生成的 jobs/<id>/app.json 后

python deb2apk.py app.deb --config jobs/<id>/app.json --serial 898cd909

```


含多个可见 `.desktop` 入口时，脚本列出选择项并要求 `--desktop example.desktop`，不会随便选一个。没有桌面入口时用 `--entry usr/bin/example`。符号链接会解析到 deb 内实际可执行文件；指向包外可执行文件的入口不能自动推断。脚本入口会提示检查其绝对路径。


`--inspect`、`--configure-only` 不需要连接平板。生成完整新镜像需要平板；复用从同一 deb 构建的镜像时，可用 `--reuse-image image.erofs --image-sha256 <完整SHA256>`，脚本校验摘要与 EROFS 超级块。复用时应由调用者保证镜像和输入 deb 对应，不能拿另一个软件的镜像替代。


## 常用适配


```powershell

python deb2apk.py app.deb --serial 898cd909 --id my_editor --package local.pclinux.myeditor --label "My Editor PC" --entry usr/lib/myeditor/editor --arg=--ozone-platform=x11 --arg=--disable-gpu


python deb2apk.py app.deb --serial 898cd909 --env "LD_LIBRARY_PATH=@APP@/usr/lib/myeditor" --env "MY_CONFIG=@DATA@/config"


python deb2apk.py app.deb --serial 898cd909 --scheme myeditor --url-arg=--open-url --url-arg=@URL@

```


`--arg` 是**替换整组启动参数**，可重复使用；以 `--` 开头的参数使用 `--arg=--flag` 写法。`@APP@` 替换成镜像挂载目录，`@DATA@` 替换成此应用的数据目录。环境变量通过 `env` JSON 对象或 `--env NAME=VALUE` 配置；PATH、BROWSER、DBUS_SESSION_BUS_ADDRESS 由桥接保留。


默认使用独立 HOME/XDG 数据目录；软件若依赖共享的 `/home/xiaomi` 可在配置中明确修改。默认用 `flock` 防止重复启动长期运行的 GUI 进程，特殊会自行派生并退出的程序可设置 `single_instance_lock: false` 后自行管理单实例。


已知 VS Code 路径会自动应用现有可用参数、独立配置和 vscode 回调。其他 Electron 软件可选择 `--preset electron`，加入 `--no-sandbox --disable-gpu --disable-dev-shm-usage --ozone-platform=x11`；这是兼容性取舍，需要自行确认。`--preset generic` 禁用自动的 VS Code/Electron 预设。


桌面 Exec 解析支持通常的独立参数和标准字段；`%f/%F/%u/%U/%i` 等启动时无上下文的字段会省略。复杂 `env` 包装命令、特殊字段或脚本应改用显式入口与参数。可执行程序必须在镜像中，未自动执行 apt 依赖解析或安装；缺依赖时需要进一步准备运行环境或制作含依赖的重定位包。


## 图标与登录


按 `.desktop` 的 Icon 字段找到 deb 内 PNG，优先取较大尺寸，提取原始字节作为 Android drawable，并写入 manifest 的 `android:icon`。图标摘要、包内路径和尺寸记录在构建信息中。SVG-only 软件可通过 `--icon icon.png` 提供 PNG；未找到 PNG 时使用 Android 默认图标并提示。


所有应用复用 HTTP(S) → Android 浏览器桥。自定义回调仅注册配置中的 `callback_schemes`；没有配置时不会注册 vscode 或其他应用协议。`callback_args` 必须包含一个单独的 `@URL@`，其他内容作为普通参数引用。授权回调由原应用校验和交换令牌，启动器不代替 OAuth 客户端。


JSON 示例：


```json

{

  "id": "my_editor",

  "package": "local.pclinux.myeditor",

  "label": "My Editor PC",

  "version_code": 1,

  "version_name": "1.0",

  "entry": "usr/lib/myeditor/editor",

  "args": ["--profile", "@DATA@/profile"],

  "env": {"XDG_CONFIG_HOME": "@DATA@/config"},

  "callback_schemes": ["myeditor"],

  "callback_args": ["--open-url", "@URL@"]

}

```


若配置含 `deb_sha256`，输入必须匹配该摘要。升级 deb 时先重新检查元数据，再更新摘要；脚本不会悄悄忽略不匹配。升级 APK 要保持 package 和签名，递增 `version_code`。默认使用目录内的 `local-test.jks`（公开实验密码、别名 pclinux），可通过 `--key` 指定同格式实验密钥；不要把这种公开密码签名当作生产密钥管理。


## 本次 VS Code 更新


`vscode.json` 保持 `local.pclinux.vscode`，versionCode 3，versionName 0.2.1。图标来自 `usr/share/pixmaps/vscode.png`，原图 1024×1024，SHA256 为 `7537330cec94b308feaa9bb66db45b5554b8379ec7dce83990521d2860bca4b2`。原镜像及用户数据路径沿用 v0.2，登录回调改为配置读取。


```powershell

python deb2apk.py downloads/vscode-arm64.deb --config vscode.json --serial 898cd909 --output VSCode-PC-arm64-1.138.0-launcher-v0.2.1.apk

```


框架限制仍在：使用私有 Binder 协议、appType 0，建议一次运行一个封装应用；APK 不是独立 Linux 虚拟机，不能脱离小米 rootfs。系统升级可能影响兼容性。源码中的原始 `repack.py`、`make_assets.py` 和 `build_apk.py` 仍可分步调用，统一入口优先使用本脚本。

将官方 ARM64 deb 校验、规范化为只读 EROFS 镜像，再与原创 Android 启动器打包、签名为独立 APK。测试应用为 VS Code 1.138.0。APK 内包含应用镜像，不需要另外下载 deb；运行时依赖平板已有的小米 PC Linux 环境。

## 使用完整 APK

1. 先通过 WPS PC 或 CAJViewer PC 初始化小米 PC 框架，再打开 VS Code PC。重启后也建议先完成此步骤；本版尚未实现独立冷启动整套框架。
2. 安装 `VSCode-PC-arm64-1.138.0-launcher-v0.2.apk`。如果使用隐藏 root 的模块，把 `local.pclinux.vscode` 加入其许可范围并授权 root。启动器会验证实际 UID，而不是仅检查 su 文件存在。
3. 首次启动会展开约 490 MiB 镜像、校验 SHA256、只读挂载并启动应用。为 APK、安装过程和镜像预留至少约 2 GiB 可用空间。
4. 点击编辑区的文本焦点会自动打开系统输入法；上方“键盘”按钮保留为手动入口。键盘显示采用覆盖模式，Linux 画面不随之缩小。中文通过候选提交进入 Linux 应用。ASCII 路径输入时切换同一输入法的英文模式，避免拼音转换文件名。

本机已验证 `/debug_ramdisk/su` 能获得 UID 0；普通 `su` 曾被隐藏 root 策略拒绝。工具未修改全局 root 策略，也未关闭 SELinux。不同设备仍需按其模块配置许可。

本轮用系统 Gboard 拼音逐段输入“关关雎鸠，在河之洲，窈窕淑女，君子好逑”，保存后核对 57 字节完全一致。软键盘退格、Ctrl+N、Ctrl+S 和原生另存为窗口已验证。实体键盘目前已拆下，实际硬件回归待测。键盘覆盖区域内的光标自动避让尚未验证。

## 从源码复现（Windows）

需要 Python 3.11+、Java 17、已经启动且能连接设备的 ADB server，以及设备 ADB shell 的 su 权限。构建时利用设备上的 ARM64 mkfs.erofs；不要求在 Windows 解包 Linux 符号链接。

```powershell
python setup_tools.py
python download_deb.py
python repack.py --config vscode.json --deb downloads/vscode-arm64.deb --serial YOUR_SERIAL
python build_apk.py
python install_apk.py build/vscode-pc.apk --serial YOUR_SERIAL
```

脚本按自身所在目录定位工具和产物。Java 默认目录是本次测试的 Microsoft JDK 17 安装目录；其他机器请设置 `PCLINUX_JAVA_BIN` 指向 JDK 的 bin。也可设置 `PCLINUX_BUILD_TOOLS`、`PCLINUX_ANDROID_JAR`。`setup_tools.py` 从 Google 和 erofs-tools 上游下载固定版本并验证固定校验值。

`build_apk.py --thin` 仅用于已有镜像的开发测试，不能作为首次安装交付包。正式构建不要加此参数。

仅重新生成启动脚本时：

```powershell
python make_assets.py --config vscode.json --image staging/vscode/application.erofs
python build_apk.py
```

源码压缩包未包含 Google 构建工具、VS Code deb、EROFS 镜像和测试签名私钥。首次构建自动产生 `local-test.jks`，密码 `pclinux-local-test`。新生成的证书不能覆盖安装本次交付 APK；另提供本次测试密钥，放到脚本同级可保持签名一致。此公开密码密钥仅用于本地实验，正式分发应自行管理签名。

## 封装其他软件

复制 `vscode.json` 并修改 `id`、`package`、`label`、`entry`、`args`、`source_url`、`deb_sha256`。`id` 是 Linux 安装和数据目录名；`package` 是 Android 应用 ID。入口使用 deb 内实际可执行文件的相对路径，例如 `usr/share/code/code`，不要使用依赖原始绝对安装路径的包装脚本。参数中的 `@APP@`、`@DATA@` 会替换为挂载目录和独立配置目录。

依次运行下载、repack、build 即可。当前 Java 类名保留 `local.pclinux.vscode`，生成的 manifest 使用完整 Activity 类名，因此 Android application ID 可通过配置变化。

流程不会运行 deb 维护脚本、安装依赖或覆盖 rootfs `/usr`。需人工确认软件与 Ubuntu 22.04 ARM64/glibc 2.35 兼容，依赖库已存在，且能从重定位目录启动。只验证了 VS Code；依赖绝对路径、系统服务或特权安装脚本的软件可能需要额外适配。Python 标准库 tarfile 的压缩支持决定可读格式；本次 deb 的格式已验证，较旧 Python 不支持的 zstd deb 需另行适配。

## 流程与关键实现

`deb + 配置 → SHA256/arm64/路径/入口检查 → 规范化 tar.gz → 平板 mkfs.erofs → fsck.erofs → 镜像与启动脚本作为 assets → javac/D8 → zipalign/apksigner → 完整 APK`

- 校验 tar 路径、重复条目、文件类型；清除 setuid/setgid；统一 UID/GID/时间戳。符号链接保存在镜像内，不在 Windows 落地，不执行维护脚本。符号链接可能指向镜像外部，这是兼容性需求，不构成应用安全隔离。
- APK 使用原创 Binder 客户端绑定 `com.xiaomi.mslgrdp`，以 appType 0 注册未知 Linux 应用窗口。Linux X11 → Xwayland → Weston RDP → Android Canvas。
- 原创 `FrameBroker` 通过已授权 root 读取 `/dev/msl/rdp/` 的 UUID 帧文件，限制文件名和读取边界，以匿名管道传给 Activity；未复制小米专有 JNI 库进 APK。
- 镜像位于 `/data/rootfs/pclimg/<hash16>.erofs`，规避 Android losetup 的短路径限制，标签为 `u:object_r:mslg_rootfs_file:s0`。挂载使用 `ro,nosuid,nodev`。
- 应用作为用户 7100 运行，使用干净 Linux 环境；启动时读取现有 Fcitx5 的 `DBUS_SESSION_BUS_ADDRESS`，设置 GTK/QT/XMODIFIERS，避免硬编码会话地址。
- 当前后端未实现标准 RDP Unicode 注入。ASCII 提交映射为带节流的按键；非 ASCII 整段提交使用 Binder `sendStringTo`，配合特殊键 300。Android composing 文本不提前写入 Linux，避免候选取消时残留。

## 已知边界与卸载

这是针对实测小米框架的 v0.2 原型，使用私有 Binder 协议，系统升级可能破坏兼容性。未知应用共享 appType 0，目前请一次运行一个此类封装应用；已接入原生窗口/输入法回调，次级 Linux 窗口使用 Android Dialog 承载。复杂弹窗层级、预编辑、组合键、剪贴板、触控手势及性能并未达到原厂客户端的完整程度。

VS Code 使用 `--no-sandbox --disable-gpu` 和 X11。Linux 应用共享 chroot、UID 7100 及环境，不是隔离容器。未测试硬件加速、音视频、开发调试工具链、重启后的独立冷启动；互联网账号登录的实测结果见 v0.2 测试报告。

卸载 APK 保留 Linux 镜像和配置。VS Code 配置在 `/data/rootfs/home/xiaomi/.pclinux/vscode`，挂载目录在 `/data/rootfs/opt/pclinux/vscode`。若需彻底清理，先备份文档并结束本应用 Linux 进程，再卸载其 EROFS 挂载，最后仅删除本应用对应 hash 的镜像、目录与配置；不要对整个 `/data/rootfs`、`/opt`、`/pclimg` 执行递归清理。开发阶段留下的旧镜像/配置备份见测试报告，暂不自动删除。

官方 VS Code 二进制保留其原有许可证；本包是用户本地兼容性实验，不代表小米或 Microsoft 官方产品。再次分发二进制时应遵守其许可证。

## v0.2 浏览器与回调

应用自己的 PATH/BROWSER 指向作用域内的 xdg-open 包装器，以带随机令牌的本机 HTTP 请求交给 Android 浏览器。服务仅绑定 127.0.0.1；拒绝错误令牌、非 HTTP(S) 链接、带用户信息的链接。不会覆盖系统 /usr/bin/xdg-open。

Android 注册 vscode://，收到链接后在原 Linux 用户和配置目录下执行 VS Code --open-url。回调通过标准输入交给固定的 root 命令，启动器日志仅记录转发状态；OAuth state/PKCE 校验及令牌交换由原 VS Code 扩展执行。浏览器和 chroot 共享网络命名空间，因此应用自己的 localhost 回调服务器也可被宿主浏览器访问。

请从 VS Code 内发起登录，并在浏览器完成授权和允许返回应用。普通 GitHub 登录页不能代替应用 OAuth 登录。Apple/Google 联合登录及 Microsoft 登录是否可用还受上游支持与网络影响，本轮不能视为全部提供商都已实测。

小米 rootfs 未提供标准 Linux 系统钥匙环，VS Code 可能弹出凭据保存提示。弱加密模式只能在用户明确选择后用于实验；启动器不自动设置 --password-store=basic。

封装其他应用时，HTTP 浏览器桥可以复用；回调 URI scheme 和调用参数仍需按应用适配，当前 manifest/Java 的 vscode:// 与 launch.sh 回调路径是 VS Code 专用。

原厂 WPS/CAJ 的 Activity/View 位于其 APK 私有代码中，并非框架导出的 Activity。本版使用相同 MultiWindowService/Binder 协议与原生 IME 回调，配合原创 Android 窗口承载，没有声称复用其完整私有 UI 类。
