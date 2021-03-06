#!/usr/bin/env python3
import os
import hashlib
import sys
import subprocess
import math
from s3fs import S3FileSystem

from zfs_backup_lib import ZfsSyncedSnapshot, get_sync_state

# I use aws configure set default.s3.multipart_chunksize 256MB, default is 8MB
DEFAULT_MULTIPART_CHUNKSIZE = 256

if "ZFS_BACKUP_BUCKET" not in os.environ:
    raise Exception("Please export ZFS_BACKUP_BUCKET=bucketname before running this script")
if "ZFS_BACKUP_POOL" not in os.environ:
    raise Exception("Please export ZFS_BACKUP_POOL=pool before running this script")

WANTED_BUCKET = os.environ["ZFS_BACKUP_BUCKET"]
WANTED_POOL = os.environ["ZFS_BACKUP_POOL"]
s3fs = S3FileSystem()

def md5_checksum(entry: ZfsSyncedSnapshot, chunksize_in_mb=DEFAULT_MULTIPART_CHUNKSIZE, large_file=False):
    p = subprocess.Popen(
        f"sudo {entry.short_send_cmd()}", stdout=subprocess.PIPE, shell=True
    )
    m = hashlib.md5()
    md5s = []
    while p.poll() is None:
        if large_file:
            data = p.stdout.read(chunksize_in_mb * 1024 * 1024)
            md5s.append(hashlib.md5(data).digest())
        else:
            data = p.stdout.read(1024 * 1024)
            m.update(data)
    if p.returncode != 0:
        raise Exception(f"Failure for calculating md5sum {p.returncode}")
    if large_file:
        m = hashlib.md5(b"".join(md5s))
        return "{}-{}".format(m.hexdigest(), len(md5s))
    return m.hexdigest()


def calc_chunksize(filesize, etag):
    filesize_mb = float(filesize / 1024 / 1024)
    aws_chunks = float(etag.split("-")[-1])
    return max(math.ceil(filesize_mb / aws_chunks), DEFAULT_MULTIPART_CHUNKSIZE)


def perform_check():
    failures = 0
    all_states = {v.snapshot: v for v in get_sync_state(WANTED_POOL)}
    for s3_path in s3fs.glob(f"s3://{WANTED_BUCKET}/**"):
        fileinfo = s3fs.info(s3_path)
        if fileinfo["type"] == "directory":
            continue
        tags = s3fs.get_tags(s3_path)
        etag = fileinfo["ETag"][1:-1]  # strip quotes

        snapshot = ZfsSyncedSnapshot.reverse_s3_name(
            s3_path.replace(f"{WANTED_BUCKET}/", "")
        )
        if "zfsbackup_confirmed" in tags:
            print(f"{snapshot} - OK (S3 tag set)")
            continue
        if snapshot not in all_states:
            print(f"Can't check {snapshot}")
            break
        entry = all_states[snapshot]
        if "-" in etag:
            large = True
            chunksize = calc_chunksize(fileinfo["Size"], etag)
        else:
            large = False
            chunksize = None
        checksum = md5_checksum(entry, chunksize, large)
        if checksum == etag:
            print(f"{entry.snapshot} - OK (computed)")
            s3fs.put_tags(s3_path, {"zfsbackup_confirmed": "true"})
        else:
            perc_size = (entry.estimate_size() / fileinfo['Size']) * 100
            if perc_size > 0.95:
                print(f"{entry.snapshot} - WARN Checksum mismatch - but filesize within {perc_size} size estimate")
                print(f"      local:{checksum} aws:{etag} ")
            else:
                print(f"{entry.snapshot} - FAILURE local:{checksum} aws:{etag}")
                failures += 1
            #print(f"Local size:{entry.estimate_size()} size on aws:{fileinfo['Size']} - {perc_size}")
            
    if failures > 0:
        print("FAILURES DETECTED!")
        sys.exit(1)


perform_check()
