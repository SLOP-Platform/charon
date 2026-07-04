# PyInstaller spec for charon.exe — ADR-0005 D7 / P5
#
# Single-file Windows executable bundling charon.cli:main.
# PyInstaller is a BUILD-time tool only; never a runtime dep of src/charon.
#
# Build:  pip install .[packaging] && pyinstaller packaging/charon.spec
# Output: dist/charon.exe

from PyInstaller.building.api import PYZ, EXE
from PyInstaller.building.build_main import Analysis

a = Analysis(
    ["charon_entry.py"],
    pathex=["../src"],
    binaries=[],
    datas=[],
    # Modules dynamically imported inside CLI branches that static analysis misses
    hiddenimports=[
        "charon.adapters.review_mock",
        "charon.adapters.review",
        "charon.parallel",
        "charon.validate",
        "charon.decompose",
        "charon.land",
        "charon.handoff",
        "charon.failover",
        "charon.providers",
        "charon.secrets",
        "charon.config",
        "charon.netutil",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # service/app.py requires FastAPI (optional-extra) — excluded from the exe;
    # the gateway path is stdlib-only (ADR-0005 D5/R9)
    excludes=["fastapi", "uvicorn", "pydantic"],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

# Onefile mode: pass a.binaries + a.datas directly to EXE (no COLLECT step)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="charon",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
