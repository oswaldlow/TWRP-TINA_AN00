#!/usr/bin/env python3
"""Debug patch for TWRP init: leave a trail in the raw `reserved2` partition.

The Hi Nova bootloader keeps no log of a failed recovery boot, and TWRP's init
reboots straight to the bootloader on a fatal error. This patch makes init
write to `reserved2` (112 MB, all zeros on stock, never read by the bootloader):

  offset 0                    whole kernel log, written in RebootSystem()
                              (every reboot path: fatal errors, critical
                              service crashes, normal reboots)
  offset 16 MiB               live kernel log: a child forked in first stage
                              rewrites the whole log every 0.3 s for ~3 min,
                              so a hang (watchdog reset) or panic still leaves
                              the last kernel messages
  offset 100 MiB + slot*4 KiB stage markers:
      slot 0  FirstStageMain() entry (before /sys is mounted)
      slot 1  first stage, kernel logging initialised
      slot 2  SetupSelinux() entry
      slot 5  after MountMissingSystemPartitions()
      slot 6  after ReadPolicy()
      slot 7  LoadSelinuxPolicy(), right before security_load_policy()
      slot 3  policy loaded, before SelinuxSetEnforcement()
      slot 4  SecondStageMain() entry

Read back from Android (build\read_reserved2.ps1 does all of this):
    su -c 'dd if=/dev/block/by-name/reserved2 bs=1M count=8'               # kmsg at reboot
    su -c 'dd if=/dev/block/by-name/reserved2 bs=1M skip=16 count=8'       # live kmsg
    su -c 'dd if=/dev/block/by-name/reserved2 bs=4096 skip=25600 count=16' # markers

Usage: hinova_kmsg_dump.py <path to system/core/init>
"""
import os
import sys

init_dir = sys.argv[1]


def patch(name, edits):
    path = os.path.join(init_dir, name)
    src = open(path).read()
    for anchor, replacement in edits:
        if src.count(anchor) != 1:
            sys.exit('%s: anchor not found exactly once: %r' % (name, anchor))
        src = src.replace(anchor, replacement, 1)
    open(path, 'w').write(src)
    print('patched', path)


INCLUDES = """#include <unistd.h>

#include <dirent.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/klog.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <time.h>
"""

HELPER = r'''
// ---- Hi Nova debug: trail in the raw `reserved2` partition ----
// Stock: /dev/block/sda36 = 259:20; used when /sys is not mounted yet.
static constexpr int kHinovaFallbackMajor = 259;
static constexpr int kHinovaFallbackMinor = 20;
static constexpr off_t kHinovaMarkBase = 100LL * 1024 * 1024;

static int HinovaOpenReserved2() {
    int fd = open("/dev/block/by-name/reserved2", O_WRONLY | O_CLOEXEC);
    if (fd >= 0) return fd;

    int major_num = -1, minor_num = -1;
    DIR* dir = opendir("/sys/class/block");
    if (dir != nullptr) {
        char path[320];
        char buf[1024];
        struct dirent* ent;
        while ((ent = readdir(dir)) != nullptr) {
            snprintf(path, sizeof(path), "/sys/class/block/%s/uevent", ent->d_name);
            int ufd = open(path, O_RDONLY | O_CLOEXEC);
            if (ufd < 0) continue;
            ssize_t n = read(ufd, buf, sizeof(buf) - 1);
            close(ufd);
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
    }
    if (major_num < 0) {
        major_num = kHinovaFallbackMajor;
        minor_num = kHinovaFallbackMinor;
    }

    const char* nodes[] = {"/dev/.hinova_r2", "/.hinova_r2"};
    for (const char* node : nodes) {
        unlink(node);
        if (mknod(node, S_IFBLK | 0600, makedev(major_num, minor_num)) != 0) continue;
        fd = open(node, O_WRONLY | O_CLOEXEC);
        unlink(node);
        if (fd >= 0) return fd;
    }
    return -1;
}

void HinovaMark(int slot, const char* tag) {
    int fd = HinovaOpenReserved2();
    if (fd < 0) return;
    struct timespec ts = {};
    clock_gettime(CLOCK_BOOTTIME, &ts);
    char buf[256];
    int n = snprintf(buf, sizeof(buf), "HINOVA-MARK slot=%d tag=%s pid=%d boottime=%ld.%03ld\n",
                     slot, tag, getpid(), static_cast<long>(ts.tv_sec), ts.tv_nsec / 1000000);
    if (n > 0) {
        ssize_t w = pwrite(fd, buf, n, kHinovaMarkBase + static_cast<off_t>(slot) * 4096);
        (void)w;
    }
    fsync(fd);
    close(fd);
}

static void HinovaDumpKmsg(const char* why) {
    static bool done = false;
    if (done) return;
    done = true;

    int size = klogctl(10 /* SYSLOG_ACTION_SIZE_BUFFER */, nullptr, 0);
    if (size <= 0) size = 4 << 20;
    char* log = static_cast<char*>(malloc(size));
    if (log == nullptr) return;
    int got = klogctl(3 /* SYSLOG_ACTION_READ_ALL */, log, size);
    if (got < 0) got = 0;

    int fd = HinovaOpenReserved2();
    if (fd >= 0) {
        char hdr[512];
        int h = snprintf(hdr, sizeof(hdr), "HINOVA-KMSG-DUMP v2\npid=%d reason=%s len=%d\n\n",
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

// Fork a child that keeps rewriting the whole kernel log to reserved2 @16 MiB.
static constexpr off_t kHinovaLiveBase = 16LL * 1024 * 1024;

void HinovaStartKmsgLogger() {
    pid_t pid = fork();
    if (pid != 0) return;  // parent, or fork failed

    int size = klogctl(10 /* SYSLOG_ACTION_SIZE_BUFFER */, nullptr, 0);
    if (size <= 0) size = 4 << 20;
    char* log = static_cast<char*>(malloc(size));
    if (log == nullptr) _exit(0);
    int fd = -1;
    for (int seq = 0; seq < 600; seq++) {
        if (fd < 0) fd = HinovaOpenReserved2();
        if (fd >= 0) {
            int got = klogctl(3 /* SYSLOG_ACTION_READ_ALL */, log, size);
            if (got < 0) got = 0;
            struct timespec ts = {};
            clock_gettime(CLOCK_BOOTTIME, &ts);
            char hdr[256];
            int h = snprintf(hdr, sizeof(hdr),
                             "HINOVA-KMSG-LIVE v1\nseq=%d boottime=%ld.%03ld len=%d\n\n", seq,
                             static_cast<long>(ts.tv_sec), ts.tv_nsec / 1000000, got);
            if (h < 0) h = 0;
            ssize_t w = 0;
            w += pwrite(fd, hdr, h, kHinovaLiveBase);
            w += pwrite(fd, log, got, kHinovaLiveBase + h);
            w += pwrite(fd, "\nHINOVA-KMSG-END\n", 17, kHinovaLiveBase + h + got);
            (void)w;
            fdatasync(fd);
        }
        usleep(300 * 1000);
    }
    _exit(0);
}
// ---- end Hi Nova debug ----

bool IsRebootCapable() {'''

DUMP_ANCHOR = '    LOG(INFO) << "Reboot ending, jumping to kernel";\n'

patch('reboot_utils.cpp', [
    ('#include <unistd.h>\n', INCLUDES),
    ('\nbool IsRebootCapable() {', HELPER),
    (DUMP_ANCHOR, DUMP_ANCHOR + '    HinovaDumpKmsg(rebootTarget.c_str());\n'),
])

patch('reboot_utils.h', [
    ('void InstallRebootSignalHandlers();\n',
     'void InstallRebootSignalHandlers();\n'
     '// Hi Nova debug: stage marker / live kernel log in the reserved2 partition.\n'
     'void HinovaMark(int slot, const char* tag);\n'
     'void HinovaStartKmsgLogger();\n'),
])

patch('first_stage_init.cpp', [
    ('int FirstStageMain(int argc, char** argv) {\n',
     'int FirstStageMain(int argc, char** argv) {\n'
     '    HinovaMark(0, "first_stage_entry");\n'),
    ('    LOG(INFO) << "init first stage started!";\n',
     '    LOG(INFO) << "init first stage started!";\n'
     '    HinovaMark(1, "first_stage_logging");\n'
     '    HinovaStartKmsgLogger();\n'),
])

patch('selinux.cpp', [
    ('int SetupSelinux(char** argv) {\n',
     'int SetupSelinux(char** argv) {\n'
     '    HinovaMark(2, "selinux_setup_entry");\n'),
    ('    MountMissingSystemPartitions();\n',
     '    MountMissingSystemPartitions();\n'
     '    HinovaMark(5, "after_mount_missing");\n'),
    ('    ReadPolicy(&policy);\n',
     '    ReadPolicy(&policy);\n'
     '    HinovaMark(6, "policy_read");\n'),
    ('    set_selinuxmnt("/sys/fs/selinux");\n',
     '    set_selinuxmnt("/sys/fs/selinux");\n'
     '    HinovaMark(7, "before_load_policy");\n'),
    ('    SelinuxSetEnforcement();\n',
     '    HinovaMark(3, "selinux_policy_loaded");\n'
     '    SelinuxSetEnforcement();\n'),
])

patch('init.cpp', [
    ('int SecondStageMain(int argc, char** argv) {\n',
     'int SecondStageMain(int argc, char** argv) {\n'
     '    HinovaMark(4, "second_stage_entry");\n'),
])
