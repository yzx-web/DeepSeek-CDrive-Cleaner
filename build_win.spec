# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = [
    "pystray._win32",
    "pystray._util.win32",
    "send2trash.win",
    "send2trash.win.modern",
    "send2trash.win.legacy",
] + collect_submodules("send2trash")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("assets", "assets")],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter", "unittest", "pydoc_data",
        "PySide6.QtNetwork", "PySide6.QtSvg", "PySide6.QtQml", "PySide6.QtQuick",
        "PySide6.QtMultimedia", "PySide6.QtOpenGL", "PySide6.QtPdf", "PySide6.QtTest",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtDBus",
        "Pythonwin", "win32ui",
        "PIL.ImageTk", "PIL.ImageQt", "PIL.ImageShow", "PIL.AvifImagePlugin",
        "PIL.WebPImagePlugin", "PIL.Jpeg2KImagePlugin", "PIL.MpoImagePlugin",
        "PIL.BlpImagePlugin", "PIL.BmpImagePlugin", "PIL.DdsImagePlugin",
        "PIL.FitsImagePlugin", "PIL.FliImagePlugin", "PIL.FpxImagePlugin",
        "PIL.GbrImagePlugin", "PIL.GifImagePlugin", "PIL.IcnsImagePlugin",
        "PIL.ImImagePlugin", "PIL.ImtImagePlugin", "PIL.IptcImagePlugin",
        "PIL.JpegImagePlugin", "PIL.MicImagePlugin", "PIL.PcdImagePlugin",
        "PIL.PcxImagePlugin", "PIL.PdfImagePlugin", "PIL.PixarImagePlugin",
        "PIL.PpmImagePlugin", "PIL.PsdImagePlugin", "PIL.SgiImagePlugin",
        "PIL.SpiderImagePlugin", "PIL.SunImagePlugin", "PIL.TgaImagePlugin",
        "PIL.TiffImagePlugin", "PIL.WmfImagePlugin", "PIL.XVThumbImagePlugin",
        "PIL.XbmImagePlugin", "PIL.XpmImagePlugin",
    ],
    noarchive=False,
)

# 裁掉运行不需要的 Qt 翻译、OpenGL 软件渲染器和额外插件，控制单文件体积。
def _n(name):
    return name.replace("/", "\\").lower()

def _keep_binary(entry):
    n = _n(entry[0])
    drop_exact = {
        "pyside6\\opengl32sw.dll",
        "pyside6\\qt6network.dll",
        "pyside6\\qtnetwork.pyd",
        "pyside6\\qt6svg.dll",
        "pyside6\\qtsvg.pyd",
        "pythonwin\\mfc140u.dll",
        "pythonwin\\win32ui.pyd",
        "win32ui.pyd",
    }
    if n in drop_exact:
        return False
    if n.startswith("pythonwin\\"):
        return False
    if n.startswith("pyside6\\translations\\"):
        return False
    if n.startswith("pyside6\\plugins\\"):
        keep = {
            "pyside6\\plugins\\platforms\\qwindows.dll",
            "pyside6\\plugins\\styles\\qmodernwindowsstyle.dll",
            "pyside6\\plugins\\imageformats\\qico.dll",
        }
        return n in keep
    if n.startswith("pil\\"):
        return n.endswith("_imaging.cp311-win_amd64.pyd")
    return True

a.binaries = [b for b in a.binaries if _keep_binary(b)]
a.datas = [d for d in a.datas if not _n(d[0]).startswith("pyside6\\translations\\")]

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DeepSeekCleaner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=["assets/app_icon.ico"],
    version="version_info.txt",
    manifest="app.manifest",
)
