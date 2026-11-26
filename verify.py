"""Compare a legacy cache, automatic validation, and manual rebuild on one real segment."""
import gc
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time
import types
from unittest.mock import patch

import numpy as np
import torch
from dinovol_2.dataset import object_labels as candidate
from dinovol_2.dataset.ssl_zarr_dataset import SSLZarrDataset
from inputs import MESH, ROOT, SEG, VOL, Z5, fine

VILLA = Path(os.environ["VILLA"])
SEED = 388169
STAGE = ROOT / "run"
STAGE.mkdir(exist_ok=False)
META = STAGE / "metadata.json"
META.write_bytes((ROOT / "metadata.json").read_bytes())
LEGACY = STAGE / "mesh.npz"
SIGNED = LEGACY.with_name(LEGACY.name + ".signed.npz")
SHAPE = tuple(json.loads((ROOT / "volume.zarr/2/.zarray").read_text())["shape"])
PUBLIC_VOLUME = "s3://vesuvius-challenge-open-data/" + VOL
SOURCE = "dinovol/dinovol_2/dataset/object_labels.py"
started = time.perf_counter()


def event(label, **values):
    print(json.dumps(dict(stage=label, wall_s=round(time.perf_counter()-started, 3),
                          process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                          **values)), flush=True)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def module(name, code):
    m = types.ModuleType(name)
    sys.modules[name] = m
    exec(compile(code, name, "exec"), m.__dict__)
    return m


def tiff(url, opts=None):
    assert url.rsplit("/", 1)[0] == "s3://vesuvius-challenge-open-data/" + MESH, url
    return candidate.images.read(str(ROOT / url.rsplit("/", 1)[1]))


def build(m, path, **kw):
    return m.load_or_build_volume_meshes(
        str(ROOT / "volume.zarr"), 2, SHAPE, sample_id="PHercParis4", volume_id="20260411134726",
        metadata_path=META, mesh_cache_path=path, s3_storage_options={"anon": True}, **kw)


def geometry(meshes):
    (m,) = meshes
    assert m.segment_id == SEG
    h = hashlib.sha256()
    for a in [m.zyx, m.valid, m.ink_state, m.bbox_lo, m.bbox_hi]:
        h.update(memoryview(a).cast("B"))
    return dict(valid=m.n_valid_points, bbox_lo_zyx=m.bbox_lo.tolist(),
                bbox_hi_zyx=m.bbox_hi.tolist(), arrays_sha256=h.hexdigest())


def metrics(ds, meshes):
    v = ds.volumes[0]
    previous, v.meshes = v.meshes, meshes
    try:
        anchors = meshes[0].anchor_valid_zyx
        np.random.seed(SEED)
        rng = np.random.default_rng(SEED)
        inside = admitted = covered = 0
        lo, hi = np.array(v.usable_bbox[:3]), np.array(v.usable_bbox[3:])
        for i in rng.integers(len(anchors), size=10000):
            pt = anchors[i]
            if np.all((pt >= lo) & (pt < hi)):
                inside += 1
                start = ds._sample_point_centered_source_start(v.usable_bbox, pt)
                admitted += ds._start_allowed(v, start)
                # Level-5 chunk edges expressed in level-2 voxels. Missing
                # chunks inside the fetched bands are genuine Zarr fill.
                first = start[0] // 1024
                last = (start[0] + ds.source_sampling_size[0] - 1) // 1024
                covered += all(z in Z5 for z in range(first, last + 1))
        np.random.seed(SEED)
        successes = sum(ds._sample_mesh_centered_start(v, prefer_ink=False) is not None
                        for _ in range(1000))
        return dict(window_attempts=10000, anchors_in_usable_bbox=inside,
                    object_mask_accepted=int(admitted), windows_wholly_in_fetched_bands=covered,
                    centered_attempts=1000,
                    centered_success=successes, **geometry(meshes))
    finally:
        v.meshes = previous


def prohibit(*args, **kwargs):
    raise AssertionError("unexpected TIFF read")


torch.set_num_threads(2)
event("environment", seed=SEED, os=platform.platform(), python=platform.python_version(),
      torch=torch.__version__, numpy=np.__version__, shape=SHAPE,
      candidate_source_sha256=sha(candidate.__file__), metadata_sha256=sha(META),
      upstream=subprocess.check_output(["git", "-C", str(VILLA), "rev-parse", "HEAD"], text=True).strip(),
      tiff_sha256={a: sha(ROOT / (a + ".tif")) for a in "xyz"})
base = subprocess.check_output(["git", "-C", str(VILLA), "show", f"HEAD:{SOURCE}"], text=True)
corrected_source = Path(os.environ["CORRECTED_SOURCE"]).read_text()
old = module("original_coordinates", base)
corrected = module("corrected_coordinates_legacy_loader", corrected_source)
old._read_tiff = corrected._read_tiff = tiff
# Only this fixture creation uses the old transform. All evaluated loaders include #2558.
stale = build(old, LEGACY)
event("legacy_created", **geometry(stale))
del stale
gc.collect()
old_hash = sha(LEGACY)
event("legacy_checksum", archive_sha256=old_hash)
cfg = json.loads((VILLA / "dinovol/dinovol_2/configs/pretrain_8_9um.json").read_text())["dataset"]
(entry,) = [x for x in cfg["datasets"] if x["sample_id"] == "PHercParis4"]
assert entry["volume_path"].rstrip("/") == PUBLIC_VOLUME
# Omit other supervision to isolate the metadata-mesh contribution.
entry = {k: entry[k] for k in ("sample_id", "pixel_size_um", "volume_scale")}
entry.update(volume_path=str(ROOT / "volume.zarr"), volume_id="20260411134726",
             metadata_path=str(META), mesh_cache_path=str(LEGACY))
cfg.update(datasets=[entry], read_ahead=0)
cfg["object_points"].update(mesh_cache_dir=None, mesh_anchor_prob=1, ink_anchor_prob=0)
event("candidate_start")
with patch.object(candidate, "_read_tiff", tiff):
    ds = SSLZarrDataset(cfg, do_augmentations=False)
assert SIGNED.is_file()
assert sha(LEGACY) == old_hash
assert ds.volumes[0].start_cells is not None
event("candidate_mask", mask_eligible_starts=ds.volumes[0].valid_crop_starts,
      z_level5_chunk_bands=[2, 8, 9])
result = metrics(ds, ds.volumes[0].meshes)
event("automatic", **result)

with patch.object(corrected, "_read_tiff", prohibit):
    m = build(corrected, LEGACY)
event("baseline", **metrics(ds, m))
del m
gc.collect()

stamp = SIGNED.stat().st_mtime_ns
with patch.object(candidate, "_read_tiff", prohibit):
    m = build(candidate, LEGACY)
assert geometry(m)["arrays_sha256"] == result["arrays_sha256"] and SIGNED.stat().st_mtime_ns == stamp
event("second_use", no_tiff_reads=True, archive_unchanged=True)
del m
gc.collect()

m = build(corrected, STAGE / "manual.npz")
manual = metrics(ds, m)
assert result == manual
event("manual", **manual)
del m
gc.collect()

# Changed metadata at the same path must attempt a rebuild. The injected I/O
# failure must not publish a cache or clobber either last-good archive.
metadata_raw = META.read_bytes()
mutation = json.loads(metadata_raw)
mutation["samples"]["PHercParis4"]["segments"][SEG]["properties"]["original_volume_downscale"] = 2
META.write_text(json.dumps(mutation))
try:
    with patch.object(candidate, "_read_tiff", prohibit):
        try:
            build(candidate, LEGACY)
        except RuntimeError as exc:
            assert isinstance(exc.__cause__, AssertionError)
        else:
            raise AssertionError("same-path mutation did not invalidate")
finally:
    META.write_bytes(metadata_raw)
assert SIGNED.stat().st_mtime_ns == stamp and sha(LEGACY) == old_hash
event("input_change", reopen_same_path=True, rebuild_attempted=True, archives_unchanged=True)
assert result["object_mask_accepted"] > 0

# Read one genuine fine-scale source window through the actual Dataset item path.
for sample_seed in range(SEED, SEED+100):
    np.random.seed(sample_seed)
    plan = ds._draw_source_plan(0.3)
    if plan.mesh_anchor is not None:
        break
else:
    raise AssertionError("No real mesh-centered source plan")
fine(plan.starts, ds.source_sampling_size)
raw = ds._read_source_window(plan.array, plan.starts)
assert raw.shape == tuple(ds.source_sampling_size) and np.count_nonzero(raw)
np.random.seed(sample_seed)
torch.manual_seed(sample_seed)
sample = ds[0]
labeled = (sample["object_point_objects"] > 0) & (sample["object_point_kinds"] == candidate.SHEET_KIND)
valid = [int((x & labeled).sum()) for x in sample["object_point_valid"]]
assert all(n > 0 for n in valid)
event("training_item", seed=sample_seed, source_start=plan.starts, raw_shape=raw.shape,
      raw_nonzero=int(np.count_nonzero(raw)), global_shapes=[list(v.shape) for v in sample["global_views"]],
      valid_labeled_mesh_points=valid, source_bytes=sum(p.stat().st_size for p in ROOT.rglob("*")
                                                if p.is_file() and STAGE not in p.parents))
ds.close()
event("complete")

