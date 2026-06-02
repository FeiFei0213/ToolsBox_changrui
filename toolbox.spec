# toolbox.spec
from PyInstaller.utils.hooks import collect_submodules, collect_all

block_cipher = None

# registry.py 用 importlib 动态加载，必须手动声明所有工具子模块
tool_hidden = collect_submodules('tools')

# cv2 / numpy / PySide6 有编译扩展和平台插件，collect_all 确保全部打入
cv2_datas,     cv2_bins,     cv2_hidden     = collect_all('cv2')
numpy_datas,   numpy_bins,   numpy_hidden   = collect_all('numpy')
pyside6_datas, pyside6_bins, pyside6_hidden = collect_all('PySide6')

hidden_imports = tool_hidden + cv2_hidden + numpy_hidden + pyside6_hidden

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=cv2_bins + numpy_bins + pyside6_bins,
    datas=[
        ('tools/pixel_starfire/config', 'tools/pixel_starfire/config'),
        ('icon', 'icon'),
    ] + cv2_datas + numpy_datas + pyside6_datas,
    hiddenimports=hidden_imports,
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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ToolsBox',
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
    icon='icon/icon.ico',
)
