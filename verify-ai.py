"""Verify the persistent RiffLab AI installation without PowerShell quoting issues."""
import importlib
import sys

for name in ("demucs", "torch", "librosa"):
    try:
        module = importlib.import_module(name)
        print(f"[OK] {name}: {getattr(module, '__version__', 'installed')}")
    except Exception as exc:
        print(f"[MISSING/BROKEN] {name}: {type(exc).__name__}: {exc}")
        sys.exit(1)
print("AI components verified.")
