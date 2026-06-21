from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.api_utils import cleanup_uploads


class UploadCleanupTest(unittest.TestCase):
    def test_cleanup_uploads_deletes_all_files_and_clears_upload_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            upload_dir = Path(tmp) / "uploads"
            upload_dir.mkdir()
            nested = upload_dir / "nested"
            nested.mkdir()
            first = upload_dir / "first.xlsx"
            second = nested / "second.csv"
            first.write_bytes(b"abc")
            second.write_bytes(b"defg")
            upload_map = {"a": first, "b": second}

            result = cleanup_uploads(upload_dir=upload_dir, upload_map=upload_map, all_files=True)

            self.assertEqual(result["deleted_files"], 2)
            self.assertEqual(result["deleted_bytes"], 7)
            self.assertEqual(result["errors"], [])
            self.assertEqual(upload_map, {})
            self.assertFalse(first.exists())
            self.assertFalse(second.exists())
            self.assertFalse(nested.exists())

    def test_cleanup_uploads_refuses_paths_outside_upload_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upload_dir = root / "uploads"
            upload_dir.mkdir()
            outside = root / "outside.txt"
            outside.write_text("keep", encoding="utf-8")
            upload_map = {"bad": outside}

            result = cleanup_uploads(upload_dir=upload_dir, upload_map=upload_map)

            self.assertEqual(result["deleted_files"], 0)
            self.assertTrue(result["errors"])
            self.assertTrue(outside.exists())
            self.assertIn("bad", upload_map)


if __name__ == "__main__":
    unittest.main()
