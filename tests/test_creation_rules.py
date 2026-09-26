"""PRD 9.1–9.3：内容方向、评论布局、单方向兜底与导出列。"""

import copy, csv, io, os, sqlite3, tempfile, unittest
from server import adapters


def batch(p):
    content = adapters.demo_content(0, p)
    outputs, _ = adapters.create(content, [], "测试主题", "", 1)
    return outputs


class CreationRuleTests(unittest.TestCase):
    def test_demo_batches_use_platform_directions(self):
        for p in ("xhs", "douyin"):
            outputs = batch(p)
            adapters.validate_creation({"outputs": outputs}, p)
            self.assertEqual(
                {o["direction"] for o in outputs}, set(adapters.DIRECTIONS[p])
            )
            self.assertTrue(all(o["role"] and o["angle"] for o in outputs))
        self.assertTrue(all("comment_layout" in o for o in batch("xhs")))

    def test_direction_must_be_one_of_the_two(self):
        outputs = batch("xhs")
        outputs[0]["direction"] = "种草"
        with self.assertRaisesRegex(ValueError, "内容方向"):
            adapters.validate_creation({"outputs": outputs}, "xhs")
        outputs = batch("douyin")
        outputs[0]["direction"] = "测评"
        with self.assertRaisesRegex(ValueError, "内容方向"):
            adapters.validate_creation({"outputs": outputs}, "douyin")

    def test_role_and_angle_required(self):
        for key in ("role", "angle"):
            outputs = batch("xhs")
            outputs[1][key] = " "
            with self.assertRaises(ValueError):
                adapters.validate_creation({"outputs": outputs}, "xhs")

    def test_same_direction_same_angle_rejected(self):
        outputs = batch("xhs")
        same = [o for o in outputs if o["direction"] == "测评"]
        same[1]["angle"] = same[0]["angle"]
        with self.assertRaisesRegex(ValueError, "切角"):
            adapters.validate_creation({"outputs": outputs}, "xhs")

    def test_single_direction_needs_missing_explanation(self):
        outputs = batch("xhs")
        for n, o in enumerate(outputs):
            o["direction"] = "测评"
            o["angle"] = f"切角{n}"
            o["missing"] = ["缺少价格"]
        with self.assertRaisesRegex(ValueError, "钓鱼帖"):
            adapters.validate_creation({"outputs": outputs}, "xhs")
        outputs[0]["missing"].append("钓鱼帖缺少用户常问的真实问题")
        adapters.validate_creation({"outputs": outputs}, "xhs")

    def test_xhs_comment_layout_required_and_complete(self):
        cases = [
            lambda l: None,
            lambda l: {**l, "atmosphere": []},
            lambda l: {**l, "knowledge": [""]},
            lambda l: {**l, "pinned": {**l["pinned"], "text": ""}},
            lambda l: {**l, "pinned": {**l["pinned"], "keep_on_top": ""}},
            lambda l: {**l, "first_hour": ""},
        ]
        for n, change in enumerate(cases):
            with self.subTest(n=n):
                outputs = batch("xhs")
                outputs[0]["comment_layout"] = change(
                    copy.deepcopy(outputs[0]["comment_layout"])
                )
                with self.assertRaisesRegex(ValueError, "评论布局"):
                    adapters.validate_creation({"outputs": outputs}, "xhs")
        # 抖音不要求评论布局
        outputs = batch("douyin")
        self.assertNotIn("comment_layout", outputs[0])
        adapters.validate_creation({"outputs": outputs}, "douyin")

    def test_instruction_and_schema_carry_new_rules(self):
        xhs = adapters.creation_instruction("xhs")
        for text in ("测评", "钓鱼帖", "missing", "comment_layout", "好生产、好复制"):
            self.assertIn(text, xhs)
        self.assertNotIn("comment_layout", adapters.creation_instruction("douyin"))
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent / "schemas"
        s = json.loads((root / "xhs-creation.schema.json").read_text())
        item = s["properties"]["outputs"]["items"]
        self.assertIn("comment_layout", item["required"])
        self.assertEqual(item["properties"]["direction"]["enum"], ["测评", "钓鱼帖"])
        d = json.loads((root / "douyin-creation.schema.json").read_text())
        self.assertEqual(
            d["properties"]["outputs"]["items"]["properties"]["direction"]["enum"],
            ["建立信任", "截流"],
        )


class ModelInputTests(unittest.TestCase):
    def test_create_sends_analysis_and_previous_without_raw_evidence(self):
        from unittest.mock import patch

        content = {
            "platform": "xhs",
            "title": "t",
            "body": "b",
            "demo": False,
            "evidence": {"huge": "raw"},
            "media_url": "https://v/x.mp4",
        }
        seen = {}

        def fake(prompt, schema, version, kind, validator):
            seen.update(prompt)
            return {"outputs": batch("xhs")}, "m"

        with patch.object(adapters, "model_json", side_effect=fake):
            adapters.create(
                content,
                [],
                "",
                "prompt",
                2,
                analysis=[{"name": "爆点判断", "text": "x"}],
                previous=[{"direction": "测评", "angle": "A", "title": "T"}],
            )
        self.assertNotIn("evidence", seen["reference"])
        self.assertNotIn("media_url", seen["reference"])
        self.assertEqual(seen["analysis"][0]["name"], "爆点判断")
        self.assertEqual(seen["previous_outputs"][0]["angle"], "A")
        self.assertIn("previous_outputs", seen["instruction"])


class SkillSeedTests(unittest.TestCase):
    def test_release_publishes_once_and_archives_previous(self):
        from server import db, skills

        path = tempfile.mktemp(suffix=".db")
        old = db.DB_PATH
        db.DB_PATH = path
        try:
            db.init()
            with sqlite3.connect(path) as c:
                # 模拟管理员之后发布了自己的版本：再次启动不应被覆盖。
                c.execute(
                    "UPDATE skill_versions SET status='Archived' WHERE name='xhs_creation' AND status='Published'"
                )
                c.execute(
                    "INSERT INTO skill_versions VALUES ('mine','xhs_creation',9,'我的版本','Published','x')"
                )
            db.init()
            with sqlite3.connect(path) as c:
                for name, prompt in skills.RELEASE.items():
                    rows = c.execute(
                        "SELECT version,status,prompt FROM skill_versions WHERE name=? ORDER BY version",
                        (name,),
                    ).fetchall()
                    self.assertEqual(rows[0][1], "Archived")
                    self.assertEqual(rows[1][2], prompt)
                    live = [r for r in rows if r[1] == "Published"]
                    self.assertEqual(len(live), 1)
                self.assertEqual(
                    c.execute(
                        "SELECT prompt FROM skill_versions WHERE name='xhs_creation' AND status='Published'"
                    ).fetchone()[0],
                    "我的版本",
                )
        finally:
            db.DB_PATH = old
            if os.path.exists(path):
                os.remove(path)

    def test_analysis_prompts_use_transcript_and_directions(self):
        from server import skills

        for text in ("transcript", "account_median", "测评", "钓鱼帖", "气氛"):
            self.assertIn(text, skills.XHS_ANALYSIS_V4)
        for text in ("transcript", "建立信任", "截流"):
            self.assertIn(text, skills.DOUYIN_ANALYSIS_V4)
        for prompt in (skills.XHS_CREATION_V5, skills.DOUYIN_CREATION_V5):
            self.assertIn("previous_outputs", prompt)
            self.assertIn("analysis", prompt)

    def test_v5_prompt_drops_fixed_persona_and_invented_experience(self):
        from server import skills

        xhs = skills.XHS_CREATION_V5
        self.assertNotIn("闺蜜", xhs)
        self.assertIn("语气服从资料", xhs)
        for text in ("评论布局", "atmosphere", "pinned", "first_hour", "20%"):
            self.assertIn(text, xhs)


class ExportTests(unittest.TestCase):
    def test_comment_layout_text(self):
        from server.app import comment_layout_text

        layout = batch("xhs")[0]["comment_layout"]
        text = comment_layout_text(layout)
        for label in ("【气氛】", "【知识】", "【置顶】", "发布后一小时"):
            self.assertIn(label, text)
        self.assertEqual(comment_layout_text(None), "")


if __name__ == "__main__":
    unittest.main()
