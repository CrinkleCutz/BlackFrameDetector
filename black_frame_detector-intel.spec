# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Black Frame Detector
Target: macOS Intel (x86_64)
"""

import os
from pathlib import Path

block_cipher = None

# Project paths
PROJECT_DIR = Path(SPECPATH)
VENDOR_BIN = PROJECT_DIR / 'vendor' / 'bin-intel'

# Binaries to bundle (ffmpeg/ffprobe)
binaries = []
if VENDOR_BIN.exists():
    ffmpeg_path = VENDOR_BIN / 'ffmpeg'
    ffprobe_path = VENDOR_BIN / 'ffprobe'
    if ffmpeg_path.exists():
        binaries.append((str(ffmpeg_path), 'bin'))
    if ffprobe_path.exists():
        binaries.append((str(ffprobe_path), 'bin'))

# Data files to bundle (logo, etc.)
datas = []
logo_path = PROJECT_DIR / 'logo.png'
if logo_path.exists():
    datas.append((str(logo_path), '.'))
logo2_path = PROJECT_DIR / 'logo2.png'
if logo2_path.exists():
    datas.append((str(logo2_path), '.'))

# Qt modules to exclude (reduces app size significantly)
excludes = [
    'PySide6.QtWebEngine',
    'PySide6.QtWebEngineCore',
    'PySide6.QtWebEngineWidgets',
    'PySide6.Qt3DCore',
    'PySide6.Qt3DRender',
    'PySide6.Qt3DInput',
    'PySide6.Qt3DLogic',
    'PySide6.Qt3DExtras',
    'PySide6.Qt3DAnimation',
    'PySide6.QtBluetooth',
    'PySide6.QtCharts',
    'PySide6.QtDataVisualization',
    'PySide6.QtDesigner',
    'PySide6.QtHelp',
    'PySide6.QtLocation',
    'PySide6.QtMultimedia',
    'PySide6.QtMultimediaWidgets',
    'PySide6.QtNetwork',
    'PySide6.QtNetworkAuth',
    'PySide6.QtNfc',
    'PySide6.QtOpenGL',
    'PySide6.QtOpenGLWidgets',
    'PySide6.QtPositioning',
    'PySide6.QtPrintSupport',
    'PySide6.QtQml',
    'PySide6.QtQuick',
    'PySide6.QtQuickControls2',
    'PySide6.QtQuickWidgets',
    'PySide6.QtRemoteObjects',
    'PySide6.QtSensors',
    'PySide6.QtSerialPort',
    'PySide6.QtSql',
    'PySide6.QtStateMachine',
    'PySide6.QtSvg',
    'PySide6.QtSvgWidgets',
    'PySide6.QtTest',
    'PySide6.QtUiTools',
    'PySide6.QtWebChannel',
    'PySide6.QtWebSockets',
    'PySide6.QtXml',
]

a = Analysis(
    ['black_frame_detector.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Black Frame Detector',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch='x86_64',
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Black Frame Detector',
)

app = BUNDLE(
    coll,
    name='Black Frame Detector.app',
    icon=None,
    bundle_identifier='com.blackframedetector.app',
    version='1.0.0',
    info_plist={
        'CFBundleName': 'Black Frame Detector',
        'CFBundleDisplayName': 'Black Frame Detector',
        'CFBundleGetInfoString': 'Detect black frames in video files',
        'CFBundleIdentifier': 'com.blackframedetector.app',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHumanReadableCopyright': 'Copyright 2025',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.15',
        'NSRequiresAquaSystemAppearance': False,
    },
)
