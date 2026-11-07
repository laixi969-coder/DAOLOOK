"""Observation provenance, project isolation and the published-feedback lifecycle."""
import copy
import csv
import io
import json
import queue
import unittest
from unittest.mock import patch
from server import questions, adapters, jobs, editing, maintenance, resource_limits, account_deletion, overseas
from tests import test_original as fixture

D = fixture.D


class QuestionUnitTests(unittest.TestCase):
    def test_untrusted_sources_and_bounds(self):
        self.assertIsNone(questions.clean(None))
        self.assertIsNone(questions.clean({"text": "  "}))
        self.assertEqual(questions.clean({"text": "多少钱？"})["source"], "merchant_record")
        for value in ([], {"text": 4}, {"text": "x" * 2001}, {"source": []},
                      {"source": "published_feedback"}, {"verified": True}, {"occurred_on": "2026-02-30"}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                questions.clean(value)

    def test_question_citation_does_not_prove_answer(self):
        obs = [{"id": "q", "text": "可以当天交片吗？", "source": "customer_quote"}]
        out = {"topic_plan": {**questions.example(), "refs": [{"id": "q", "quote": "当天交片"}]}, "evidence": []}
        questions.validate([out], obs)
        questions.attach([out], obs)
        self.assertEqual(out["topic_basis"]["status"], "sourced")
        self.assertEqual(out["topic_basis"]["answer_sources"], [])
        for refs in ([{"id": "other", "quote": "当天交片"}], [{"id": "q", "quote": "很多客户都担心"}],
                     [{"id": "q", "quote": "当天交片"}] * 2):
            with self.assertRaises(ValueError):
                questions.validate([{**out, "topic_plan": {**out["topic_plan"], "refs": refs}}], obs)

    def test_hypothesis_market_and_material_never_become_customer_fact(self):
        for source, status in (("hypothesis", "hypothesis"), ("market_topic", "clue"),
                               ("business_material", "clue"), ("market_comment", "clue")):
            obs = [{"id": "q", "text": "价格会不会很贵", "source": source}]
            out = {"topic_plan": {**questions.example(), "refs": [{"id": "q", "quote": "价格会不会很贵"}]}}
            questions.attach([out], obs)
            self.assertEqual(out["topic_basis"]["status"], status)
        out = {"topic_plan": questions.example()}
        questions.attach([out], [])
        self.assertEqual(out["topic_basis"]["status"], "hypothesis")

    def test_missing_or_unbounded_plan_is_rejected(self):
        for plan in (None, {}, {**questions.example(), "answer": "a" * 601},
                     {**questions.example(), "refs": "q"}, {**questions.example(), "approach": "夸大风险"}):
            with self.assertRaises(ValueError):
                questions.validate([{"topic_plan": plan}], [])

    def test_edit_and_rewrite_preserve_history_without_recertifying(self):
        original = {"title": "原稿", "body": "原稿正文", "topic_plan": questions.example(),
                    "topic_basis": {"status": "sourced", "sources": [{"id": "q"}], "answer_sources": []}}
        edited = editing.edited_data(original, {"body": "修改后的正文"}, "douyin")
        self.assertTrue(edited["topic_basis"]["review_required"])
        self.assertNotIn("review_required", original["topic_basis"])
        forged = {"body": "new", "topic_basis": {"sources": [{"id": "forged"}]}}
        updated = questions.mark_edited(forged, original)
        self.assertEqual(updated["topic_basis"]["sources"], [{"id": "q"}])
        self.assertNotIn("topic_basis", questions.mark_edited(copy.deepcopy(forged), {}))


class QuestionApiTests(unittest.TestCase):
    setUp = fixture.OriginalTests.setUp
    tearDown = fixture.OriginalTests.tearDown
    post = fixture.OriginalTests.post
    ws = fixture.OriginalTests.ws
    run_task = fixture.OriginalTests.run_task
    formal_account = fixture.OriginalTests.formal_account

    def listing(self):
        status, result = self.c.req(f"/api/questions?project_id={self.p}")
        self.assertEqual(status, 200, result)
        return result

    def generate(self, **extra):
        status, result = self.post("/api/original", {"platform": "xhs", "topic": "写真套餐",
                                  "temporary": "写真套餐包含20张精修，底片全部交付。可私信咨询。",
                                  "skip_question": True, **extra})
        self.assertEqual(status, 202, result)
        return result

    def test_collect_repeat_edit_delete_and_pagination(self):
        observation = {"text": "底片全部给吗？", "source": "customer_quote", "context": "初次拍写真"}
        first = self.generate(observation=observation)
        self.assertEqual(self.run_task(first)[0]["state"], "SUCCEEDED")
        records = self.listing()["items"]
        self.assertEqual(len(records), 1)
        ident = records[0]["id"]
        repeat = self.post("/api/original", {"brief_id": first["brief_id"], "skip_question": True})[1]
        self.assertEqual(self.run_task(repeat)[0]["state"], "SUCCEEDED")
        self.assertEqual(len(self.listing()["items"]), 1)
        with D.db() as c:
            payload = json.loads(c.execute("SELECT payload FROM tasks WHERE id=?", (repeat["task_ids"][0],)).fetchone()[0])
        self.assertEqual(payload["question_context"][0]["id"], ident)
        self.assertEqual(self.post("/api/questions", {"observation": observation})[1]["id"], ident)
        self.assertEqual(self.post("/api/questions/" + ident, {"observation": {"text": "精修可以加吗？", "source": "merchant_record"}})[0], 200)
        self.assertEqual(self.listing()["items"][0]["text"], "精修可以加吗？")
        self.assertEqual(self.c.req(f"/api/questions/{ident}?project_id={self.p}", "DELETE")[0], 200)
        self.assertEqual(self.listing()["items"], [])
        with D.db() as c:
            for i in range(22):
                questions.save(c, self.p, {"text": f"套餐问题{i}"})
        result = self.listing()
        self.assertEqual(len(result["items"]), 20)
        self.assertTrue(result["more"])
        self.assertEqual(len(self.c.req(f"/api/questions?project_id={self.p}&offset=20")[1]["items"]), 2)

    def test_invalid_input_and_task_admission_rollback(self):
        for invalid in ({"source": "customer_quote", "text": 5}, {"source": "ai_verified", "text": "假的"}):
            self.assertEqual(self.post("/api/questions", {"observation": invalid})[0], 400)
            self.assertEqual(self.post("/api/original", {"platform": "xhs", "topic": "套餐", "temporary": "业务资料", "observation": invalid, "skip_question": True})[0], 400)
        with patch.object(jobs.Q, "put", side_effect=queue.Full):
            status, _ = self.post("/api/original", {"platform": "xhs", "topic": "套餐", "temporary": "业务资料", "observation": {"text": "有底片吗？"}, "skip_question": True})
        self.assertEqual(status, 503)
        self.assertEqual(self.listing()["items"], [])

    def test_automatic_context_does_not_reject_valid_user_input(self):
        with D.db() as c:
            for index in range(12):
                questions.save(c, self.p, {'text': '写真套餐问题' + str(index) + '细节' * 900})
        with patch.object(resource_limits, 'MAX_INPUT_BYTES', 4000):
            result = self.generate()
        with D.db() as c:
            payload = json.loads(c.execute('SELECT payload FROM tasks WHERE id=?', (result['task_ids'][0],)).fetchone()[0])
        self.assertLess(len(payload['question_context']), 12)
        self.assertEqual(payload['temporary'], '写真套餐包含20张精修，底片全部交付。可私信咨询。')
        with patch.object(resource_limits, 'MAX_INPUT_BYTES', 4000):
            resource_limits.validate_inputs(payload)

    def test_project_ownership_on_all_routes(self):
        ident = self.post("/api/questions", {"observation": {"text": "项目甲问题"}})[1]["id"]
        old = self.p
        self.p = self.c.req("/api/projects", "POST", {"name": "项目乙"})[1]["id"]
        self.assertEqual(self.listing()["items"], [])
        self.assertEqual(self.post("/api/questions/" + ident, {"observation": {"text": "越权修改"}})[0], 404)
        self.assertEqual(self.c.req(f"/api/questions/{ident}?project_id={self.p}", "DELETE")[0], 404)
        with D.db() as c:
            self.assertEqual(questions.context(c, self.p, "xhs", "项目甲", ident), [])
        self.p = old
        self.assertEqual(self.listing()["items"][0]["text"], "项目甲问题")

    def test_feedback_updates_clears_and_requires_real_published_creation(self):
        result = self.generate()
        self.run_task(result)
        creation = next(c for c in self.ws()["creations"] if c["source_id"] == result["brief_id"])
        ident = creation["id"]
        self.post("/api/results/" + ident, {"results": {"note": "底片要另外付钱吗？", "leads": 0}})
        self.assertEqual(self.listing()["feedback"], [])
        self.post("/api/tracking/" + ident, {"status": "published"})
        self.assertEqual(self.listing()["feedback"], [])  # demo never becomes evidence
        with D.db() as c:
            output = {**creation["data"], "demo": False, "goal": "sales"}
            c.execute("UPDATE creation_outputs SET data=? WHERE id=?", (D.dumps(output), ident))
        feed = self.listing()["feedback"]
        self.assertEqual(feed[0]["text"], "底片要另外付钱吗？")
        self.assertEqual(feed[0]["results"]["leads"], 0)
        with D.db() as c:
            context = questions.context(c, self.p, "xhs", "底片")
            self.assertEqual(context[0]["id"], "feedback:" + ident)
            self.assertNotIn("results", context[0])  # goals may differ; metrics must not leak into comparisons
            self.assertEqual(questions.context(c, self.p, "douyin", "底片"), [])
        self.post("/api/results/" + ident, {"results": {"note": "精修交付要多久？"}})
        self.assertEqual(len(self.listing()["feedback"]), 1)
        self.assertEqual(self.listing()["feedback"][0]["text"], "精修交付要多久？")
        self.post("/api/tracking/" + ident, {"status": "draft"})
        self.assertEqual(self.listing()["feedback"], [])
        self.post("/api/tracking/" + ident, {"status": "published"})
        self.post("/api/results/" + ident, {"results": {"note": ""}})
        self.assertEqual(self.listing()["feedback"], [])
        self.post("/api/results/" + ident, {"results": {"note": "新的问题"}})
        self.c.req(f"/api/creations/{ident}?project_id={self.p}", "DELETE")
        self.assertEqual(self.listing()["feedback"], [])

    def test_real_generation_paths_resolve_verified_provenance_and_export(self):
        self.formal_account()
        with D.db() as c:
            c.execute("UPDATE settings SET value='\"live\"' WHERE key='mode'")
        captured = []
        def model(prompt, schema, version, kind, validator):
            captured.append(prompt)
            outputs = adapters.demo_outputs("xhs", "写真", prompt["batch"])
            obs = prompt["question_observations"][0]
            for out in outputs:
                out["topic_plan"] = {**questions.example(), "refs": [{"id": obs["id"], "quote": obs["text"]}]}
                out["evidence"] = [{"asset_id": "temporary", "quote": "底片全部交付"}]
                out["topic_basis"] = {"status": "verified", "sources": [{"id": "forged"}]}
            validator({"outputs": outputs})
            return {"outputs": outputs}, "test/model"
        with patch.object(adapters, "model_json", side_effect=model), patch.object(adapters, "fetch_benchmark", return_value={}):
            first = self.generate(observation={"text": "套餐底片全部给吗？", "source": "customer_quote"})
            self.assertEqual(self.run_task(first)[0]["state"], "SUCCEEDED")
            with D.db() as c:
                source_id = D.uid()
                c.execute("INSERT INTO source_contents VALUES (?,?,?,?,?,?,?)", (source_id, self.p, "xhs", "", D.dumps({"platform": "xhs", "title": "写真套餐", "demo": False}), 0, D.now()))
            result = self.post("/api/create", {"source_id": source_id, "temporary": "底片全部交付，可私信咨询", "skip_question": True})[1]
            self.assertEqual(self.run_task(result)[0]["state"], "SUCCEEDED")
        self.assertEqual(len(captured), 2)
        for prompt in captured:
            self.assertEqual(prompt["question_observations"][0]["source"], "customer_quote")
            self.assertNotIn("套餐底片全部给吗", prompt["assets"][0]["content"])
        for creation in self.ws()["creations"]:
            basis = creation["data"]["topic_basis"]
            self.assertEqual(basis["status"], "sourced")
            self.assertNotEqual(basis["sources"][0]["id"], "forged")
            self.assertEqual(basis["answer_sources"][0]["quote"], "底片全部交付")
        _, raw = self.c.req(f"/api/export?project_id={self.p}", raw=True)
        rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
        self.assertIn("问题出处", rows[0])
        self.assertTrue(all(len(r) == len(rows[0]) for r in rows))
        self.assertIn("套餐底片全部给吗", rows[1][rows[0].index("问题出处")])

    def test_overseas_keeps_story_and_routes_feedback_by_actual_target_platform(self):
        self.formal_account()
        with D.db() as c:
            c.execute("UPDATE settings SET value='\"live\"' WHERE key='mode'")
        seen = []
        def model(prompt, schema, version, kind, validator):
            seen.append(prompt)
            outputs = overseas.demo_outputs(prompt['brief'], prompt['assets'], prompt['batch'])
            for output in outputs:
                output['topic_plan'] = {**questions.example(), 'approach': '故事',
                                       'refs': [{'id': prompt['question_observations'][0]['id'], 'quote': '出门充电线太多'}]}
            validator({'outputs': outputs})
            return {'outputs': outputs}, 'test/model'
        with patch.object(adapters, 'model_json', side_effect=model), patch.object(overseas, 'benchmark', return_value={}):
            status, result = self.post('/api/overseas/create', {'platform': 'overseas', 'topic': '便携充电器',
                                      'observation': {'text': '出门充电线太多', 'source': 'field_observation'}})
            self.assertEqual(status, 202, result)
            self.assertEqual(self.run_task(result)[0]['state'], 'SUCCEEDED')
        creations = [c for c in self.ws()['creations'] if c['source_id'] == result['brief_id']]
        self.assertEqual(len(creations), 3)
        for creation in creations:
            output = creation['data']
            self.assertEqual(output['topic_plan']['approach'], '故事')
            self.assertEqual(output['topic_basis']['sources'][0]['source'], 'field_observation')
            self.assertNotIn('demo', output)
            self.post('/api/tracking/' + creation['id'], {'status': 'published'})
            self.post('/api/results/' + creation['id'], {'results': {'note': output['target_platform'] + ' 用户问是否便携'}})
        with D.db() as c:
            self.assertEqual(len(questions.feedback(c, self.p, 'overseas')), 3)
            self.assertEqual(len(questions.feedback(c, self.p, 'tiktok')), 1)
            self.assertEqual(questions.feedback(c, self.p, 'xhs'), [])
        self.assertEqual(seen[0]['question_observations'][0]['text'], '出门充电线太多')
        self.assertEqual(len(jobs.history_results(self.p, 'tiktok', 'leads')), 1)
        self.assertEqual(jobs.history_results(self.p, 'tiktok', 'sales'), [])
        self.assertEqual({r['platform'] for r in jobs.history_results(self.p, 'overseas', 'leads')}, {'tiktok','instagram','youtube'})

    def test_forged_topic_ref_fails_task_and_refunds_credits(self):
        self.formal_account()
        with D.db() as c:
            c.execute("UPDATE settings SET value='\"live\"' WHERE key='mode'")
        before = self.c.req('/api/bootstrap')[1]['credits']['balance']
        def model(prompt, schema, version, kind, validator):
            outputs = adapters.demo_outputs('xhs', '写真', 1)
            outputs[0]['topic_plan']['refs'] = [{'id': 'not-in-this-project', 'quote': '有底片吗'}]
            validator({'outputs': outputs})
            return {'outputs': outputs}, 'test/model'
        with patch.object(adapters, 'model_json', side_effect=model), patch.object(adapters, 'fetch_benchmark', return_value={}):
            result = self.generate(observation={'text': '底片全部给吗？'})
            with self.assertRaisesRegex(ValueError, '来源') as failure:
                jobs.run(result['task_ids'][0])
            # Match the queue worker's failure settlement; run() itself propagates.
            jobs.fail(result['task_ids'][0], str(failure.exception))
            with D.db() as c:
                task = dict(c.execute('SELECT * FROM tasks WHERE id=?', (result['task_ids'][0],)).fetchone())
        self.assertEqual(task['state'], 'FAILED')
        self.assertIn('来源', task['error'])
        self.assertEqual(self.c.req('/api/bootstrap')[1]['credits']['balance'], before)
        self.assertEqual(len(self.listing()['items']), 1)  # saved user input survives provider failure
        self.assertEqual(self.ws()['creations'], [])

    def test_material_cues_require_current_selected_original_quote(self):
        assets = [{"id": "a", "content": "担心精修加价", "kind": "产品信息"}]
        fact = {"asset_id": "a", "category": "常见顾虑", "quote": "担心精修加价", "demo": False}
        with D.db() as c:
            found = questions.context(c, self.p, "xhs", "精修", facts=[fact], assets=assets)
            self.assertEqual(found[0]["source"], "business_material")
            for facts, selected in (([{**fact, "demo": True}], assets), ([fact], []), ([{**fact, "quote": "编造"}], assets)):
                self.assertEqual(questions.context(c, self.p, "xhs", "精修", facts=facts, assets=selected), [])

    def test_maintenance_and_account_deletion_include_observations(self):
        result = self.generate(observation={"text": "底片如何交付？"})
        self.run_task(result)
        with D.db() as c:
            c.execute("UPDATE tasks SET updated_at='2000-01-01T00:00:00+00:00' WHERE id=?", (result["task_ids"][0],))
        maintenance.cleanup()
        with D.db() as c:
            payload = json.loads(c.execute("SELECT payload FROM tasks WHERE id=?", (result["task_ids"][0],)).fetchone()[0])
            self.assertNotIn("question_context", payload)
            self.assertNotIn("observation", payload)
            self.assertEqual(len(questions.saved(c, self.p)), 1)
            user = c.execute("SELECT user_id FROM projects WHERE id=?", (self.p,)).fetchone()[0]
            self.assertGreater(resource_limits.usage(c, user), 0)
        account_deletion.delete_user(user, "test-admin")
        with D.db() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM question_observations WHERE project_id=?", (self.p,)).fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
