#!/bin/bash
# Build a pinned engine inside the target Debian system for both supported CPUs.
set -euo pipefail
PIN=b29c606e28a01b1bc8c1351026a0fa6e616bf6c4
BUILD=$(mktemp -d)
trap 'rm -rf "$BUILD"' EXIT
git -c init.defaultBranch=main init "$BUILD/source"
git -C "$BUILD/source" remote add origin https://github.com/ggml-org/llama.cpp.git
git -C "$BUILD/source" fetch --depth 1 origin "$PIN"
git -C "$BUILD/source" checkout --detach FETCH_HEAD
test "$(git -C "$BUILD/source" rev-parse HEAD)" = "$PIN"
cmake -S "$BUILD/source" -B "$BUILD/build" \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF \
  -DGGML_NATIVE=OFF -DGGML_SSE42=OFF -DGGML_AVX=OFF -DGGML_AVX2=OFF \
  -DGGML_FMA=OFF -DGGML_F16C=OFF -DGGML_AVX512=OFF \
  -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_APP=OFF \
  -DLLAMA_BUILD_UI=OFF -DLLAMA_USE_PREBUILT_UI=OFF -DLLAMA_BUILD_SERVER=ON
cmake --build "$BUILD/build" --parallel 2 --target llama-server
install -D -m 755 "$BUILD/build/bin/llama-server" /opt/sidekick/llama-server
/opt/sidekick/llama-server --version
printf '%s\n' "$PIN" > /opt/sidekick/engine-version.txt
install -D -m 644 "$BUILD/source/LICENSE" /opt/sidekick/licenses/llama.cpp-LICENSE
