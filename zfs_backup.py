import os
import subprocess
import sys
from s3fs import S3FileSystem
from zfs_backup_lib import get_sync_state, human_readable_size

if "ZFS_BACKUP_BUCKET" not in os.environ:
    raise Exception("Please export ZFS_BACKUP_BUCKET=bucketname before running this script")
if "ZFS_BACKUP_POOL" not in os.environ:
    raise Exception("Please export ZFS_BACKUP_POOL=pool before running this script")

WANTED_BUCKET = os.environ["ZFS_BACKUP_BUCKET"]
WANTED_POOL = os.environ["ZFS_BACKUP_POOL"]
BACKUP_MAXDAYS = int(os.environ["BACKUP_MAXDAYS"]) if "BACKUP_MAXDAYS" in os.environ else 60

s3fs = S3FileSystem()
existing_backups = [v.replace(f"{WANTED_BUCKET}/", "") for v in s3fs.glob(f"s3://{WANTED_BUCKET}/**")]

for entry in get_sync_state(WANTED_POOL, BACKUP_MAXDAYS):
    target_name = entry.get_s3_name()
    if target_name in existing_backups:
        s3_size = s3fs.size(f"{WANTED_BUCKET}/{target_name}")
        print(f"{entry.snapshot} - In sync")
        continue
    backup_cmd = entry.short_send_cmd()
    incremental = entry.incremental_sync()
    print(f"backing up {entry.snapshot} {human_readable_size(entry.estimate_size())} (incremental : {incremental})")
    cmd = f"sudo {backup_cmd} | aws s3 cp --expected-size {entry.estimate_size()} - s3://{WANTED_BUCKET}/{target_name}"
    try:
        subprocess.run(
            cmd, shell=True, check=True, capture_output=True
        )
    except subprocess.CalledProcessError as process_error:
        print(process_error)
        print(process_error.stdout.decode())
        print(process_error.stderr.decode())
        sys.exit(1)
