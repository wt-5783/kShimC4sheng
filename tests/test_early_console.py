"""The early console is opt-in and must not rewrite unrelated DT resources."""
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "packer"))
import fdt
import make_boot


class EarlyConsoleTest(unittest.TestCase):
    def tree(self):
        tree = fdt.Fdt(fdt.Node(""), b"\0" * 16)
        tree.set("/", "compatible", b"xiaomi,sheng\0qcom,sm8550\0")
        tree.set("/chosen", "bootargs", b"root=PARTLABEL=linux rw\0")
        tree.set("/bluetooth", "local-bd-address", b"\x01\x02\x03\x04\x05\x06")
        return tree

    def test_disabled_template_and_bus_cells(self):
        tree = self.tree()
        make_boot.add_early_console_template(tree)
        self.assertEqual(tree.get("/chosen/framebuffer", "compatible"),
                         b"simple-framebuffer\0")
        self.assertEqual(tree.get("/chosen/framebuffer", "status"), b"disabled\0")
        # Physical addresses and geometry must come from runtime, not another board.
        for prop in ("reg", "width", "height", "stride", "memory-region"):
            self.assertIsNone(tree.get("/chosen/framebuffer", prop))
        for prop in ("#address-cells", "#size-cells"):
            self.assertEqual(tree.get("/chosen", prop), struct.pack(">I", 2))
        self.assertEqual(tree.get("/chosen", "ranges"), b"")
        self.assertEqual(tree.get("/chosen", "bootargs"), b"root=PARTLABEL=linux rw\0")
        self.assertEqual(tree.get("/bluetooth", "local-bd-address"),
                         b"\x01\x02\x03\x04\x05\x06")

    def test_idempotent_and_preserves_template_clock_references(self):
        tree = self.tree()
        node = tree.ensure_node("/chosen/framebuffer@12340000")
        node.set("compatible", b"simple-framebuffer\0")
        node.set("status", b"disabled\0")
        node.set("clocks", struct.pack(">II", 17, 3))
        make_boot.add_early_console_template(tree)
        before = tree.tobytes()
        make_boot.add_early_console_template(tree)
        self.assertEqual(tree.tobytes(), before)
        self.assertEqual(len(tree.node("/chosen").children), 1)
        self.assertEqual(node.get("clocks"), struct.pack(">II", 17, 3))

    def test_rejects_other_board(self):
        tree = self.tree()
        tree.set("/", "compatible", b"lenovo,tb710fu\0qcom,pineapple\0")
        with self.assertRaisesRegex(fdt.FdtError, "sheng"):
            make_boot.add_early_console_template(tree)

    def test_rejects_incompatible_chosen_layout_without_mutation(self):
        for prop, value in (("#address-cells", struct.pack(">I", 1)),
                            ("#size-cells", struct.pack(">I", 1)),
                            ("ranges", b"not-an-identity-map")):
            with self.subTest(prop=prop):
                tree = self.tree()
                tree.set("/chosen", prop, value)
                before = tree.tobytes()
                with self.assertRaises(fdt.FdtError):
                    make_boot.add_early_console_template(tree)
                self.assertEqual(tree.tobytes(), before)

    def test_rejects_unsafe_or_duplicate_templates_without_mutation(self):
        for bad in ("enabled", "memory-region", "duplicate", "name-collision"):
            with self.subTest(bad=bad):
                tree = self.tree()
                node = tree.ensure_node("/chosen/framebuffer")
                if bad != "name-collision":
                    node.set("compatible", b"simple-framebuffer\0")
                    node.set("status", b"okay\0" if bad == "enabled" else b"disabled\0")
                if bad == "memory-region":
                    node.set("memory-region", b"")
                if bad == "duplicate":
                    second = tree.ensure_node("/chosen/another-framebuffer")
                    second.set("compatible", b"simple-framebuffer\0")
                    second.set("status", b"disabled\0")
                before = tree.tobytes()
                with self.assertRaises(fdt.FdtError):
                    make_boot.add_early_console_template(tree)
                self.assertEqual(tree.tobytes(), before)


if __name__ == "__main__":
    unittest.main()
