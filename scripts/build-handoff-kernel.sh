#!/usr/bin/env bash
# Build, never install/flash, the pinned sheng kernel with the MDP clock fix.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
COMMIT=42f3b40c702abbc37c3a04c95af008cd283aeaf3
RELEASE=7.2.6-sm8550-00103-g42f3b40c702a
CONFIG_SHA256=7013c8620f31cf5c8d2a23dc68a717b48e66669776b3f87e0ac0a6c857cd275f
PATCH="$ROOT/patches/kernel/0001-sm8550-mdp-clock-parent-enable.patch"
source_dir=""; config="/boot/config-$RELEASE"
out="$ROOT/out/linux-handoff-kernel"; jobs=4
usage() {
  printf '%s\n' 'usage: scripts/build-handoff-kernel.sh --source PATH [--config FILE] [--out DIR] [--jobs N]' \
    'Requires ianchb/sm8550-mainline at 42f3b40c702abbc37c3a04c95af008cd283aeaf3.' \
    'Requires the original config fingerprint; keeps the existing module lookup release.' \
    'Only Image is built. No modules, /boot files or partitions are installed.'
}
while [ $# -gt 0 ]; do
  case "$1" in
    --source) source_dir=$2; shift 2 ;;
    --config) config=$2; shift 2 ;;
    --out) out=$2; shift 2 ;;
    --jobs) jobs=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 1 ;;
  esac
done
[ -n "$source_dir" ] && [ -f "$config" ] || { usage >&2; exit 1; }
[[ "$jobs" =~ ^[1-9][0-9]*$ ]] || { echo 'invalid --jobs' >&2; exit 1; }
source_dir=$(realpath "$source_dir")
config=$(realpath "$config")
[ "$(sha256sum "$config" | cut -d' ' -f1)" = "$CONFIG_SHA256" ] || {
  echo 'wrong baseline config; refusing to risk compatibility with installed modules' >&2; exit 1;
}
mkdir -p "$out"
out=$(realpath "$out")
[ "$source_dir" != "$out" ] || { echo 'out-of-tree build required' >&2; exit 1; }
[ "$config" != "$out/.config" ] || { echo '--config must be a preserved input config' >&2; exit 1; }
[ "$(git -C "$source_dir" rev-parse HEAD)" = "$COMMIT" ] || {
  echo 'wrong kernel source revision; refusing to mix kernel/module versions' >&2; exit 1;
}
for tool in make clang ld.lld llvm-ar llvm-nm llvm-objcopy llvm-objdump llvm-readelf llvm-strip flex bison bc pkg-config; do
  command -v "$tool" >/dev/null || { echo "missing build tool: $tool" >&2; exit 1; }
done
pkg-config --exists libelf
# Do not silently compile unrelated local changes. Accept only the exact one-line fix.
changed=$(git -C "$source_dir" diff HEAD --name-only)
if [ -z "$changed" ]; then
  git -C "$source_dir" apply --check "$PATCH"
  git -C "$source_dir" apply "$PATCH"
else
  [ "$changed" = drivers/clk/qcom/dispcc-sm8550.c ] &&
    [ "$(git -C "$source_dir" diff HEAD --numstat)" = $'1\t1\tdrivers/clk/qcom/dispcc-sm8550.c' ] &&
    git -C "$source_dir" apply --reverse --check "$PATCH" || {
      echo 'kernel source has unexpected tracked changes' >&2; exit 1;
    }
fi
cp "$config" "$out/config.input"
cp "$config" "$out/.config"
"$source_dir/scripts/config" --file "$out/.config" --disable LOCALVERSION_AUTO
# The change is clock-internal, adds no symbols, and needs no changed module
# configuration. Preserve the known source/config/release; review config.diff
# for any toolchain-induced changes before using the resulting image.
args=(-C "$source_dir" O="$out" ARCH=arm64 LLVM=1 LLVM_IAS=1
      LOCALVERSION=-00103-g42f3b40c702a KBUILD_BUILD_VERSION=243)
make "${args[@]}" olddefconfig
make "${args[@]}" -s kernelrelease > "$out/kernelrelease.txt"
[ "$(<"$out/kernelrelease.txt")" = "$RELEASE" ] || {
  echo 'unexpected kernel release; refusing to use existing modules' >&2; exit 1;
}
"$source_dir/scripts/diffconfig" "$out/config.input" "$out/.config" > "$out/config.diff"
# Only the reviewed compiler-capability/version changes may differ from the
# original config. Same release alone is not evidence of module compatibility.
python3 - "$out/config.input" "$out/.config" <<'PY'
import re
import sys

def config(path):
    values = {}
    with open(path) as file:
        for line in file:
            match = re.match(r'CONFIG_(\w+)=(.*)', line)
            if match:
                values[match[1]] = match[2]
            else:
                match = re.match(r'# CONFIG_(\w+) is not set', line)
                if match:
                    values[match[1]] = 'n'
    return values

before, after = map(config, sys.argv[1:])
allowed = set('''CC_HAS_BROKEN_COUNTED_BY_REF AS_VERSION CC_MS_EXTENSIONS
CC_VERSION_TEXT CLANG_VERSION LLD_VERSION LOCALVERSION_AUTO PAHOLE_VERSION
RUSTC_LLVM_MAJOR_VERSION RUSTC_LLVM_VERSION RUSTC_VERSION CC_HAS_ALLOC_TOKEN
CC_HAS_COUNTED_BY_PTR RUSTC_HAS_SUSPICIOUS_RUNTIME_SYMBOL_DEFINITIONS
WARN_CONTEXT_ANALYSIS'''.split())
unexpected = sorted(key for key in before.keys() | after.keys()
                    if before.get(key) != after.get(key) and key not in allowed)
if unexpected:
    sys.exit('unreviewed config changes; inspect config.diff: ' + ', '.join(unexpected))
PY
printf 'Source: %s\nExpected module release: %s\nCompiler: ' "$COMMIT" "$RELEASE"
clang --version
make "${args[@]}" -j"$jobs" Image
sha256sum "$out/arch/arm64/boot/Image" "$out/.config" "$config" "$PATCH" > "$out/SHA256SUMS"
printf '\nBuilt: %s\nNo files installed or flashed. Review config.diff and test boot before deployment.\n' \
  "$out/arch/arm64/boot/Image"
