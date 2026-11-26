#!/usr/bin/env bash
# Usage: bash reproduce.sh /path/to/pinned/villa /path/to/new/inputs
set -euo pipefail
here=$(cd -- "$(dirname -- "$0")" && pwd)
export VILLA
VILLA=$(cd -- "$1" && pwd)
mkdir -p -- "$2"
input=$(cd -- "$2" && pwd)
test "$(git -C "$VILLA" rev-parse HEAD)" = 9c1afbb1b97a3490156f828704aa706fe3f6cb85
test -z "$(git -C "$VILLA" status --porcelain --untracked-files=no)"
test ! -e "$input/run"
git -C "$VILLA" apply --check "$here/2558-coordinate-prerequisite.patch"
git -C "$VILLA" apply "$here/2558-coordinate-prerequisite.patch"
export CORRECTED_SOURCE="$input/corrected-source.py"
cp "$VILLA/dinovol/dinovol_2/dataset/object_labels.py" "$CORRECTED_SOURCE"
git -C "$VILLA" apply --check "$here/cache-validation.patch" "$here/offline-fixture.patch"
git -C "$VILLA" apply "$here/cache-validation.patch" "$here/offline-fixture.patch"
export PYTHONPATH="$VILLA/dinovol${PYTHONPATH:+:$PYTHONPATH}"
export OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2
python "$here/inputs.py" "$input"
python "$here/test_cache.py"
python -m unittest discover -s "$VILLA/dinovol/tests" -p test_object_points.py
python "$here/verify.py" "$input" | tee "$input/results.jsonl"

