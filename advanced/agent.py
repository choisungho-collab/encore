#!/usr/bin/env python3
"""
StarCraft 자동 녹화 에이전트 (Windows)
================================================
한 번 켜두면, 스타크래프트를 할 때마다 알아서:
  1) 스타크래프트 실행을 감지하면 OBS 녹화를 시작
  2) 게임이 끝나 새 .rep 파일이 저장되면  →  그 순간을 "한 판 끝"으로 보고
     녹화를 끊어서 [방금 게임 영상 + 그 .rep] 을 짝지어 서버로 업로드
  3) 곧바로 다음 판 녹화를 다시 시작
  4) 스타를 끄면 대기 상태로 돌아감

* 영상은 실제 게임 화면을 그대로 녹화하므로 리마스터 HD 화질 그대로입니다.
* NVIDIA 그래픽카드면 OBS 출력 인코더를 'NVIDIA NVENC' 로 두세요 (게임 성능 저하 거의 없음).
* 사전 준비/설정은 README.md 참고.

실행:  python agent.py
"""
import os, sys, json, time, glob, datetime, traceback

try:
    import psutil, requests
    from obsws_python import ReqClient
except ImportError as e:
    print("필요한 패키지가 없어요. 먼저:  pip install -r requirements.txt")
    print("   (psutil, requests, obsws-python)")
    print("상세:", e); sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
PENDING_PATH = os.path.join(HERE, "pending_uploads.json")

DEFAULT_CONFIG = {
    "starcraft_process": "StarCraft.exe",
    "replay_autosave_dir": r"%USERPROFILE%\Documents\StarCraft\Maps\Replays\AutoSave",
    "obs": {"host": "localhost", "port": 4455, "password": "YOUR_OBS_WEBSOCKET_PASSWORD"},
    "server": {"url": "http://localhost:8000", "api_key": "change-me-please"},
    "poll_seconds": 4,
    "delete_video_after_upload": False,
}

def log(msg):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)

def load_config():
    if not os.path.isfile(CONFIG_PATH):
        json.dump(DEFAULT_CONFIG, open(CONFIG_PATH, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        log(f"config.json 을 새로 만들었어요. 값을 채우고 다시 실행하세요 → {CONFIG_PATH}")
        sys.exit(0)
    cfg = json.load(open(CONFIG_PATH, encoding="utf-8"))
    cfg["replay_autosave_dir"] = os.path.expandvars(cfg["replay_autosave_dir"])
    return cfg

# ----------------------- 프로세스 / 리플레이 감지 -----------------------
def sc_running(proc_name):
    pn = proc_name.lower()
    for p in psutil.process_iter(["name"]):
        try:
            if (p.info["name"] or "").lower() == pn:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False

def list_reps(autosave_dir):
    if not os.path.isdir(autosave_dir):
        return {}
    out = {}
    for f in glob.glob(os.path.join(autosave_dir, "**", "*.rep"), recursive=True):
        try: out[f] = os.path.getmtime(f)
        except OSError: pass
    return out

# ----------------------- OBS 제어 -----------------------
def obs_client(cfg):
    o = cfg["obs"]
    return ReqClient(host=o["host"], port=int(o["port"]), password=o["password"], timeout=4)

def obs_recording(cfg):
    try:
        cl = obs_client(cfg)
        return bool(cl.get_record_status().output_active)
    except Exception:
        return None  # None = OBS 연결 불가

def obs_start(cfg):
    try:
        cl = obs_client(cfg)
        if not cl.get_record_status().output_active:
            cl.start_record(); log("● OBS 녹화 시작")
        return True
    except Exception as e:
        log(f"OBS 녹화 시작 실패 (OBS 켜져있고 WebSocket 켰는지 확인): {e}")
        return False

def obs_stop(cfg):
    """녹화 중지 후 저장된 영상 파일 경로 반환 (실패시 None)."""
    try:
        cl = obs_client(cfg)
        if not cl.get_record_status().output_active:
            return None
        resp = cl.stop_record()
        path = getattr(resp, "output_path", None)
        log(f"■ OBS 녹화 종료 → {path}")
        return path
    except Exception as e:
        log(f"OBS 녹화 종료 실패: {e}")
        return None

# ----------------------- 업로드 -----------------------
def upload(cfg, video_path, rep_path):
    url = cfg["server"]["url"].rstrip("/") + "/upload"
    key = cfg["server"]["api_key"]
    if not video_path or not os.path.isfile(video_path):
        log(f"영상 파일이 없어 업로드 건너뜀: {video_path}"); return False
    try:
        files = {"video": (os.path.basename(video_path), open(video_path, "rb"), "video/mp4")}
        if rep_path and os.path.isfile(rep_path):
            files["replay"] = (os.path.basename(rep_path), open(rep_path, "rb"),
                               "application/octet-stream")
        log(f"↑ 업로드 중… ({os.path.getsize(video_path)/1048576:.0f} MB)")
        r = requests.post(url, files=files, data={"key": key}, timeout=(10, 1800))
        for f in files.values():
            try: f[1].close()
            except Exception: pass
        if r.status_code == 200:
            log(f"✓ 업로드 완료: {r.json().get('id')}")
            if cfg.get("delete_video_after_upload"):
                try: os.remove(video_path); log("  (로컬 영상 삭제됨)")
                except OSError: pass
            return True
        log(f"✗ 서버 거부 {r.status_code}: {r.text[:200]}")
        return False
    except Exception as e:
        log(f"✗ 업로드 실패(서버 꺼져있나?): {e}")
        return False

# 업로드 실패분은 큐에 적어뒀다가 다음 루프에서 재시도
def load_pending():
    if os.path.isfile(PENDING_PATH):
        try: return json.load(open(PENDING_PATH, encoding="utf-8"))
        except Exception: return []
    return []

def save_pending(q):
    json.dump(q, open(PENDING_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def queue_pending(video_path, rep_path):
    q = load_pending(); q.append({"video": video_path, "rep": rep_path}); save_pending(q)
    log("  → 나중에 재시도하도록 대기열에 넣었어요.")

def flush_pending(cfg):
    q = load_pending()
    if not q: return
    still = []
    for item in q:
        if not os.path.isfile(item.get("video") or ""):
            continue  # 영상이 사라졌으면 버림
        if not upload(cfg, item["video"], item.get("rep")):
            still.append(item)
    save_pending(still)

# ----------------------- 메인 루프 -----------------------
def main():
    cfg = load_config()
    proc = cfg["starcraft_process"]
    autosave = cfg["replay_autosave_dir"]
    poll = float(cfg.get("poll_seconds", 4))

    log("=" * 52)
    log("StarCraft 자동 녹화 에이전트 시작")
    log(f"  감지 프로세스 : {proc}")
    log(f"  리플레이 폴더 : {autosave}")
    log(f"  업로드 서버   : {cfg['server']['url']}")
    if not os.path.isdir(autosave):
        log("  ⚠ 리플레이 폴더가 없어요. config.json 의 replay_autosave_dir 를 확인하세요.")
    log("  (스타를 켜면 자동으로 녹화가 시작됩니다. Ctrl+C 로 종료)")
    log("=" * 52)

    known = list_reps(autosave)        # 시작 시점의 기존 리플레이 (얘네는 무시)
    was_running = False
    record_active = False              # 우리가 녹화를 켰다고 보는 상태

    while True:
        try:
            running = sc_running(proc)

            # --- 스타 실행 시작 ---
            if running and not was_running:
                log("스타크래프트 감지됨.")
                known = list_reps(autosave)
                if obs_start(cfg):
                    record_active = True

            # --- 스타 켜져 있는 동안: 새 리플레이(=한 판 종료) 감시 ---
            if running:
                if not record_active:                       # OBS가 늦게 켜졌을 수 있음 → 재시도
                    if obs_start(cfg): record_active = True
                current = list_reps(autosave)
                new_reps = [f for f in current if f not in known]
                if new_reps:
                    newest = max(new_reps, key=lambda f: current[f])
                    log(f"새 리플레이 감지 = 한 판 종료: {os.path.basename(newest)}")
                    time.sleep(1.5)                          # 파일 쓰기 마무리 대기
                    video = obs_stop(cfg); record_active = False
                    if video:
                        if not upload(cfg, video, newest):
                            queue_pending(video, newest)
                    else:
                        log("  영상이 없어 이 판은 리플레이만 남았어요(녹화 미동작).")
                    known = current
                    if sc_running(proc):                     # 다음 판 대비 재녹화
                        if obs_start(cfg): record_active = True

            # --- 스타 종료 ---
            if not running and was_running:
                log("스타크래프트 종료됨.")
                if record_active or obs_recording(cfg):
                    video = obs_stop(cfg); record_active = False
                    # 마지막 클립은 보통 메뉴/대기화면이라 새 리플레이 없으면 버림
                    current = list_reps(autosave)
                    new_reps = [f for f in current if f not in known]
                    if video and new_reps:
                        newest = max(new_reps, key=lambda f: current[f])
                        if not upload(cfg, video, newest): queue_pending(video, newest)
                    elif video:
                        log("  (메뉴 구간 클립으로 보고 업로드 생략)")
                    known = current
                log("대기 상태로 돌아갑니다.")

            flush_pending(cfg)                               # 실패분 재시도
            was_running = running
            time.sleep(poll)

        except KeyboardInterrupt:
            log("종료합니다. 안녕히 ㅎㅎ")
            if record_active:
                obs_stop(cfg)
            break
        except Exception:
            log("루프 오류:\n" + traceback.format_exc())
            time.sleep(poll)

if __name__ == "__main__":
    main()
