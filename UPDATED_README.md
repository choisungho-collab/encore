# ENCORE — 전체 프로젝트 (업데이트본)

이 zip = 레코더 + 백엔드 + **수정된 웹앱** + 배포 번들 전부.

## 폴더 구조
- `sc_recorder.py`, `config.json`, `START.bat` 등 — **데스크톱 레코더** (원본 그대로)
- `supabase/` — 기존 스키마
- `advanced/` — 레거시(OBS) 참고용
- `.github/`, `build.yml` — 빌드 워크플로우
- **`web/`** — **라이브 웹앱(수정 반영 완료)**. Netlify에 이 폴더를 배포. Ctrl+Shift+R로 캐시 무시.
- **`DEPLOY/`** — 보안/업로드 아키텍처 + 레코더 신뢰성 패치 (아래 참고)

## 이번에 바뀐 것 (web/)
1. **감독판(자동 시점 전환) 개선** — 컷 10→23개, 평균 세그 83초→36초. 판단주기·히스테리시스·최소세그 완화 + 지루함 방지 로직.
2. **클립 공유 딥링크** — 영상 우상단 "클립 공유" 버튼 → 현재 장면 타임스탬프(`?t=`) 링크 복사. 그 링크로 들어오면 해당 시점부터 재생.
3. **프레임 스텝** — `,` / `.` 키로 1프레임씩 (정지 후, 단일 시점).
4. **전체화면 자동숨김** — 2.6초 무동작 시 컨트롤바·커서 숨김.
5. **헤더 재설계(전 페이지)** — 모바일에서 ENCORE 좌상단 고정 + 햄버거 우측 이동, 서브메뉴를 전폭 드롭다운 → 우측 카드로.
6. 통계 반올림, 모바일 컨트롤바 줄바꿈/간결화 등.

## 레코더 패치는 "적용 안 된 드롭인" 상태
`sc_recorder.py`는 **원본 그대로** 두었다. 622KB 파일을 자동 편집하다 깨뜨리는 위험을 피하려고, 변경은 `DEPLOY/`의 문서형 드롭인으로 제공:
- `DEPLOY/RECORDER_PATCH.md` — 업로드를 서명 프록시(Netlify) + `upload_match` RPC로 전환
- `DEPLOY/RECORDER_PATCH_v2_reliability.md` — 원자적 JSON 저장 / 크래시 로그 / 인코더 NVENC→AMF→QSV→libx264 / ffmpeg 공유폴더
직접 복붙해 적용하면 됨. 각 패치는 독립적.

## 백엔드/보안 배포 순서
`DEPLOY/README_START_HERE.md` 참고. 요약: Netlify 환경변수 5개 → 함수 push → `01_identity.sql` → 새 레코더 → `02_security.sql` → `03_ops_limits.sql`.
(주의: 라이브 DB에 이미 identities/sessions가 다른 형태로 있으면 `01_identity.sql`을 그대로 돌리지 말 것.)
