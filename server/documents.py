"""把上传的 Word / PDF 资料转成纯文本。原文件只在内存和临时目录中短暂存在，不入库。

- .docx：标准库解析 word/document.xml（段落、表格、换行）。
- .pdf：优先 pypdf（若已安装）；在 macOS 上退回系统自带的 PDFKit；都不可用时提示。
- 旧版 .doc 不支持，提示另存为 .docx。
"""

import base64, io, os, re, subprocess, sys, tempfile, zipfile
from xml.etree import ElementTree as ET

MAX_BYTES = 2 * 1024 * 1024
MAX_CHARS = 100000
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def decode_data_url(data):
    match = re.fullmatch(r"data:[\w/.+-]*;base64,([A-Za-z0-9+/=\s]+)", data or "")
    if not match:
        raise ValueError("文件数据格式不正确")
    blob = base64.b64decode(match.group(1))
    if len(blob) > MAX_BYTES:
        raise ValueError("文件最大支持 2 MB")
    return blob


def docx_text(blob):
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            info = z.getinfo("word/document.xml")
            if info.file_size > 20 * 1024 * 1024:
                raise ValueError("文档内容过大")
            root = ET.fromstring(z.read(info))
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        raise ValueError("无法读取这个 Word 文件，请确认是 .docx 格式")
    lines = []
    body = root.find(W + "body")
    for block in body if body is not None else []:
        if block.tag == W + "p":
            lines.append(_paragraph(block))
        elif block.tag == W + "tbl":
            for row in block.iter(W + "tr"):
                cells = [
                    " ".join(_paragraph(p) for p in cell.iter(W + "p")).strip()
                    for cell in row.iter(W + "tc")
                ]
                lines.append(" | ".join(cells))
    return _clean("\n".join(lines))


def _paragraph(p):
    parts = []
    for node in p.iter():
        if node.tag == W + "t" and node.text:
            parts.append(node.text)
        elif node.tag == W + "tab":
            parts.append("\t")
        elif node.tag in (W + "br", W + "cr"):
            parts.append("\n")
    return "".join(parts)


def pdf_text(blob):
    if not blob.startswith(b"%PDF"):
        raise ValueError("无法读取这个 PDF 文件")
    try:
        from pypdf import PdfReader  # 可选依赖

        reader = PdfReader(io.BytesIO(blob))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        if text.strip():
            return _clean(text)
    except ImportError:
        pass
    except Exception:
        raise ValueError("PDF 解析失败，文件可能已加密或损坏")
    if sys.platform == "darwin":
        text = _pdfkit_text(blob)
        if text.strip():
            return _clean(text)
        raise ValueError("没有从 PDF 中读到文字，可能是扫描件；请粘贴文字内容")
    raise ValueError("当前环境无法解析 PDF：请安装 pypdf（pip3 install pypdf）或直接粘贴文字")


def _pdfkit_text(blob):
    script = (
        "ObjC.import('PDFKit');"
        "function run(argv){"
        "var d=$.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(argv[0]));"
        "if(!d){return ''};var s=d.string;return s?ObjC.unwrap(s):''}"
    )
    fd, path = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(blob)
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", script, path],
            capture_output=True,
            timeout=30,
        )
        return result.stdout.decode("utf-8", "replace")
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("PDF 解析失败，请直接粘贴文字")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _clean(text):
    text = text.replace("\r\n", "\n").replace("\x00", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise ValueError("文件中没有可读取的文字")
    return text[:MAX_CHARS]


def extract(name, data_url):
    ext = os.path.splitext(str(name or "").lower())[1]
    blob = decode_data_url(data_url)
    if ext == ".docx":
        return docx_text(blob)
    if ext == ".pdf":
        return pdf_text(blob)
    if ext == ".doc":
        raise ValueError("暂不支持旧版 .doc，请在 Word 中另存为 .docx 后上传")
    raise ValueError("只支持 .docx 与 .pdf 文件解析")
