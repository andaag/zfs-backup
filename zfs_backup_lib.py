from dataclasses import dataclass
import subprocess
from datetime import datetime
from typing import List

@dataclass
class ZfsSyncedSnapshot:
    snapshot: str
    parent: "ZfsSyncedSnapshot"

    def incremental_sync(self):
        return self.parent is not None

    def estimate_size(self):
        cmd = self.send_cmd(dryrun=True)
        return int(
            subprocess.check_output(cmd, shell=True)
            .decode("utf-8")
            .strip()
            .split("\t")[-1]
        )

    def send_cmd(self, dryrun=False):
        if dryrun:
            dryrun = "n"
        else:
            dryrun = ""
        if self.incremental_sync():
            return f"zfs send -{dryrun}vPw -i {self.parent.snapshot} {self.snapshot}"
        else:
            return f"zfs send -{dryrun}vPw {self.snapshot}"

    def short_send_cmd(self):
        if self.incremental_sync():
            return f"zfs send -w -i {self.parent.snapshot} {self.snapshot}"
        else:
            return f"zfs send -w {self.snapshot}"

    def get_creation_time(self):
        return datetime.fromtimestamp(int((subprocess.check_output(f"zfs get creation -Hpr {self.snapshot}", shell=True)
            .decode("utf-8")
            .strip()).split("\t")[2]))
        

    def get_s3_name(self):
        return self.snapshot.replace("@", "_AT_").replace(":", "_CN_")

    @staticmethod
    def reverse_s3_name(s3_name):
        return s3_name.replace("_AT_", "@").replace("_CN_", ":")


def get_sync_state(pool) -> List[ZfsSyncedSnapshot]:
    db = []
    for row in (
        subprocess.check_output("zfs list -t snapshot -H", shell=True)
        .decode("utf-8")
        .split("\n")
    ):
        if row == "" or not row.startswith(pool + "/"):
            continue
        row = row.split("\t")
        snapshot = row[0]
        parent = None
        if "monthly" in snapshot or "daily" in snapshot:
            full_backup = "monthly" in snapshot
            if "hourly" in snapshot:
                continue
            if not full_backup:
                parent = db[-1]
            entry = ZfsSyncedSnapshot(snapshot, parent)
            db.append(entry)
        else:
            if "autozsys" not in snapshot and "_hourly" not in snapshot:
                print("Skipping snapshot {} - unknown naming.".format(snapshot))
    return db


def human_readable_size(size, decimal_places=3):
    for unit in ["B", "KiB", "MiB", "GiB", "TiB"]:
        if size < 1024.0:
            break
        size /= 1024.0
    return f"{size:.{decimal_places}f}{unit}"
