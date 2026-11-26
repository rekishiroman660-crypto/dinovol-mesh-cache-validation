"""Fetch only the validation inputs. No credentials or whole-volume transfer."""
import concurrent.futures
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request
from urllib.parse import urlencode
from xml.etree import ElementTree

ROOT = Path(sys.argv[1]).resolve()
ROOT.mkdir(parents=True, exist_ok=True)
BASE = "https://vesuvius-challenge-open-data.s3.amazonaws.com"
VOL = "PHercParis4/volumes/20260411134726-2.400um-0.2m-78keV-masked.zarr"
MESH = "PHercParis4/segments/20260926044226-spiral-output-generation-19/mesh/intermediate/tifxyz_normalized"
SEG = "20260926044226"
Z5 = (2, 8, 9)


def fetch(key, path, limit, *, optional=False, expected=None):
    if path.exists():
        if expected is not None and path.stat().st_size != expected:
            raise ValueError(f"Wrong size for {path}")
        return
    try:
        response = urllib.request.urlopen(f"{BASE}/{key}", timeout=45)
    except urllib.error.HTTPError as exc:
        if optional and exc.code == 404:
            return
        raise
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    with response, tmp.open("wb") as out:
        total = 0
        while block := response.read(1024**2):
            total += len(block)
            if total > limit:
                raise ValueError(f"Download bound exceeded for {key}")
            out.write(block)
    if expected is not None and total != expected:
        raise ValueError(f"Download size mismatch for {key}: {total}")
    tmp.replace(path)


def chunk(job):
    level, z, y, x = job
    rel = f"{level}/{z}/{y}/{x}"
    fetch(f"{VOL}/{rel}", ROOT / "volume.zarr" / rel, 128**3,
          optional=True, expected=128**3)


def fine(starts, size):
    grid = [range(s // 128, (s + n - 1) // 128 + 1) for s, n in zip(starts, size)]
    jobs = [(2, *k) for k in itertools.product(*grid)]
    if len(jobs) > 27:
        raise ValueError("Fine transfer exceeds one source window")
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        list(pool.map(chunk, jobs))


def prepare():
    fetch("metadata.json", ROOT / "catalog.raw", 12_000_000)
    raw = (ROOT / "catalog.raw").read_bytes()
    catalog = json.loads(gzip.decompress(raw) if raw.startswith(bytes([31, 139])) else raw)
    sample = catalog["samples"]["PHercParis4"]
    sample["segments"] = {SEG: sample["segments"][SEG]}
    (ROOT / "metadata.json").write_text(json.dumps({"samples": {"PHercParis4": sample}}))
    for level in (2, 5):
        fetch(f"{VOL}/{level}/.zarray", ROOT / "volume.zarr" / str(level) / ".zarray", 10000)
    for name in (".zgroup", ".zattrs"):
        fetch(f"{VOL}/{name}", ROOT / "volume.zarr" / name, 100000, optional=True)
    # Verify source-side listing size before fetching any strip.
    coarse_bytes = 0
    for z in Z5:
        prefix = f"{VOL}/5/{z}/"
        query = urlencode({"list-type": 2, "prefix": prefix})
        with urllib.request.urlopen(f"{BASE}/?{query}", timeout=45) as response:
            doc = ElementTree.parse(response)
        if doc.findtext(".//{*}IsTruncated") != "false":
            raise ValueError("Unexpectedly large chunk listing")
        coarse_bytes += sum(int(x.text) for x in doc.findall(".//{*}Size"))
    if coarse_bytes > 220_000_000:
        raise ValueError(f"Coarse transfer bound exceeded: {coarse_bytes}")
    # Total possible transfer: 653 MB TIFF + 220 MB coarse + 57 MB fine + 12 MB catalog.
    with concurrent.futures.ThreadPoolExecutor(12) as pool:
        list(pool.map(chunk, [(5, z, y, x) for z, y, x in itertools.product(Z5, range(8), range(8))]))
    with concurrent.futures.ThreadPoolExecutor(3) as pool:
        futures = [pool.submit(fetch, f"{MESH}/{a}.tif", ROOT / f"{a}.tif",
                               217635584, expected=217635584) for a in "xyz"]
        for f in futures:
            f.result()
    print(json.dumps({"metadata_sha256": hashlib.sha256(raw).hexdigest(),
                      "input_bytes_on_disk": sum(p.stat().st_size for p in ROOT.rglob("*") if p.is_file())}), flush=True)


if __name__ == "__main__":
    prepare()

