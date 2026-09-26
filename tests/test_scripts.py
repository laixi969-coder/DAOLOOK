import json, sqlite3, subprocess, sys, tempfile, time, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import calibrate_ranking as cal


class CalibrationTests(unittest.TestCase):
    def test_auc_and_compositions(self):
        self.assertEqual(cal.auc([0.9, 0.8, 0.1, 0.2], [1, 1, 0, 0]), 1.0)
        self.assertEqual(cal.auc([0.1, 0.9], [1, 0]), 0.0)
        self.assertIsNone(cal.auc([0.5, 0.5], [1, 1]))
        combos = list(cal.compositions(10, 6))
        self.assertEqual(len(combos), 3003)
        self.assertTrue(all(sum(c) == 10 and min(c) >= 0 for c in combos))

    def test_script_reports_suggested_weights(self):
        with tempfile.TemporaryDirectory() as d:
            rows = []
            for i in range(30):
                hit = i % 3 == 0
                likes = 9000 if hit else 300 + i
                rows.append(
                    {
                        "platform": "xhs",
                        "label": int(hit),
                        "group": "g",
                        "response": {
                            "data": {
                                "note_id": str(i),
                                "title": f"t{i}",
                                "time": int(time.time()) - 86400,
                                "interact_info": {"liked_count": likes},
                                "user": {"fans": "1万" if hit else "20万"},
                            }
                        },
                    }
                )
            samples = Path(d) / "s.jsonl"
            samples.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows))
            out = Path(d) / "r.json"
            subprocess.run(
                [sys.executable, str(ROOT / "scripts/calibrate_ranking.py"), str(samples), "--output", str(out)],
                check=True,
                capture_output=True,
                cwd=ROOT,
            )
            report = json.loads(out.read_text())
            self.assertEqual(report["samples"], 30)
            self.assertTrue(report["target_30_50_met"])
            self.assertEqual(report["per_component"]["efficiency"]["auc"], 1.0)
            self.assertAlmostEqual(sum(report["suggested_weights"].values()), 1.0)


class BackupTests(unittest.TestCase):
    def test_online_backup_and_rotation(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "live.db"
            with sqlite3.connect(db) as c:
                c.execute("CREATE TABLE t(x)")
                c.execute("INSERT INTO t VALUES (1)")
            for _ in range(3):
                subprocess.run(
                    [sys.executable, str(ROOT / "scripts/backup_db.py"), "--db", str(db), "--dir", str(Path(d) / "b"), "--keep", "2"],
                    check=True,
                    capture_output=True,
                )
                time.sleep(1.05)
            backups = sorted((Path(d) / "b").glob("daolook-*.db"))
            self.assertEqual(len(backups), 2)
            with sqlite3.connect(backups[-1]) as c:
                self.assertEqual(c.execute("SELECT x FROM t").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
