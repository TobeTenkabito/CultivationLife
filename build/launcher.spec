# -*- mode: python ; coding: utf-8 -*-

import importlib.util
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable,
    VSVersionInfo, VarFileInfo, VarStruct,
)

project_root = Path(SPECPATH).resolve().parent
version_spec = importlib.util.spec_from_file_location(
    "cultivation_life_build_version", project_root / "cultivation_life" / "version.py",
)
version_module = importlib.util.module_from_spec(version_spec)
version_spec.loader.exec_module(version_module)
BASE_GAME_NAME = version_module.BASE_GAME_NAME
BASE_GAME_VERSION = version_module.BASE_GAME_VERSION
BASE_GAME_VERSION_TUPLE = version_module.BASE_GAME_VERSION_TUPLE


version_quad = (*BASE_GAME_VERSION_TUPLE, 0)
launcher_version = VSVersionInfo(
    ffi=FixedFileInfo(filevers=version_quad, prodvers=version_quad),
    kids=[
        StringFileInfo([
            StringTable("080404b0", [
                StringStruct("FileDescription", f"{BASE_GAME_NAME}本地启动器"),
                StringStruct("FileVersion", BASE_GAME_VERSION),
                StringStruct("InternalName", "CultivationLifeLauncher"),
                StringStruct("OriginalFilename", "launcher.exe"),
                StringStruct("ProductName", BASE_GAME_NAME),
                StringStruct("ProductVersion", BASE_GAME_VERSION),
            ]),
        ]),
        VarFileInfo([VarStruct("Translation", [2052, 1200])]),
    ],
)


a = Analysis(
    [str(project_root / 'launcher.py')],
    pathex=[str(project_root)],
    binaries=[],
    datas=[(str(project_root / 'content'), 'content'), (str(project_root / 'web'), 'web')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='launcher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=launcher_version,
)
