# SubSync

字幕时间轴对齐工具（GUI）。

## 打包为可独立运行的 App（推荐 PyInstaller）

> 说明：打包会把 Python 运行时与依赖一起封装，生成可双击的应用程序。

1. 安装打包工具（仅需要一次）：

```bash
python3 -m pip install --upgrade pyinstaller
```

2. 在项目根目录执行：

```bash
pyinstaller --noconfirm --windowed --name SubSyncPro subtitle_sync_gui.py
```

也可以直接运行：

```bash
./build_app.sh
```

3. 打包产物位置：

```
dist/SubSyncPro
```

macOS 用户可将 `dist/SubSyncPro.app` 拖入「应用程序」目录；Windows 用户可将生成的 `.exe` 分发给他人。
