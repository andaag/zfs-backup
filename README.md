# zfs-backup

A simple app I made for myself to backup zfs snapshots to S3.

This is not designed as a generic tool, but rather something tiny for myself to do my backups. If it's useful for you, great. It's less than 200 lines of code, and most of the actual work is pushed to zfs/the aws s3 client.

## Why

I considered rsync.net for zfs backups, but I'm backing up fairly small amounts of data, so their minimum purchase of 1tb of data seemed excessive. Also this is backup of a backup server, so I do not need quick access to it.

In rsync.net price they usually compare with s3, which at the time of this writing is around 0.023$/gb. That's a fair comparison, however, I don't need quick access to my data, if I loose this backup server something has gone *very* wrong, and chances are I can wait 12h for my backup to restore. Therefor I'm able to use amazon deep glacier, the price for that is 0.00099$/gb. Aka a different scale.

## How

This runs backups of zfs -w, aka if your volume is encrypted (like mine is), that encryption is kept. For the same reason no extra compression is run.

- This will do a fullsnapshot of anything matching:

```python
# zfs_backup.lib.py:
full_backup = "yearly" in snapshot or "monthly" in snapshot

# confirm_consistency.py
DEFAULT_MULTIPART_CHUNKSIZE = X
```

- Otherwise incremental snapshots is done

## NB's

- This does intentionally not split files, this is needed in s3 uploads once a snapshot becomes larger than 5tb. Avoiding splitting means hash checking/consistency checking is easier.
- Ensure that you backup your encrypted key for this as well, and that it is backed up somewhere else. If you don't have that and your volume is encrypted this is worthless...
- The amazon etag algorithm is undocumented, but not complex. However it is subject to change... See md5_checksum in confirm_consistency.py. (Basically the etag is [md5sums in chunks]-[number of chunks])
- This does not push directly to glacier, it pushes to S3. In order to move from there to glacier you'll need a bucket lifecycle policy.

## Info on my setup

- I use sanoid to do the snapshots themselves.
- I use an encrypted+compressed volume.
- I use a isolated amazon account for this backup (even though it's encrypted..)
- I use a s3 policy to move the files to deep glacier after 3 days.
- I use healthchecks.io to confirm backups are running and working.
```sh
#!/bin/bash
export CHECK_URL="https://hc-ping.com/X"
export ZFS_BACKUP_BUCKET="bucket-name"
export ZFS_BACKUP_POOL="rpool"
export AWS_SECRET_ACCESS_KEY="X"
export AWS_ACCESS_KEY_ID="X"

cd /mnt/storagepool/backup/root/zfs-s3-backup/zfs-backup
url=$CHECK_URL
curl -fsS --retry 3 -X GET $url/start

. .venv/bin/activate
echo "* * * * Performing backup * * * *"
python zfs_backup.py &>backup.log
if [ $? -ne 0 ]; then
    url=$url/fail
    curl -fsS --retry 3 -X POST --data-raw "$(cat backup.log)" $url
    exit 1
fi

echo "* * * * Performing checksum confirmation * * * *"
python confirm_consistency.py &>>backup.log
if [ $? -ne 0 ]; then url=$url/fail; fi
curl -fsS --retry 3 -X POST --data-raw "$(cat backup.log)" $url
```
