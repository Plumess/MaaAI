#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
release_tag="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["release"]["tag"])' "$MAA_OCR_PROJECT/configs/sources.lock.json")"
release="$MAA_OCR_RUNTIME/releases/$release_tag"
source_dir="$MAA_OCR_RUNTIME/vendor/MAA-release"
deps="$source_dir/src/MaaUtils/MaaDeps/vcpkg/installed/maa-x64-linux/include"
"$MAA_OCR_RUNTIME/toolchains/native/bin/clang++" -O2 -std=c++20 -stdlib=libc++ -nostdlib++ \
 -I"$MAA_OCR_RUNTIME/toolchains/native/include/c++/v1" -I"$release" \
 -I"$source_dir/src/MaaCore" -I"$source_dir/src/MaaUtils/include" -I"$deps" -I"$deps/opencv4" \
 "$MAA_OCR_PROJECT/native/maa_acceptance_probe.cpp" \
 -L"$release" -Wl,-rpath,"$release" -Wl,-rpath-link,"$release" -Wl,--export-dynamic \
 -lMaaCore -lMaaUtils -l:libonnxruntime.so.1 -l:libfastdeploy_ppocr.so -l:libopencv_world4.so.412 -l:libc++.so.1 -l:libc++abi.so.1 -l:libunwind.so.1 -pthread -ldl \
 -o "$MAA_OCR_RUNTIME/build/maa_acceptance_probe"
