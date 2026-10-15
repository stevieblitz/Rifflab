import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from ai_engine_installer import install_engine


class Response(io.BytesIO):
    def __init__(self, content):
        super().__init__(content)
        self.headers = {"Content-Length": str(len(content))}
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.close()


class InstallerTests(unittest.TestCase):
    def setUp(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as z:
            z.writestr("RiffLabAI.exe", b"fake-test-exe")
            z.writestr("_internal/example.dat", b"data")
        self.archive = data.getvalue()
        self.manifest = json.dumps({
            "version": "test",
            "url": "https://github.com/stevieblitz/Rifflab/releases/download/test/RiffLabAI.zip",
            "sha256": hashlib.sha256(self.archive).hexdigest(),
        }).encode()

    def fetch(self, url, timeout=30):
        return Response(self.manifest if url.endswith("manifest.json") else self.archive)

    def test_installs_verified_archive(self):
        with tempfile.TemporaryDirectory() as tmp, patch("ai_engine_installer.urllib.request.urlopen", side_effect=self.fetch):
            root = install_engine("https://github.com/stevieblitz/Rifflab/releases/download/test/manifest.json", Path(tmp) / "AI")
            self.assertEqual((root / "RiffLabAI.exe").read_bytes(), b"fake-test-exe")

    def test_rejects_wrong_checksum_and_keeps_existing_install(self):
        bad = json.loads(self.manifest)
        bad["sha256"] = "0" * 64
        def fetch(url, timeout=30):
            return Response(json.dumps(bad).encode() if url.endswith("manifest.json") else self.archive)
        with tempfile.TemporaryDirectory() as tmp, patch("ai_engine_installer.urllib.request.urlopen", side_effect=fetch):
            root = Path(tmp) / "AI"
            root.mkdir()
            (root / "RiffLabAI.exe").write_bytes(b"previous")
            with self.assertRaises(ValueError):
                install_engine("https://github.com/stevieblitz/Rifflab/releases/download/test/manifest.json", root)
            self.assertEqual((root / "RiffLabAI.exe").read_bytes(), b"previous")

    def test_rejects_zip_traversal(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as z:
            z.writestr("../escape.txt", "oops")
            z.writestr("RiffLabAI.exe", "fake")
        archive = data.getvalue()
        manifest = json.dumps({"version":"test", "url":"https://github.com/stevieblitz/Rifflab/releases/download/test/RiffLabAI.zip", "sha256":hashlib.sha256(archive).hexdigest()}).encode()
        def fetch(url, timeout=30):
            return Response(manifest if url.endswith("manifest.json") else archive)
        with tempfile.TemporaryDirectory() as tmp, patch("ai_engine_installer.urllib.request.urlopen", side_effect=fetch):
            with self.assertRaises(ValueError):
                install_engine("https://github.com/stevieblitz/Rifflab/releases/download/test/manifest.json", Path(tmp) / "AI")


if __name__ == "__main__":
    unittest.main()
