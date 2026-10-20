# 수집 소스

`/daily` 수집 단계에서 쓰는 소스와 접근 방법. 목록 수집은 `tools/collect.py` 가 하고, 상세·공고문 확인은 `tools/extract_text.py` 로 한다.
2026-10-20 기준 동작 확인. 소스를 추가·변경하면 이 파일, `collect.py` 의 `SOURCES`, 아래 허용 도메인을 함께 고친다.

| 이름(--only) | 유형 | 소스 | 목록 | 상세·첨부 |
|---|---|---|---|---|
| `ntis` | rnd | NTIS 국가R&D통합공고 | POST `https://www.ntis.go.kr/rndgate/eg/un/ra/mng.do` (`pageIndex`, `pageUnit=100`). 등록순, 마감 섞임 | `view.do?roRndUid=<id>` — **공고금액(억원)·접수마감시간**이 정형으로 있음. 본문은 "IRIS 에서 확인" 인 경우가 많다 |
| `iris` | rnd | IRIS 범부처통합연구지원시스템 | POST `https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituList.do` (`ancmPrg=ancmIng`·`ancmPre`, `pageIndex`) → JSON. 접수예정은 페이지당 10초+ | `retrieveBsnsAncmView.do?ancmId=<id>` 본문 + 첨부(`/comm/file/fileDownload.do?atchDocId=&atchFileId=`, GET 으로 받아짐). **공고문 hwp/hwpx 에 과제목록·지원규모·자격** |
| `bizinfo` | support | 기업마당 지원사업 | GET `https://www.bizinfo.go.kr/sii/siia/selectSIIA200View.do?rows=15&cpage=<n>&schEndAt=N` (15건 고정, 등록일 최신순) | `selectSIIA200Detail.do?pblancId=<id>` — 사업개요·신청방법 본문, 첨부 `/cmm/fms/fileDown.do?...`. R&D 공고도 섞여 있으니 NTIS/IRIS 와 중복 확인 |
| `nipa` | support | NIPA 정보통신산업진흥원 사업공고 | GET `https://www.nipa.kr/home/2-2?curPage=<n>` | `https://www.nipa.kr/home/2-2/<id>` |
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

## 키워드 (collect.py `KEYWORDS` / `OFF_TOPIC`)

- 포함: 소프트웨어·SW·인공지능·AI·AX·LLM·생성형·데이터·빅데이터·클라우드·SaaS·플랫폼·정보시스템·정보화·시스템 구축·고도화·전산·ICT·IT·디지털·디지털트윈·DX·메타버스·보안·사이버·블록체인·자율·로봇·스마트공장/스마트제조/스마트시티·알고리즘·지능형·XR·IoT·5G/6G·양자·SI·솔루션·모바일·전자정부·공공데이터·마이데이터
- 무관 표시(후보에는 남기고 `[무관?]` 표시): 의약·신약·임상·농식품·축산·수산·산림·관광·경영안정자금·융자·보증·전시회·박람회·엑스포·인력교류·장학·채용·입점·판로·물류비·측정기기·상담회·품질인증
- 키워드가 놓친 공고가 의심되면 `python tools/collect.py --all --only <소스>` 로 전체를 훑어 보고 KEYWORDS 를 고친다.

## 클라우드 루틴 네트워크 허용 목록

루틴 환경은 네트워크 접근 **Custom** + "Also include default list". 실제 적용은 claude.ai/code 환경 설정의 Allowed domains 에서 하고, 이 목록은 참고용 사본이다.

```
*.kr
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
