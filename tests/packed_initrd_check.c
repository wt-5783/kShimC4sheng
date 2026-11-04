/* Replay the real initrd handoff validator against a packed boot image.
 * Host RAM layout is synthetic; kernel header, manifest, DTB and initrd spans
 * come from the actual image. This is not a hardware boot test. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "initrd.h"
#include "dt_simplefb.h"

#define CAPACITY (512 * 1024)
#define BASE 0xa8000000ULL

int main(int argc, char **argv)
{
    assert(argc == 4 || (argc == 5 && strcmp(argv[4], "--early-console") == 0));
    FILE *file = fopen(argv[1], "rb");
    assert(file);
    assert(fseek(file, 0, SEEK_END) == 0);
    long length = ftell(file);
    assert(length > 4096);
    rewind(file);
    unsigned char *image = malloc((size_t)length);
    assert(image && fread(image, 1, (size_t)length, file) == (size_t)length);
    fclose(file);
    size_t skip = memcmp(image, "ANDROID!", 8) == 0 ? 4096 : 0;
    unsigned char *packed = image + skip;
    size_t size = (size_t)length - skip;
    uint64_t offset;
    memcpy(&offset, packed + 0x20, sizeof(offset));
    assert(offset < size && size - offset >= sizeof(MANIFEST_HEADER));
    const MANIFEST_HEADER *header = (const void *)(packed + offset);
    assert(header->magic == MANIFEST_MAGIC);
    assert(header->entry_count <= MANIFEST_MAX_ENTRIES);
    const MANIFEST_ENTRY *entries[MANIFEST_MAX_ENTRIES];
    size_t cursor = (size_t)offset + sizeof(*header);
    for (unsigned i = 0; i < header->entry_count; ++i) {
        assert(cursor <= size && size - cursor >= sizeof(MANIFEST_ENTRY));
        entries[i] = (const void *)(packed + cursor);
        assert(entries[i]->offset <= offset && entries[i]->size <= offset - entries[i]->offset);
        cursor += (sizeof(MANIFEST_ENTRY) + entries[i]->name_len + 3) & ~(size_t)3;
    }
    unsigned index = (unsigned)strtoul(argv[2], NULL, 0);
    assert(index < header->entry_count);
    const MANIFEST_ENTRY *entry = entries[index];
    assert(entry->type == MF_ENTRY_TYPE_LINUX);
    assert(entry->flags & MF_ENTRY_FLAG_HAS_DEVICE_TREE_BLOB);
    assert(entry->device_tree_blob_entry < header->entry_count);
    const MANIFEST_ENTRY *dtb = entries[entry->device_tree_blob_entry];
    void *tree = malloc(CAPACITY);
    assert(tree && fdt_open_into(packed + dtb->offset, tree, CAPACITY) == 0);
    /* Model usable RAM. Preserve all original reservations and /chosen. */
    assert(fdt_setprop_u32(tree, 0, "#address-cells", 2) == 0);
    assert(fdt_setprop_u32(tree, 0, "#size-cells", 2) == 0);
    /* The embedded DT has a zero-sized placeholder replaced by the firmware
     * memory overlay on hardware. Remove placeholders in this host model too. */
    int node;
    while ((node = fdt_node_offset_by_prop_value(tree, -1, "device_type", "memory", 7)) >= 0)
        assert(fdt_del_node(tree, node) == 0);
    node = fdt_add_subnode(tree, 0, "memory@80000000");
    if (node == -FDT_ERR_EXISTS) node = fdt_subnode_offset(tree, 0, "memory@80000000");
    assert(node >= 0);
    assert(fdt_setprop_string(tree, node, "device_type", "memory") == 0);
    fdt64_t reg[] = { cpu_to_fdt64(0x80000000ULL), cpu_to_fdt64(0x40000000ULL) };
    assert(fdt_setprop(tree, node, "reg", reg, sizeof(reg)) == 0);
    const MANIFEST_ENTRY *shim = entries[header->entry_count - 1];
    struct kshim_initrd_context ctx = {
        .entries = entries, .entry_count = header->entry_count,
        .packed_base = BASE, .packed_payload_size = offset,
        .entry = entry, .header = packed + entry->offset,
        .runtime = { BASE + shim->offset, shim->size },
        .runtime_fdt = { 0x90000000ULL, 0x40000 },
        .payload_fdt = { BASE + dtb->offset, dtb->size },
    };
    int result = kshim_initrd_apply(tree, CAPACITY, &ctx);
    printf("entry %u (%.*s): kshim_initrd_apply=%d (%s)\n", index,
           (int)entry->name_len, entry->name, result, fdt_strerror(result));
    int expected = atoi(argv[3]);
    if (result != expected) return 1;
    if (result == 0) {
        int chosen = fdt_path_offset(tree, "/chosen"), len;
        const fdt32_t *ref = fdt_getprop(tree, chosen, "kshim,initrd-entry", &len);
        assert(ref && len == 4 && fdt32_to_cpu(*ref) < header->entry_count);
        const MANIFEST_ENTRY *blob = entries[fdt32_to_cpu(*ref)];
        const fdt64_t *start = fdt_getprop(tree, chosen, "linux,initrd-start", &len);
        assert(start && len == 8 && fdt64_to_cpu(*start) == BASE + blob->offset);
        const fdt64_t *end = fdt_getprop(tree, chosen, "linux,initrd-end", &len);
        assert(end && len == 8 && fdt64_to_cpu(*end) == BASE + blob->offset + blob->size);
        if (argc == 5) {
            /* The fallback geometry used by the sheng runtime. These are
             * modeled physical addresses, never dereferenced on the host. */
            const kshim_framebuffer_config_t fb = {
                .render_address = 0xb8000000ULL,
                .width = 3048, .height = 2032, .stride = 12192,
                .bpp = 32, .format = KSHIM_FB_FORMAT_XRGB8888,
                .buffer_size = (size_t)12192 * 2032,
            };
            int template = fdt_node_offset_by_compatible(tree, -1, "simple-framebuffer");
            assert(template >= 0);
            assert(strcmp(fdt_getprop(tree, template, "status", NULL), "disabled") == 0);
            assert(fdt_node_offset_by_compatible(tree, template, "simple-framebuffer") == -FDT_ERR_NOTFOUND);
            size_t before_size = fdt_totalsize(tree);
            void *before = malloc(before_size);
            assert(before);
            memcpy(before, tree, before_size);
            assert(dt_simplefb_apply(tree, CAPACITY, NULL) < 0);
            assert(memcmp(before, tree, before_size) == 0);
            free(before);
            assert(dt_simplefb_apply(tree, CAPACITY, &fb) == 0);
            int node = fdt_path_offset(tree, "/chosen/framebuffer@b8000000");
            assert(node >= 0);
            assert(strcmp(fdt_getprop(tree, node, "status", NULL), "okay") == 0);
            assert(strcmp(fdt_getprop(tree, node, "format", NULL), "x8r8g8b8") == 0);
            const fdt64_t *reg = fdt_getprop(tree, node, "reg", &len);
            assert(reg && len == 16 && fdt64_to_cpu(reg[0]) == fb.render_address);
            assert(fdt64_to_cpu(reg[1]) == fb.buffer_size);
            const char *props[] = { "width", "height", "stride" };
            const uint32_t values[] = { 3048, 2032, 12192 };
            for (unsigned i = 0; i < 3; ++i) {
                const fdt32_t *value = fdt_getprop(tree, node, props[i], &len);
                assert(value && len == 4 && fdt32_to_cpu(*value) == values[i]);
            }
            node = fdt_path_offset(tree, "/reserved-memory/kshim-framebuffer@b8000000");
            assert(node >= 0 && fdt_get_property(tree, node, "no-map", NULL));
            reg = fdt_getprop(tree, node, "reg", &len);
            assert(reg && len == 16 && fdt64_to_cpu(reg[0]) == fb.render_address);
            assert(fdt64_to_cpu(reg[1]) == fb.buffer_size);
            int reserved = 0;
            for (int i = 0; i < fdt_num_mem_rsv(tree); ++i) {
                uint64_t base, span;
                assert(fdt_get_mem_rsv(tree, i, &base, &span) == 0);
                if (base <= fb.render_address && base + span >= fb.render_address + fb.buffer_size)
                    reserved = 1;
            }
            assert(reserved);
            puts("PASS: real simplefb handoff enables sheng scanout and reserves its full buffer");
        }
        assert(fdt_pack(tree) == 0);
        assert(dt_validate(tree, CAPACITY) == 0);
        puts("PASS: exact initrd bounds exported; packed handoff DT validates");
    }
    free(tree);
    free(image);
    return 0;
}
