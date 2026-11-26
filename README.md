# Dinovol mesh cache validation

This patch prevents Dinovol pretraining from silently reusing metadata mesh coordinates computed for a different volume, pyramid shape, or coordinate conversion. It runs inside the existing loader used by `SSLZarrDataset` and `cache_metadata_meshes`. It does not change the model, the loss, the sampler, or the coordinate fix in ScrollPrize/villa PR #2558.

## Use it

1. Start with [ScrollPrize/villa at 9c1afbb](https://github.com/ScrollPrize/villa/tree/9c1afbb1b97a3490156f828704aa706fe3f6cb85). Keep the original license.
2. Apply `2558-coordinate-prerequisite.patch`, then `cache-validation.patch` with `git apply`. The first patch is Cmssmc-code's [existing PR #2558](https://github.com/ScrollPrize/villa/pull/2558), not a result of this work. The third patch, `offline-fixture.patch`, is only needed for the upstream object-point tests.
3. Retain the original metadata catalog for the volumes. Use the existing `dataset.object_points.metadata_path` and `mesh_cache_dir` settings, or pass the volume-level `metadata_path` and `mesh_cache_path`. Run the normal Dinovol dataset or pre-cache command. No need to remove any files.

The loader signs the mesh builder version, volume identity and path, scale, selected and source shapes, and the selected sample's segment and transform metadata. It checks the signature in the same NPZ read used to load the arrays. A mismatch or corrupt signed cache triggers a rebuild. The new archive is written to a unique temporary neighbor before atomic replacement. The unsigned archive and any last successful signed archive survive a failed rebuild. New archives are named `<original-name>.signed.npz`. This preserves both the old path and the original NPZ arrays. Direct readers using `load_mesh_segments_cache` still accept the old archive format. For deliberately pinned offline fixtures, load a trusted NPZ explicitly and pass its resulting meshes with `datasets[].meshes`; automatic cache use does not trust unsigned files without metadata.

Mutable data behind an unchanged remote path is outside this cache's detection scope unless its catalog record changes. Update the catalog or bump the mesh builder version when member content or coordinate semantics change. Initial rebuild cost includes the actual TIFF reads, coordinate conversion, indexing, and serialization. Deployment must provision memory for the meshes of its chosen volumes.

See the [recorded comparison](RESULTS.md) for the measured recovery. Project-authored additions are under the [MIT license](LICENSE).

## Reproduce

`bash reproduce.sh /path/to/pinned/villa /path/to/new/inputs` prepares one public segment and three coarse bands, applies the patches, and runs the verification and tests. Use a clean checkout and fresh `inputs/run`; partial results are not success. See [ENVIRONMENT.md](ENVIRONMENT.md) for packages. Expected transfer is below 1 GB. Do not use a full-volume download.

- Input: PHercParis4 volume `20260411134726-2.400um-0.2m-78keV-masked.zarr` from `pretrain_8_9um.json` at level 2. Mesh: `20260926044226`, normalized public tifxyz. The input URLs and download limits are in `inputs.py`.
- Source windows use the real Dinovol object mask and 192³ source size, with level-5 data read only from chunk bands 2, 8, and 9. These include one band in the old coordinate range and two in the corrected range. Missing storage objects within those bands are native Zarr fill. Other bands are **not evaluated** and appear as fill in the bounded local copy. The output reports how many attempted windows were wholly in the fetched bands. These are not full-scroll acceptance rates.
- The baseline is the corrected upstream loader opening an old-format cache created by the pre-#2558 transform. The candidate is the integrated dataset automatically rebuilding the same cache. The manual control is the corrected loader rebuilding into an unused cache path. Coordinate conversion #2558 is common to the compared code paths and is used in both rebuilds.
- 10,000 deterministic anchor-window attempts check mask acceptance. A further 1,000 calls use the existing retrying mesh-centered sampler. The independent manual control must produce byte-equal decoded arrays and equal summary metrics. A real fine-scale window is then read into `SSLZarrDataset.__getitem__` and checked for labeled sheet points in both global views. Other sources of labels are disabled for isolation.
- This is a training-input regression check, not a result about downstream model quality, ink detection, or legible text.

## Credit

[Issue #2549](https://github.com/ScrollPrize/villa/issues/2549) describes the original coordinate problem. CedBern's reported results are independent prior evidence, not numbers from this run. Credit for the normalized-tifxyz scale fix goes to Cmssmc-code. Gzip catalog handling addresses the known separate issue [#2544](https://github.com/ScrollPrize/villa/pull/2544) and is not claimed as a new contribution. No changes from the normal-grid partial reader or 64-row workarounds are used. Upstream code is licensed under the included [upstream MIT license](UPSTREAM-LICENSE.txt).
