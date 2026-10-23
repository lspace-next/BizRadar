"""발행 전 검증. data/notices.json · data/meta.json 의 구조와 규칙을 본다. FAIL 이 하나라도 있으면 exit 1.

    python tools/check_notices.py            # 전체 검사 + 오늘(KST) 추가·수정된 공고의 링크 확인
    python tools/check_notices.py --links    # 모든 공고 링크 확인 (느림)
    python tools/check_notices.py --no-links # 링크 확인 생략

규칙은 CLAUDE.md "데이터 규칙" 과 같다.
"""
import datetime as dt
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
KST = dt.timezone(dt.timedelta(hours=9))

TYPES = {"rnd", "support", "bid"}
FITS = {"high", "mid"}
FIT_ITEMS = ["분야", "주관 자격", "지역", "부담·조건"]  # 순서 고정
FIT_RESULTS = {"ok", "partial", "no", "check"}
TAGS = {"AI", "SW개발", "데이터", "클라우드", "보안", "디지털전환", "제조·스마트공장", "조선·해양", "네트워크·통신", "공공정보화", "기타IT"}
REQUIRED = ["id", "type", "title", "agency", "source", "url", "src_ids", "posted", "deadline", "budget", "budget_won",
            "summary", "why", "conditions", "tags", "fit", "fit_analysis", "added", "updated"]
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DEADLINE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?$")


def status(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def check(notices, label, fails, warns, today):
    ids, urls = set(), set()
    for i, n in enumerate(notices):
        where = f"{label}[{i}] {n.get('id', '?')}"
        missing = [k for k in REQUIRED if k not in n]
        if missing:
            fails.append(f"{where}: 필드 없음 {missing}")
            continue
        if n["id"] in ids:
            fails.append(f"{where}: id 중복")
        ids.add(n["id"])
        if n["url"] in urls:
            fails.append(f"{where}: url 중복")
        urls.add(n["url"])
        if not re.fullmatch(r"[a-z0-9]+-[A-Za-z0-9_.-]+", n["id"]):
            fails.append(f"{where}: id 형식(소스접두어-원번호) 아님")
        if n["type"] not in TYPES:
            fails.append(f"{where}: type '{n['type']}' (rnd/support/bid)")
        if n["fit"] not in FITS:
            fails.append(f"{where}: fit '{n['fit']}' (high/mid)")
        if "attach" in n:
            fails.append(f"{where}: attach 는 쓰지 않음 (첨부는 원문 공고에서 확인)")
        if not n["title"].strip() or not n["agency"].strip():
            fails.append(f"{where}: 제목·기관 비어 있음")
        if not n["url"].startswith("https://") and not n["url"].startswith("http://"):
            fails.append(f"{where}: url 형식")
        if not isinstance(n["src_ids"], list) or not n["src_ids"]:
            fails.append(f"{where}: src_ids 는 1개 이상 목록")
        for k in ("posted", "added", "updated"):
            if not DATE.match(n[k]):
                fails.append(f"{where}: {k} '{n[k]}' (YYYY-MM-DD)")
        if n["deadline"] and not DEADLINE.match(n["deadline"]):
            fails.append(f"{where}: deadline '{n['deadline']}' (YYYY-MM-DD 또는 YYYY-MM-DDTHH:MM, 상시면 빈칸)")
        if n["deadline"] and n["posted"] and n["deadline"][:10] < n["posted"]:
            fails.append(f"{where}: deadline 이 posted 보다 이름")
        if n.get("start") and not DATE.match(n["start"]):
            fails.append(f"{where}: start '{n['start']}' (YYYY-MM-DD)")
        if n["added"] > today or n["updated"] > today:
            fails.append(f"{where}: added/updated 가 오늘({today}) 이후")
        if n["updated"] < n["added"]:
            fails.append(f"{where}: updated 가 added 보다 이름")
        if not isinstance(n["budget_won"], (int, float)) or isinstance(n["budget_won"], bool) or n["budget_won"] < 0:
            fails.append(f"{where}: budget_won 은 0 이상 숫자(모르면 0)")
        if n["budget_won"] and not n["budget"]:
            fails.append(f"{where}: budget_won 이 있으면 budget 표시 문구도 필요")
        s = n["summary"].strip()
        if not s:
            fails.append(f"{where}: summary 비어 있음")
        elif len(s) > 400:
            warns.append(f"{where}: summary {len(s)}자 (2–3문장 권장)")
        w = n["why"].strip()
        if not w:
            fails.append(f"{where}: why 비어 있음 (L.SPACE 입장에서 왜 중요한가 1문장)")
        elif len(w) > 160:
            warns.append(f"{where}: why {len(w)}자 (1문장 권장)")
        fa = n["fit_analysis"]
        if not isinstance(fa, list) or [a.get("item") for a in fa if isinstance(a, dict)] != FIT_ITEMS:
            fails.append(f"{where}: fit_analysis 는 {FIT_ITEMS} 순서의 항목 목록")
        else:
            res = {a["item"]: a.get("result") for a in fa}
            for a in fa:
                if a.get("result") not in FIT_RESULTS:
                    fails.append(f"{where}: fit_analysis '{a['item']}' result '{a.get('result')}' (ok/partial/no/check)")
                if not str(a.get("note", "")).strip():
                    fails.append(f"{where}: fit_analysis '{a['item']}' note 비어 있음")
            if n["fit"] == "high" and any(res[k] != "ok" for k in ("분야", "주관 자격", "지역")):
                fails.append(f"{where}: fit high 는 분야·주관 자격·지역이 모두 ok 여야 함")
            if res.get("지역") == "no":
                fails.append(f"{where}: 지역 불충족 공고는 싣지 않음")
        if not isinstance(n["conditions"], list):
            fails.append(f"{where}: conditions 는 목록")
        elif not n["conditions"]:
            warns.append(f"{where}: conditions 비어 있음 (핵심 조건 확인)")
        if not isinstance(n["tags"], list) or not n["tags"]:
            fails.append(f"{where}: tags 1개 이상")
        else:
            bad = [t for t in n["tags"] if t not in TAGS]
            if bad:
                fails.append(f"{where}: 허용되지 않은 태그 {bad} (CLAUDE.md 태그 표)")
        if n["type"] == "bid":
            b = n.get("bid")
            if not isinstance(b, dict) or "method" not in b:
                fails.append(f"{where}: 입찰 공고는 bid.method 필요")
    return ids


def main():
    args = sys.argv[1:]
    today = dt.datetime.now(KST).date().isoformat()
    fails, warns = [], []

    path = ROOT / "data/notices.json"
    try:
        notices = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"FAIL data/notices.json 읽기 실패: {e}")
        return 1
    if not isinstance(notices, list):
        print("FAIL data/notices.json 은 배열이어야 함")
        return 1
    ids = check(notices, "notices", fails, warns, today)

    order = [(n.get("added", ""), n.get("id", "")) for n in notices]
    if order != sorted(order, key=lambda x: x[0], reverse=True):
        fails.append("notices.json 은 added 최신순이어야 함 (새 공고는 배열 맨 앞)")

    for f in sorted((ROOT / "data/archive").glob("*.json")):
        arch = json.loads(f.read_text(encoding="utf-8"))
        dup = ids & check(arch, f.name, fails, warns, today)
        if dup:
            fails.append(f"{f.name}: notices.json 과 id 중복 {sorted(dup)[:3]}")

    try:
        meta = json.loads((ROOT / "data/meta.json").read_text(encoding="utf-8"))
        if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", meta.get("last_run", "")):
            fails.append("meta.json last_run 형식 (YYYY-MM-DDTHH:MM+09:00)")
        for k in ("new", "updated"):
            if not isinstance(meta.get(k), int):
                fails.append(f"meta.json {k} 는 정수")
        for k, v in (meta.get("sources") or {}).items():
            if v.get("status") not in ("ok", "error", "skip"):
                fails.append(f"meta.json sources.{k}.status 는 ok·error·skip")
            if v.get("status") == "error":
                warns.append(f"수집 실패 소스 {k}: {v.get('error', '')}")
    except Exception as e:
        fails.append(f"data/meta.json 읽기 실패: {e}")

    if "--no-links" not in args:
        targets = notices if "--links" in args else [n for n in notices if n.get("updated") == today]
        for n in targets:
            for u in [n.get("url", "")]:
                code = status(u)
                if code in (401, 403, 405) or code == 0:
                    warns.append(f"{n['id']}: 링크 확인 불가({code}) — 브라우저/WebFetch 로 확인 {u}")
                elif code >= 400:
                    fails.append(f"{n['id']}: 링크 {code} {u}")

    for w in warns:
        print("WARN", w)
    for f in fails:
        print("FAIL", f)
    print(f"{'FAIL' if fails else 'PASS'} — 공고 {len(notices)}건, FAIL {len(fails)}, WARN {len(warns)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
