---
description: 국가R&D·지원사업·SW입찰 공고를 수집해 data/notices.json 에 추가·갱신한다
argument-hint: "[YYYY-MM-DD 기준일 (생략 시 마지막 실행 전날)] [auto | dry-run]"
---

CLAUDE.md 의 규칙(선정 기준·데이터 규칙)을 따라 새 공고를 싣고 기존 공고를 갱신한다. 인자: `$ARGUMENTS`

**인자 해석** (순서 무관, 모두 생략 가능)
- `YYYY-MM-DD` → 수집 기준일(`collect.py --since`). 없으면 meta.json `last_run` 전날.
- 모드: 없음 = 대화형(커밋·푸시는 사용자 승인 후) / `auto` = 클라우드 루틴용, 묻지 않고 검증 통과 시 푸시 / `dry-run` = auto 와 같되 커밋·푸시 안 함.
- 오늘 = KST 날짜. `added`·`updated`·meta 에 쓰는 날짜는 모두 오늘(KST).

0. **준비**
   - (auto·dry-run) `git pull --rebase origin main`. 작업 트리가 깨끗하지 않으면 중단하고 보고한다.
   - `pip install -q olefile pypdf` (없을 때만).

1. **후보 수집**: `python tools/collect.py [--since 기준일]`
   - 소스별 결과 줄에 `ERROR` 가 있으면 보고에 적는다(나머지 소스로 계속). `g2b` 는 `DATA_GO_KR_KEY` 가 없으면 건너뛰는 게 정상이다.
   - `.cache/candidates.json` 의 `new` = 신규 후보, `known` = 이미 실린 공고(정정·연장 확인용).

2. **선별** (제목·기관·기간만으로 1차)
   - CLAUDE.md "선정 기준"에 맞지 않는 후보는 버린다. `[무관?]` 표시는 대부분 버리되 제목에 SW·AI 성격이 분명하면 상세를 본다.
   - `[중복? X]` 는 같은 사업의 다른 소스·트랙이다. 이미 실린 공고(X 가 notices.json id)면 그 공고의 `src_ids` 에 추가만 하고, 후보끼리면 하나로 묶는다.
   - `[정정?]` 은 기존 공고의 정정·연장·재공고일 수 있다. 기존 공고가 있으면 3단계 갱신으로 처리한다.
   - 남은 후보가 많으면 마감이 가까운 것, fit 이 높을 것 같은 것부터 처리한다. 한 번 실행에 **신규 최대 15건**. 못 다 본 후보는 다음 실행에서 다시 후보로 뜬다(실리지 않았으므로).

3. **확인·작성** (후보마다)
   - `python tools/extract_text.py page "<상세 URL>"` 로 본문과 첨부 목록을 본다.
   - 규모·자격·기한이 본문에 없으면 공고문 첨부를 읽는다: `python tools/extract_text.py "<첨부 URL>" --max 15000`. 서식·양식 파일은 건너뛴다.
     NTIS 상세의 `공고금액`·`접수마감시간` 은 정형 값이라 우선 참고하되 IRIS 공고문과 대조한다.
   - 공고문까지 보고 선정 기준에 맞지 않으면 버리고 사유를 보고에 남긴다.
   - CLAUDE.md "데이터 규칙"대로 항목을 만든다. `added`·`updated` = 오늘. 새 항목은 notices.json **배열 맨 앞**에.
   - 기존 공고 갱신(정정·연장·마감 변경·예산 변경): 해당 필드 수정, `updated` = 오늘, `note` 에 변경 한 줄. 새 소스 id 는 `src_ids` 에 추가. 순서(added)는 그대로.
   - 입찰(bid): 나라장터 상세에서 공고번호·추정가격·입찰마감·계약방법·대기업 참여제한·공동수급·제안설명회를 확인한다.

4. **정리**
   - 마감 후 60일 지난 공고를 `data/archive/<마감 연도>.json` 으로 옮긴다(파일이 없으면 `[]` 로 만든다).
   - `data/meta.json`: `{"last_run": "<오늘>T<지금 HH:MM>+09:00", "new": <신규 수>, "updated": <갱신 수>}`.
     신규·갱신이 0건이어도 last_run 은 갱신한다(다음 실행의 수집 기준).

5. **검증·커밋**
   - `python tools/check_notices.py` — FAIL 은 고치거나 그 항목을 뺀다. 링크 WARN(403·접속 불가)은 WebFetch 로 존재를 확인한다.
   - auto: PASS 일 때만 커밋·푸시. 실패하면 되돌리고(`git checkout -- data/ && git clean -fd data/`) 사유를 보고한다.
     ```
     git add data/
     git commit -m "Content: MM.DD 공고 업데이트 (신규 N, 갱신 M, auto)" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
     git push origin HEAD:main  # 거부되면 git pull --rebase origin main 후 1회 재시도
     ```
   - 대화형: 변경 요약을 보여주고 승인 후 커밋·푸시.

6. **보고**: 신규 공고(유형·제목·기관·규모·마감·fit), 갱신 공고(무엇이 바뀌었나), 버린 후보 중 애매했던 것과 이유, 소스 ERROR, 다음 실행으로 넘긴 후보 수, check_notices 결과, (auto) 커밋 해시와 사이트 URL(https://lspace-next.github.io/BizRadar/).
