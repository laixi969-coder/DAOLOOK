import base64, io, unittest, zipfile
from unittest.mock import patch
from server import documents

DOC = """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
<w:p><w:r><w:t>品牌：</w:t></w:r><w:r><w:t>山野咖啡</w:t></w:r></w:p>
<w:p><w:r><w:t>第一行</w:t><w:br/><w:t>第二行</w:t></w:r></w:p>
<w:tbl><w:tr><w:tc><w:p><w:r><w:t>产品</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>价格 XX</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
</w:body></w:document>"""


def data_url(blob, mime="application/octet-stream"):
    return f"data:{mime};base64," + base64.b64encode(blob).decode()


def docx():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("word/document.xml", DOC)
    return out.getvalue()


class DocumentTests(unittest.TestCase):
    def test_docx_paragraphs_breaks_and_tables(self):
        text = documents.extract("资料.DOCX", data_url(docx()))
        self.assertIn("品牌：山野咖啡", text)
        self.assertIn("第一行\n第二行", text)
        self.assertIn("产品 | 价格 XX", text)

    def test_rejections(self):
        with self.assertRaisesRegex(ValueError, "另存为 .docx"):
            documents.extract("a.doc", data_url(b"x"))
        with self.assertRaisesRegex(ValueError, ".docx 格式"):
            documents.extract("a.docx", data_url(b"not a zip"))
        with self.assertRaisesRegex(ValueError, "2 MB"):
            documents.extract("a.docx", data_url(b"0" * (2 * 1024 * 1024 + 1)))
        with self.assertRaisesRegex(ValueError, "格式不正确"):
            documents.extract("a.docx", "hello")
        with self.assertRaisesRegex(ValueError, "PDF"):
            documents.extract("a.pdf", data_url(b"not pdf"))
        with self.assertRaises(ValueError):
            documents.extract("a.exe", data_url(b"MZ"))

    def test_pdf_without_parser_off_mac_explains(self):
        import builtins

        real = builtins.__import__

        def blocked(name, *a, **k):
            if name == "pypdf":
                raise ImportError
            return real(name, *a, **k)

        with patch("builtins.__import__", blocked), patch.object(
            documents.sys, "platform", "linux"
        ):
            with self.assertRaisesRegex(ValueError, "pypdf"):
                documents.extract("a.pdf", data_url(b"%PDF-1.4 ..."))

    def test_pdf_uses_pdfkit_on_mac(self):
        import builtins

        real = builtins.__import__

        def blocked(name, *a, **k):
            if name == "pypdf":
                raise ImportError
            return real(name, *a, **k)

        with patch("builtins.__import__", blocked), patch.object(
            documents.sys, "platform", "darwin"
        ), patch.object(documents, "_pdfkit_text", return_value="山野咖啡 PDF"):
            self.assertEqual(
                documents.extract("a.pdf", data_url(b"%PDF-1.4 ...")), "山野咖啡 PDF"
            )


if __name__ == "__main__":
    unittest.main()
