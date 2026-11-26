# PHercParis4 verification

Run `169-phercparis4-20261126-seed388169` completed on a 16 GiB Linux cloud instance using the pinned villa base and the two separate code patches. See [events](results.jsonl), [input hashes](source-manifest.sha256) and [test output](test-results.txt).

| Measurement | Old cache | Automatic rebuild | Manual rebuild |
|---|---:|---:|---:|
| Object-mask admissions per 10,000 mesh-anchor windows | 0 (0%) | 941 (9.41%) | 941 (9.41%) |
| Windows wholly inside the fetched bands | 2,328 | 1,190 | 1,190 |
| Admissions among windows wholly inside the fetched bands | 0/2,328 | 941/1,190 (79.08%) | 941/1,190 (79.08%) |
| Successful calls to the retrying mesh-centered sampler, out of 1,000 | 0 | 560 | 560 |
| Valid mesh vertices | 47,026,606 | 47,026,606 | 47,026,606 |

Selected-scale bounding boxes in Z, Y, X (voxel centers, rounded to two decimals):

- Old cache lower (1000.86, 297.54, 321.71), upper (4436.34, 1860.13, 1897.01).
- Both rebuilds lower (4004.56, 1191.28, 1287.97), upper (17746.49, 7441.63, 7589.17).

The automatic and manual rebuilds produced byte-identical decoded coordinate, validity, ink-state and bounding-box arrays. The second automatic call reused the signed archive without reading TIFF data or rewriting it. Changing the downscale record in the metadata file at the same path attempted a rebuild, and an injected read failure preserved both the old and last-good signed archives.

The real level-2 scan window at (9383, 3860, 6700) returned 7,077,865 nonzero voxels in a 192³ input. The actual Dinovol dataset returned two 1×128×128×128 global views containing **181 and 182 valid labeled mesh points**. No surface or fiber fallback supplied those labels.

Total verification elapsed time was **336.539 s** after imports. The automatic initialization stage, including building the signed archive, computing the mask and checking the old archive checksum, took **129.187 s**. Maximum process RSS was **9,817,620 KiB (9.36 GiB)**. Source inputs stored were **876,423,800 bytes**, including the filtered catalog. The native compilation was separate. Four cache regressions and 16 upstream object-point tests passed.

Rates above apply to this one mesh and the three downloaded coarse bands only. The comparison is against stale coordinates with the same corrected code installed, not against the corrected loader after a manual refresh. No full-scroll training, transcription, or change in ink prediction quality is claimed.
