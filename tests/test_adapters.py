import unittest, json
from unittest.mock import patch
from server import adapters


class AdapterTests(unittest.TestCase):
    def test_platform_spoofing_is_rejected(self):
        for text in [
            "https://xiaohongshu.com.evil.com/x",
            "https://evil.com/?site=douyin.com",
            "file:///etc/passwd",
            "not a url",
        ]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                adapters.platform(text)
        self.assertEqual(
            adapters.platform("看看这个 https://v.douyin.com/abc 分享内容"), "douyin"
        )

    def test_real_metrics_are_not_generated_by_a_model(self):
        raw = {
            "data": {
                "aweme_detail": {
                    "aweme_id": "123",
                    "desc": "真实的原文",
                    "author": {"nickname": "作者"},
                    "statistics": {"digg_count": 123, "comment_count": 5},
                }
            }
        }
        d = adapters.normalize(raw, "douyin", "https://www.douyin.com/video/123")
        self.assertEqual(d["title"], "真实的原文")
        self.assertEqual(d["likes"], 123)
        self.assertIsNone(d["saves"])
        self.assertIsNone(d["followers"])
        self.assertFalse(d["demo"])

    def test_search_extracts_only_actual_ids(self):
        raw = {
            "data": [
                {"aweme_info": {"aweme_id": "123"}},
                {"aweme_info": {"aweme_id": "123"}},
                {"aweme_info": {"aweme_id": "456"}},
            ]
        }
        self.assertEqual(
            adapters.content_links(raw, "douyin"),
            ["https://www.douyin.com/video/123", "https://www.douyin.com/video/456"],
        )
        with self.assertRaises(ValueError):
            adapters.content_links({"error": "empty"}, "xhs")

    def test_douyin_search_uses_post_and_mapped_body(self):
        config = {
            "api_key": "test-key",
            "base_url": "https://example.com",
            "endpoints": {
                "douyin_search": {
                    "path": "/search",
                    "method": "POST",
                    "params": {"keyword": "{text}", "cursor": 0},
                }
            },
        }
        with (
            patch.object(
                adapters,
                "setting",
                side_effect=lambda key: config if key == "tikhub" else {"timeout": 10},
            ),
            patch.object(
                adapters, "request_json", return_value={"code": 200, "data": []}
            ) as req,
        ):
            adapters.TikHubAdapter().searchContents("咖啡", "douyin")
            self.assertEqual(
                req.call_args.args,
                (
                    "https://example.com/search",
                    "test-key",
                    {"keyword": "咖啡", "cursor": 0},
                    10,
                ),
            )

    def test_invalid_primary_output_falls_back(self):
        options = [
            ("one", {"base_url": "https://one.example", "api_key": "a"}, "primary"),
            ("two", {"base_url": "https://two.example", "api_key": "b"}, "backup"),
        ]
        bad = {"choices": [{"message": {"content": '{"sections":[]}'}}]}
        good = {
            "sections": [
                {"name": name, "text": "依据原文的分析"} for name in adapters.XHS_FIELDS
            ]
        }
        with (
            patch.object(adapters, "candidates", return_value=options),
            patch.object(
                adapters, "setting", return_value={"retries": 0, "timeout": 10}
            ),
            patch.object(
                adapters,
                "request_json",
                side_effect=[
                    bad,
                    {"choices": [{"message": {"content": json.dumps(good)}}]},
                ],
            ),
        ):
            result, model = adapters.model_json(
                {},
                {},
                "rules",
                validator=lambda r: adapters.validate_analysis(r, adapters.XHS_FIELDS),
            )
            self.assertEqual(model, "two/backup")
            self.assertEqual(result, good)

    def test_40_synthetic_platform_contract_fixtures(self):
        # These are synthetic contract tests, not the 30–50 real samples required for calibration.
        for n in range(40):
            p = "xhs" if n % 2 == 0 else "douyin"
            content = adapters.demo_content(n, p)
            with self.subTest(n=n, platform=p):
                result, _ = adapters.analyze(content, "")
                adapters.validate_analysis(
                    result, adapters.XHS_FIELDS if p == "xhs" else adapters.DY_FIELDS
                )
                outputs, _ = adapters.create(content, [], "测试主题", "", n)
                adapters.validate_creation({"outputs": outputs}, p)
                outputs[2]["body"] = outputs[0]["body"]
                with self.assertRaises(ValueError):
                    adapters.validate_creation({"outputs": outputs}, p)

    def test_multimodal_assets_are_not_embedded_in_text(self):
        with (
            patch.object(
                adapters,
                "candidates",
                return_value=[
                    (
                        "one",
                        {"base_url": "https://one.example", "api_key": "a"},
                        "vision",
                    )
                ],
            ),
            patch.object(
                adapters, "setting", return_value={"retries": 0, "timeout": 10}
            ),
            patch.object(
                adapters,
                "request_json",
                return_value={"choices": [{"message": {"content": "{}"}}]},
            ) as req,
        ):
            adapters.model_json(
                {
                    "assets": [
                        {
                            "name": "图",
                            "kind": "图片",
                            "content": "data:image/png;base64,AAAA",
                        }
                    ]
                },
                {},
                "rules",
            )
            content = req.call_args.args[2]["messages"][1]["content"]
            self.assertEqual(content[1]["type"], "image_url")
            self.assertNotIn("AAAA", content[0]["text"])


if __name__ == "__main__":
    unittest.main()
