from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

from tests import test_rewrite as fixture
from server import db as D, publish_pack


class PublishPackTests(unittest.TestCase):
    tearDown = fixture.RewriteTests.tearDown
    post = fixture.RewriteTests.post

    def setUp(self):
        fixture.RewriteTests.setUp(self)
        self.project = self.p
        photo = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a2uoAAAAASUVORK5CYII="
        self.photo = self.post("/api/assets", {"kind": "图片", "name": "门店图", "content": photo})[1]["id"]
        with D.db() as c:
            c.execute("INSERT INTO source_contents(id,project_id,platform,url,data,created_at) VALUES (?,?,?,?,?,?)",
                      ("a"*32, self.project, "xhs", "", "{}", D.now()))
            self.content = {"title": "手冲挂耳", "body": "本周到店价199元，仅限会员。\n营业期间可在门店购买。",
                             "cover_text": "手冲挂耳", "tags": ["咖啡"], "image_asset_ids": [self.photo]}
            c.execute("INSERT INTO creation_outputs(id,source_id,project_id,data,created_at) VALUES (?,?,?,?,?)",
                      ("b"*32, "a"*32, self.project, D.dumps(self.content), D.now()))
        self.route = "/api/creations/" + "b"*32

    def get(self, extra="", project=None, revision=0):
        return self.c.req(self.route + f"/publish-pack?project_id={project or self.project}&revision={revision}" + extra)

    def test_confirmation_project_and_revision_required_for_preview_and_export(self):
        self.assertEqual(self.get()[0], 409)
        self.assertEqual(self.post(self.route + "/ready", {"revision": 0})[0], 200)
        status, preview = self.get()
        self.assertEqual(status, 200, preview)
        self.assertEqual(len(preview["pages"]), 3)
        self.assertEqual(list(preview["images"]), [self.photo])
        self.assertTrue(all(p["photo"] == self.photo for p in preview["pages"]))
        self.assertIn("199元，仅限会员。", preview["pages"][1]["svg"])
        self.assertEqual(preview["copy"]["body"], self.content["body"])
        check = "&check=" + preview["state"]
        self.assertEqual(self.get(check)[1], {"ok": True})
        other = self.c.req("/api/projects", "POST", {"name": "其他项目"})[1]["id"]
        self.assertEqual(self.get(check, project=other)[0], 404)
        edited = self.post(self.route + "/edit", {"revision": 0, "changes": {"title":"改过的标题"}})
        self.assertEqual(edited[0], 200, edited)
        self.assertEqual(self.get(check)[0], 409)
        self.assertEqual(self.get(revision=1)[0], 409)

    def test_unlinked_photos_require_selection_and_deleted_media_invalidates_export(self):
        with D.db() as c:
            c.execute("UPDATE creation_outputs SET data=json_remove(data,'$.image_asset_ids') WHERE id=?", ("b"*32,))
        self.post(self.route + "/ready", {"revision": 0})
        self.assertEqual(self.get()[1]["pages"], [])
        self.assertEqual(self.get("&photo=" + "c"*32)[0], 409)
        status, preview = self.get("&photo=" + self.photo)
        self.assertEqual(status, 200, preview)
        self.c.req("/api/assets/"+self.photo, "DELETE", {"project_id":self.project})
        self.assertEqual(self.get("&photo="+self.photo+"&check="+preview["state"])[0], 409)
        self.assertEqual(self.get()[1], {"choices": [], "pages": []})
        with D.db() as c:
            c.execute("UPDATE source_contents SET platform='douyin' WHERE id=?", ("a"*32,))
        self.assertEqual(self.get()[0], 400)

    def test_single_paragraph_drafts_keep_restrictions_and_never_export_empty_pages(self):
        for body in ("挂耳咖啡199元。仅限到店会员。温水冲开即可。",
                     "挂耳咖啡199元。\n仅限到店会员。\n温水冲开即可。"):
            points = publish_pack.info_pages({"body": body})
            self.assertEqual(len(points), 2)
            self.assertIn("199元", points[0])
            self.assertIn("仅限到店会员", points[0])
            self.assertEqual(points[1], "温水冲开即可。")
        long = "原始背景文字" * 180 + "。另外有冷萃做法。也可以做成热饮。"
        self.assertEqual(publish_pack.info_pages({"body":long}), ["另外有冷萃做法。", "也可以做成热饮。"])
        self.assertEqual(publish_pack.info_pages({"body":"品质好", "cta":"品质好", "title":"好咖啡"}), [])
        self.assertEqual(publish_pack.info_pages({"body":"到店可试饮", "hook":"想知道风味吗？"}), ["到店可试饮", "想知道风味吗？"])
        with D.db() as c:
            c.execute("UPDATE creation_outputs SET data=json_set(data,'$.body','只有一段') WHERE id=?", ("b"*32,))
        self.post(self.route + "/ready", {"revision": 0})
        result = self.get()[1]
        self.assertTrue(result["needs_edit"])
        self.assertEqual(result["pages"], [])
        self.assertNotIn("state", result)

    def test_changes_to_selected_facts_invalidate_confirmation_and_open_download(self):
        product = {"name":"门店价格","kind":"产品信息","content":"本周到店价199元，仅限会员。"}
        aid = self.post("/api/assets", product)[1]["id"]
        task = self.post("/api/original",{"topic":"价格","platform":"xhs","assets":[aid],"skip_question":True})[1]["task_ids"][0]
        cid = "b"*32
        with D.db() as c:
            c.execute("UPDATE creation_outputs SET task_id=? WHERE id=?", (task, cid))
        def view():
            return self.c.req(self.route+"?project_id="+self.project)[1]
        def confirm(digest):
            return self.post(self.route+"/ready",{"revision":0,"source_digest":digest})
        original = view()["source_digest"]
        self.c.req("/api/assets/"+aid,"PATCH",{**product,"project_id":self.project,"content":"会员价189元。"})
        self.assertEqual(confirm(original)[0],409)
        self.assertEqual(self.post(self.route+"/ready",{"revision":0})[0],409)
        original = view()["source_digest"]
        self.assertEqual(confirm(original)[0],200)
        old_pack = self.get()[1]["state"]
        self.c.req("/api/assets/"+aid,"PATCH",{**product,"project_id":self.project,"content":"目前到店价299元。"})
        updated = view()
        self.assertTrue(updated["readiness_stale"])
        self.assertIsNone(updated["ready_at"])
        self.assertNotEqual(original,updated["source_digest"])
        self.assertEqual(confirm(original)[0],409)
        self.assertEqual(self.get("&check="+old_pack)[0],409)
        self.assertEqual(confirm(updated["source_digest"])[0],200)
        self.assertEqual(self.get("&check="+old_pack)[0],409)
        new_pack = self.get()[1]["state"]
        self.assertEqual(self.get("&check="+new_pack)[0],200)
        self.c.req("/api/assets/"+aid,"DELETE",{"project_id":self.project})
        self.assertEqual(self.get("&check="+new_pack)[0],409)
        self.assertTrue(view()["readiness_stale"])

    def test_legacy_confirmation_can_be_reviewed_after_publication_and_keeps_first_timestamp(self):
        cid = "b"*32
        legacy = "2026-01-01T08:00:00+00:00"
        with D.db() as c:
            c.execute("INSERT INTO creation_readiness(creation_id,revision,first_confirmed_at,confirmed_at) VALUES (?,0,?,?)",
                      (cid,legacy,legacy))
        self.assertEqual(self.post("/api/tracking/"+cid,{"status":"published"})[0],200)
        self.assertEqual(self.get()[0],409)
        view = self.c.req(self.route+"?project_id="+self.project)[1]
        self.assertTrue(view["readiness_stale"])
        self.assertEqual(self.post(self.route+"/ready",{"revision":0,"source_digest":view["source_digest"]})[0],200)
        self.assertEqual(self.get()[0],200)
        with D.db() as c:
            self.assertEqual(c.execute("SELECT first_confirmed_at FROM creation_readiness WHERE creation_id=?",(cid,)).fetchone()[0],legacy)

    def test_zip_opens_with_standard_reader_and_chinese_filenames(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / "图文.zip"
            js = ("const {zip}=require('./web/publish-pack.js');"
                  "const {writeFileSync}=require('node:fs');"
                  "zip([['1-封面.png',new Uint8Array([0,127,255])],['正文.txt',new TextEncoder().encode('完整正文')]])"
                  ".arrayBuffer().then(b=>writeFileSync(process.argv[1],Buffer.from(b)))")
            subprocess.run(["node", "-e", js, str(dest)], cwd=root, check=True)
            with zipfile.ZipFile(dest) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(archive.read("正文.txt").decode(), "完整正文")
                self.assertEqual(archive.read("1-封面.png"), bytes([0,127,255]))

    def test_offers_without_price_keep_their_conditions_and_multiline_cover_keeps_the_title(self):
        for body in ("本周买一赠一。\n仅限会员。\n欢迎进店参观。","免费换新。仅限会员。门店周末营业。"):
            pages = publish_pack.info_pages({"body": body})
            self.assertEqual(len(pages),2)
            self.assertIn("仅限会员",pages[0])
        title = "\n".join(["会员","专享"]*9)
        from xml.etree import ElementTree
        cover = ElementTree.fromstring(publish_pack.layouts({"title":title},["内页一","内页二"])[0])
        visible = "".join(node.text or "" for node in cover.findall(".//{*}text"))
        self.assertEqual("".join(visible.split()),"".join(title.split()))
