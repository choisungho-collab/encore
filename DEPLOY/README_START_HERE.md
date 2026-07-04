# ENCORE 보안·업로드 개편 배포 (PENTA에서 이식한 1·2·3·4)

이 번들은 PENTA의 검증된 구조를 ENCORE 스키마에 맞춰 이식한 것.
| # | 내용 | 파일 |
|---|------|------|
| 1 | service_key 클라이언트에서 제거 (서명 업로드 프록시) | `netlify/functions/storage.js` + `RECORDER_PATCH.md` |
| 2 | repo에 보안·신원 SQL (스키마 드리프트 해결) | `2_RUN_SQL_IN_SUPABASE/01_identity.sql`, `02_security.sql` |
| 3 | 업로드 쿼터 + 에러 로그 (스팸/스토리지 폭탄 방어) | `2_RUN_SQL_IN_SUPABASE/03_ops_limits.sql` |
| 4 | env 기반 관리자(HMAC 세션) | `netlify/functions/admin.js` |

폴더:
- `1_PUSH_TO_REPO/`        → 레포에 병합(netlify.toml + netlify/functions/*)
- `2_RUN_SQL_IN_SUPABASE/` → SQL 3개 (번호순)
- `RECORDER_PATCH.md`      → sc_recorder.py 수정 안내

---

## ⚠ 배포 순서 — 반드시 이 순서 (안 지키면 업로드 잠깐 막힘)

**STEP 0. Netlify 환경변수 5개** (Site settings → Environment variables)
| 변수 | 값 |
|---|---|
| `SUPABASE_URL` | https://luljnalcnxfyxmlgoxbc.supabase.co |
| `SUPABASE_SERVICE_KEY` | Supabase → Settings → API → service_role 키 |
| `SUPABASE_BUCKET` | media |
| `ADMIN_ID` | 관리자 아이디 |
| `ADMIN_PW` | 관리자 비번 (`python -c "import secrets;print(secrets.token_urlsafe(24))"`) |

**STEP 1. 함수/설정 배포** — `1_PUSH_TO_REPO/` 를 레포에 병합 후 push.
- 확인: 주소창에 `https://encorestar.netlify.app/api/storage` → `{"error":"POST only"}` 뜨면 배포 OK.
- ⚠ `netlify.toml` 의 `publish` 가 실제 HTML 위치와 맞는지 확인(루트면 `.`, `web/`면 `web`).

**STEP 2. 01_identity.sql 실행** — 신원/세션 계층 생성.
- 확인: `select verify_device('없는사람','1234567890abcdef');` → `false`.

**STEP 3. 새 레코더 배포** — `RECORDER_PATCH.md` 적용해 빌드 → 유저에게 배포.
- 이유: 다음 STEP 의 02_security 가 anon 직접 업로드를 막으므로, **서명 업로드 되는 레코더가 먼저** 나가야 함.

**STEP 4. 02_security.sql 실행** — RLS 하드닝 + 등록 RPC + 삭제.
- 확인: `select policyname from pg_policies where tablename='matches';` → insert 정책 없어야 정상.

**STEP 5. 03_ops_limits.sql 실행** — 쿼터/에러 로그. (없어도 업로드는 되지만 제한이 안 걸림)

---

## 🔴 실행 전 꼭 확인할 것 (라이브 DB 대조)

ENCORE 신원 SQL은 원래 repo에 없었음 → 이 번들의 `01_identity.sql` 이 표준본.
**만약 라이브 Supabase에 이미 `identities`/`sessions`/`login_codes` 가 다른 컬럼 구조로 존재하면**,
`01_identity.sql` 을 그대로 돌리기 전에 컬럼을 대조하세요:
- 핵심 요구: `identities.device_secrets text[]` (기기 비밀키 sha256 해시 배열).
  이 컬럼이 없으면 `verify_device` 가 작동 안 함 → 서명 업로드 실패.
- `create table if not exists` 는 기존 테이블을 **바꾸지 않으므로**, 컬럼이 다르면
  수동으로 `alter table ... add column if not exists device_secrets text[] default '{}';` 후,
  기존 기기 해시를 채우는 마이그레이션이 필요할 수 있음.
- 처음부터 새로 세팅하는 경우엔 그냥 순서대로 돌리면 완결.

각 함수는 `create or replace` 라 RPC 시그니처가 같으면 덮어쓰기 안전.

---

## #4 관리자 — 남은 연결 한 스텝

`admin.js` 는 배포하면 바로 동작(`/api/admin`). 다만 **`admin.html` 이 지금은 기존
`encore-admin.sql` 의 RPC(admin_login/admin_whoami…)를 호출**하고 있을 것.
env 기반으로 전환하려면 admin.html 의 로그인/요청부를 아래처럼 바꾸면 됨:

```js
// 로그인
const r = await fetch('/api/admin', {method:'POST', headers:{'Content-Type':'application/json'},
  body: JSON.stringify({action:'login', id, pw})});
const {token} = await r.json();           // localStorage 에 저장
// 이후 모든 요청
const r2 = await fetch('/api/admin', {method:'POST',
  headers:{'Content-Type':'application/json','X-Admin-Token':token},
  body: JSON.stringify({action:'stats'})});   // stats/matches/delete-match/orphan-scan/orphan-clean/errors
```

전환이 부담되면 **당분간 기존 `encore-admin.sql` 관리자 유지**도 됨(단 `CHANGE_ME_비밀번호` 를
실제 값으로 꼭 바꿔서 Run). admin.html 개편은 원하면 이어서 도와줄게.

---

## 동작 요약 (개편 후)
- 녹화기 → `/api/storage`(기기검증+쿼터) → 서명 URL 받아 Storage 직접 PUT → `upload_match` RPC 로 등록.
- service_key 는 Netlify env 에만(storage.js/admin.js). 클라이언트·레코더엔 없음.
- 익명/타인은 남의 소유 경기 못 덮음. 스토리지 직접 업로드 차단(읽기만 공개).
- 기기당 업로드 쿼터로 스팸/용량폭탄 방어. 함수 에러는 error_log → 관리자에서 조회.
- 관리자: env ID/PW → 12h HMAC 세션, 삭제 시 스토리지 파일까지 제거, 고아 파일 정리.
