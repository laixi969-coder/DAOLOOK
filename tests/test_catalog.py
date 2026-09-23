import unittest
from unittest.mock import patch
from server.catalog import classify, evidence
from server.ranking import score


class CatalogTests(unittest.TestCase):
    def test_separate_industry_and_format(self):
        c = classify({"title": "咖啡器具测评", "body": ""})
        self.assertEqual(c["industry"], "美食饮品")
        self.assertEqual(c["format"], "测评对比")
        self.assertIn("咖啡", c["basis"])
        self.assertTrue(c["provisional"])

    def test_missing_and_ambiguous_not_forced(self):
        self.assertEqual(classify({"title": "无法识别主题"})["industry"], "待分类")
        self.assertEqual(classify({"title": "咖啡与手机"})["industry"], "待分类")
        self.assertEqual(classify({"title": "手机评测"})["industry"], "数码科技")

    def test_seed_industry_preserved_but_not_old_mixed_tag(self):
        c = classify(
            {
                "demo": True,
                "category": "美食饮品",
                "tag": "干货教程",
                "title": "咖啡使用教程",
            }
        )
        self.assertEqual(c["industry"], "美食饮品")
        self.assertEqual(c["format"], "教程方法")
        self.assertIn("预设", c["basis"])

    def test_evidence_never_calls_samples_real(self):
        lines = evidence({"demo": True}, {"components": {"engagement": 1}})
        self.assertIn("预置示例", "".join(lines))
        lines = evidence(
            {"origin": {"entry": "keyword", "query": "咖啡"}}, {"components": {}}
        )
        self.assertIn("咖啡", "".join(lines))
        self.assertIn("缺少", "".join(lines))
        self.assertIn("未按爆款筛选", "".join(lines))

    @patch(
        "server.ranking.setting", return_value={"engagement": 0.3, "efficiency": 0.25}
    )
    def test_nonfinite_and_negative_metrics_ignored(self, _):
        for value in (float("inf"), float("nan"), -10, True):
            self.assertIsNone(score({"likes": value})["score"])

    @patch(
        "server.ranking.setting", return_value={"engagement": 0.3, "efficiency": 0.25}
    )
    def test_missing_data_no_score(self, _):
        self.assertIsNone(score({})["score"])
        self.assertNotIn(
            "efficiency", score({"likes": 50, "followers": None})["components"]
        )
