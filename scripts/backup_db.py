"""在服务运行中安全备份 SQLite 数据库（使用 SQLite 在线备份接口，不会读到写了一半的数据）。

  python3 scripts/backup_db.py                 # 备份到 data/backups/daolook-时间.db
  python3 scripts/backup_db.py --keep 14       # 只保留最近 14 份

建议用系统定时任务（如 macOS launchd 或 cron）每天执行一次，并把备份目录同步到另一台设备。
"""

import argparse, datetime, os, sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=os.environ.get("DAOLOOK_DB", str(ROOT / "data/daolook.db")))
    parser.add_argument("--dir", default=str(ROOT / "data/backups"))
    parser.add_argument("--keep", type=int, default=30)
    args = parser.parse_args()
    target_dir = Path(args.dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = target_dir / f"daolook-{stamp}.db"
    src = sqlite3.connect(args.db)
    dst = sqlite3.connect(target)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    os.chmod(target, 0o600)
    backups = sorted(target_dir.glob("daolook-*.db"))
    for old in backups[: max(0, len(backups) - args.keep)]:
        old.unlink()
    print(target)


if __name__ == "__main__":
    main()
