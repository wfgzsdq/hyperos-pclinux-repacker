# ARM64 Linux 发行包转小米 PC 框架 APK

本项目为小米平板内置 PC Linux 框架的第三方兼容性实验。设备需要解锁并取得 root 权限，且通常需要先由 WPS PC 或 CAJViewer PC 初始化框架。隐藏 root 模块需要把新 APK 的包名加入许可范围。

## 项目状态

项目尚未达到正式可用状态。在此之前，所有 GitHub Release 都标记为 **Pre-Release**。不同 HyperOS、PC 框架或 root 模块版本可能改变私有接口和权限行为；当前代码不会关闭 SELinux，也不会修改全局 root 策略。

示例 APK 从 [Releases](https://github.com/wfgzsdq/hyperos-pclinux-repacker/releases) 下载。Release 中的测试签名只用于实验，不能视为生产签名。

`linux2apk.py` 是统一入口，支持以下输入：

- Debian `arm64` 软件包（`.deb`）；
- gzip、xz、bzip2 或未压缩的 tar 发行包（`.tar.gz`、`.tar.xz`、`.tar.bz2`、`.tar`）。

工具检查 SHA256、归档路径、特殊文件和可执行 ELF 架构，规范化文件元数据，生成只读 EROFS，再把镜像、启动配置和原包 PNG 图标封装进 Android APK。它不会运行 deb 维护脚本，不会向宿主 rootfs 安装依赖，也不能保证依赖不完整或写死安装路径的软件可运行。

## 构建环境

需要 Windows、Python 3.11+、Java 17 和 `setup_tools.py` 下载的 Android 构建工具。EROFS 可选择一种后端：

1. 已连接且具有 `su` 权限的 ARM64 小米平板：使用 `--serial <ADB序列号>`；
2. 已安装 `erofs-utils` 的 WSL 发行版：使用 `--wsl-distro <发行版名称>`。

Arch Linux WSL 可运行：

```powershell
python setup_tools.py
wsl -d archlinux -- pacman -Sy --needed erofs-utils
```

Java 路径可通过 `PCLINUX_JAVA_BIN` 指定；Android build-tools 和 platform 路径可分别通过 `PCLINUX_BUILD_TOOLS`、`PCLINUX_ANDROID_JAR` 指定。

## 先检查再构建

```powershell
python linux2apk.py "D:\Downloads\application_linux-arm64.tar.xz" --inspect
python linux2apk.py "D:\Downloads\application_linux-arm64.tar.xz" --configure-only
```

工具会生成 `jobs/<id>/app.json`。确认 `entry`、`args`、`env`、图标和回调协议后再构建：

```powershell
# 本机 WSL 后端
python linux2apk.py package.tar.xz --config jobs/example/app.json --wsl-distro archlinux

# 小米平板后端
python linux2apk.py package.tar.xz --config jobs/example/app.json --serial 898cd909 --adb-su /debug_ramdisk/su
```

deb 使用相同入口：

```powershell
python linux2apk.py package_arm64.deb --config jobs/example/app.json --wsl-distro archlinux
```

若 tar 只有一个顶层目录，工具默认剥离该目录。可用 `--strip-components 0` 禁用，或在 JSON 中设置 `archive_strip_components`。没有 `.desktop` 时必须用 `--entry` 指定归档内可执行文件。原包图标可用 `--icon-member icons/icon128.png` 指定，外部 PNG 使用 `--icon icon.png`。

## Zotero 示例

```powershell
python linux2apk.py `
  "H:\Downloads\Zotero-10.0.3-beta.1+cfec88e31_linux-arm64.tar.xz" `
  --config zotero.json `
  --wsl-distro archlinux `
  --work-dir jobs/zotero `
  --output Zotero-PC-arm64-10.0.3-beta.1-launcher-v0.1.apk
```

此配置使用 `zotero-bin -app @APP@/app/application.ini`，以 X11 启动，并注册 `zotero://` 回调。APK 安装、启动和运行兼容性测试是独立步骤，不属于构建过程。

## 运行机制与边界

构建流程为：

`软件包 + 配置 → 归档与 ARM64 检查 → 规范化 tar.gz → EROFS → Android 启动器 → zipalign → APK 签名`

启动器复用小米 PC Linux 框架的窗口 Binder 服务，并为每个应用维护独立镜像、挂载目录和 HOME/XDG 数据目录。Linux 程序仍运行在平板现有 rootfs 中；APK 不是虚拟机或完整容器，也不会自动提供软件包声明之外的系统依赖。

浏览器桥只接受带随机令牌的本机请求，并把 HTTP(S) 地址交给 Android 浏览器。OAuth 回调协议和参数按应用配置，令牌校验与交换仍由原 Linux 应用负责。

卸载 APK 不会自动删除 Linux 镜像和用户数据。清理时只应处理该应用在 `/data/rootfs/pclimg`、`/data/rootfs/opt/pclinux` 与 `/data/rootfs/home/xiaomi/.pclinux` 下对应的文件，避免递归删除整个框架目录。

## 离线校验

```powershell
python verify_artifact.py output.apk source-package.tar.xz --output verification.json
```

脚本核对源包、APK、内嵌 EROFS、图标、包名、回调和必要资源。另可使用 Android build-tools 的 `apksigner verify`、`zipalign -c 4` 与 `aapt2 dump badging` 检查签名、对齐和 manifest。

运行打包器测试：

```powershell
python -m unittest discover -s tests -v
```
