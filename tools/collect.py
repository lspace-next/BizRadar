"""공고 후보 수집. 소스별 목록을 읽어 키워드로 1차 거르고, 이미 실린 공고를 빼서 후보 파일을 만든다.

    python tools/collect.py                     # 마지막 실행(meta.json last_run) 하루 전부터
    python tools/collect.py --since 2026-10-01  # 기준일 지정 (게시일·접수시작일 기준)
    python tools/collect.py --all               # 키워드 필터 없이 전부 (키워드 조정용)
    python tools/collect.py --only ntis,iris    # 일부 소스만

결과: .cache/candidates.json (커밋하지 않음). 후보마다 src_id·제목·기관·기간·상세 URL·맞은 키워드·
중복/정정 표시가 있다. 적합도 판정·요약은 사람(Claude)이 상세 페이지·공고문을 읽고 한다.
나라장터는 환경 변수 DATA_GO_KR_KEY(공공데이터포털 인증키)가 있을 때만 수집한다.
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / ".cache/candidates.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
KST = dt.timezone(dt.timedelta(hours=9))

# 하나라도 맞으면 후보. 짧은 영문(AI, SW 등)은 단어 경계로 본다.
KEYWORDS = [
    "소프트웨어", "SW", "인공지능", "AI", "AX", "LLM", "생성형", "데이터", "빅데이터", "클라우드", "SaaS",
    "플랫폼", "정보시스템", "정보화", "시스템 구축", "시스템구축", "고도화", "전산", "ICT", "IT", "디지털",
    "디지털트윈", "디지털 트윈", "DX", "메타버스", "보안", "사이버", "블록체인", "자율", "로봇",
    "스마트공장", "스마트 공장", "스마트제조", "스마트시티", "알고리즘", "지능형", "XR", "IoT", "사물인터넷",
    "5G", "6G", "양자", "SI", "솔루션", "S/W", "모바일", "전자정부", "공공데이터", "마이데이터",
    "조선", "선박", "해양", "자율운항", "스마트야드", "기자재",  # 조선·해양 IT 가 주력 분야
]
_SHORT = {k for k in KEYWORDS if re.fullmatch(r"[A-Za-z0-9]{1,4}", k)}
_KW_RE = re.compile("|".join(
    (rf"(?<![A-Za-z]){re.escape(k)}(?![A-Za-z])" if k in _SHORT else re.escape(k))
    for k in sorted(KEYWORDS, key=len, reverse=True)))
# 맞아도 대부분 IT 와 무관한 공고 (제목에 IT 키워드가 같이 있으면 남긴다 — 표시만 함)
OFF_TOPIC = ["의약", "신약", "임상", "농식품", "축산", "수산", "산림", "관광", "경영안정자금", "융자", "보증",
             "수출바우처", "전시회", "박람회", "엑스포", "인력교류", "장학", "채용", "입점", "판로", "물류비", "측정기기",
             "IR ", "상담회", "품질인증"]
REVISION = re.compile(r"정정|연장|재공고|변경|수정공고|추가공고|추가 공고")
# 지역: 전국 공고와 부산·경남만 싣는다. 제목 머리의 [지역] 이 이 밖이면 후보에서 뺀다.
HOME_REGIONS = ("부산", "경남")
OTHER_REGIONS = ["서울", "인천", "경기", "강원", "충북", "충남", "대전", "세종", "전북", "전남", "광주", "대구", "경북",
                 "울산", "제주"]
_OTHER_RE = re.compile("|".join(OTHER_REGIONS))
# 키워드 필터 없이 전부 후보로 보는 소스 (조선·해양 전문기관 — 건수가 적고 주력 분야)
NO_KEYWORD_FILTER = {"rims"}


def region_of(title):
    """('home'|'other'|'', 표시용 지역명). 제목 머리 [지역] 기준, 없으면 본문 지역명은 표시만."""
    m = re.match(r"\s*\[([^\]]+)\]", title)
    if m:
        tag = m[1]
        if any(r in tag for r in HOME_REGIONS):
            return "home", tag
        if _OTHER_RE.search(tag):
            return "other", tag
    hit = _OTHER_RE.search(title)
    return "", hit[0] if hit else ""


def fetch(url, data=None, timeout=30, ua=UA):
    body = urllib.parse.urlencode(data).encode() if isinstance(data, dict) else data
    req = urllib.request.Request(url, data=body, headers={"User-Agent": ua, "Accept-Language": "ko-KR,ko"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        # 일부 기관(중소조선연구원 등)은 전체 브라우저 UA 문자열을 막고 짧은 UA 는 통과시킨다
        if e.code == 403 and ua == UA:
            return fetch(url, data, timeout, ua="Mozilla/5.0")
        raise


def text(fragment):
    fragment = re.sub(r"<!--.*?-->", " ", fragment or "", flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def ymd(s):
    """'2026.10.16' / '2026-10-16 08:00' / '20261016' → '2026-10-16' (없으면 '')"""
    m = re.search(r"(\d{4})[.\-/]?(\d{2})[.\-/]?(\d{2})", s or "")
    return f"{m[1]}-{m[2]}-{m[3]}" if m else ""


# ---------------------------------------------------------------- 소스 어댑터
# 각 어댑터는 since(YYYY-MM-DD) 이후 게시·접수 시작된 공고를 dict 목록으로 낸다.
# 공통 키: src, src_id, type, title, agency, posted, start, end, url, extra

def ntis(since):
    """NTIS 국가R&D통합공고 (부처 전체 R&D 공고. 공고금액·마감시간은 상세에 있음)"""
    out = []
    for page in range(1, 6):
        s = fetch("https://www.ntis.go.kr/rndgate/eg/un/ra/mng.do", {"pageIndex": page, "pageUnit": 100})
        rows = re.findall(r"<tr>(.*?)</tr>", s, re.S)
        open_rows = 0
        for row in rows:
            uid = re.search(r"fn_view\('(\d+)'\)", row)
            if not uid:
                continue
            cell = lambda name: text((re.search(rf'data-title="{name}"[^>]*>(.*?)</td>', row, re.S) or [None, ""])[1])
            title = html.unescape(re.search(r'<a[^>]*title="([^"]*)"', row)[1]).strip()
            state = cell("현황")
            if state == "마감":
                continue
            open_rows += 1
            out.append({
                "src": "NTIS", "src_id": f"ntis:{uid[1]}", "type": "rnd", "title": title,
                "agency": cell("부처명"), "posted": "", "start": ymd(cell("접수일")), "end": ymd(cell("마감일")),
                "url": f"https://www.ntis.go.kr/rndgate/eg/un/ra/view.do?roRndUid={uid[1]}",
                "extra": {"state": state},
            })
        # 목록은 등록순(최신 먼저)이라 뒤로 갈수록 마감 공고뿐이다. 한 페이지가 전부 마감이면 그만 본다.
        if not open_rows:
            break
    return out


def iris(since):
    """IRIS 범부처통합연구지원시스템 사업공고. 접수중은 전체(수십 건), 접수예정(공고예고)은 공고일 기준일 이후만.
    접수예정 목록은 오래된 예고까지 수백 페이지라 공고일 최신순으로 읽다가 기준일 이전이 나오면 멈춘다(페이지당 10초 이상 걸림)."""
    out = []
    for prg in ("ancmIng", "ancmPre"):
        page = 1
        while True:
            d = json.loads(fetch("https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituList.do",
                                 {"ancmPrg": prg, "pageIndex": page}, timeout=60))
            items = d.get("listBsnsAncmBtinSitu", [])
            if prg == "ancmPre":
                items = [a for a in items if ymd(a.get("ancmDe")) >= since]
            for a in items:
                out.append({
                    "src": "IRIS", "src_id": f"iris:{a['ancmId']}", "type": "rnd", "title": a["ancmTl"].strip(),
                    "agency": f"{a.get('blngGovdSeNm', '')} / {a.get('sorgnNm', '')}".strip(" /"),
                    "posted": ymd(a.get("ancmDe")), "start": ymd(a.get("rcveStrDe")), "end": ymd(a.get("rcveEndDe")),
                    "url": f"https://www.iris.go.kr/contents/retrieveBsnsAncmView.do?ancmId={a['ancmId']}&ancmPrg={prg}",
                    "extra": {"ancmNo": a.get("ancmNo", ""), "pbofrTp": a.get("pbofrTpSeNmLst", ""), "state": a.get("rcveSttSeNmLst", "")},
                })
            info = d.get("paginationInfo", {})
            if page >= info.get("totalPageCount", 1) or (prg == "ancmPre" and len(items) < 10) or page >= 20:
                break
            page += 1
    return out


def bizinfo(since):
    """기업마당 지원사업 공고 (중기부·지자체·전문기관 지원사업 통합)"""
    out = []
    for page in range(1, 21):
        s = fetch(f"https://www.bizinfo.go.kr/sii/siia/selectSIIA200View.do?rows=15&cpage={page}&schEndAt=N")
        body = s.split("<tbody", 1)[-1].split("</tbody>", 1)[0]
        rows = re.findall(r"<tr>(.*?)</tr>", body, re.S)
        stop = not rows
        for row in rows:
            tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            pid = re.search(r"pblancId=(PBLN_\d+)", row)
            if not pid or len(tds) < 7:
                continue
            posted = ymd(text(tds[6]))
            if posted and posted < since:
                stop = True
                continue
            period = text(tds[3])
            dates = re.findall(r"\d{4}-\d{2}-\d{2}", period)
            out.append({
                "src": "기업마당", "src_id": f"bizinfo:{pid[1]}", "type": "support", "title": text(tds[2]),
                "agency": f"{text(tds[4])} / {text(tds[5])}".strip(" /"), "posted": posted,
                "start": dates[0] if dates else "", "end": dates[1] if len(dates) > 1 else "",
                "url": f"https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId={pid[1]}",
                "extra": {"field": text(tds[1]), "period": period},
            })
        if stop:
            break
    return out


def nipa(since):
    """NIPA 정보통신산업진흥원 사업공고 (SW·클라우드·AI 바우처 등 비R&D 사업, 용역 모집)"""
    out = []
    for page in range(1, 6):
        s = fetch(f"https://www.nipa.kr/home/2-2?curPage={page}")
        body = s.split("<tbody", 1)[-1].split("</tbody>", 1)[0]
        rows = re.findall(r"<tr>(.*?)</tr>", body, re.S)
        stop = not rows
        for row in rows:
            a = re.search(r'<a href="(/home/2-2/(\d+))">(.*?)</a>', row, re.S)
            if not a:
                continue
            spans = re.findall(r'<span class="bco">(.*?)</span>', row, re.S)
            posted = ymd(text(spans[-1])) if spans else ""
            if posted and posted < since:
                stop = True
                continue
            period = text((re.search(r"신청기간 : ([^<]*)", row) or [None, ""])[1])
            dates = re.findall(r"\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?", period)
            biz = text((re.search(r'<span class="box[^"]*">(.*?)</span>', row, re.S) or [None, ""])[1])
            out.append({
                "src": "NIPA", "src_id": f"nipa:{a[2]}", "type": "support", "title": text(a[3]),
                "agency": "과기정통부 / NIPA", "posted": posted,
                "start": ymd(dates[0]) if dates else "", "end": ymd(dates[1]) if len(dates) > 1 else "",
                "url": "https://www.nipa.kr" + a[1], "extra": {"business": biz, "period": period},
            })
        if stop:
            break
    return out


def rims(since):
    """중소조선연구원 사업공고·입찰공고 (그누보드 게시판. 날짜가 MM-DD 라 연도를 추정한다)"""
    out, today = [], dt.datetime.now(KST).date()
    for table, kind in (("m0602", "support"), ("m0605", "bid")):
        s = fetch(f"https://www.rims.re.kr/bbs/board.php?bo_table={table}")
        body = s.split("<tbody", 1)[-1].split("</tbody>", 1)[0]
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
            a = re.search(r'<a href="([^"]*wr_id=(\d+))"[^>]*>(.*?)</a>', row, re.S)
            d = re.search(r'td_datetime">\s*([\d-]+)', row)
            if not a or not d:
                continue
            raw = d[1]
            if re.fullmatch(r"\d{2}-\d{2}", raw):  # 올해 글은 MM-DD, 지난해 글은 YY-MM-DD
                y = today.year - (1 if raw > today.strftime("%m-%d") else 0)
                raw = f"{y}-{raw}"
            elif re.fullmatch(r"\d{2}-\d{2}-\d{2}", raw):
                raw = "20" + raw
            posted = ymd(raw)
            if posted and posted < since:
                continue
            title = text(a[3])
            if "(마감)" in title:
                continue
            # 제목에 마감이 적힌 경우: (~26.10.08)
            m = re.search(r"~\s*(\d{2})\.(\d{1,2})\.(\d{1,2})", title)
            end = f"20{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}" if m else ""
            out.append({
                "src": "중소조선연구원", "src_id": f"rims:{table}-{a[2]}", "type": kind, "title": title,
                "agency": "중소조선연구원", "posted": posted, "start": "", "end": end,
                "url": html.unescape(a[1]), "extra": {"board": "사업공고" if table == "m0602" else "입찰공고"},
            })
    # 공지(상단 고정)와 일반 목록에 같은 글이 두 번 나오므로 합친다
    return list({r["src_id"]: r for r in out}.values())


def g2b(since):
    """나라장터 용역 입찰공고 (공공데이터포털 조달청_나라장터 입찰공고정보서비스, 인증키 필요)"""
    key = os.environ.get("DATA_GO_KR_KEY")
    if not key:
        raise RuntimeError("DATA_GO_KR_KEY 없음 — 건너뜀")
    now = dt.datetime.now(KST)
    begin = dt.datetime.strptime(since, "%Y-%m-%d")
    out, page = [], 1
    while True:
        q = urllib.parse.urlencode({
            "serviceKey": key, "type": "json", "numOfRows": 100, "pageNo": page, "inqryDiv": 1,
            "inqryBgnDt": begin.strftime("%Y%m%d0000"), "inqryEndDt": now.strftime("%Y%m%d%H%M"),
        }, safe="%")
        d = json.loads(fetch("https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc?" + q))
        body = d.get("response", {}).get("body", {})
        items = body.get("items") or []
        if isinstance(items, dict):  # 1건이면 dict 로 오는 경우
            items = items.get("item", [])
            items = items if isinstance(items, list) else [items]
        for it in items:
            no, ord_ = it.get("bidNtceNo", ""), it.get("bidNtceOrd", "")
            price = it.get("presmptPrce") or it.get("asignBdgtAmt") or ""
            out.append({
                "src": "나라장터", "src_id": f"g2b:{no}-{ord_}", "type": "bid", "title": (it.get("bidNtceNm") or "").strip(),
                "agency": it.get("dminsttNm") or it.get("ntceInsttNm") or "", "posted": ymd(it.get("bidNtceDt")),
                "start": ymd(it.get("bidBeginDt")), "end": ymd(it.get("bidClseDt")),
                "url": it.get("bidNtceDtlUrl") or f"https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo={no}&bidPbancOrd={ord_}",
                "extra": {
                    "price": price, "method": it.get("cntrctCnclsMthdNm", ""), "close": it.get("bidClseDt", ""),
                    "ntce_org": it.get("ntceInsttNm", ""), "kind": it.get("srvceDivNm", ""),
                },
            })
        total = int(body.get("totalCount") or 0)
        if page * 100 >= total or not items:
            break
        page += 1
    # 1억 미만 소액 용역은 뺀다 (가격 정보가 없으면 남김)
    keep = []
    for c in out:
        try:
            if c["extra"]["price"] and float(c["extra"]["price"]) < 100_000_000:
                continue
        except ValueError:
            pass
        keep.append(c)
    return keep


SOURCES = {"ntis": ntis, "iris": iris, "bizinfo": bizinfo, "nipa": nipa, "rims": rims, "g2b": g2b}


# ---------------------------------------------------------------- 필터·중복

def norm_title(t):
    t = re.sub(r"\[[^\]]*\]|\([^)]*\)|「|」|『|』|<[^>]*>", "", t)
    t = re.sub(r"(정정|연장|재|변경|추가)?\s*공고|공모|안내|모집", "", t)
    return re.sub(r"[\s\W_]+", "", t).lower()


def load_known():
    """notices.json + archive 의 src_ids, url, 정규화 제목"""
    known_ids, known_titles = {}, {}
    files = [ROOT / "data/notices.json", *sorted((ROOT / "data/archive").glob("*.json"))]
    for f in files:
        if not f.exists():
            continue
        for n in json.loads(f.read_text(encoding="utf-8")):
            for sid in n.get("src_ids", []):
                known_ids[sid] = n["id"]
            known_ids[n.get("url", "")] = n["id"]
            known_titles[norm_title(n["title"])] = n["id"]
    return known_ids, known_titles


def default_since():
    meta = ROOT / "data/meta.json"
    if meta.exists():
        last = json.loads(meta.read_text(encoding="utf-8")).get("last_run", "")[:10]
        if last:
            return (dt.date.fromisoformat(last) - dt.timedelta(days=1)).isoformat()
    return (dt.datetime.now(KST).date() - dt.timedelta(days=14)).isoformat()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None)
    ap.add_argument("--all", action="store_true", help="키워드 필터 없이 전부")
    ap.add_argument("--only", default="", help="쉼표로 구분한 소스 이름")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    since = args.since or default_since()
    today = dt.datetime.now(KST).date().isoformat()
    names = [s for s in args.only.split(",") if s] or list(SOURCES)

    known_ids, known_titles = load_known()
    report, cands, seen_titles = {}, [], {}
    for name in names:
        try:
            rows = SOURCES[name](since)
        except Exception as e:  # 소스 하나가 막혀도 나머지는 계속
            report[name] = f"ERROR {type(e).__name__}: {e}"
            continue
        kept = other = 0
        for r in rows:
            if r["end"] and r["end"] < today:
                continue  # 이미 마감
            scope, r["region"] = region_of(r["title"])
            if scope == "other":
                other += 1
                continue  # 부산·경남 밖 지역 공고
            r["keywords"] = sorted(set(_KW_RE.findall(r["title"])))
            r["off_topic"] = [w for w in OFF_TOPIC if w in r["title"]]
            if not args.all and not r["keywords"] and name not in NO_KEYWORD_FILTER:
                continue
            r["known"] = known_ids.get(r["src_id"]) or known_ids.get(r["url"]) or ""
            nt = norm_title(r["title"])
            r["maybe_dup_of"] = known_titles.get(nt, "") or seen_titles.get(nt, "")
            r["revision"] = bool(REVISION.search(r["title"]))
            seen_titles.setdefault(nt, r["src_id"])
            cands.append(r)
            kept += 1
        report[name] = f"{len(rows)}건 중 후보 {kept}건" + (f" (타 지역 {other}건 제외)" if other else "")

    new = [c for c in cands if not c["known"]]
    out = {"generated": dt.datetime.now(KST).isoformat(timespec="minutes"), "since": since,
           "report": report, "new": new, "known": [c for c in cands if c["known"]]}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"기준일 {since} · 결과 {args.out}")
    for k, v in report.items():
        print(f"  {k:8} {v}")
    print(f"신규 후보 {len(new)}건 (이미 실린 공고 {len(out['known'])}건 제외)")
    for c in new:
        flags = "".join([" [정정?]" if c["revision"] else "", f" [중복? {c['maybe_dup_of']}]" if c["maybe_dup_of"] else "",
                         f" [무관?{','.join(c['off_topic'])}]" if c["off_topic"] else "",
                         f" [지역? {c['region']}]" if c["region"] and not c["region"].startswith(HOME_REGIONS) else ""])
        print(f"  {c['src_id']:24} ~{c['end'] or '?':10} {c['title'][:70]}{flags}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
