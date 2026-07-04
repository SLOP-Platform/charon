"""PyInstaller entry point for charon.exe.

This wrapper is frozen as ``__main__``, so it MUST use an ABSOLUTE import.
Freezing ``src/charon/cli.py`` directly (the previous spec) ran that module as a
parent-less ``__main__``, and its module-level relative imports (``from . import
…``) crashed the exe at startup:

    ImportError: attempted relative import with no known parent package

Importing ``charon.cli`` as a proper package module (charon is on ``pathex``)
restores the parent package, so its relative imports resolve normally.
"""
import sys

from charon.cli import main

if __name__ == "__main__":
    sys.exit(main())
