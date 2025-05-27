# -*- mode: python ; coding: utf-8 -*-
import platform
import os

block_cipher = None

# Add source files
src_path = os.path.join(os.getcwd(), 'src')
# docker-compose.yml is in the same directory as the build script
docker_compose_path = os.path.join(os.getcwd(), 'docker-compose.yml')

# Determine which Qt framework to use and exclude the other
system = platform.system()
if system == "Windows":
    # On Windows, use PySide6 and exclude PyQt6
    qt_hiddenimports = [
        'PySide6.QtCore',
        'PySide6.QtWidgets', 
        'PySide6.QtGui',
    ]
    qt_excludes = [
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtWidgets',
        'PyQt6.QtGui',
    ]
else:
    # On other platforms, prefer PyQt6 and exclude PySide6
    qt_hiddenimports = [
        'PyQt6.QtCore',
        'PyQt6.QtWidgets',
        'PyQt6.QtGui',
    ]
    qt_excludes = [
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtWidgets',
        'PySide6.QtGui',
    ]

a = Analysis(
    [os.path.join('src', 'ti_csc_launcher.py')],
    pathex=[src_path],
    binaries=[],
    datas=[
        (docker_compose_path, '.'),  # Include docker-compose.yml in the root of the bundle
        ('src/*.py', 'src'),  # Include all Python files from src
    ],
    hiddenimports=qt_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=qt_excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Determine icon path based on platform
icon_path = None
if platform.system() == "Windows":
    icon_path = "icon.ico"
elif platform.system() == "Darwin":
    icon_path = "icon.icns"
# Linux can use PNG directly, but we'll use ICO for consistency
else:
    icon_path = "icon.ico"

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='TI-CSC',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Disable console window for all platforms
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,  # Use platform-appropriate icon
)

# For macOS, always create an app bundle to prevent terminal window
if platform.system() == "Darwin":
    app = BUNDLE(
        exe,
        name='TI-CSC.app',
        icon='icon.icns',  # Use ICNS for macOS app bundle
        bundle_identifier='com.yourcompany.ti-csc',
        info_plist={
            'NSHighResolutionCapable': 'True',
            'LSUIElement': '0',  # Ensure it shows in the dock
            'CFBundleDisplayName': 'TI-CSC',
            'CFBundleName': 'TI-CSC',
        },
    ) 