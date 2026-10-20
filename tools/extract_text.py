"""공고문 첨부(hwp·hwpx·pdf·zip)·상세 페이지에서 본문 텍스트를 뽑는다. 규모·기한·자격 조건 확인용.

    python tools/extract_text.py <URL 또는 파일> [--max 20000]
    python tools/extract_text.py "https://www.iris.go.kr/comm/file/fileDownload.do?atchDocId=...&atchFileId=..."
    python tools/extract_text.py page "https://www.iris.go.kr/contents/retrieveBsnsAncmView.do?ancmId=024477"
        → 상세 페이지 본문 텍스트 + 첨부 다운로드 URL 목록 (IRIS·기업마당·NIPA·NTIS)

내려받은 파일은 .cache/files/ 에 둔다(커밋 안 함). hwp 는 olefile, pdf 는 pypdf 가 필요하다:
    pip install olefile pypdf
"""
import html
import io
import re
import struct
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache/files"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


def urlopen(url):
    """전체 브라우저 UA 를 막는 기관(중소조선연구원 등)은 짧은 UA 로 한 번 더 시도한다"""
    try:
        return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60)
    except urllib.error.HTTPError as e:
        if e.code != 403:
            raise
        return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60)


def download(url):
    with urlopen(url) as r:
        data = r.read()
        name = ""
        cd = r.headers.get("Content-Disposition", "")
        m = re.search(r"filename\*=UTF-8''([^;]+)", cd) or re.search(r'filename="?([^";]+)', cd)
        if m:
            raw = m[1]
            try:  # 서버마다 인코딩이 제각각(UTF-8 퍼센트 인코딩 / latin-1 로 읽힌 UTF-8·EUC-KR)
                name = urllib.parse.unquote(raw)
                if "Ã" in name or "ì" in name:
                    name = raw.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                name = raw.encode("latin-1", "ignore").decode("euc-kr", "ignore")
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (re.sub(r'[\\/:*?"<>|]', "_", name)[-120:] if name else "download.bin")
    path.write_bytes(data)
    return path, data


def kind(data, name=""):
    n = name.lower()
    if data[:4] == b"%PDF":
        return "pdf"
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "hwp"
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
        if any(x.startswith("Contents/section") for x in names) or n.endswith(".hwpx"):
            return "hwpx"
        if "word/document.xml" in names:
            return "docx"
        return "zip"
    return "txt"


def hwpx_text(data):
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        secs = sorted((x for x in z.namelist() if re.match(r"Contents/section\d+\.xml", x)),
                      key=lambda x: int(re.search(r"\d+", x)[0]))
        for s in secs:
            xml = z.read(s).decode("utf-8", "replace")
            xml = re.sub(r"</hp:p>", "\n", xml)
            xml = re.sub(r"<hp:tab[^>]*/>", "\t", xml)
            out.append(html.unescape(re.sub(r"<[^>]+>", "", xml)))
    return "\n".join(out)


def docx_text(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    return html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"</w:p>", "\n", xml)))


def hwp_text(data):
    """HWP 5.0 바이너리: BodyText/SectionN 스트림의 PARA_TEXT(태그 67) 레코드만 읽는다."""
    import olefile
    ole = olefile.OleFileIO(io.BytesIO(data))
    header = ole.openstream("FileHeader").read()
    compressed = bool(header[36] & 1)
    secs = sorted((e for e in ole.listdir() if e[0] == "BodyText"), key=lambda e: int(e[1][7:]))
    out = []
    for e in secs:
        raw = ole.openstream(e).read()
        if compressed:
            raw = zlib.decompress(raw, -15)
        i = 0
        while i + 4 <= len(raw):
            h = struct.unpack_from("<I", raw, i)[0]
            tag, size = h & 0x3FF, (h >> 20) & 0xFFF
            i += 4
            if size == 0xFFF:
                size = struct.unpack_from("<I", raw, i)[0]
                i += 4
            if tag == 67:
                out.append(para_text(raw[i:i + size]))
            i += size
    return "\n".join(out)


def para_text(b):
    chars, i = [], 0
    while i + 2 <= len(b):
        c = struct.unpack_from("<H", b, i)[0]
        if c < 32:
            if c in (10, 13):
                chars.append("\n")
            elif c == 9:
                chars.append("\t")
            # 확장/인라인 제어문자는 8 WCHAR(16바이트)를 차지한다
            if c in (1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23):
                i += 16
                continue
            i += 2
            continue
        chars.append(chr(c))
        i += 2
    return "".join(chars)


def pdf_text(data):
    from pypdf import PdfReader
    return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)


def extract(data, name=""):
    k = kind(data, name)
    if k == "zip":
        parts = []
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist():
                fn = info.filename
                try:
                    fn = fn.encode("cp437").decode("cp949")  # 한글 파일명 zip
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass
                if info.is_dir() or not re.search(r"\.(hwpx?|pdf|docx)$", fn, re.I):
                    continue
                # 서식·양식 파일은 건너뛰고 공고문 위주로
                if re.search(r"서식|양식|신청서|계획서", fn) and not re.search(r"공고", fn):
                    parts.append(f"\n=== {fn} (서식 — 생략) ===")
                    continue
                try:
                    parts.append(f"\n=== {fn} ===\n" + extract(z.read(info), fn))
                except Exception as e:
                    parts.append(f"\n=== {fn} (추출 실패: {e}) ===")
        return "\n".join(parts)
    return {"pdf": pdf_text, "hwp": hwp_text, "hwpx": hwpx_text, "docx": docx_text}.get(
        k, lambda d: d.decode("utf-8", "replace"))(data)


def page(url):
    """상세 페이지 본문 + 첨부 URL"""
    with urlopen(url) as r:
        s = r.read().decode("utf-8", "replace")
    host = "{0.scheme}://{0.netloc}".format(urllib.parse.urlparse(url))
    files = []
    # IRIS: f_bsnsAncm_downloadAtchFile('docId','fileId','이름', ...)
    for doc, fid, name in re.findall(r"downloadAtchFile\('([^']+)','([^']+)','([^']+)'", s):
        files.append((name.strip(), host + "/comm/file/fileDownload.do?" + urllib.parse.urlencode({"atchDocId": doc, "atchFileId": fid})))
    # 기업마당·NIPA 등: 일반 링크
    for href, label in re.findall(r'<a[^>]+href="([^"]*(?:fileDown|download|FileDown|fileDownload)[^"]*)"[^>]*>(.*?)</a>', s, re.S):
        if href.startswith("javascript"):
            continue
        files.append((re.sub(r"<[^>]+>|\s+", " ", label).strip() or href, urllib.parse.urljoin(url, html.unescape(href))))
    body = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", "", s, flags=re.S)
    body = re.sub(r"<br\s*/?>|</p>|</tr>|</li>|</h\d>", "\n", body)
    body = html.unescape(re.sub(r"<[^>]+>", " ", body))
    body = re.sub(r"[ \t\xa0]+", " ", body)
    body = re.sub(r"\n\s*\n+", "\n", body)
    return body.strip(), files


def main():
    args = sys.argv[1:]
    limit = 20000
    if "--max" in args:
        i = args.index("--max")
        limit = int(args[i + 1])
        del args[i:i + 2]
    if not args:
        print(__doc__)
        return 1
    if args[0] == "page":
        body, files = page(args[1])
        print(body[:limit])
        print("\n--- 첨부 ---")
        seen = set()
        for name, u in files:
            if u not in seen:
                seen.add(u)
                print(f"{name}\n  {u}")
        return 0
    src = args[0]
    if re.match(r"https?://", src):
        path, data = download(src)
        print(f"[saved] {path}")
    else:
        path, data = Path(src), Path(src).read_bytes()
    out = extract(data, path.name)
    out = re.sub(r"\n\s*\n+", "\n", out)
    print(out[:limit])
    if len(out) > limit:
        print(f"\n... ({len(out) - limit}자 생략, --max 로 늘릴 수 있음)")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
