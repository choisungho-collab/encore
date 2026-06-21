# 리플레이 캐스트 — 스타크래프트 자동 녹화·분석·아카이브

스타 켜두면 경기가 **실제 HD로 자동 녹화**되고, 끝나면 **빌드오더까지 분석**돼서
한 곳(웹 갤러리)에 모입니다. OBS 필요 없음. NVIDIA NVENC 하드웨어 인코딩.

## 빠른 시작 (혼자 쓰기)
1. 압축을 풉니다.
2. **START.bat** 더블클릭.
3. 브라우저에 갤러리가 열립니다. 스타 켜고 게임하면 끝 — 판마다 자동 등록.

> 첫 실행 때 ffmpeg와 리플레이 분석기를 자동으로 받아옵니다. 콘솔 창은 켜둔 채로.

## 화면 구성 (하나의 서버에 통합)
| 주소 | 내용 |
|------|------|
| `/`           | **메인 — 전술 방송 갤러리** (스타 영상, 첫 화면) |
| `/match/<id>` | 매치 분석 — 플레이어 클릭 → 빌드오더·유닛·APM |
| `/get`        | 설치/다운로드 안내 화면 |
| `/manual`     | 전체 메뉴얼 |
| `/app.zip`    | 프로그램 다운로드 (서버가 자기 자신을 압축해 배포) |

갤러리 상단 **"프로그램 받기"** 버튼 → `/get` → 다운로드. 친구는 호스트의
`http://<IP>:<포트>/get` 에서 바로 받아갈 수 있습니다.

## 친구들과 같이 모으기 (중앙 서버)
**호스트** — config.json:  { "mode": "server", "port": 8000 }
실행하면 콘솔에 접속 주소와 업로드 키(upload_key)가 표시됩니다.

**참가자** — config.json:
{ "mode": "recorder", "username": "내이름",
  "server": { "url": "http://호스트IP:8000", "api_key": "호스트가_알려준_키" } }
저장 후 실행 → 게임 끝날 때마다 중앙 서버로 업로드(끊기면 자동 재전송).

자세한 설정·문제 해결(검은 화면 등)은 실행 후 `/manual` 참고.

## 모드
- all (기본) — 이 PC에서 녹화 + 갤러리
- server — 갤러리만 운영(중앙 호스트)
- recorder — 녹화 후 중앙 서버로 업로드

## 확장 / 운영
- 인덱스는 SQLite(data/matches.db) — 동시 업로드 안전, 페이지네이션
- 경기 많이 쌓을 거면 호스트에서  pip install waitress  (자동 사용)
- 영상은 용량이 큽니다. 디스크 여유를 두세요.

## 요구 사항
Windows 10/11 · NVIDIA GeForce 권장 · Python 3.9+ · StarCraft: Remastered

---
팬이 만든 비공식 커뮤니티 프로젝트. StarCraft / Brood War 는 Blizzard Entertainment, Inc.
의 상표이며 본 프로젝트는 Blizzard 와 무관합니다.

## 영상 저장을 Cloudflare R2로 (권장: 용량/전송비)
영상은 크고 전송비가 핵심이라, **호스트(server 모드)** 에 R2를 연결하면 영상은
서버를 거치지 않고 R2로 직접 올라가고(클라이언트 → R2), 재생도 R2 CDN에서 바로 됩니다.
전송(egress) 무료라 사실상 저장비(약 $0.015/GB)만 듭니다. (R2 미설정 시 기존 로컬 저장으로 동작)

### Cloudflare 쪽 (한 번)
1. Cloudflare 대시보드 → R2 → 버킷 생성 (예: `sc-replays`)
2. R2 → "Manage API Tokens" → Object Read & Write 토큰 발급
   → **Account ID, Access Key ID, Secret Access Key** 확보
3. 공개 재생용 주소: 버킷 Settings → 커스텀 도메인 연결(권장) 또는 r2.dev 개발 URL
   → 이 주소가 `public_base_url` (예: `https://media.내도메인.com`)

### 호스트 config.json (server 모드 PC 에만)
```json
"r2": {
  "account_id": "xxxxxxxx",
  "bucket": "sc-replays",
  "access_key_id": "xxxx",
  "secret_access_key": "xxxx",
  "public_base_url": "https://media.내도메인.com"
}
```
- 클라이언트(recorder)는 **R2 키가 필요 없습니다** — 서버에서 1회용 업로드 주소(presigned URL)를
  받아 영상을 R2로 직접 PUT 합니다. (server.api_key 만 있으면 됨)
- 동작: 녹화기 → `/api/presign`(주소 발급) → 영상 R2로 직접 PUT → `/api/register`(작은 .rep+메타만 서버로)
  → DB엔 R2 영상 URL 저장 → 갤러리에서 R2에서 바로 재생.
- 첫 R2 사용 시 호스트에 boto3가 자동 설치됩니다.

### 용량 팁
- 녹화 화질/해상도/fps를 낮추면 한 판 용량이 확 줄어요(config `fps`, 추후 해상도 옵션).
- `.rep`(아주 작음)은 계속 보관, 영상은 오래된 건 R2에서 주기적으로 정리하면 저장비도 최소화.
