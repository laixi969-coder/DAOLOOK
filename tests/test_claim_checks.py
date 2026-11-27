import unittest
from datetime import date

from server import content_quality
from server.claim_checks import check_claims


class ClaimCheckTests(unittest.TestCase):
    def check(self, source, copy):
        assets = source if isinstance(source, list) else [{"id": "source", "content": source}]
        checks, issues = check_claims(copy, assets, date(2026, 11, 26))
        for check in checks:
            if "source" in check:
                quote = check["source"]
                original = next(a["content"] for a in assets if a["id"] == quote["asset_id"])
                self.assertIn(quote["quote"], original)
        return checks, issues

    def test_otherwise_valid_citation_cannot_cover_a_changed_price(self):
        output = {"title": "到店体验", "body": "现在只要99元。欢迎留言咨询。", "audience": "顾客",
                  "value": "了解价格", "cta": "欢迎留言咨询。", "evidence": [{"asset_id": "p", "quote": "售价199元"}]}
        for platform in ("xhs", "douyin"):
            result = content_quality.assess(output, [{"id": "p", "content": "售价199元，仅限到店。"}], platform)
            self.assertEqual(result["status"], "needs_input")
            self.assertIn("现在只要99元", result["issues"][0])
            self.assertEqual(result["claim_checks"][0]["source"]["asset_id"], "p")
            self.assertIn("199", result["claim_checks"][0]["source"]["quote"])

    def test_product_specific_evidence_instead_of_a_bag_of_numbers(self):
        for source, valid, wrong in [
            ("商品A售价99元，商品B售价199元", "商品B只需199元", "商品B只需99元"),
            ("美式售价19元，拿铁售价29元", "拿铁29元", "拿铁19元"),
            ("美式售价19元", "美式售价19元", "拿铁售价19元"),
            ("小份15元和大份25元", "大份25元", "大份15元"),
            ("小杯每杯250毫升，大杯每杯500毫升", "大杯500ml", "大杯250ml"),
            ("250ml装99元、500ml装199元", "0.5升装199元", "0.5升装99元"),
        ]:
            with self.subTest(source=source):
                self.assertFalse(self.check(source, valid)[1])
                self.assertTrue(self.check(source, wrong)[1])

    def test_conditions_stay_with_their_price(self):
        source = "199元到店价、99元仅限会员。"
        checks, issues = self.check(source, "到店价199元，会员价99元。")
        self.assertFalse(issues)
        self.assertEqual([c["status"] for c in checks], ["matched", "matched"])
        self.assertTrue(self.check(source, "每人只要99元")[1])
        self.assertTrue(self.check(source, "非会员价99元")[1])
        self.assertTrue(self.check("售价199元。仅限到店。", "线上只要199元")[1])

    def test_bare_product_price_and_generic_product_reference(self):
        for copy in ("美式19元", "本品19元", "本品售价19元", "只要19元"):
            self.assertFalse(self.check("美式售价19元", copy)[1], copy)
        checks, issues = self.check("美式售价19元", "拿铁19元")
        self.assertTrue(issues)
        self.assertEqual(checks[0]["status"], "review")

    def test_explicit_promotion_restrictions_stay_with_the_price(self):
        source = "优惠价99元，仅限三人团购。"
        for copy in ("优惠价99元，仅限三人团购。", "3人拼团只要99元"):
            self.assertFalse(self.check(source, copy)[1], copy)
        for copy in ("全场优惠价99元", "两人团购只需99元", "13人团购只需99元", "无需三人团购也能享99元"):
            self.assertTrue(self.check(source, copy)[1], copy)
        source = "售价99元。仅适用于持通行证的访客。"
        self.assertTrue(self.check(source, "所有访客均可99元购买")[1])
        self.assertFalse(self.check(source, "售价99元，仅限持通行证的访客")[1])
        self.assertFalse(self.check("99元仅限新用户", "新客价99元")[1])

    def test_conflicting_sources_trigger_review(self):
        source = [{"id": "p1", "content": "标准版售价199元"}, {"id": "p2", "content": "标准版售价99元"}]
        self.assertTrue(self.check(source, "标准版只需99元")[1])
        source[1]["content"] = "升级版售价99元"
        self.assertFalse(self.check(source, "升级版只需99元")[1])

    def test_waiving_a_known_condition_does_not_confirm_it(self):
        for source, copy in [("售价99元，仅限新客", "不限新客，售价99元"),
                             ("会员价99元", "不用开通会员也能买，99元"),
                             ("到店满200减30", "不到店也能满200减30"),
                             ("仅限新客，99元", "新客身份不限，99元")]:
            with self.subTest(copy=copy):
                self.assertTrue(self.check(source, copy)[1])
        self.assertFalse(self.check("仅限新客，99元", "新用户99元")[1])

    def test_future_offers_keep_their_start_date(self):
        source = "活动自2026年12月1日起，满200减30"
        self.assertTrue(self.check(source, "今天满200减30")[1])
        self.assertTrue(self.check(source, "活动截至2026年12月1日，满200减30")[1])
        self.assertFalse(self.check(source, "自2026-12-01开始，满200元减30元")[1])
        self.assertFalse(self.check("2026年11月26日开始，满200减30", "满200减30")[1])

    def test_spec_units_and_pack_scope(self):
        for source, copy in [("产品净含量500毫升", "本品容量0.5升"), ("12 克一包，每盒10包", "每包１２g"), ("售价1,299元", "价格为1299元")]:
            with self.subTest(source=source):
                self.assertFalse(self.check(source, copy)[1])
        self.assertTrue(self.check("每盒12克", "每包12克")[1])
        self.assertTrue(self.check("含量500毫克", "含量500克")[1])
        self.assertTrue(self.check("每盒99元", "每包99元")[1])
        self.assertFalse(self.check("每包12克，每盒99元", "每盒99元")[1])

    def test_promotion_and_dates(self):
        self.assertFalse(self.check("会员满200减30", "会员满200元减30元")[1])
        self.assertTrue(self.check("会员满200减30", "会员满100减30")[1])
        self.assertTrue(self.check("满199元减99元", "售价99元")[1])
        self.assertTrue(self.check("满300减20", "满30减20")[1])
        self.assertTrue(self.check("会员享8折", "全场8折")[1])
        self.assertFalse(self.check("活动有效至2027年1月31日", "优惠截至2027-01-31")[1])
        self.assertTrue(self.check("活动有效至2027年1月31日", "优惠截至2027-02-01")[1])
        self.assertTrue(self.check("活动有效期30天", "有效期3天")[1])
        for source in ("活动价99元，有效至2026年1月1日", "活动价99元。活动有效至2026年1月1日",
                       "活动价99元。该优惠截止2022年5月1日。"):
            self.assertIn("到期", self.check(source, "现在只要99元")[1][0])
        self.assertFalse(self.check("A款99元。B款售价399元。该优惠截止2022年5月1日。", "A款99元")[1])
        self.assertFalse(self.check("售价99元，有效至2026年11月26日", "售价99元")[1])

    def test_purchase_routes_include_exact_url_and_negation(self):
        for source, valid, wrong in [
            ("可在京东下单", "去京东购买", "去淘宝购买"),
            ("不支持京东下单", "不能在京东购买", "可在京东购买"),
            ("购买链接 https://example.cn/item?a=1", "下单 https://example.cn/item?a=1", "下单 https://example.cn/item?a=2"),
            ("产品不含酒精", "本品无酒精", "本品含酒精"),
            ("禁止标注售价99元", "不得宣称售价99元", "售价99元"),
        ]:
            with self.subTest(source=source):
                self.assertFalse(self.check(source, valid)[1])
                self.assertTrue(self.check(source, wrong)[1])

    def test_unrelated_language_and_no_cross_platform_change(self):
        self.assertEqual(self.check("咖啡每包12克", "预算100元怎么挑礼物？在淘宝搜灵感。加入250毫升水。欢迎私信咨询。"), ([], []))
        for platform in ("youtube", "tiktok"):
            self.assertEqual(content_quality.assess({"body": "售价99元"}, [], platform)["claim_checks"], [])

    def test_demo_edits_show_local_checks_alongside_the_demo_label(self):
        assets = [{"id": "p", "content": "售价199元"}]
        output = {"demo": True, "body": "售价99元", "evidence": [{"asset_id": "p", "quote": "售价199元"}]}
        result = content_quality.assess(output, assets, "xhs")
        self.assertEqual(result["status"], "needs_input")
        self.assertTrue(any("演示" in message for message in result["issues"]))
        self.assertEqual(result["claim_checks"][0]["status"], "review")

    def test_forbidden_words_and_images_are_never_positive_evidence(self):
        assets = [{"id": "p", "content": "本品售价99元", "kind": kind} for kind in ("禁用词", "图片")]
        self.assertTrue(self.check(assets, "售价99元")[1])
        self.assertFalse(content_quality.evidence_valid({"evidence": [{"asset_id": "p", "quote": "本品售价99元"}]}, assets))

    def test_duplicate_fields_and_distinct_restrictions(self):
        checks, _ = self.check("零售价12元", "售价12元。售价12元。")
        self.assertEqual(len(checks), 1)
        self.assertTrue(self.check("新客价99元", "老客价99元")[1])


if __name__ == "__main__":
    unittest.main()
