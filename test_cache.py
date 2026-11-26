"""Fast policy/format regressions for the integrated mesh loader."""
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np
from dinovol_2.dataset import object_labels as m


class MeshCacheTests(unittest.TestCase):
    def setUp(self):
        t = TemporaryDirectory()
        self.addCleanup(t.cleanup)
        root = Path(t.name)
        self.meta = root / "metadata.json"
        self.legacy = root / "mesh.npz"
        self.signed = root / "mesh.npz.signed.npz"
        self.volume = "20260411134726"
        self.data = {"samples": {"PHercParis4": {
            "volumes": {self.volume: {"id": self.volume, "properties": {"shape": [32]*3}}},
            "segments": {"sheet": {"id": "sheet", "original_volume_id": self.volume,
                "data": [{"type": "tifxyz-normalized", "url": "example"}],
                "properties": {"original_volume_downscale": 2}}}
        }}}
        self.write()
        v = np.ones((3, 5), dtype=np.float32)
        reader = patch.object(m, "_read_tiff", return_value=v)
        self.reader = reader.start()
        self.addCleanup(reader.stop)

    def write(self, compressed=False):
        data = json.dumps(self.data).encode()
        self.meta.write_bytes(gzip.compress(data) if compressed else data)

    def load(self, *, path=None, scale=1, shape=(16,16,16)):
        return m.load_or_build_volume_meshes(
            path or f"/PHercParis4/volumes/{self.volume}-scan.zarr",
            scale, shape, sample_id="PHercParis4", metadata_path=self.meta,
            mesh_cache_path=self.legacy,
        )

    def test_legacy_kept_and_archive_compatible(self):
        m.save_mesh_segments_cache(self.legacy, [])
        before = self.legacy.read_bytes()
        (segment,) = self.load()
        self.assertEqual(segment.valid.shape, (3, 5))
        self.assertEqual(self.legacy.read_bytes(), before)
        self.assertEqual(m.load_mesh_segments_cache(self.legacy), [])
        self.assertEqual(m.load_mesh_segments_cache(self.signed)[0].segment_id, "sheet")
        mtime = self.signed.stat().st_mtime_ns
        self.reader.reset_mock()
        self.load()
        self.reader.assert_not_called()
        self.assertEqual(self.signed.stat().st_mtime_ns, mtime)

    def test_each_input_can_invalidate(self):
        self.load()
        for kw in ({"scale": 0}, {"shape": (15,16,16)},
                   {"path": f"/elsewhere/PHercParis4/volumes/{self.volume}-scan.zarr"}):
            self.reader.reset_mock()
            self.load(**kw)
            self.assertEqual(self.reader.call_count, 3)
            self.load()
        self.reader.reset_mock()
        with patch.object(m, "MESH_BUILD_VERSION", "changed"):
            self.load()
        self.assertEqual(self.reader.call_count, 3)
        self.reader.reset_mock()
        self.data["samples"]["PHercParis4"]["segments"]["sheet"]["properties"]["original_volume_downscale"] = 3
        self.write(compressed=True)
        (segment,) = self.load()
        self.assertEqual(self.reader.call_count, 3)
        np.testing.assert_array_equal(segment.bbox_lo, [1.25]*3)
        self.reader.reset_mock()
        self.write(compressed=False)
        self.load()
        self.reader.assert_not_called()

    def test_failed_rebuild_is_not_published(self):
        self.load()
        signed = self.signed.read_bytes()
        self.reader.side_effect = OSError("test unavailable coordinate file")
        with self.assertRaises(RuntimeError):
            self.load(shape=(15,16,16))
        self.assertEqual(self.signed.read_bytes(), signed)
        self.meta.unlink()
        with self.assertRaises(FileNotFoundError):
            self.load()

    def test_corrupt_signed_archive_is_rebuilt(self):
        self.signed.write_bytes(b"broken zip")
        self.assertEqual(self.load()[0].segment_id, "sheet")
        self.assertEqual(self.reader.call_count, 3)


if __name__ == "__main__":
    unittest.main()

