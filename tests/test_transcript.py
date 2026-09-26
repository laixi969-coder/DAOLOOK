import importlib, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from server import adapters

D = importlib.import_module("server.db")


class TranscriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = D.DB_PATH
        D.DB_PATH = str(Path(self.temp.name) / "db.sqlite")
        D.init()

    def tearDown(self):
        D.DB_PATH = self.original
        self.temp.cleanup()

    def test_user_text_wins(self):
        c = adapters.attach_transcript({"media_url": "https://v.example/a.mp4"}, " 口播原文 ")
        self.assertEqual((c["transcript"], c["transcript_source"]), ("口播原文", "用户提供"))

    def test_no_media_or_model_is_labelled(self):
        c = adapters.attach_transcript({"platform": "douyin"})
        self.assertIn("未提供视频地址", c["transcript_note"])
        c = adapters.attach_transcript({"media_url": "https://v.example/a.mp4"})
        self.assertIn("未配置转写模型", c["transcript_note"])
        self.assertNotIn("transcript", c)

    def test_auto_transcribe_and_failure(self):
        with patch.object(adapters, "transcribe_media", return_value="自动文字"):
            c = adapters.attach_transcript({"media_url": "https://v.example/a.mp4"})
        self.assertEqual(c["transcript_source"], "自动转写")
        with patch.object(adapters, "transcribe_media", side_effect=ValueError("视频超过转写大小上限")):
            c = adapters.attach_transcript({"media_url": "https://v.example/a.mp4"})
        self.assertIn("自动转写失败", c["transcript_note"])

    def test_media_download_rejects_unsafe_hosts(self):
        for url in ("http://v.example/a", "https://127.0.0.1/a", "https://localhost/a", "https://[::1]/a"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                adapters.download_media(url)

    def test_media_url_extraction(self):
        node = {
            "video": {
                "cover": {"url_list": ["https://img/x.jpeg"]},
                "play_addr": {"url_list": ["https://v.example/play.mp4"]},
            }
        }
        self.assertEqual(adapters.media_url(node), "https://v.example/play.mp4")
        self.assertEqual(
            adapters.media_url({"media": {"stream": {"h264": [{"master_url": "https://x/m.mp4"}]}}}),
            "https://x/m.mp4",
        )
        self.assertIsNone(adapters.media_url({"title": "图文"}))

    def test_multipart_body(self):
        body, ctype = adapters.multipart({"model": "m"}, "file", "a.mp4", b"\x00\x01", "video/mp4")
        self.assertIn(b'name="model"\r\n\r\nm', body)
        self.assertIn(b"\x00\x01", body)
        self.assertTrue(ctype.startswith("multipart/form-data; boundary="))


if __name__ == "__main__":
    unittest.main()
