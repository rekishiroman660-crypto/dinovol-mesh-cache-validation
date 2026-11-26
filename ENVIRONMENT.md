# Reproduction environment

Verified stack for the CPU-only validation (no GPU or full-scroll model training):

- Linux x86-64, Debian 13 userspace, Python 3.12.14, GCC/G++ 14.2.
- 16 GiB cgroup memory limit. Allow up to several GiB of workspace disk for a sparse volume mirror, three TIFFs, two rebuild archives, a legacy fixture and compilation artifacts. Keep the verification and native compilation sequential on a small machine.
- PyTorch 2.10.0+cpu, NumPy 2.4.3, SciPy 1.18.1, scikit-image 0.26.0, Pillow 13.0.0, einops 0.8.2, tqdm 4.70.1.
- vc_reader is built directly from the pinned villa checkout. No mocked replacement for its TIFF or Zarr readers is required. The experiment only redirects the known TIFF URLs to byte-for-byte local copies and uses a bounded local Zarr mirror.
- Native libraries from conda-forge, concurrentqueue tag v1.0.4 at commit `6dd38b8a1dbaa7863aa907045f32308a56a6ff5d`. vc_reader's CMake dependency fetch resolved vc_delta3d to `427248122a088bad7d5b1209ea55c311de3378bb`.

Example setup using an existing `uv`, `micromamba`, and Linux C/C++ toolchain with libcurl development files. The working paths below are not required names. Set `kit` to a new writable directory and `villa` to the pinned clone.

```bash
uv venv "$kit/.venv" --python 3.12.14
source "$kit/.venv/bin/activate"
uv pip install --index-url https://download.pytorch.org/whl/cpu torch==2.10.0 torchvision==0.25.0
uv pip install numpy==2.4.3 scipy==1.18.1 pillow==13.0.0 scikit-image==0.26.0 \
  einops==0.8.2 tqdm==4.70.1 timm==1.0.20 cmake==4.4.5 ninja==1.13.2 nanobind==3.1.0 scikit-build-core==1.1.2

export MAMBA_ROOT_PREFIX="$kit/mamba-root"
micromamba create -y -p "$kit/native" -c conda-forge \
  blosc=1.21.7 c-blosc2=3.8.0 libtiff=4.7.2 libpng=1.6.59 libjpeg-turbo=3.2.1 \
  sqlite=3.54.1 nlohmann_json=3.12.0 libboost-devel=1.92.0 zlib=1.3.2
export CMAKE_PREFIX_PATH="$kit/native" PKG_CONFIG_PATH="$kit/native/lib/pkgconfig"
export LD_LIBRARY_PATH="$kit/native/lib" CMAKE_BUILD_PARALLEL_LEVEL=4
export CC=/usr/bin/gcc CXX=/usr/bin/g++ AGENTS_AGENT_MODE=1 AGENTS_ALLOW_INSTALL=1
git clone --depth 1 --branch v1.0.4 https://github.com/cameron314/concurrentqueue.git "$kit/concurrentqueue"
cmake -S "$kit/concurrentqueue" -B "$kit/queue-build" -DCMAKE_INSTALL_PREFIX="$kit/native"
cmake --install "$kit/queue-build"
uv pip install --no-build-isolation "$villa/vc_reader" \
  --config-setting=cmake.define.VC_READER_ENABLE_CUDA=OFF \
  --config-setting=cmake.define.CMAKE_INSTALL_RPATH="$kit/native/lib"
```

Clone the pinned villa revision with both `dinovol/` and `vc_reader/`. Run `bash reproduce.sh "$villa" "$kit/inputs"`. A completed run must contain the `complete` event. The public catalog is mutable, so compare input digests before comparing counts to the recorded run. Peak RSS is process-wide and cumulative, in KiB. Stage times are elapsed from verification entry after imports, not a timed end-to-end training run.
