"""《DAOLOOK 创作方法论与使用手册》：再来一批不重复方向+切角、演示模式不调模型也不读 Skill、导出 Skill 版本。"""

import json, unittest
from unittest.mock import patch

from server import adapters, jobs
from tests import test_original as base

D = base.D


class PreviousPairTests(unittest.TestCase):
    def outputs(self, batch=1):
        return adapters.demo_outputs("xhs", "冷萃挂耳", batch)

    def test_repeat_of_previous_direction_and_angle_rejected(self):
        outputs = self.outputs()
        previous = [{"direction": outputs[0]["direction"], "angle": outputs[0]["angle"] + " "}]
        with self.assertRaisesRegex(ValueError, "已生成稿件"):
            adapters.validate_creation({"outputs": outputs}, "xhs", previous)
        # 同切角换了方向不算重复
        other = [d for d in adapters.DIRECTIONS["xhs"] if d != outputs[0]["direction"]][0]
        adapters.validate_creation(
            {"outputs": outputs}, "xhs", [{"direction": other, "angle": outputs[0]["angle"]}]
        )

    def test_demo_next_batch_uses_new_angles(self):
        first = self.outputs(1)
        adapters.validate_creation({"outputs": self.outputs(2)}, "xhs", first)

    def test_live_validator_receives_previous(self):
        seen = {}

        def fake(prompt, schema, version, kind, validator):
            seen["validator"] = validator
            return {"outputs": self.outputs()}, "m"

        previous = [{"direction": "测评", "angle": "标准对比"}]
        with patch.object(adapters, "model_json", side_effect=fake):
            adapters.create(
                {"platform": "xhs", "title": "t", "demo": False}, [], "", "p", 2, previous=previous
            )
        with self.assertRaisesRegex(ValueError, "已生成稿件"):
            seen["validator"]({"outputs": self.outputs()})


class HandbookFlowTests(base.OriginalTests):
    def analyze(self):
        status, r = self.post(
            "/api/analyze", {"entry": "single", "text": "https://www.xiaohongshu.com/explore/example"}
        )
        self.assertEqual(status, 202)
        task = self.run_task(r)[0]
        self.assertEqual(task["state"], "SUCCEEDED", task)
        return json.loads(task["result"])["source_ids"][0]

    def test_demo_mode_never_calls_model_for_real_reference(self):
        sid = self.analyze()
        with D.db() as c:
            row = c.execute("SELECT data FROM source_contents WHERE id=?", (sid,)).fetchone()
            data = json.loads(row["data"])
            data["demo"] = False  # 真实服务模式下拆解的参考
            c.execute("UPDATE source_contents SET data=? WHERE id=?", (json.dumps(data), sid))
        with patch.object(adapters, "model_json", side_effect=AssertionError("演示模式调用了模型")):
            status, r = self.post("/api/create", {"source_id": sid})
            self.assertEqual(status, 202)
            task = self.run_task(r)[0]
        self.assertEqual(task["state"], "SUCCEEDED", task)
        self.assertEqual(task["model"], "demo")

    def test_demo_mode_does_not_need_published_skill(self):
        with D.db() as c:
            c.execute("UPDATE skill_versions SET status='Archived'")
        sid = self.analyze()
        status, r = self.post("/api/create", {"source_id": sid})
        self.assertEqual(self.run_task(r)[0]["state"], "SUCCEEDED")

    def test_create_again_reuses_selection_appends_and_exports_skill_version(self):
        aid = self.asset()
        sid = self.analyze()
        status, r = self.post(
            "/api/create", {"source_id": sid, "assets": [aid], "requirements": "面向上班族"}
        )
        self.assertEqual(self.run_task(r)[0]["state"], "SUCCEEDED")
        status, r2 = self.post("/api/create", {"source_id": sid, "again": True})
        self.assertEqual(status, 202, r2)
        with D.db() as c:
            payload = json.loads(
                c.execute("SELECT payload FROM tasks WHERE id=?", (r2["task_ids"][0],)).fetchone()[0]
            )
        self.assertEqual(payload["assets"], [aid])
        self.assertEqual(payload["requirements"], "面向上班族")
        self.assertEqual(self.run_task(r2)[0]["state"], "SUCCEEDED")
        outs = [c["data"] for c in self.ws()["creations"] if c["source_id"] == sid]
        self.assertEqual(len(outs), 16)
        pairs = [(o["direction"], o["angle"]) for o in outs]
        self.assertEqual(len(set(pairs)), 16)
        status, csv = self.c.req(f"/api/export?project_id={self.p}", raw=True)
        self.assertIn("xhs_creation v", csv.decode())


# 继承而来的自主创作用例已在 test_original 中运行，这里不重复。
for name in [n for n in dir(base.OriginalTests) if n.startswith("test_")]:
    setattr(HandbookFlowTests, name, None)


if __name__ == "__main__":
    unittest.main()
