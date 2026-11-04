import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers
sys.path.insert(0, helpers.sys_path)
import bootimg  # noqa: E402
import manifest  # noqa: E402
import fdt  # noqa: E402

MAKE_BOOT = os.path.join(helpers.ROOT, "packer", "make_boot.py")
PACKER = os.path.join(helpers.ROOT, "build", "packer", "MultiBootKernelPatcher")


class PackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(PACKER):
            subprocess.run(["make", "packer"], cwd=helpers.ROOT, check=True,
                           capture_output=True)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.stock_kernel = helpers.make_image()
        self.stock = os.path.join(self.d, "boot_stock.img")
        open(self.stock, "wb").write(helpers.make_v4_boot(self.stock_kernel))
        self.linux = os.path.join(self.d, "Image")
        open(self.linux, "wb").write(helpers.make_image(16384))
        self.dtb = helpers.make_dtb(os.path.join(self.d, "sheng.dtb"))
        self.runtime = os.path.join(self.d, "runtime.bin")
        open(self.runtime, "wb").write(b"\0" * (4 * 1024 * 1024))
        self.out = os.path.join(self.d, "boot_a.img")

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, *extra):
        cmd = [sys.executable, MAKE_BOOT,
               "--stock-boot", self.stock,
               "--linux-image", self.linux,
               "--dtb", self.dtb,
               "--runtime", self.runtime,
               "--out", self.out,
               "--work", os.path.join(self.d, "work"), *extra]
        return subprocess.run(cmd, capture_output=True, text=True)

    def load(self):
        image = bootimg.parse(open(self.out, "rb").read())
        m = manifest.parse(image["kernel"])
        return image, m

    def test_build_layout(self):
        p = self.build()
        self.assertEqual(p.returncode, 0, p.stderr)
        image, m = self.load()
        self.assertEqual(image["version"], 4)
        self.assertEqual(image["kernel_size"], len(image["kernel"]))
        self.assertEqual(m["default_entry"], 0)
        self.assertEqual(m["timeout_ms"], 8000)
        self.assertEqual([e["name"] for e in m["entries"]],
                         ["Android", "Linux", "sheng-dtb", "Attached Shim"])
        self.assertEqual(m["entries"][0]["type_name"], "Linux")
        self.assertIn("BASE_IMAGE", m["entries"][0]["flag_names"])
        self.assertEqual(m["entries"][0]["size"], len(self.stock_kernel))
        self.assertIn("HAS_DTB", m["entries"][1]["flag_names"])
        self.assertEqual(m["entries"][1]["dtb_entry"], 2)
        self.assertGreaterEqual(m["entries"][2]["size"], os.path.getsize(self.dtb))
        self.assertEqual(m["entries"][3]["size"], 4 * 1024 * 1024)

    def test_linux_default_and_bootargs(self):
        p = self.build("--default", "linux", "--timeout-ms", "3000",
                       "--bootargs", "root=PARTLABEL=linux rw console=tty0")
        self.assertEqual(p.returncode, 0, p.stderr)
        image, m = self.load()
        self.assertEqual(m["default_entry"], 1)
        self.assertEqual(m["timeout_ms"], 3000)
        entry = m["entries"][2]
        dtb = image["kernel"][entry["offset"]:entry["offset"] + entry["size"]]
        dtb_path = os.path.join(self.d, "out.dtb")
        open(dtb_path, "wb").write(dtb)
        got = subprocess.run(["fdtget", "-t", "s", dtb_path, "/chosen", "bootargs"],
                             capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(got, "root=PARTLABEL=linux rw console=tty0")

    def test_initrd_entry(self):
        initrd = os.path.join(self.d, "initrd.img")
        open(initrd, "wb").write(b"x" * 4096)
        p = self.build("--initrd", initrd)
        self.assertEqual(p.returncode, 0, p.stderr)
        image, m = self.load()
        self.assertEqual([e["name"] for e in m["entries"]],
                         ["Android", "Linux", "sheng-dtb", "initrd", "Attached Shim"])
        self.assertEqual(m["entries"][3]["type_name"], "Blob")
        entry = m["entries"][2]
        dtb = image["kernel"][entry["offset"]:entry["offset"] + entry["size"]]
        dtb_path = os.path.join(self.d, "out.dtb")
        open(dtb_path, "wb").write(dtb)
        idx = subprocess.run(["fdtget", "-t", "u", dtb_path, "/chosen", "kshim,initrd-entry"],
                             capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(idx, "3")

    def test_diagnostic_entry(self):
        for with_initrd in (False, True):
            with self.subTest(initrd=with_initrd):
                extra = []
                if with_initrd:
                    initrd = os.path.join(self.d, "initrd.img")
                    with open(initrd, "wb") as out:
                        # Real initrds rarely end exactly on a page boundary.
                        out.write(b"x" * 4097)
                    extra = ["--initrd", initrd]
                normal_args = "root=PARTLABEL=linux rw quiet loglevel=3 systemd.unit=graphical.target"
                p = self.build("--diagnostic", "--bootargs", normal_args, *extra)
                self.assertEqual(p.returncode, 0, p.stderr)
                image, m = self.load()
                normal = m["entries"][1]
                diag_idx = 4 if with_initrd else 3
                diag = m["entries"][diag_idx]
                self.assertEqual(diag["name"], "Linux diagnostics")
                self.assertIn("EXECUTABLE", diag["flag_names"])
                self.assertEqual((diag["offset"], diag["size"]),
                                 (normal["offset"], normal["size"]))
                self.assertEqual(diag["dtb_entry"], diag_idx + 1)
                if with_initrd:
                    blob = m["entries"][3]
                    dtb_entry = m["entries"][diag["dtb_entry"]]
                    for page in (4096, 16384, 65536):
                        rounded_end = (blob["offset"] + blob["size"] + page - 1) & ~(page - 1)
                        self.assertGreaterEqual(dtb_entry["offset"], rounded_end,
                                                "diagnostic DTB overlaps initrd copy pages")
                self.assertEqual(m["default_entry"], 0)
                def tree(index):
                    e = m["entries"][index]
                    return fdt.Fdt.parse(image["kernel"][e["offset"]:e["offset"] + e["size"]])
                normal_tree = tree(normal["dtb_entry"])
                self.assertEqual(normal_tree.get("/chosen", "bootargs"),
                                 normal_args.encode() + b"\0")
                self.assertIsNone(normal_tree.get("/chosen", "armada,boot-stage"))
                dt = tree(diag["dtb_entry"])
                self.assertEqual(dt.get("/chosen", "armada,boot-stage"), b"maintenance\0")
                args = dt.get("/chosen", "bootargs").rstrip(b"\0").decode().split()
                self.assertIn("systemd.unit=multi-user.target", args)
                self.assertIn("loglevel=7", args)
                self.assertNotIn("quiet", args)
                self.assertNotIn("systemd.unit=graphical.target", args)
                self.assertNotIn("loglevel=3", args)
                self.assertEqual(dt.get("/chosen", "kshim,initrd-entry"),
                                 (3).to_bytes(4, "big") if with_initrd else None)

    def test_early_console_and_diagnostic_real_handoff(self):
        # Preserve unit identity while adding only the disabled display template.
        source = fdt.Fdt.parse(Path(self.dtb).read_bytes())
        source.set("/bluetooth", "local-bd-address", b"\x01\x02\x03\x04\x05\x06")
        source.write(self.dtb)
        original = Path(self.dtb).read_bytes()
        initrd = os.path.join(self.d, "initrd.img")
        with open(initrd, "wb") as out:
            out.write(b"x" * 4097)
        args = "root=PARTLABEL=linux rw console=tty0 loglevel=7"
        p = self.build("--early-console", "--diagnostic", "--initrd", initrd,
                       "--bootargs", args)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(Path(self.dtb).read_bytes(), original)
        image, m = self.load()
        for index in (1, 4):
            entry = m["entries"][m["entries"][index]["dtb_entry"]]
            tree = fdt.Fdt.parse(image["kernel"][entry["offset"]:entry["offset"] + entry["size"]])
            self.assertEqual(tree.get("/chosen/framebuffer", "status"), b"disabled\0")
            self.assertIsNone(tree.get("/chosen/framebuffer", "reg"))
            self.assertEqual(tree.get("/bluetooth", "local-bd-address"),
                             b"\x01\x02\x03\x04\x05\x06")
            # Replay both real C validators, not just the Python packer.
            check = subprocess.run(
                ["bash", "tests/check-packed-initrd.sh", self.out, str(index), "0", "--early-console"],
                cwd=helpers.ROOT, capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
            self.assertIn("real simplefb handoff enables sheng scanout", check.stdout)
        report = json.loads(Path(self.out + ".json").read_text())
        self.assertTrue(report["early_console"])
        normal = m["entries"][2]
        tree = fdt.Fdt.parse(image["kernel"][normal["offset"]:normal["offset"] + normal["size"]])
        self.assertEqual(tree.get("/chosen", "bootargs"), args.encode() + b"\0")

    def test_early_console_is_opt_in(self):
        p = self.build()
        self.assertEqual(p.returncode, 0, p.stderr)
        image, m = self.load()
        entry = m["entries"][2]
        tree = fdt.Fdt.parse(image["kernel"][entry["offset"]:entry["offset"] + entry["size"]])
        self.assertIsNone(tree.node("/chosen/framebuffer"))
        self.assertFalse(json.loads(Path(self.out + ".json").read_text())["early_console"])

    def test_early_console_rejects_other_board(self):
        helpers.make_dtb(self.dtb, compatible="lenovo,other")
        p = self.build("--early-console")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("requires a xiaomi,sheng DTB", p.stderr)
        self.assertFalse(os.path.exists(self.out))

    def test_rejects_oversized_payload(self):
        p = self.build("--partition-size", "1048576")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("exceeds partition budget", p.stderr)

    def test_accepts_gzip_linux_image(self):
        raw = helpers.make_image()
        open(self.linux, "wb").write(helpers.gzip_bytes(raw))
        p = self.build()
        self.assertEqual(p.returncode, 0, p.stderr)
        _, m = self.load()
        linux = [e for e in m["entries"] if e["name"] == "Linux"][0]
        self.assertEqual(linux["size"], len(raw))


if __name__ == "__main__":
    unittest.main()
