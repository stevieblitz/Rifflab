"""Check UI dependencies without PowerShell inline Python code."""
import importlib.util
import sys
for name in ("PySide6", "numpy", "sounddevice", "yt_dlp"):
    if importlib.util.find_spec(name) is None:
        print(f"Missing UI dependency: {name}")
        sys.exit(1)
print("UI dependencies verified.")
