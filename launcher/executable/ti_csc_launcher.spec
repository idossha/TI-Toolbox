# -*- mode: python ; coding: utf-8 -*-
import platform

block_cipher = None

a = Analysis(
    ['ti_csc_launcher.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('docker-compose.yml', '.'),
    ],
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtWidgets',
        'PyQt6.QtGui',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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