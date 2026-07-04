# RECORDER_PATCH v2 — 신뢰성 패턴 (sc_recorder.py)

PENTA 레코더에 있던 안정성 장치를 ENCORE로 이식. **RECORDER_PATCH.md(업로드 프록시)와 별개로 추가**해도 되고, 같이 넣어도 됨.
아래 4개는 서로 독립적이라 원하는 것만 골라 넣어도 작동함.

확인된 현황:
- 없음 → **추가**: ① 원자적 JSON 저장, ② 글로벌 크래시 로그
- 부분 → **개선**: ③ 인코더 폴백에 AMD(amf)·Intel(qsv) 추가, ④ ffmpeg 공유폴더(업데이트 시 재다운로드 방지)
- ⑤ 레코더→아카이브 자동로그인 = **이미 구현됨**. `01_identity.sql`만 돌리면 작동 (별도 코드 불필요).

---

## ① 원자적 JSON 저장 (파일 깨짐 방지)

config.json / device_secret / identity / pending.json 이 지금은 `json.dump(x, open(path,"w"))` 라
쓰는 도중 크래시·정전이면 **파일이 반쯤 써져 깨진다**. 임시파일→fsync→os.replace 로 바꾼다.

**(A) 상단(임포트 근처)에 헬퍼 추가:**

```python
def _atomic_write_json(path, obj, **kw):
    """임시파일에 쓰고 fsync 후 os.replace — 도중 크래시/정전에도 파일이 깨지지 않음."""
    kw.setdefault("ensure_ascii", False)
    d = os.path.dirname(path) or "."
    try: os.makedirs(d, exist_ok=True)
    except Exception: pass
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, **kw)
        f.flush()
        try: os.fsync(f.fileno())
        except Exception: pass
    os.replace(tmp, path)
```

**(B) 아래 4곳 교체** (라인번호는 대략, 문자열로 찾아 바꾸면 됨):

```python
# ~L233  save_config
- json.dump(cfg, open(CONFIG_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
+ _atomic_write_json(CONFIG_PATH, cfg, indent=2)

# ~L240  device_secret 저장
- json.dump({"service_key": _sk}, open(_secret, "w", encoding="utf-8"))
+ _atomic_write_json(_secret, {"service_key": _sk})

# ~L1250 identity 저장
- json.dump(st, open(_ID_FILE, "w", encoding="utf-8"), ensure_ascii=False)
+ _atomic_write_json(_ID_FILE, st)

# ~L2457 pending 큐 저장
- def _save_pending(q): json.dump(q, open(PENDING_PATH, "w", encoding="utf-8"))
+ def _save_pending(q): _atomic_write_json(PENDING_PATH, q)
```

> index.json 등 다른 `json.dump(..., open(...,"w"))` 가 더 있으면 동일하게 `_atomic_write_json`으로.

---

## ② 글로벌 크래시 로그

지금은 백그라운드 스레드에서 죽으면 흔적이 안 남아 원인 파악이 어렵다.
메인/스레드 예외를 모두 `crash.log`에 남긴다.

**상단(DATA_DIR 정의 이후 아무 곳)에 추가:**

```python
import traceback, threading   # 이미 임포트돼 있으면 중복돼도 무해
CRASH_LOG = os.path.join(DATA_DIR, "crash.log")

def _write_crash(kind, exc_type, exc, tb):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(CRASH_LOG, "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 60 + "\n")
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {kind}\n")
            f.write("".join(traceback.format_exception(exc_type, exc, tb)))
    except Exception:
        pass

_prev_excepthook = sys.excepthook
def _excepthook(exc_type, exc, tb):
    _write_crash("MAIN THREAD", exc_type, exc, tb)
    _prev_excepthook(exc_type, exc, tb)
sys.excepthook = _excepthook

def _thread_excepthook(args):
    _write_crash(f"THREAD {getattr(args, 'thread', None)}",
                 args.exc_type, args.exc_value, args.exc_traceback)
try:
    threading.excepthook = _thread_excepthook   # Python 3.8+
except Exception:
    pass
```

`%USERPROFILE%\ReplayCast\data\crash.log` 에 쌓임. 문제 생기면 이 파일 보면 됨.

---

## ③ 인코더 폴백에 AMD(amf) · Intel(qsv) 추가

현재 `_encoder_args()`는 **NVENC → libx264** 2단계뿐이라, AMD/Intel GPU 유저는 하드웨어를 못 쓰고 바로 소프트웨어로 떨어진다.
**NVENC → AMF → QSV → libx264** 로 바꾼다 (각 후보를 720p로 실제 인코딩 테스트해서 되는 걸 채택).

**`_encoder_args()` 함수 전체를 교체** (기존 함수 통째로 지우고 아래로):

```python
def _encoder_args():
    """인코더 자동 선택. HW 인코더(NVENC/AMF/QSV)는 '실제로 인코딩 되는지'까지 테스트 —
       목록엔 있어도 런타임 실패면 다음 후보로, 최종적으로 libx264(소프트웨어)."""
    global _ENC_CACHE, _ENC_IS_SW
    if _ENC_CACHE is not None: return _ENC_CACHE
    pref = (CFG.get("encoder") or "auto").lower()
    if _ENC_FORCE_SW: pref = "x264"   # 런타임 폴백 발동 시 사용자 설정보다 우선
    have = ""
    try:
        have = _run([FFMPEG, "-hide_banner", "-encoders"],
                    capture_output=True, text=True, timeout=15).stdout or ""
    except Exception: pass

    def _hw_ok(codec):
        # 초소형 해상도는 HW 인코더가 거부할 수 있어 720p로 테스트.
        try:
            r = _run([FFMPEG, "-hide_banner", "-loglevel", "error",
                      "-f", "lavfi", "-i", "color=c=black:s=1280x720:r=30:d=1",
                      "-c:v", codec, "-pix_fmt", "yuv420p", "-f", "null", "-"],
                     capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                errs = [l for l in (r.stderr or "").splitlines() if l.strip()]
                if errs: log(f"  {codec} error: " + "  /  ".join(errs[-2:]))
                return False
            return True
        except Exception as e:
            log(f"  {codec} test exception: {e}")
            return False

    try: _gop = max(15, int(round(2 * float(CFG.get("fps", FPS) or FPS))))
    except Exception: _gop = 60

    def _nvenc(): return ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "22", "-g", str(_gop)]
    def _amf():   return ["-c:v", "h264_amf", "-quality", "balanced", "-rc", "cqp",
                          "-qp_i", "22", "-qp_p", "22", "-g", str(_gop)]
    def _qsv():   return ["-c:v", "h264_qsv", "-preset", "fast", "-global_quality", "23", "-g", str(_gop)]
    def _sw():
        preset = (CFG.get("preset") or "auto").lower()
        if preset in ("auto", ""): preset = "superfast"   # 소프트웨어는 게임 끊김 방지 위해 가벼운 프리셋
        args = ["-c:v", "libx264", "-preset", preset, "-crf", "25",
                "-g", str(_gop), "-keyint_min", str(max(1, _gop // 2))]
        return args, f"libx264 (소프트웨어, {preset})"

    if pref in ("x264", "libx264", "software", "cpu"):
        chosen, name = _sw(); _ENC_IS_SW = True
    elif pref == "nvenc":
        chosen, name, _ENC_IS_SW = _nvenc(), "NVENC (NVIDIA 하드웨어)", False
    elif pref in ("amf", "amd"):
        chosen, name, _ENC_IS_SW = _amf(), "AMF (AMD 하드웨어)", False
    elif pref in ("qsv", "intel"):
        chosen, name, _ENC_IS_SW = _qsv(), "QSV (Intel 하드웨어)", False
    else:  # auto — 실제 인코딩 테스트로 NVENC → AMF → QSV → libx264
        if ("h264_nvenc" in have) and _hw_ok("h264_nvenc"):
            chosen, name, _ENC_IS_SW = _nvenc(), "NVENC (NVIDIA 하드웨어)", False
        elif ("h264_amf" in have) and _hw_ok("h264_amf"):
            chosen, name, _ENC_IS_SW = _amf(), "AMF (AMD 하드웨어)", False
        elif ("h264_qsv" in have) and _hw_ok("h264_qsv"):
            chosen, name, _ENC_IS_SW = _qsv(), "QSV (Intel 하드웨어)", False
        else:
            if any(c in have for c in ("h264_nvenc", "h264_amf", "h264_qsv")):
                log("  HW 인코더가 목록엔 있으나 실제 인코딩 실패 → 소프트웨어(libx264)로 전환")
            chosen, name = _sw(); _ENC_IS_SW = True

    _ENC_CACHE = chosen
    log(f"Encoder: {name}")
    return _ENC_CACHE
```

> `_target_height()`/`_scale_vf()` 는 그대로 두면 됨 (`_ENC_IS_SW` 를 그대로 참조하므로 동작 동일).
> config에서 `"encoder": "amf"` / `"qsv"` 로 강제 지정도 가능해짐.

---

## ④ ffmpeg 공유폴더 (업데이트 시 재다운로드 방지)

지금은 ffmpeg를 앱 폴더(`HERE`)에 받아서, **새 버전으로 업데이트하면 ~90MB를 또 받는다.**
자료 폴더(`_data_root()`, 업데이트해도 유지됨) 밑 `bin/` 에 보관하도록 바꾼다.
ffprobe는 FFMPEG 경로 옆에서 자동으로 찾으므로(같은 폴더) 추가 수정 불필요.

**`ensure_ffmpeg()` 함수 전체를 교체:**

```python
def ensure_ffmpeg():
    # 업데이트(새 폴더에 압축 해제)해도 재다운로드하지 않도록 사용자 폴더(_data_root)에 보관.
    bindir = os.path.join(_data_root(), "bin")
    try: os.makedirs(bindir, exist_ok=True)
    except Exception: bindir = HERE
    shared = os.path.join(bindir, "ffmpeg.exe")
    if os.path.isfile(shared): return shared

    legacy = os.path.join(HERE, "ffmpeg.exe")
    if os.path.isfile(legacy):
        try:  # 기존 앱 폴더에 있으면 공유 폴더로 옮겨 다음 업데이트부터 재사용
            shutil.move(legacy, shared)
            lp = os.path.join(HERE, "ffprobe.exe")
            if os.path.isfile(lp): shutil.move(lp, os.path.join(bindir, "ffprobe.exe"))
            return shared
        except Exception:
            return legacy

    found = shutil.which("ffmpeg")
    if found: return found

    log("Downloading ffmpeg… (~90MB, first run only, 1-2 min)")
    sources = [
        ("BtbN", "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"),
        ("gyan-essentials", "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"),
        ("gyan-full", "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-full.zip"),
    ]
    try:
        api = urllib.request.Request("https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest",
                                     headers={"User-Agent": "Mozilla/5.0", "Accept": "application/vnd.github+json"})
        rel = json.loads(urllib.request.urlopen(api, timeout=30).read().decode("utf-8"))
        for a in rel.get("assets", []):
            n = a.get("name", "")
            if "win64-gpl" in n and n.endswith(".zip") and "shared" not in n and "lgpl" not in n:
                sources.append(("BtbN-api", a["browser_download_url"])); break
    except Exception:
        pass
    for label, url in sources:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=180).read()
            z = zipfile.ZipFile(io.BytesIO(data))
            member = next(n for n in z.namelist() if n.lower().endswith("/bin/ffmpeg.exe"))
            with z.open(member) as src, open(shared, "wb") as dst:
                shutil.copyfileobj(src, dst)
            try:
                pm = next((n for n in z.namelist() if n.lower().endswith("/bin/ffprobe.exe")), None)
                if pm:
                    with z.open(pm) as src, open(os.path.join(bindir, "ffprobe.exe"), "wb") as dst:
                        shutil.copyfileobj(src, dst)
            except Exception:
                pass
            log(f"ffmpeg ready. (source: {label})")
            return shared
        except Exception as e:
            log(f"    {label} failed: {e} → trying next source")
    log("[!] All ffmpeg auto-downloads failed. Please download it manually:")
    log("    1) Download https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip")
    log("    2) Unzip it and find  bin\\ffmpeg.exe  inside")
    log(f"    3) Copy it into this folder:  {bindir}")
    log("    4) Run START.bat again")
    return None
```

---

## ⑤ (선택) 재시도 상태코드 구분

현재 pending 큐는 **어떤 실패든 재시도**한다. 401(잘못된 신원) 같은 영구 오류도 무한 재시도해 낭비.
전송 실패를 잡는 곳에서 상태코드로 구분하면 됨(짧은 헬퍼):

```python
_RETRYABLE = {408, 429, 500, 502, 503, 504}
def _is_retryable(status):
    # status: HTTP 코드(int) 또는 None(네트워크 끊김 등) → None은 재시도 대상
    return (status is None) or (int(status) in _RETRYABLE) or (500 <= int(status) < 600)
```

업로드 실패를 큐에 넣는 지점에서:
`if _is_retryable(status): q=_load_pending(); q.append({...}); _save_pending(q)` 처럼 감싸고,
아니면(4xx 영구오류) 큐에 넣지 말고 로그만 남기면 됨.
(서명 프록시(RECORDER_PATCH.md)를 쓰면 429=한도초과=재시도, 나머지 4xx=버림 — 위 규칙과 일치.)

---

## 넣는 순서 / 주의
- ①②③④는 순서 무관, 독립적. 하나씩 넣고 실행해봐도 됨.
- 넣은 뒤 `python sc_recorder.py` 로 한 번 켜서 콘솔에 `Encoder: ...` 가 뜨는지 확인.
- ④ 적용 후 첫 실행 때 기존 `ffmpeg.exe`가 `%USERPROFILE%\ReplayCast\bin\` 로 옮겨짐(정상).
