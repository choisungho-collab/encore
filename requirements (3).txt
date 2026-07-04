# GitHub Actions 로 윈도우 EXE 자동 빌드

코드를 GitHub에 올리면 윈도우용 `sc_recorder.exe` 가 자동으로 만들어집니다.
(파이썬 없이 더블클릭만으로 실행되는 단일 exe)

## 1. 레포 만들기
1. github.com 로그인 → 우상단 **New repository** → 이름(예: `sc-replay-recorder`) → Private 가능 → Create

## 2. 파일 올리기 (둘 중 하나)
**A. 웹 업로드(쉬움)**: 레포 페이지 → **Add file → Upload files** →
이 폴더 전체(`sc_recorder.py`, `web/`, `requirements.txt`, `.github/`, `README.md`, `START.bat` …)를 드래그 → Commit.

**B. git 명령**:
```
git init
git add .
git commit -m "init"
git branch -M main
git remote add origin https://github.com/<아이디>/<레포>.git
git push -u origin main
```

## 3. 자동 빌드
- `main` 에 올리면 **Actions** 탭에서 빌드가 바로 돌아요(윈도우, 1~2분).
- 끝나면 해당 실행 페이지 하단 **Artifacts → `sc_recorder-windows`** 다운로드 → 압축 풀면 `sc_recorder.exe`.
  - (Artifacts 는 로그인해야 받음 — 내가 테스트용으로 받을 때 사용)

## 4. 친구 배포용 공개 링크 = "릴리스"
공개 다운로드 주소를 만들려면 **버전 태그**를 올리세요:
```
git tag v1.0
git push --tags
```
→ 자동으로 **Releases** 에 `sc_recorder.exe` 가 첨부됩니다. 그 링크를 공유하거나 Netlify 의 다운로드 버튼에 연결하면 끝.

## 5. 사용자
`sc_recorder.exe` 받아서 더블클릭 → (파이썬 불필요) 갤러리가 열리고 녹화 시작.
처음 실행 때 ffmpeg 를 exe 옆에 자동으로 받아옵니다.

## 참고
- 단일 exe(`--onefile`)는 첫 실행 시 백신/SmartScreen 경고가 뜰 수 있어요 → **추가 정보 → 실행**.
  완전히 없애려면 코드 서명 인증서가 필요. 오탐이 잦으면 워크플로의 `--onefile` 을 `--onedir`(폴더형) 로 바꾸면 줄어듭니다.
- `data/`, `config.json`, `ffmpeg.exe` 는 exe 와 같은 폴더에 생기니, **쓰기 가능한 폴더**(바탕화면/다운로드 등, Program Files 말고)에 두세요.
