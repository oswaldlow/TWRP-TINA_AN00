#!/usr/bin/env python3
"""Debug patch: dump the kernel log to the `reserved2` partition before init reboots.

The Hi Nova bootloader keeps no log of a failed recovery boot, and TWRP's init
reboots straight to the bootloader on a fatal error. With this patch every
reboot path (fatal errors, critical service crashes, normal reboots) goes
through RebootSystem(), which first writes the whole kernel log buffer to the
raw `reserved2` partition (all zeros on stock, never read by the bootloader).
It is read back from Android with:
    su -c 'dd if=/dev/block/by-name/reserved2 bs=1M count=4' > dump.bin

Usage: hinova_kmsg_dump.py <path to system/core/init/reboot_utils.cpp>
"""
import sys

path = sys.argv[1]
src = open(path).read()

INCLUDES = """#include <unistd.h>

#include <dirent.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/klog.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
"""

HELPER = r'''
// Hi Nova debug: write the kernel log to the raw `reserved2` partition.
static void HinovaDumpKmsg(const char* why) {
    static bool done = false;
    if (done) return;
    done = true;

    int major_num = -1, minor_num = -1;
    DIR* dir = opendir("/sys/class/block");
    if (dir == nullptr) return;
    char path[320];
    char buf[1024];
    struct dirent* ent;
    while ((ent = readdir(dir)) != nullptr) {
        snprintf(path, sizeof(path), "/sys/class/block/%s/uevent", ent->d_name);
        int fd = open(path, O_RDONLY | O_CLOEXEC);
        if (fd < 0) continue;
        ssize_t n = read(fd, buf, sizeof(buf) - 1);
        close(fd);
        if (n <= 0) continue;
        buf[n] = '\0';
        if (strstr(buf, "PARTNAME=reserved2\n") == nullptr) continue;
        char* ma = strstr(buf, "MAJOR=");
        char* mi = strstr(buf, "MINOR=");
        if (ma != nullptr && mi != nullptr) {
            major_num = atoi(ma + 6);
            minor_num = atoi(mi + 6);
        }
        break;
    }
    closedir(dir);
    if (major_num < 0) return;

    const char* node = "/dev/.hinova_kmsgdump";
    unlink(node);
    if (mknod(node, S_IFBLK | 0600, makedev(major_num, minor_num)) != 0) return;

    int size = klogctl(10 /* SYSLOG_ACTION_SIZE_BUFFER */, nullptr, 0);
    if (size <= 0) size = 4 << 20;
    char* log = static_cast<char*>(malloc(size));
    if (log != nullptr) {
        int got = klogctl(3 /* SYSLOG_ACTION_READ_ALL */, log, size);
        if (got < 0) got = 0;
        int fd = open(node, O_WRONLY | O_CLOEXEC);
        if (fd >= 0) {
            char hdr[512];
            int h = snprintf(hdr, sizeof(hdr), "HINOVA-KMSG-DUMP v1\npid=%d reason=%s len=%d\n\n",
                             getpid(), why != nullptr ? why : "", got);
            ssize_t w = 0;
            if (h > 0) w += write(fd, hdr, h);
            w += write(fd, log, got);
            w += write(fd, "\nHINOVA-KMSG-END\n", 17);
            (void)w;
            fsync(fd);
            close(fd);
        }
        free(log);
    }
    unlink(node);
}

bool IsRebootCapable() {'''

CALL_ANCHOR = '    LOG(INFO) << "Reboot ending, jumping to kernel";\n'
CALL = CALL_ANCHOR + '    HinovaDumpKmsg(rebootTarget.c_str());\n'

for anchor in ('#include <unistd.h>\n', '\nbool IsRebootCapable() {', CALL_ANCHOR):
    if src.count(anchor) != 1:
        sys.exit('anchor not found exactly once: %r' % anchor)

src = src.replace('#include <unistd.h>\n', INCLUDES, 1)
src = src.replace('\nbool IsRebootCapable() {', HELPER, 1)
src = src.replace(CALL_ANCHOR, CALL, 1)
open(path, 'w').write(src)
print('patched', path)
