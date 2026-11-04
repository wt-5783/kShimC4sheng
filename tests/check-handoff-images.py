#!/usr/bin/env python3
"""Check real candidate payload identity and DT changes (not a hardware test)."""
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packer"))
import bootimg
import fdt
import manifest

VARIANTS = {
    "boot_a_arch_handoff.img": ("out/linux-handoff-kernel/arch/arm64/boot/Image", True),
    "boot_a_arch_handoff_clock_only.img": ("out/linux-handoff-kernel/arch/arm64/boot/Image", False),
    "boot_a_arch_handoff_simplefb_only.img": ("out/fix1-payload/linux-Image", True),
}


def outside_chosen(tree):
    result = {}

    def walk(node, path):
        if path == "/chosen":
            return
        result[path] = dict(node.props)
        for child in node.children:
            walk(child, path.rstrip("/") + "/" + child.name)
    walk(tree.root, "/")
    return result


def check(path):
    path = path.resolve()
    kernel_path, early = VARIANTS[path.name]
    packed = bootimg.parse(path.read_bytes())["kernel"]
    meta = manifest.parse(packed)
    entries = meta["entries"]

    def payload(index):
        entry = entries[index]
        return packed[entry["offset"]:entry["offset"] + entry["size"]]

    stock = bootimg.parse((ROOT / "out/backup/boot_a-stock-trimmed.img").read_bytes())["kernel"]
    assert payload(0)[64:] == stock[64:], "Android body changed"
    assert payload(1) == (ROOT / kernel_path).read_bytes(), "wrong Linux Image"
    assert payload(3) == (ROOT / "out/fix1-payload/linux-initrd.img").read_bytes(), "initrd changed"
    assert payload(len(entries) - 1) == (ROOT / "out/runtime.bin").read_bytes(), "runtime changed"
    source = fdt.Fdt.parse((ROOT / "out/fix1-payload/linux.dtb").read_bytes())
    for index in (1, 4):
        entry = entries[index]
        if index == 4:
            assert (entry["offset"], entry["size"]) == (entries[1]["offset"], entries[1]["size"])
        tree = fdt.Fdt.parse(payload(entry["dtb_entry"]))
        assert outside_chosen(tree) == outside_chosen(source), "non-chosen DT properties changed"
        assert tree.rsvmap == source.rsvmap, "input DT reservations changed"
        assert tree.boot_cpuid == source.boot_cpuid
        assert tree.get("/chosen", "kshim,initrd-entry") == (3).to_bytes(4, "big")
        assert tree.get("/chosen", "armada,boot-stage") == (b"maintenance\0" if index == 4 else None)
        template = tree.node("/chosen/framebuffer")
        assert (template is not None) == early
        if early:
            assert template.get("status") == b"disabled\0"
            assert template.get("reg") is None, "physical scanout must be supplied at runtime"
        args = tree.get("/chosen", "bootargs").rstrip(b"\0").decode().split()
        assert "console=tty0" in args
        assert "root=PARTLABEL=linux" in args
        assert "udmabuf.size_limit_mb=256" in args
        if index == 4:
            assert "systemd.unit=multi-user.target" in args
    print(f"PASS {path.name}: payload identities, device DT properties and both Linux entries; "
          f"sha256={hashlib.sha256(path.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    for path in (map(Path, sys.argv[1:]) if len(sys.argv) > 1
                 else (ROOT / "out" / name for name in VARIANTS)):
        check(path)
