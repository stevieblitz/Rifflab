"""Install a verified, separately published RiffLab AI Engine ZIP.

The release manifest is a small JSON file with:
{"version":"...","url":"https://github.com/.../releases/download/.../RiffLabAI.zip","sha256":"64 lowercase hex chars"}
Only HTTPS GitHub release downloads are accepted. No executable is run during install.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import urllib.parse
import urllib.request
import zipfile


def install_engine(manifest_url, destination=None, progress=None):
    url = urllib.parse.urlparse(manifest_url)
    if url.scheme != "https" or url.hostname != "github.com":
        raise ValueError("AI manifest must be hosted on HTTPS github.com")
    with urllib.request.urlopen(manifest_url, timeout=30) as response:
        manifest = json.load(response)
    download = manifest["url"]
    parsed = urllib.parse.urlparse(download)
    if parsed.scheme != "https" or parsed.hostname != "github.com" or "/releases/download/" not in parsed.path:
        raise ValueError("AI engine must come from a GitHub Release")
    expected = manifest["sha256"].lower()
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError("Invalid SHA-256 in manifest")
    root = Path(destination or (Path(os.environ.get("LOCALAPPDATA", Path.home())) / "RiffLab" / "AI"))
    root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rifflab-ai-", dir=root.parent) as tmp:
        tmp = Path(tmp)
        archive = tmp / "engine.zip"
        digest = hashlib.sha256()
        with urllib.request.urlopen(download, timeout=120) as response, archive.open("wb") as target:
            total = int(response.headers.get("Content-Length", 0))
            count = 0
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                target.write(block)
                digest.update(block)
                count += len(block)
                if progress:
                    progress(count, total)
        if digest.hexdigest() != expected:
            raise ValueError("AI Engine SHA-256 mismatch")
        stage = tmp / "unpacked"
        stage.mkdir()
        with zipfile.ZipFile(archive) as zf:
            for member in zf.infolist():
                target = (stage / member.filename).resolve()
                if not target.is_relative_to(stage.resolve()):
                    raise ValueError("Unsafe ZIP path")
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)
        if not (stage / "RiffLabAI.exe").is_file():
            raise ValueError("AI Engine executable missing from archive")
        # Preserve the previous installation until the new archive is verified.
        incoming = root.with_name(root.name + ".incoming")
        backup = root.with_name(root.name + ".backup")
        if incoming.exists():
            shutil.rmtree(incoming)
        shutil.copytree(stage, incoming)
        if backup.exists():
            shutil.rmtree(backup)
        if root.exists():
            root.rename(backup)
        try:
            incoming.rename(root)
        except Exception:
            if backup.exists() and not root.exists():
                backup.rename(root)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    return root
