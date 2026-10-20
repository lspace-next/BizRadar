# L.SPACE Biz Radar

https://lspace-next.github.io/BizRadar/

국가R&D 과제 · 정부 지원사업 · 나라장터 SW 입찰공고 중 프로그램 개발·AI·IT 관련 공고를 매일 모아
사업명·내용·규모·신청기한·핵심 조건을 정리하는 정적 사이트 (GitHub Pages).

## 매일 업데이트

Claude Code 에서:

```
/daily                # 마지막 실행 이후 공고 수집·정리 (대화형, 커밋은 승인 후)
/daily 2026-10-01     # 기준일 지정 (초기 적재·누락 보충)
/daily dry-run        # 자동 모드로 끝까지 하고 검증만 (커밋·푸시 안 함)
/daily auto           # 자동: 검증 통과 시 main 에 커밋·푸시
```

평일 07:00 KST 에 Claude Code 클라우드 루틴이 `/daily auto` 를 실행한다. 실행 기록은 claude.ai 의 루틴 화면, 또는 Claude Code 의 `/schedule` 로 확인·수정한다.

도구만 따로 쓰기:

```
python tools/collect.py --since 2026-10-15    # 후보 목록 (.cache/candidates.json)
python tools/extract_text.py page "<상세 URL>" # 상세 본문 + 첨부 URL
python tools/extract_text.py "<첨부 URL>"      # 공고문(hwp·hwpx·pdf·zip) 텍스트
python tools/check_notices.py                 # 발행 전 검증
```

나라장터 입찰 수집에는 공공데이터포털의 `조달청_나라장터 입찰공고정보서비스` 활용신청 후 받은 인증키를 환경 변수 `DATA_GO_KR_KEY` 로 넣어야 한다.

규칙은 [CLAUDE.md](CLAUDE.md), 소스는 [.claude/sources.md](.claude/sources.md), 절차는 [.claude/commands/daily.md](.claude/commands/daily.md).

## 로컬 확인

```
pip install olefile pypdf
python -m http.server 8000
```
http://localhost:8000 (file:// 로 열면 목록이 안 뜸)

## 배포

- GitHub Pages: Settings → Pages → Source `Deploy from a branch`, Branch `main` / `(root)`
- `main` 에 push 하면 1–2분 뒤 반영된다.
