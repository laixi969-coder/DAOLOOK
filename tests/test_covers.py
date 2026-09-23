import base64
import unittest
import xml.etree.ElementTree as ET
from server import covers


class CoverTests(unittest.TestCase):
    def test_content_recommendation_without_invented_numbers(self):
        p = covers.plan({"title": "收纳方法清单"})
        self.assertEqual(p["recommended"], "method")
        self.assertEqual(p["brief"]["title"], "收纳方法清单")
        self.assertEqual(p["brief"]["points"], [])

    def test_all_layouts_escape_and_preserve_text(self):
        title = "<测试>&中文标题"
        for style in ("brand", "method", "portrait"):
            p = covers.prepare({"title": title}, {"style": style}, [])
            result = covers.render(p)
            svg = base64.b64decode(result["url"].split(",")[1])
            root = ET.fromstring(svg)
            text = "".join(root.itertext())
            self.assertIn(title, text)
            self.assertEqual(root.attrib["width"], "1080")
            self.assertEqual(root.attrib["height"], "1440")

    def test_portrait_requires_real_asset_before_save(self):
        p = covers.prepare({"title": "真实体验"}, {"style": "portrait"}, [])
        self.assertFalse(covers.render(p)["validation"]["ready"])
        with self.assertRaises(ValueError):
            covers.render(p, final=True)

    def test_reject_overflow_and_unowned_or_unsafe_assets(self):
        for brief in (
            {"title": "字" * 37},
            {"subtitle": "\n".join(["一"] * 8)},
            {"points": ["一"] * 4},
            {"asset_id": "someone-elses"},
            {"style": "unknown"},
        ):
            with self.assertRaises(ValueError):
                covers.prepare({"title": "标题"}, brief, [])
        with self.assertRaises(ValueError):
            covers.prepare(
                {"title": "标题"},
                {"asset_id": "x"},
                [
                    {
                        "id": "x",
                        "name": "x",
                        "kind": "图片",
                        "content": "https://example.com/image.png",
                    }
                ],
            )

    def test_real_photo_embedded_and_crop_retained(self):
        photo = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a2uoAAAAASUVORK5CYII="
        p = covers.prepare(
            {"title": "我的真实照片"},
            {"style": "portrait", "asset_id": "a", "crop": "top"},
            [{"id": "a", "name": "本人照片", "kind": "图片", "content": photo}],
        )
        result = covers.render(p, final=True)
        svg = base64.b64decode(result["url"].split(",")[1]).decode()
        self.assertIn(photo, svg)
        self.assertIn("xMidYMin slice", svg)
        self.assertTrue(result["validation"]["ready"])
        self.assertFalse(result["demo"])
