# 클라우드(서버리스) 셋업 — Supabase + Cloudflare R2

상시 켜두는 서버 없이: **영상·썸네일·.rep 는 R2**, **메타+분석+댓글은 Supabase(Postgres)**.
녹화기는 리플레이를 로컬에서 분석한 뒤 R2로 직접 올리고, 작은 메타+분석만 Edge Function 으로 보냅니다.

준비물: Supabase 프로젝트, Cloudflare 계정(R2), 그리고 Supabase CLI.

---

## 1. Supabase — DB 만들기
1. supabase.com 에서 프로젝트 생성(이미 있으면 그대로 사용).
2. 좌측 **SQL Editor** → `supabase/schema.sql` 내용 붙여넣고 **Run**.
   → `matches`, `comments` 테이블 + 인덱스 + 좋아요/조회수 함수가 생성됨.
3. **Project Settings → API** 에서 다음을 메모:
   - `Project URL`  (예: `https://abcd.supabase.co`)
   - `anon` 키 (프론트엔드가 읽기에 사용 — 공개되어도 되는 키)

## 2. Cloudflare R2 — 저장소 만들기
1. 대시보드 → **R2** → 버킷 생성 (예: `sc-replays`).
2. **R2 → Manage R2 API Tokens** → Object Read & Write 토큰 발급 →
   - **Account ID**, **Access Key ID**, **Secret Access Key** 확보.
3. 공개 재생 주소: 버킷 **Settings → Public access → Custom Domain** 연결(권장) 또는 r2.dev 개발 URL.
   - 이 주소가 `R2_PUBLIC_BASE_URL` (예: `https://media.내도메인.com`)
4. CORS 는 필요 없음 (데스크톱 녹화기 업로드 + `<video>` 재생 모두 CORS 불필요).

## 3. Supabase Edge Function — presign + register 배포
```bash
npm i -g supabase             # 또는 brew install supabase/tap/supabase
supabase login
supabase link --project-ref <프로젝트ref>     # 대시보드 URL 의 그 ref

# R2 관련 시크릿만 설정 (SUPABASE_URL / SERVICE_ROLE_KEY 는 자동 주입됨)
supabase secrets set \
  UPLOAD_KEY=원하는_긴_랜덤문자열 \
  R2_ACCOUNT_ID=xxxx \
  R2_BUCKET=sc-replays \
  R2_ACCESS_KEY_ID=xxxx \
  R2_SECRET_ACCESS_KEY=xxxx \
  R2_PUBLIC_BASE_URL=https://media.내도메인.com

# 함수 배포 (우리 키로 인증하므로 JWT 검증 끔)
supabase functions deploy ingest --no-verify-jwt
```
배포되면 함수 URL 이 나옵니다: `https://<프로젝트ref>.supabase.co/functions/v1/ingest`

### 빠른 점검
```bash
curl -X POST https://<ref>.supabase.co/functions/v1/ingest \
  -H "content-type: application/json" \
  -d '{"key":"위에_정한_UPLOAD_KEY","action":"presign"}'
```
→ `video_put`, `video_url` … 가 들어있는 JSON 이 오면 성공.

## 4. 녹화기(클라이언트) 설정
각 PC 의 `config.json` (exe 옆) 에:
```json
{
  "mode": "recorder",
  "username": "본인_게임아이디",
  "cloud": {
    "function_url": "https://<ref>.supabase.co/functions/v1/ingest",
    "upload_key": "위에_정한_UPLOAD_KEY"
  },
  "gallery_url": "https://내사이트.netlify.app"
}
```
- 클라이언트는 **R2 키도, Supabase service 키도 필요 없음** — `upload_key` 만.
- 실행하면: 게임 끝날 때마다 → 로컬 분석 → 영상·썸네일·.rep 를 R2로 직접 → 메타+분석을 함수로 → Supabase 에 저장.
- `gallery_url` 을 넣으면 시작 시 그 사이트(아래 4번째 단계의 Netlify 프론트)를 열어줍니다.

## 5. (다음 단계) Netlify 프론트엔드
갤러리/매치 분석/프로필을 Supabase 에서 읽어와 R2 영상을 보여주는 정적 사이트.
`anon` 키로 `matches`/`comments` 를 읽고, 댓글/좋아요는 그대로 Supabase 에 기록.
→ 이건 별도로 만들어 드립니다.

---

### 흐름 요약
```
녹화기(PC)
  ├─ 로컬에서 .rep 분석 (screp)
  ├─ Edge Function /ingest  (action:presign)  → R2 업로드 URL 3개
  ├─ 영상·썸네일·.rep  →  R2  (직접 PUT)
  └─ Edge Function /ingest  (action:register) → Supabase matches 에 행 저장
Netlify(정적)  →  Supabase 읽기 + R2 영상 임베드  →  갤러리/분석/프로필
```
상시 서버 0. 비용 ≈ R2 저장비(전송 무료) + Supabase/Netlify 무료 티어.
