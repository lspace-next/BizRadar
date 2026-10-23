"""data/meta.json 을 쓴다. /daily 4단계에서 신규·갱신 건수를 넘겨 실행한다.

    python tools/write_meta.py --new 3 --updated 1

last_run = 지금(KST). sources = collect.py 가 남긴 .cache/scan.json 의 소스별 결과(오늘 수집한 것만) —
사이트 상단 "수집 현황"이 이걸로 소스마다 정상·접속 실패·보류를 보여 준다.
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN = ROOT / ".cache/scan.json"
META = ROOT / "data/meta.json"
KST = dt.timezone(dt.timedelta(hours=9))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--new", type=int, required=True)
    ap.add_argument("--updated", type=int, required=True)
    args = ap.parse_args()
    now = dt.datetime.now(KST)
    scan = json.loads(SCAN.read_text(encoding="utf-8")) if SCAN.exists() else {}
    # 오늘 수집하지 않은 소스(이전 실행에 남은 결과)는 싣지 않는다
    sources = {k: v for k, v in scan.items() if v.get("at", "")[:10] == now.date().isoformat()}
    meta = {"last_run": now.strftime("%Y-%m-%dT%H:%M+09:00"), "new": args.new, "updated": args.updated, "sources": sources}
    META.write_text(json.dumps(meta, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=1))
    if not sources:
        print("WARN: .cache/scan.json 에 오늘 수집 결과가 없음 — collect.py 를 먼저 실행", file=sys.stderr)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
