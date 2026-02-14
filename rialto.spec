# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['Rialto.pyw'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/bird_icon.ico', 'assets'),
        ('assets/bird_logo.PNG', 'assets'),
        ('assets/success.wav', 'assets'),
        ('requirements.txt', '.'),
        ('templates', 'templates'),
    ],
    hiddenimports=[],
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
    name='Rialto',
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
    icon='assets/bird_icon.ico',
    version_info={
        'version': (1, 0, 0, 0),
        'file_version': (1, 0, 0, 0),
        'product_version': (1, 0, 0, 0),
        'file_description': 'Rialto Game Publishing Console',
        'product_name': 'Rialto',
        'company_name': 'We the Indies',
        'legal_copyright': 'Copyright (C) 2026 We the Indies',
        'internal_name': 'Rialto.exe',
        'original_filename': 'Rialto.exe',
    }
)
