# 수집 소스

`/daily` 수집 단계에서 쓰는 소스와 접근 방법. 목록 수집은 `tools/collect.py` 가 하고, 상세·공고문 확인은 `tools/extract_text.py` 로 한다.
2026-10-20 기준 동작 확인. 소스를 추가·변경하면 이 파일, `collect.py` 의 `SOURCES`, `assets/js/main.js` 의 `SOURCES`(화면 수집 현황), 아래 허용 도메인을 함께 고친다.

| 이름(--only) | 유형 | 소스 | 목록 | 상세·첨부 |
|---|---|---|---|---|
| `ntis` | rnd | NTIS 국가R&D통합공고 | POST `https://www.ntis.go.kr/rndgate/eg/un/ra/mng.do` (`pageIndex`, `pageUnit=100`). 등록순, 마감 섞임 | `view.do?roRndUid=<id>` — **공고금액(억원)·접수마감시간**이 정형으로 있음. 본문은 "IRIS 에서 확인" 인 경우가 많다 |
| `iris` | rnd | IRIS 범부처통합연구지원시스템 | POST `https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituList.do` (`ancmPrg=ancmIng`·`ancmPre`, `pageIndex`) → JSON. 접수예정은 페이지당 10초+ | `retrieveBsnsAncmView.do?ancmId=<id>` 본문 + 첨부(`/comm/file/fileDownload.do?atchDocId=&atchFileId=`, GET 으로 받아짐). **공고문 hwp/hwpx 에 과제목록·지원규모·자격** |
| `bizinfo` | support | 기업마당 지원사업 | GET `https://www.bizinfo.go.kr/sii/siia/selectSIIA200View.do?rows=15&cpage=<n>&schEndAt=N` (15건 고정, 등록일 최신순) | `selectSIIA200Detail.do?pblancId=<id>` — 사업개요·신청방법 본문, 첨부 `/cmm/fms/fileDown.do?...`. R&D 공고도 섞여 있으니 NTIS/IRIS 와 중복 확인 |
| `nipa` | support | NIPA 정보통신산업진흥원 사업공고 | GET `https://www.nipa.kr/home/2-2?curPage=<n>` | `https://www.nipa.kr/home/2-2/<id>` |
| `rims` | support·bid | 중소조선연구원 (부산, 조선·해양 주력 분야) | GET `https://www.rims.re.kr/bbs/board.php?bo_table=m0602`(사업공고)·`m0605`(입찰공고). 그누보드, 날짜 `MM-DD`(올해)·`YY-MM-DD`. **키워드 필터 없이 전부 후보**. 전체 브라우저 UA 는 403 → 짧은 `Mozilla/5.0` 로 재시도(collect·extract 가 자동 처리) | `board.php?bo_table=m0602&wr_id=<id>` — 본문이 비고 첨부(`download.php`)만 있는 경우가 많다. 마감일은 제목 `(~26.10.08)` 또는 첨부 공고문 |
| `btp` | support·bid | 부산테크노파크 사업공고 (부산) | GET `https://www.btp.or.kr/kor/CMS/Board/Board.do?robot=Y&mCode=MN013&page=<n>`. 표 행에 접수기간·등록일. 제목에 입찰·용역이 있으면 bid | `Board.do?mCode=MN013&mode=view&mgr_seq=<m>&board_seq=<id>` 본문 + 첨부 |
| `gntp` | support·bid | 경남테크노파크 지원사업신청 (경남) | POST `https://www.gntp.or.kr/biz/apply2` JSON `{"pageIndex":"<n>"}` → HTML(`#gridData`). 게시일이 없어 **접수시작일**로 거르고 접수마감 건은 뺀다. 마감 시각은 `extra.end_time` | `https://www.gntp.or.kr/biz/applyInfo/<id>` 본문 + 첨부(`/dextnj/streamDownload?fileAttachNo=`) |
| `ccei_bs` | support·bid | 부산창조경제혁신센터 | POST `https://ccei.creativekorea.or.kr/busan/custom/noticeList.json`(공지사항 — 부산은 사업공고를 여기 올림)·`allim/allimList.json`(`div_code=2` 입찰공고), 폼 `pn=<n>&pagePerContents=8` → JSON `result.list` (SEQ·TITLE·REG_DATE). 협의회 공통 공지(채용 등)가 섞여 있다 | `custom/notice_view.do?no=<SEQ>` / `allim/allim_view.do?no=<SEQ>&div_code=2` |
| `ccei_gn` | support·bid | 경남창조경제혁신센터 | POST `https://ccei.creativekorea.or.kr/gyeongnam/allim/allimList.json` `div_code=1`(사업공고)·`2`(입찰공고). 사업공고에 `TABLE_TITLE=notice` 인 협의회 공지가 섞이면 `custom/notice_view.do` 로 연결 | `allim/allim_view.do?no=<SEQ>&div_code=<d>` |
| `g2b` | bid | 나라장터 용역 입찰공고 | 공공데이터포털 `조달청_나라장터 입찰공고정보서비스` `getBidPblancListInfoServc` (`inqryDiv=1`, `inqryBgnDt/EndDt=YYYYMMDDHHMM`, `type=json`). **환경 변수 `DATA_GO_KR_KEY` 필요** — 없으면 건너뜀 | 응답의 `bidNtceDtlUrl`(나라장터 상세). 제안요청서는 상세의 첨부 |

키가 없을 때 나라장터 보완: WebSearch `site:g2b.go.kr 소프트웨어 개발 용역 입찰공고` 또는 조달청 보도자료. 입찰 건은 반드시 나라장터 상세에서 공고번호·마감·추정가격을 확인한다.

### 참고 (수동 확인용, collect.py 미포함)
| 소스 | URL | 비고 |
|---|---|---|
| IITP 사업공고 | https://www.iitp.kr/kr/1/business/businessNotice/list.it | ICT R&D 전문기관 — 대부분 IRIS 에도 올라옴 |
| NIA 사업공고 | https://www.nia.or.kr/site/nia_kor/ex/bbs/List.do?cbIdx=78336 | 데이터·디지털플랫폼정부 사업 (용역은 나라장터) |
| SMTECH 중기부 R&D | https://www.smtech.go.kr/front/ifg/no/notice02_list.do | 중소기업 R&D — IRIS 이관분 다수 |
| K-Startup | https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do | 창업 지원 — 대부분 선정 기준 밖 |
| KEIT 산업기술 R&D | https://srome.keit.re.kr/ | 산업부 R&D — IRIS 에도 올라옴 |

## 지역 (collect.py `HOME_REGIONS` / `OTHER_REGIONS`)

전국 공고와 부산·경남만. 제목 머리 `[지역]` 이 부산·경남이 아니면(서울·경기·대구·울산·충남 등) 후보에서 빠지고 보고 줄에 "타 지역 N건 제외" 로 나온다.
머리표 없이 제목에 다른 지역명이 있으면 `[지역? 대구]` 로 표시만 하니 공고문의 주관기관 소재 요건을 확인한다.

## 키워드 (collect.py `KEYWORDS` / `OFF_TOPIC`)

- 포함: 소프트웨어·SW·인공지능·AI·AX·LLM·생성형·데이터·빅데이터·클라우드·SaaS·플랫폼·정보시스템·정보화·시스템 구축·고도화·전산·ICT·IT·디지털·디지털트윈·DX·메타버스·보안·사이버·블록체인·자율·로봇·스마트공장/스마트제조/스마트시티·알고리즘·지능형·XR·IoT·5G/6G·양자·SI·솔루션·모바일·전자정부·공공데이터·마이데이터·조선·선박·해양·자율운항·스마트야드·기자재
- 무관 표시(후보에는 남기고 `[무관?]` 표시): 의약·신약·임상·농식품·축산·수산·산림·관광·경영안정자금·융자·보증·전시회·박람회·엑스포·인력교류·장학·채용·입점·판로·물류비·측정기기·상담회·품질인증
- 키워드가 놓친 공고가 의심되면 `python tools/collect.py --all --only <소스>` 로 전체를 훑어 보고 KEYWORDS 를 고친다.

## 클라우드 루틴 네트워크 허용 목록

루틴 환경은 네트워크 접근 **Custom** + "Also include default list". 실제 적용은 claude.ai/code 환경 설정의 Allowed domains 에서 하고, 이 목록은 참고용 사본이다.

```
*.kr
*.creativekorea.or.kr
*.go.kr
*.or.kr
*.re.kr
apis.data.go.kr
github.com
*.github.com
*.githubusercontent.com
pypi.org
files.pythonhosted.org
```

환경 변수(루틴 환경 설정): `DATA_GO_KR_KEY` = 공공데이터포털 일반 인증키(Decoding 아닌 **Encoding** 키를 그대로).
