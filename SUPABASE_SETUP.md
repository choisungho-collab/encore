# Supabase 클라우드 세팅 (R2 없이, Supabase 하나로)

> 영상·썸네일·.rep 는 **Supabase Storage**, 메타+분석+댓글+좋아요는 **Supabase Postgres**.
> 한 곳에서 다 끝. 업데이트(새 폴더에 압축 해제)해도 **클라우드라서 자료가 안 날아감.**

준비물: Supabase 프로젝트 하나(이미 `VEAT` 있음). Cloudflare R2 / CLI / Netlify **필요 없음.**

---

## 1. DB 테이블 만들기  (1분)
1. Supabase 대시보드 → 프로젝트 **VEAT** 열기
2. 좌측 **SQL Editor** → `supabase/schema.sql` 내용 전체 복사해서 붙여넣기 → **Run**
   → `matches`, `comments` 테이블 + 좋아요/조회수 함수 + 읽기 권한(RLS) 생성됨.

## 2. 영상 저장소(버킷) 만들기  (30초)
1. 좌측 **Storage** → **New bucket**
2. 이름: **`media`**  → **Public bucket** 켜기(공개) → Create
   - 공개로 해야 갤러리에서 영상이 바로 재생/다운로드됩니다.

## 3. 키 3개 복사  (30초)
좌측 **Project Settings → API** 에서:
- **Project URL**     (예: `https://wjnmrdewdhxfbqsheeiv.supabase.co`)
- **anon public** 키   (공개되어도 되는 읽기용 키)
- **service_role** 키  (비공개 — 영상 업로드/경기 등록용. 절대 공개 X)

## 4. config.json 채우기
exe(또는 sc_recorder.py) 옆 `config.json` 의 `supabase` 블록:
```json
{
  "username": "Mongjungguy",
  "supabase": {
    "url": "https://<프로젝트>.supabase.co",
    "anon_key": "eyJ... (anon public)",
    "service_key": "eyJ... (service_role)",
    "bucket": "media"
  }
}
```
- 이 블록을 채우면 **자동으로 클라우드 모드**로 켜집니다(비우면 기존처럼 로컬).
- 갤러리가 Supabase 에서 읽고, 게임이 끝나면 영상+분석이 Supabase 로 올라갑니다.

## 5. 잘 됐는지 확인
프로그램 실행 → 갤러리 열림 → 한 판 하고 끝나면 상태창 로그에
`☁ Supabase 등록: ...` 이 뜨면 성공. 새로고침하면 갤러리에 카드가 보입니다.

빠른 점검(터미널, 키는 본인 것으로):
```bash
curl "https://<프로젝트>.supabase.co/rest/v1/matches?select=id&limit=1" \
  -H "apikey: <anon_key>" -H "Authorization: Bearer <anon_key>"
```
→ `[]` 또는 `[{"id":...}]` 가 오면 DB 연결 정상.

---

### 보안 메모 (중요)
- 지금 방식은 **service_role 키를 각 PC config 에 넣는 방식**이라, 본인/믿는 크루끼리 쓰기엔 충분하지만
  키가 있으면 DB 전체에 접근 가능합니다. **config.json 을 남한테 공유하거나 공개 깃허브에 올리지 마세요.**
- 크루 여러 명에게 배포할 땐 service 키를 숨기는 **Edge Function 방식**(`CLOUD_SETUP.md`)이 더 안전합니다.
  원하면 그 방식으로도 만들어 드릴게요.

### 영상 용량
- 14분 게임 ≈ 1.8GB. Supabase Pro Storage 기본 100GB → 50~55판 정도.
- 다 채우면 오래된 영상은 Storage 에서 지우고(메타/분석은 남김) 관리하거나, 용량 더 큰 플랜으로.
- "특별한 판만 올리고 싶다" 같은 옵션도 추가 가능.
