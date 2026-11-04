import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers


class ExtractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def run_extract(self, *args):
        cmd = [sys.executable, os.path.join(helpers.ROOT, "packer", "extract.py"), *args]
        return subprocess.run(cmd, capture_output=True, text=True)

    def test_v4_stock_kernel(self):
        kernel = helpers.make_image()
        boot = os.path.join(self.d, "stock.img")
        open(boot, "wb").write(helpers.make_v4_boot(kernel))
        out = os.path.join(self.d, "out")
        p = self.run_extract("--stock", "--boot", boot, "--out", out, "--prefix", "stock")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(open(os.path.join(out, "stock-kernel.img"), "rb").read(), kernel)
        stock_boot = open(os.path.join(out, "stock-boot.img"), "rb").read()
        self.assertEqual(stock_boot[:8], b"ANDROID!")
        self.assertEqual(len(stock_boot), 4096 + len(kernel))

    def test_v0_gzip_plus_dtb_and_initrd(self):
        kernel = helpers.make_image()
        dtb = helpers.make_dtb(os.path.join(self.d, "sheng.dtb"))
        dtb_data = open(dtb, "rb").read()
        ramdisk = b"initrd-data" * 100
        boot = os.path.join(self.d, "linux.img")
        open(boot, "wb").write(helpers.make_v0_boot(
            helpers.gzip_bytes(kernel) + dtb_data, ramdisk))
        out = os.path.join(self.d, "out")
        p = self.run_extract("--boot", boot, "--out", out, "--prefix", "linux")
        self.assertEqual(p.returncode, 0, p.stderr)
        info = json.loads(p.stdout)
        self.assertEqual(open(os.path.join(out, "linux-Image"), "rb").read(), kernel)
        self.assertEqual(open(os.path.join(out, "linux.dtb"), "rb").read(), dtb_data)
        self.assertEqual(open(os.path.join(out, "linux-initrd.img"), "rb").read(), ramdisk)
        self.assertEqual(info["dtb"]["size"], len(dtb_data))

    def test_v2_separate_dtb_preserves_device_address(self):
        kernel = helpers.make_image()
        dtb = helpers.make_dtb(os.path.join(self.d, "device.dtb"), extra='''
            bluetooth { local-bd-address = [12 34 56 78 9a bc]; };
        ''')
        with open(dtb, "rb") as f:
            dtb_data = f.read()
        for second, recovery in [(b"", b""), (b"second", b"recovery")]:
            with self.subTest(second=bool(second), recovery=bool(recovery)):
                boot = os.path.join(self.d, "v2.img")
                with open(boot, "wb") as f:
                    f.write(helpers.make_v2_boot(kernel, dtb_data, b"initrd",
                                                 second, recovery))
                p = self.run_extract("--boot", boot, "--out", self.d,
                                     "--prefix", "v2")
                self.assertEqual(p.returncode, 0, p.stderr)
                with open(os.path.join(self.d, "v2.dtb"), "rb") as f:
                    self.assertEqual(f.read(), dtb_data)

    def test_rejects_truncated_v2_dtb(self):
        dtb = helpers.make_dtb(os.path.join(self.d, "truncated.dtb"))
        with open(dtb, "rb") as f:
            image = helpers.make_v2_boot(helpers.make_image(), f.read())
        boot = os.path.join(self.d, "truncated.img")
        with open(boot, "wb") as f:
            f.write(image[:-1])
        p = self.run_extract("--boot", boot, "--out", self.d, "--prefix", "bad")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("DTB extends past image", p.stderr)

    def test_rejects_gzip_as_stock(self):
        boot = os.path.join(self.d, "bad.img")
        open(boot, "wb").write(helpers.make_v4_boot(helpers.gzip_bytes(helpers.make_image())))
        p = self.run_extract("--stock", "--boot", boot, "--out", self.d, "--prefix", "bad")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("gzip", p.stderr)


if __name__ == "__main__":
    unittest.main()
