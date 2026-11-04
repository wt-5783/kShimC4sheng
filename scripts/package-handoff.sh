#!/usr/bin/env bash
# Build isolated A/B images and the combined candidate; never flash anything.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
if [ $# -ne 1 ]; then
  echo 'usage: scripts/package-handoff.sh /path/to/patched/arch/arm64/boot/Image' >&2
  exit 1
fi
kernel=$(realpath "$1")
for file in "$kernel" out/backup/boot_a-stock-trimmed.img out/fix1-payload/linux-Image \
            out/fix1-payload/linux.dtb out/fix1-payload/linux-initrd.img out/runtime.bin; do
  [ -s "$file" ] || { echo "missing input: $file" >&2; exit 1; }
done
for suffix in clock_only ''; do
  name="out/boot_a_arch_handoff${suffix:+_$suffix}.img"
  [ ! -e "$name" ] || { echo "refusing to overwrite: $name" >&2; exit 1; }
done
# The simplefb-only image may have already been produced while the kernel
# compiled. The final checksum file records exactly what was validated.
package() {
  local name=$1 image=$2; shift 2
  python3 packer/make_boot.py \
    --stock-boot out/backup/boot_a-stock-trimmed.img \
    --linux-image "$image" --dtb out/fix1-payload/linux.dtb \
    --initrd out/fix1-payload/linux-initrd.img --runtime out/runtime.bin \
    --diagnostic --bootargs 'root=PARTLABEL=linux rw rootwait udmabuf.size_limit_mb=256 console=tty0' \
    --out "$name" --work "${name%.img}-work" --keep-work "$@"
}
# Rebuild the simplefb-only control from the exact same inputs as the candidates.
package out/boot_a_arch_handoff_simplefb_only.img out/fix1-payload/linux-Image --early-console
package out/boot_a_arch_handoff_clock_only.img "$kernel"
package out/boot_a_arch_handoff.img "$kernel" --early-console
bash tests/check-packed-initrd.sh out/boot_a_arch_handoff.img 1 0 --early-console
for index in 1 4; do
  build/packed-initrd-check out/boot_a_arch_handoff.img "$index" 0 --early-console
  build/packed-initrd-check out/boot_a_arch_handoff_simplefb_only.img "$index" 0 --early-console
  build/packed-initrd-check out/boot_a_arch_handoff_clock_only.img "$index" 0
done
python3 tests/check-handoff-images.py
sha256sum out/boot_a_arch_handoff{,_clock_only,_simplefb_only}.img > out/handoff-SHA256SUMS
printf '\nCombined candidate: out/boot_a_arch_handoff.img\nAll host handoff checks passed; hardware boot remains untested. Nothing flashed.\n'
