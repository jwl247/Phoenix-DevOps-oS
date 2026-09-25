#!/usr/bin/env python3
"""
helix_fuse.py -- HelixFS as a real mounted filesystem (FUSE), integration path A
from helix_complete_stack.py.

Mounts a passthrough view of a backing directory. Every read goes through
Helix's tiered cache at the block level, not the file level: files are cut
into fixed 128 KiB blocks, and each block moves through the tiers on its own.
  L1 hot (RAM) -> L2 warm (RAM) -> L3 compressed (RAM) -> L5 disk pages (e.g. an SSD)
Helix never needs to know what a file "is": a block is bytes plus an access
history. That follows the original quadralingual intent (Helix interprets data
on her own terms, at block/stream granularity; see the
project_helix_quadralingual_true_intent memory).

Writes are write-through: bytes land on the backing store before write()
returns, and the affected cached blocks are dropped, so nothing is ever only in
Helix. Killing this process loses cache, never data.

Linux only. Requires fusepy (Debian: python3-fusepy, module name `fusepy`).

Usage:
  python3 helix_fuse.py <backing_dir> <mountpoint> [--pages DIR]
                        [--l1-mb N] [--l2-mb N] [--l3-mb N] [--stats FILE]
Unmount with: fusermount3 -u <mountpoint>   (or fusermount -u)
"""

import argparse
import errno
import json
import os
import sys
import threading
import time

try:
    from fusepy import FUSE, FuseOSError, Operations
except ImportError:  # upstream pip package installs as `fuse`
    from fuse import FUSE, FuseOSError, Operations

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helix_complete_stack import HelixCache  # noqa: E402

BLOCK = 128 * 1024  # matches FUSE's default max read size


class HelixPassthrough(Operations):
    def __init__(self, backing: str, cache: HelixCache, stats_path: str = None):
        self.root = os.path.realpath(backing)
        self.stats_path = stats_path
        self.cache = cache
        self.lock = threading.RLock()
        self.io = {'reads': 0, 'read_bytes': 0, 'backing_reads': 0,
                   'backing_read_bytes': 0, 'writes': 0, 'write_bytes': 0,
                   'invalidated_blocks': 0}

    # --- helpers -------------------------------------------------------
    def _full(self, path: str) -> str:
        full = os.path.realpath(os.path.join(self.root, path.lstrip('/')))
        if full != self.root and not full.startswith(self.root + os.sep):
            raise FuseOSError(errno.EACCES)  # never escape the backing tree
        return full

    @staticmethod
    def _key(path: str, blockno: int) -> str:
        return f"{path}#{blockno}"

    def _invalidate(self, path: str, start: int = 0, end: int = None):
        """Drop cached blocks of `path` overlapping [start, end). end=None -> to EOF."""
        with self.lock:
            prefix = f"{path}#"
            first = start // BLOCK
            last = None if end is None else (max(end - 1, start)) // BLOCK
            for tier in (self.cache.l1_cache, self.cache.l2_cache, self.cache.l3_cache):
                for k in [k for k in tier if k.startswith(prefix)]:
                    n = int(k[len(prefix):])
                    if n >= first and (last is None or n <= last):
                        self.cache.drop(k)
                        self.io['invalidated_blocks'] += 1
            for k in [k for k in list(self.cache._disk_index) if k.startswith(prefix)]:
                n = int(k[len(prefix):])
                if n >= first and (last is None or n <= last):
                    self.cache.drop(k)
                    self.io['invalidated_blocks'] += 1

    def init(self, path):
        # Runs after FUSE has daemonized, so the thread survives the fork.
        if self.stats_path:
            threading.Thread(target=_stats_writer, args=(self, self.stats_path, 5.0),
                             daemon=True).start()

    # --- metadata --------------------------------------------------------
    def access(self, path, mode):
        if not os.access(self._full(path), mode):
            raise FuseOSError(errno.EACCES)

    def getattr(self, path, fh=None):
        st = os.lstat(self._full(path))
        return {k: getattr(st, k) for k in (
            'st_atime', 'st_ctime', 'st_gid', 'st_mode', 'st_mtime',
            'st_nlink', 'st_size', 'st_uid', 'st_blocks')}

    def readdir(self, path, fh):
        return ['.', '..'] + os.listdir(self._full(path))

    def readlink(self, path):
        return os.readlink(self._full(path))

    def statfs(self, path):
        sv = os.statvfs(self._full(path))
        return {k: getattr(sv, k) for k in (
            'f_bavail', 'f_bfree', 'f_blocks', 'f_bsize', 'f_favail',
            'f_ffree', 'f_files', 'f_flag', 'f_frsize', 'f_namemax')}

    def chmod(self, path, mode):
        return os.chmod(self._full(path), mode)

    def chown(self, path, uid, gid):
        return os.chown(self._full(path), uid, gid)

    def utimens(self, path, times=None):
        return os.utime(self._full(path), times)

    def mkdir(self, path, mode):
        return os.mkdir(self._full(path), mode)

    def rmdir(self, path):
        return os.rmdir(self._full(path))

    def unlink(self, path):
        self._invalidate(path)
        return os.unlink(self._full(path))

    def rename(self, old, new):
        self._invalidate(old)
        self._invalidate(new)
        return os.rename(self._full(old), self._full(new))

    def symlink(self, name, target):
        return os.symlink(target, self._full(name))

    def link(self, target, name):
        return os.link(self._full(name), self._full(target))

    # --- file I/O --------------------------------------------------------
    def open(self, path, flags):
        return os.open(self._full(path), flags)

    def create(self, path, mode, fi=None):
        self._invalidate(path)
        return os.open(self._full(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)

    def read(self, path, size, offset, fh):
        out = bytearray()
        pos = offset
        end = offset + size
        while pos < end:
            bno = pos // BLOCK
            key = self._key(path, bno)
            block = self.cache.get(key)
            if block is None:
                block = os.pread(fh, BLOCK, bno * BLOCK)
                with self.lock:
                    self.io['backing_reads'] += 1
                    self.io['backing_read_bytes'] += len(block)
                if block:
                    self.cache.put(key, block, len(block))
            if not block:
                break
            lo = pos - bno * BLOCK
            if lo >= len(block):
                break  # EOF inside this block
            chunk = block[lo: min(len(block), lo + (end - pos))]
            out += chunk
            pos += len(chunk)
            if len(block) < BLOCK:
                break  # short block == EOF
        with self.lock:
            self.io['reads'] += 1
            self.io['read_bytes'] += len(out)
        return bytes(out)

    def write(self, path, data, offset, fh):
        n = os.pwrite(fh, data, offset)  # write-through: backing first
        self._invalidate(path, offset, offset + n)
        with self.lock:
            self.io['writes'] += 1
            self.io['write_bytes'] += n
        return n

    def truncate(self, path, length, fh=None):
        with open(self._full(path), 'r+b') as f:
            f.truncate(length)
        self._invalidate(path, (length // BLOCK) * BLOCK)

    def flush(self, path, fh):
        return 0

    def release(self, path, fh):
        return os.close(fh)

    def fsync(self, path, fdatasync, fh):
        return os.fsync(fh)


def _stats_writer(fs: HelixPassthrough, path: str, every: float):
    while True:
        time.sleep(every)
        try:
            snap = {'ts': time.time(), 'io': dict(fs.io), 'cache': dict(fs.cache.stats),
                    'tier_bytes': {
                        'l1': fs.cache._get_tier_size(fs.cache.l1_cache),
                        'l2': fs.cache._get_tier_size(fs.cache.l2_cache),
                        'l3': fs.cache._get_tier_size(fs.cache.l3_cache),
                        'disk_pages': fs.cache.disk_pages_count()}}
            tmp = path + '.tmp'
            with open(tmp, 'w') as f:
                json.dump(snap, f, indent=1)
            os.replace(tmp, path)
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('backing')
    ap.add_argument('mountpoint')
    ap.add_argument('--pages', help='L5 page directory (put this on the fastest disk)')
    ap.add_argument('--l1-mb', type=int, default=256)
    ap.add_argument('--l2-mb', type=int, default=512)
    ap.add_argument('--l3-mb', type=int, default=1024)
    ap.add_argument('--stats', help='write a JSON stats snapshot here every 5s')
    ap.add_argument('--foreground', action='store_true')
    a = ap.parse_args()

    cache = HelixCache(a.l1_mb, a.l2_mb, a.l3_mb, page_dir=a.pages)
    fs = HelixPassthrough(a.backing, cache, stats_path=a.stats)
    FUSE(fs, a.mountpoint, foreground=a.foreground, nothreads=False)


if __name__ == '__main__':
    main()
