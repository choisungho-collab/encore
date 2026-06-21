#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
스타크래프트 자동 녹화 — 올인원 (한 번 실행하면 다 됨)
=====================================================
이 파일 하나만 실행하면:
  · 필요한 파이썬 패키지 자동 설치
  · ffmpeg(녹화기) 자동 다운로드 (처음 한 번)
  · screp(메타데이터 파서) 자동 다운로드 시도 (선택)
  · 리플레이 자동저장 폴더 자동 탐지
  · 갤러리 사이트 + 녹화기를 한 프로세스로 같이 실행, 브라우저 자동 오픈

그 다음부턴 스타 켜서 게임하면 → 판마다 자동 녹화 → 영상+리플레이가 갤러리에 자동 등록.
OBS 필요 없음. NVIDIA NVENC 하드웨어 인코딩이라 게임 성능 저하 거의 없음.

실행:  START.bat 더블클릭   (또는  python sc_recorder.py)
"""
import os, sys, json, time, glob, socket, subprocess, datetime, traceback, threading
import sqlite3, secrets
from collections import Counter, defaultdict
from urllib.parse import quote

# --windowed(콘솔 없는 exe) 실행 시 sys.stdout 이 None → print 크래시 방지
class _NullIO:
    def write(self, *a): pass
    def flush(self): pass
if sys.stdout is None: sys.stdout = _NullIO()
if sys.stderr is None: sys.stderr = _NullIO()
# 윈도우 콘솔을 UTF-8 로 (한글·기호 깨짐/크래시 방지) — bat 없이 직접 실행해도 적용됨
if sys.platform == "win32":
    try: os.system("chcp 65001 >nul 2>&1")
    except Exception: pass
    for _s in (sys.stdout, sys.stderr):
        try: _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass
# 콘솔 없이(pythonw / --windowed) 실행돼 stdout 이 없을 때 print 가 죽지 않도록
for _nm in ("stdout", "stderr"):
    if getattr(sys, _nm, None) is None:
        try: setattr(sys, _nm, open(os.devnull, "w", encoding="utf-8"))
        except Exception: pass
def _safe_input(prompt=""):
    try: return input(prompt)
    except Exception: return ""
def _run(args, **kw):
    kw.setdefault("creationflags", getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return subprocess.run(args, **kw)

FROZEN     = getattr(sys, "frozen", False)
APP_DIR    = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.abspath(__file__))  # 쓰기 가능(exe 옆)
BUNDLE_DIR = getattr(sys, "_MEIPASS", APP_DIR)                                                          # 번들 읽기전용(web/)
HERE       = APP_DIR

# ===================== 0. 의존성 자동 설치 =====================
def ensure_deps():
    if getattr(sys, "frozen", False): return   # exe(번들)면 패키지가 이미 포함됨
    need = []
    for mod, pkg in [("flask", "flask"), ("psutil", "psutil"), ("requests", "requests")]:
        try: __import__(mod)
        except ImportError: need.append(pkg)
    if need:
        print(f"[준비] 파이썬 패키지 설치 중: {', '.join(need)} …")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", *need])
        except Exception as e:
            print("[!] 패키지 자동 설치 실패. 수동으로 실행해 주세요:")
            print(f"    {sys.executable} -m pip install {' '.join(need)}")
            print("상세:", e); _safe_input("\n엔터를 누르면 종료..."); sys.exit(1)
ensure_deps()

import psutil, requests
import urllib.request, zipfile, io, webbrowser, re, html, shutil
from flask import Flask, request, send_file, abort, Response, jsonify

# ===================== 경로 / 전역 =====================
def _data_root():
    # 업데이트(새 폴더에 압축 해제)해도 자료가 유지되도록 사용자 폴더에 고정 저장.
    # config.json 의 "data_dir" 로 바꿀 수 있음 (기본: 윈도우 %USERPROFILE%\ReplayCast).
    try:
        cfgp = os.path.join(HERE, "config.json")
        if os.path.isfile(cfgp):
            dd = (json.load(open(cfgp, encoding="utf-8")) or {}).get("data_dir")
            if dd: return os.path.expanduser(os.path.expandvars(dd))
    except Exception: pass
    if sys.platform == "win32":
        return os.path.join(os.environ.get("USERPROFILE") or HERE, "ReplayCast")
    return os.path.join(os.path.expanduser("~"), ".replaycast")
DATA_DIR   = os.path.join(_data_root(), "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
REC_DIR    = os.path.join(DATA_DIR, "recordings")
INDEX_PATH = os.path.join(DATA_DIR, "index.json")
DB_PATH    = os.path.join(DATA_DIR, "matches.db")
CONFIG_PATH= os.path.join(HERE, "config.json")
WEB_DIR    = os.path.join(BUNDLE_DIR, "web")
FPS        = 30
FPS_GAME   = 23.81
REC_STATE  = {"rec": False, "text": "대기 중", "game": None}   # 실시간 녹화 상태(웹 표시용)
for d in (DATA_DIR, UPLOAD_DIR, REC_DIR): os.makedirs(d, exist_ok=True)
# 레거시 이전: 예전엔 프로그램 폴더 안(./data)에 저장 → 같은 폴더에 덮어쓴 경우 자동 이전
try:
    _legacy = os.path.join(HERE, "data")
    if os.path.abspath(_legacy) != os.path.abspath(DATA_DIR) \
       and os.path.isfile(os.path.join(_legacy, "matches.db")) and not os.path.isfile(DB_PATH):
        import shutil as _sh
        for _it in os.listdir(_legacy):
            _s = os.path.join(_legacy, _it); _dn = os.path.join(DATA_DIR, _it)
            if not os.path.exists(_dn):
                _sh.copytree(_s, _dn) if os.path.isdir(_s) else _sh.copy2(_s, _dn)
        print(f"[이전] 예전 자료를 {DATA_DIR} 로 옮겼어요.")
except Exception: pass
FFMPEG = None
SCREP  = None
CFG    = {}

import queue as _queue
GUI_Q = _queue.Queue(maxsize=4000)
REC_STATE = {"recording": False, "encoder": "", "ready": False}
LAST_ERR = {"msg": "", "t": 0.0}
_LOGFILE = {"p": None}
def log(m):
    line = f"[{datetime.datetime.now():%H:%M:%S}] {m}"
    try: print(line, flush=True)
    except Exception: pass
    s = str(m)
    if any(k in s for k in ("오류", "에러", "실패", "Traceback", "Error")) and ("다시 시작" not in s):
        LAST_ERR["msg"] = s[:240]; LAST_ERR["t"] = time.time()
    if "녹화 시작" in s: REC_STATE["recording"] = True
    elif ("녹화 종료" in s) or ("대기 상태" in s) or ("스타크래프트 종료" in s): REC_STATE["recording"] = False
    if "준비 완료. 스타" in s: REC_STATE["ready"] = True
    if s.startswith("인코더:"): REC_STATE["encoder"] = s.split("인코더:", 1)[1].strip()
    try: GUI_Q.put_nowait(line)
    except Exception: pass
    try:
        if _LOGFILE["p"]:
            with open(_LOGFILE["p"], "a", encoding="utf-8", errors="replace") as f: f.write(line + "\n")
    except Exception: pass

# ===================== 1. 설정 (자동 생성/탐지) =====================
def detect_replay_dir():
    up = os.environ.get("USERPROFILE", os.path.expanduser("~"))
    cands = [
        os.path.join(up, "Documents", "StarCraft", "Maps", "Replays", "AutoSave"),
        os.path.join(up, "OneDrive", "Documents", "StarCraft", "Maps", "Replays", "AutoSave"),
        os.path.join(up, "OneDrive", "문서", "StarCraft", "Maps", "Replays", "AutoSave"),
        os.path.join(up, "문서", "StarCraft", "Maps", "Replays", "AutoSave"),
        os.path.join(up, "Documents", "StarCraft", "Maps", "Replays"),
    ]
    # .rep 이 실제로 있는 폴더 우선
    for c in cands:
        if os.path.isdir(c) and glob.glob(os.path.join(c, "**", "*.rep"), recursive=True):
            return c
    for c in cands:
        if os.path.isdir(c):
            return c
    return cands[0]

def free_port(pref=8000):
    s = socket.socket()
    try:
        s.bind(("0.0.0.0", pref)); s.close(); return pref
    except OSError:
        s2 = socket.socket(); s2.bind(("0.0.0.0", 0)); p = s2.getsockname()[1]; s2.close(); return p

def load_or_make_config():
    if os.path.isfile(CONFIG_PATH):
        cfg = json.load(open(CONFIG_PATH, encoding="utf-8"))
        cfg["replay_autosave_dir"] = os.path.expandvars(cfg.get("replay_autosave_dir", ""))
    else:
        cfg = {
            "mode": "all",
            "starcraft_process": "StarCraft.exe",
            "replay_autosave_dir": detect_replay_dir(),
            "username": "",
            "server": {"url": "http://localhost:8000", "api_key": ""},
            "upload_key": secrets.token_hex(8),
            "r2": {"account_id": "", "bucket": "", "access_key_id": "", "secret_access_key": "", "public_base_url": ""},
            "cloud": {"function_url": "", "upload_key": ""},
            "supabase": {"url": "", "anon_key": "", "service_key": "", "bucket": "media"},
            "data_dir": "",
            "gallery_url": "",
            "encoder": "auto",   # auto | nvenc | x264
            "ui": "window",      # window | console  (window=보기 좋은 상태창, console=검은 cmd창)
            "scale": "auto",     # auto | source | 1080 | 720 | 480  (소프트웨어 인코딩이면 auto가 720p로 낮춰 게임 끊김 방지)
            "preset": "auto",    # auto | ultrafast | superfast | veryfast | fast ...  (libx264 속도/품질)
            "output_idx": "auto",   # auto | 0 | 1 | 2  (멀티모니터면 게임 있는 모니터 번호)
            "capture": "auto",   # auto | wgc | ddagrab | gdigrab   (wgc=OBS식, 전체화면도 잡힘)
            "port": free_port(8000),
            "fps": FPS,
            "poll_seconds": 4,
            "autostart": True, "min_game_sec": 120,
        }
        json.dump(cfg, open(CONFIG_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        log(f"설정 자동 생성됨 → {CONFIG_PATH}")
    # service_key 영구보관: 한 번 넣으면 data 폴더에 저장 → 이후 zip 통째로 덮어써도 유지
    try:
        _sk = ((cfg.get("supabase") or {}).get("service_key") or "").strip()
        _secret = os.path.join(DATA_DIR, "encore_secret.json")
        if _sk:
            json.dump({"service_key": _sk}, open(_secret, "w", encoding="utf-8"))
        elif os.path.isfile(_secret):
            _v = (json.load(open(_secret, encoding="utf-8")) or {}).get("service_key") or ""
            if _v: cfg.setdefault("supabase", {})["service_key"] = _v
    except Exception: pass
    # 리플레이 폴더가 비었거나 없으면 자동 재탐지
    try:
        _rd = cfg.get("replay_autosave_dir") or ""
        if not _rd or not os.path.isdir(_rd):
            _nd = detect_replay_dir()
            if _nd: cfg["replay_autosave_dir"] = _nd
    except Exception: pass
    return cfg

# ===================== 2. ffmpeg / screp 자동 다운로드 =====================
def ensure_audio():
    """pyaudiowpatch(WASAPI 루프백) 준비 — 없으면 자동 설치. 실패해도 무음으로 진행(영상엔 영향 없음)."""
    try:
        import pyaudiowpatch  # noqa
        return True
    except Exception:
        pass
    try:
        log("소리 엔진 준비 중(pyaudiowpatch, 처음 한 번)…")
        _run([sys.executable, "-m", "pip", "install", "-q", "pyaudiowpatch", "--break-system-packages"], timeout=300)
        import pyaudiowpatch  # noqa
        log("소리 엔진 준비 완료.")
        return True
    except Exception as e:
        log(f"  (소리) pyaudiowpatch 자동 설치 실패 → 무음 녹화. 수동: pip install pyaudiowpatch ({e})")
        return False

def ensure_ffmpeg():
    local = os.path.join(HERE, "ffmpeg.exe")
    if os.path.isfile(local): return local
    found = shutil.which("ffmpeg")
    if found: return found
    log("ffmpeg 다운로드 중… (~90MB, 처음 한 번만, 1~2분)")
    sources = [
        ("BtbN", "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"),
        ("gyan-essentials", "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"),
        ("gyan-full", "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-full.zip"),
    ]
    # BtbN 최신 릴리스에서 win64-gpl 자산을 동적으로 찾아 추가 (파일명이 또 바뀌어도 대응)
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
            with z.open(member) as src, open(local, "wb") as dst:
                shutil.copyfileobj(src, dst)
            log(f"ffmpeg 준비 완료. (출처: {label})")
            return local
        except Exception as e:
            log(f"    {label} 실패: {e} → 다음 소스 시도")
    log("[!] ffmpeg 자동 다운로드에 모두 실패했어요. 수동으로 받아주세요:")
    log("    1) https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip 다운로드")
    log("    2) 압축 풀고 그 안의  bin\\ffmpeg.exe  를 찾아")
    log(f"    3) 이 폴더에 복사:  {HERE}")
    log("    4) START.bat 다시 실행")
    return None

def ensure_screp():
    local = os.path.join(HERE, "screp.exe")
    if os.path.isfile(local): return local
    found = shutil.which("screp")
    if found: return found
    try:
        req = urllib.request.Request("https://api.github.com/repos/icza/screp/releases/latest",
                                     headers={"User-Agent": "sc-recorder"})
        rel = json.load(urllib.request.urlopen(req, timeout=20))
        asset = next(a for a in rel.get("assets", [])
                     if "windows" in a["name"].lower() and ("amd64" in a["name"].lower() or "x86_64" in a["name"].lower()))
        blob = urllib.request.urlopen(asset["browser_download_url"], timeout=60).read()
        name = asset["name"].lower()
        if name.endswith(".zip"):
            z = zipfile.ZipFile(io.BytesIO(blob))
            m = next(n for n in z.namelist() if n.lower().endswith("screp.exe"))
            with z.open(m) as s, open(local, "wb") as d: shutil.copyfileobj(s, d)
        else:
            import tarfile
            t = tarfile.open(fileobj=io.BytesIO(blob))
            m = next(n for n in t.getnames() if n.lower().endswith("screp.exe"))
            with t.extractfile(m) as s, open(local, "wb") as d: shutil.copyfileobj(s, d)
        log("screp 준비 완료 (갤러리에 맵/종족/APM/승패 표시됨).")
        return local
    except Exception as e:
        log(f"(screp 자동 설치 생략 — 영상은 정상, 메타데이터만 비표시: {e})")
        return None

# ===================== 3. 리플레이 파싱 =====================
def clean(s): return re.sub(r"[\x00-\x1f]", "", s).strip() if s else s

def parse_rep(path):
    meta = {"map": None, "length": None, "type": None, "matchup": None,
            "winner": None, "saver": None, "players": []}
    if not SCREP or not os.path.isfile(path): return meta
    try:
        out = _run([SCREP, path], capture_output=True, timeout=60).stdout
        d = json.loads(out)
    except Exception: return meta
    h = d.get("Header", {}) or {}; comp = d.get("Computed", {}) or {}
    pdescs = {p["PlayerID"]: p for p in (comp.get("PlayerDescs") or [])}
    players = []
    for p in (h.get("Players") or []):
        pd = pdescs.get(p.get("ID"), {})
        players.append({"name": p.get("Name"), "race": (p.get("Race") or {}).get("ShortName"),
                        "team": p.get("Team"), "apm": pd.get("APM"),
                        "color": "#%06x" % ((p.get("Color") or {}).get("RGB", 8421504))})
    frames = h.get("Frames", 0) or 0; secs = frames / FPS_GAME
    t1 = "".join((pl["race"] or "?")[0].upper() for pl in players if pl["team"] == 1)
    t2 = "".join((pl["race"] or "?")[0].upper() for pl in players if pl["team"] == 2)
    meta.update({"map": clean(h.get("Map")), "length": "%d:%02d" % (secs // 60, secs % 60),
                 "type": (h.get("Type") or {}).get("Name"), "winner": comp.get("WinnerTeam"),
                 "saver": next((p.get("Name") for p in (h.get("Players") or [])
                               if p.get("ID") == comp.get("RepSaverPlayerID")), None),
                 "players": players,
                 "matchup": (f"{t1} vs {t2}" if t1 and t2 else None)})
    return meta

def mmss(fr): sx = max(0, fr)/FPS_GAME; return f"{int(sx//60)}:{int(sx%60):02d}"
TOWN_HALLS = {"Command Center", "Nexus", "Hatchery"}
# 빨무 데이터용 — 유닛 표시 보급값(인구). 전사 미반영 누계 추정에 사용.
UNIT_SUPPLY = {
 "Probe":1,"Zealot":2,"Dragoon":2,"High Templar":2,"Dark Templar":2,"Archon":4,"Dark Archon":4,
 "Reaver":4,"Shuttle":2,"Observer":1,"Scout":3,"Corsair":2,"Carrier":6,"Arbiter":4,
 "SCV":1,"Marine":1,"Firebat":1,"Medic":1,"Ghost":1,"Vulture":2,"Siege Tank":2,"Goliath":2,
 "Wraith":2,"Valkyrie":2,"Dropship":2,"Science Vessel":2,"Battlecruiser":6,
 "Drone":1,"Zergling":1,"Hydralisk":1,"Lurker":2,"Mutalisk":2,"Scourge":1,"Queen":2,
 "Guardian":2,"Devourer":2,"Ultralisk":4,"Defiler":2,"Infested Terran":1,"Overlord":0,
}
# 기존 유닛에서 전환되는 모프(이미 카운트됨 → 보급 중복 방지)
MORPH_FROM_UNIT = {"Lurker","Guardian","Devourer","Archon","Dark Archon"}
PROD_BUILDINGS = {"Gateway","Robotics Facility","Stargate","Barracks","Factory","Starport","Hatchery"}
def extract_analysis(rep_path):
    out = _run([SCREP, "-cmds", rep_path], capture_output=True, timeout=120).stdout
    d = json.loads(out); h = d["Header"]; comp = d.get("Computed", {}) or {}
    pdescs = {p["PlayerID"]: p for p in (comp.get("PlayerDescs") or [])}
    frames = h.get("Frames", 0) or 0; nbins = max(1, int(frames/FPS_GAME//60) + 1)
    players = {}; order = []; seen_up = defaultdict(set)
    for p in (h.get("Players") or []):
        pid = p.get("ID"); pd = pdescs.get(pid, {})
        players[pid] = {"id": pid, "name": p.get("Name"), "race": (p.get("Race") or {}).get("ShortName"),
            "team": p.get("Team"), "color": "#%06x" % ((p.get("Color") or {}).get("RGB", 8421504)),
            "apm": pd.get("APM"), "eapm": pd.get("EAPM"), "build": [], "units": Counter(),
            "unit_first": {}, "townhalls": [], "apm_series": [0]*nbins, "supply_events": []}
        order.append(pid)
    for c in d.get("Commands", {}).get("Cmds", []):
        pid = c.get("PlayerID"); pl = players.get(pid)
        if pl is None: continue
        f = c.get("Frame", 0); tn = (c.get("Type") or {}).get("Name")
        b = min(nbins-1, int(f/FPS_GAME//60)); pl["apm_series"][b] += 1
        uname = (c.get("Unit") or {}).get("Name")
        if tn == "Build":
            pl["build"].append({"t": mmss(f), "name": uname, "cat": "building"})
            if uname in TOWN_HALLS: pl["townhalls"].append({"t": mmss(f), "name": uname})
        elif tn == "Building Morph":
            pl["build"].append({"t": mmss(f), "name": uname, "cat": "morph"})
        elif tn == "Upgrade":
            up = (c.get("Upgrade") or {}).get("Name") or uname or "Upgrade"
            if up not in seen_up[pid]: seen_up[pid].add(up); pl["build"].append({"t": mmss(f), "name": up, "cat": "upgrade"})
        elif tn == "Tech":
            tech = (c.get("Tech") or {}).get("Name") or uname or "Tech"
            if tech not in seen_up[pid]: seen_up[pid].add(tech); pl["build"].append({"t": mmss(f), "name": tech, "cat": "tech"})
        elif tn in ("Train", "Train Fighter", "Unit Morph"):
            if uname:
                pl["units"][uname] += 1
                if uname not in pl["unit_first"]: pl["unit_first"][uname] = mmss(f)
                if tn == "Train" or (tn == "Unit Morph" and uname not in MORPH_FROM_UNIT):
                    pl["supply_events"].append((f, UNIT_SUPPLY.get(uname, 1)))
    res = []
    for pid in order:
        pl = players[pid]; us = sorted(pl["units"].items(), key=lambda kv: -kv[1])
        ev = sorted(pl["supply_events"]); cum = 0; t200 = None
        for fr, sup in ev:
            cum += sup
            if t200 is None and cum >= 200: t200 = mmss(fr)
        prodn = sum(1 for b in pl["build"] if b["cat"] in ("building", "morph") and b["name"] in PROD_BUILDINGS)
        res.append({"id": pl["id"], "name": pl["name"], "race": pl["race"], "team": pl["team"],
            "color": pl["color"], "apm": pl["apm"], "eapm": pl["eapm"], "build": pl["build"],
            "units": [{"name": k, "n": v, "first": pl["unit_first"].get(k)} for k, v in us],
            "townhalls": pl["townhalls"], "apm_series": pl["apm_series"],
            "max_supply": min(cum, 200), "total_supply": cum, "supply200": t200, "prod": prodn,
            "summary": {"buildings": sum(1 for b in pl["build"] if b["cat"] in ("building", "morph")),
                        "units": sum(pl["units"].values()),
                        "upgrades": sum(1 for b in pl["build"] if b["cat"] in ("upgrade", "tech")),
                        "townhalls": len(pl["townhalls"]), "prod": prodn,
                        "max_supply": min(cum, 200), "supply200": t200}})
    secs = frames / FPS_GAME
    meta = {"map": clean(h.get("Map")), "length": f"{int(secs//60)}:{int(secs%60):02d}",
            "winner": comp.get("WinnerTeam"),
            "saver": next((p.get("Name") for p in (h.get("Players") or []) if p.get("ID") == comp.get("RepSaverPlayerID")), None)}
    return {"meta": meta, "players": res}

# 임팩트 유닛(테크 마일스톤용) → 한글
TECH_UNITS = {
 "Lurker":"러커","Mutalisk":"뮤탈","Guardian":"가디언","Devourer":"디바우러","Defiler":"디파일러","Ultralisk":"울트라","Queen":"퀸","Scourge":"스컬지",
 "Reaver":"리버","Dark Templar":"다크템플러","High Templar":"하이템플러","Carrier":"캐리어","Arbiter":"아비터","Archon":"아콘","Corsair":"커세어","Scout":"스카웃",
 "Siege Tank":"시즈탱크","Tank":"탱크","Battlecruiser":"배틀크루저","Wraith":"레이스","Science Vessel":"사이언스베슬","Valkyrie":"발키리","Ghost":"고스트","Goliath":"골리앗","Dropship":"드랍십",
}
def _mmss_to_sec(t):
    try: m, s = str(t).split(":"); return int(m)*60 + int(s)
    except Exception: return 0
def compute_highlights(a):
    """리플레이 데이터로 하이라이트 추정: 교전(활동량 피크)·테크 마일스톤·첫 확장."""
    players = a.get("players") or []
    out = []
    # 1) 교전 추정 — 전원 분당 활동량(APM) 합의 국소 피크
    nb = max((len(p.get("apm_series") or []) for p in players), default=0)
    if nb >= 3:
        total = [0]*nb
        for p in players:
            for i, v in enumerate(p.get("apm_series") or []):
                if i < nb: total[i] += v
        cand = []
        for i in range(2, nb):
            nxt = total[i+1] if i+1 < nb else 0
            if total[i] > 0 and total[i] >= total[i-1] and total[i] >= nxt:
                cand.append((total[i], i))
        cand.sort(reverse=True)
        picked = []
        for v, i in cand:
            if all(abs(i-j) >= 2 for j in picked):
                picked.append(i)
            if len(picked) >= 3: break
        for i in sorted(picked):
            out.append({"sec": i*60, "t": f"{i}:00", "label": "대규모 교전 추정", "kind": "battle"})
    # 2) 테크 마일스톤 — 임팩트 유닛의 전체 최초 등장
    firsts = {}
    for p in players:
        for u in (p.get("units") or []):
            nm = u.get("name"); ft = u.get("first")
            if nm in TECH_UNITS and ft:
                sec = _mmss_to_sec(ft)
                if nm not in firsts or sec < firsts[nm][0]:
                    firsts[nm] = (sec, ft, p.get("name"))
    for nm, (sec, ft, who) in sorted(firsts.items(), key=lambda kv: kv[1][0])[:5]:
        out.append({"sec": sec, "t": ft, "label": f"첫 {TECH_UNITS[nm]}", "who": who, "kind": "tech"})
    # 3) 첫 확장 — 가장 빠른 2번째 타운홀
    exp = None
    for p in players:
        ths = p.get("townhalls") or []
        if len(ths) >= 2:
            sec = _mmss_to_sec(ths[1].get("t"))
            if exp is None or sec < exp[0]: exp = (sec, ths[1].get("t"), p.get("name"))
    if exp: out.append({"sec": exp[0], "t": exp[1], "label": "첫 확장", "who": exp[2], "kind": "expand"})
    out.sort(key=lambda hh: hh["sec"])
    return out

# ===================== 4. 인게스트 (영상+리플레이 등록) =====================
def db():
    c = sqlite3.connect(DB_PATH, timeout=15); c.row_factory = sqlite3.Row; return c
def init_db():
    c = db()
    c.execute("""CREATE TABLE IF NOT EXISTS matches(
        id TEXT PRIMARY KEY, uploader TEXT, uploaded TEXT, video TEXT, replay TEXT,
        thumb TEXT, video_size INTEGER, map TEXT, matchup TEXT, length TEXT, length_sec INTEGER,
        type TEXT, winner INTEGER, saver TEXT, np INTEGER, players TEXT, won INTEGER, analysis TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS comments(
        id INTEGER PRIMARY KEY AUTOINCREMENT, match_id TEXT, author TEXT, body TEXT, created TEXT)""")
    for col in ("likes", "views"):
        try: c.execute(f"ALTER TABLE matches ADD COLUMN {col} INTEGER DEFAULT 0")
        except Exception: pass
    c.commit(); c.close()
def _row(r):
    d = dict(r)
    try: d["players"] = json.loads(d.get("players") or "[]")
    except Exception: d["players"] = []
    return d
def get_matches(limit=24, offset=0):
    if sb_enabled(): return sb_get_matches(limit, offset)
    c = db(); rows = c.execute("SELECT * FROM matches ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall(); c.close()
    return [_row(r) for r in rows]
def get_match(mid):
    if sb_enabled(): return sb_get_match(mid)
    c = db(); r = c.execute("SELECT * FROM matches WHERE id=?", (mid,)).fetchone(); c.close()
    return _row(r) if r else None
_CNT = {"n": 0, "t": 0.0, "busy": False}
def _sb_count_cached():
    now = time.time()
    if (now - _CNT["t"] > 15) and not _CNT["busy"]:
        _CNT["busy"] = True
        def _refresh():
            try: _CNT["n"] = sb_count_matches()
            except Exception: pass
            finally: _CNT["t"] = time.time(); _CNT["busy"] = False
        threading.Thread(target=_refresh, daemon=True).start()
    return _CNT["n"]
def count_matches():
    if sb_enabled(): return _sb_count_cached()
    c = db(); n = c.execute("SELECT COUNT(*) FROM matches").fetchone()[0]; c.close(); return n
def stats_global():
    if sb_enabled(): return sb_stats()
    c = db(); r = c.execute("SELECT COUNT(*), COALESCE(SUM(length_sec),0), COALESCE(SUM(won),0), "
                            "SUM(CASE WHEN won IS NOT NULL THEN 1 ELSE 0 END) FROM matches").fetchone(); c.close()
    n, tsec, w, rated = r[0] or 0, r[1] or 0, r[2] or 0, r[3] or 0
    return n, tsec, (f"{round(100*w/rated)}%" if rated else "—")
def set_analysis(mid, js):
    if sb_enabled(): return sb_set_analysis(mid, js)
    c = db(); c.execute("UPDATE matches SET analysis=? WHERE id=?", (js, mid)); c.commit(); c.close()
# ===================== 코치 리포트 (규칙 기반, API 불필요) =====================
COACH_SUPPLY={"Zergling":.5,"Hydralisk":1,"Mutalisk":2,"Lurker":2,"Scourge":.5,"Ultralisk":4,"Defiler":2,"Queen":2,"Guardian":2,"Devourer":2,"Drone":1,
 "Marine":1,"Firebat":1,"Medic":1,"Ghost":1,"SCV":1,"Vulture":2,"Siege Tank (Tank Mode)":2,"Siege Tank (Siege Mode)":2,"Goliath":2,"Wraith":2,"Valkyrie":3,"Dropship":2,"Science Vessel":2,"Battlecruiser":6,
 "Zealot":2,"Dragoon":2,"High Templar":2,"Dark Templar":2,"Archon":4,"Dark Archon":4,"Reaver":4,"Shuttle":2,"Observer":1,"Scout":3,"Corsair":2,"Carrier":6,"Arbiter":4,"Probe":1}
COACH_WORKERS={"SCV","Drone","Probe"}
COACH_GAS={"Refinery","Assimilator","Extractor"}
COACH_PROD={"T":{"Barracks","Factory","Starport"},"P":{"Gateway","Robotics Facility","Stargate"},"Z":{"Hatchery","Lair","Hive"}}
COACH_WIN_TECH={"Z":{"Defiler":"디파일러","Lurker":"러커","Ultralisk":"울트라","Guardian":"가디언"},
 "T":{"Science Vessel":"사이언스베슬","Siege Tank (Tank Mode)":"시즈탱크","Battlecruiser":"배틀크루저"},
 "P":{"High Templar":"하이템플러","Archon":"아콘","Reaver":"리버","Arbiter":"아비터","Carrier":"캐리어"}}
COACH_UKR={"Marine":"마린","Firebat":"파벳","Medic":"메딕","Vulture":"벌처","Goliath":"골리앗","Wraith":"레이스","Dropship":"드랍십","Science Vessel":"베슬","Valkyrie":"발키리","Battlecruiser":"배틀","Ghost":"고스트",
 "Siege Tank (Tank Mode)":"탱크","Siege Tank (Siege Mode)":"탱크","Zealot":"질럿","Dragoon":"드라군","High Templar":"하템","Dark Templar":"다크","Archon":"아콘","Reaver":"리버","Corsair":"커세어","Carrier":"캐리어","Arbiter":"아비터","Scout":"스카웃","Shuttle":"셔틀",
 "Zergling":"저글링","Hydralisk":"히드라","Mutalisk":"뮤탈","Lurker":"러커","Ultralisk":"울트라","Defiler":"디파일러","Guardian":"가디언","Devourer":"디바우러","Scourge":"스컬지","Queen":"퀸"}
COACH_RACEKR={"T":"테란","P":"토스","Z":"저그","R":"랜덤"}
def _coach_sec(t):
    try: m,sx=str(t).split(":"); return int(m)*60+int(sx)
    except Exception: return 99999
def _coach_race(r, unames=None):
    r=(r or "").lower()
    if "toss" in r or "prot" in r: return "P"
    if "zerg" in r: return "Z"
    if "terr" in r: return "T"
    if r in ("p","pro"): return "P"
    if r in ("z","zer"): return "Z"
    if r in ("t","ter"): return "T"
    # "ran"/"random"/불명 → 유닛으로 추정
    if unames:
        n=set(unames)
        if n & {"SCV","Marine","Vulture","Goliath","Wraith","Siege Tank (Tank Mode)","Siege Tank"}: return "T"
        if n & {"Probe","Zealot","Dragoon","Dark Templar","Carrier","Corsair"}: return "P"
        if n & {"Drone","Zergling","Hydralisk","Mutalisk","Lurker"}: return "Z"
    return "T"
def _coach_first(build, names):
    for b in build:
        if b.get("name") in names: return b.get("t")
    return None
def coach_player(p, peers):
    unames=[u["name"] for u in p.get("units",[])]
    race=_coach_race(p.get("race"), unames); build=p.get("build",[])
    units={u["name"]:u for u in p.get("units",[])}
    pts=[]
    def T(tone,k,ti,tx): pts.append({"tone":tone,"k":k,"t":ti,"x":tx})
    gas=_coach_first(build, COACH_GAS)
    prodset=COACH_PROD[race]; prod_n=sum(1 for b in build if b.get("name") in prodset)
    ups=[b for b in build if b.get("cat") in ("upgrade","tech")]; up_n=len(ups); up1=ups[0]["t"] if ups else None
    exp=p["townhalls"][0]["t"] if p.get("townhalls") else None
    army=sum(units[n]["n"]*COACH_SUPPLY.get(n,1) for n in units if n not in COACH_WORKERS)
    workers=sum(units[n]["n"] for n in units if n in COACH_WORKERS)
    combat=sorted([(n,units[n]["n"]) for n in units if n not in COACH_WORKERS], key=lambda kv:-kv[1])
    top=combat[0] if combat else None
    apm=p.get("apm"); eapm=p.get("eapm"); series=p.get("apm_series") or [0]
    timings={"gas":gas,"prod":prod_n,"up_n":up_n,"up1":up1,"exp":exp,"army":round(army),"workers":workers,
             "max_supply":p.get("max_supply"),"supply200":p.get("supply200"),"total_supply":p.get("total_supply"),"tcount":len(p.get("townhalls",[]))}
    bnames={b.get("name") for b in build}
    # 빨무 핵심 1: 감지 수단(다크/럴커/클로킹/마인 대비). 저그는 오버로드가 자동 감지라 제외.
    if race=="P" and "Observer" not in units and "Photon Cannon" not in bnames:
        T("warn","det","감지 수단 없음","옵저버도 포토캐논도 안 보여. 빠른무한에선 상대 다크템플러·러커·벌처 마인을 못 보면 병력이 그냥 녹아. 옵저버 1~2기는 필수야.")
    elif race=="T" and "Science Vessel" not in units and "Missile Turret" not in bnames:
        T("tip","det","감지 수단 부족","베슬도 터렛도 안 보여. 상대 다크·러커·클로킹 레이스·드랍 대비로 터렛이나 베슬을 챙겨두는 게 안전해.")
    # 빨무 핵심 2: 일꾼 = 돈 = 물량. 자원 50덩이를 캐는 맵이라 일꾼 많을수록(~50기) 경제가 강함.
    if workers>=40:
        T("good","worker","일꾼 "+str(workers)+"기 — 경제 탄탄","일꾼을 넉넉히 뽑았네. 빠른무한은 자원 덩이를 일꾼으로 캐는 물량 싸움이라 일꾼=돈=병력이야. 경제 기반이 좋아 — 그만큼 병력·업글이 빠르게 나와.")
    elif workers<24:
        T("tip","worker","일꾼 "+str(workers)+"기 — 부족","일꾼이 적은 편이야. 빠른무한은 자원이 50덩이라 일꾼을 ~50기까지 꾸준히 뽑아야 돈이 넘쳐서 물량이 터져. 견제로 일꾼이 잘려도 바로 다시 채우는 게 중요해.")
    # 빨무 핵심 3: 멀티 = 일꾼 생산기지 추가 = 경제·견제 복구력. 본진 하나면 견제 한 방에 터짐.
    tc=len(p.get("townhalls",[]))
    if tc>=2:
        T("good","exp","멀티 "+str(tc)+"개 확보","멀티(추가 생산기지)를 잡았네. 빠른무한은 일꾼 생산처가 많을수록 견제로 일꾼이 잘려도 빨리 복구되고, 일꾼을 더 많이 굴려 물량도 빨라져. 좋은 판단이야.")
    else:
        T("tip","exp","본진 하나 — 멀티 권장","일꾼 생산기지가 본진 하나뿐이야. 빠른무한은 상대 견제(드랍/스플래시)로 뭉친 일꾼이 한 번에 몰살되면 본진 하나로는 복구가 느려 게임이 터질 수 있어. 멀티로 생산기지를 늘리면 훨씬 안전하고 물량도 빨라져.")
    peer_prod=[c["prod"] for c in peers if c]
    avg_prod=sum(peer_prod)/len(peer_prod) if peer_prod else prod_n
    if prod_n < max(3, avg_prod*0.7):
        T("tip","prod","생산 건물 "+str(prod_n)+"개","생산 건물이 다른 선수 평균("+("%.0f"%avg_prod)+")보다 적어. 빠른무한은 한방 싸움 뒤 다시 꽉 채우기(remax)가 핵심이라, 생산 건물을 늘리면 회복이 빨라져.")
    elif prod_n >= max(6, avg_prod*1.2):
        T("good","prod","생산력 좋음 "+str(prod_n)+"개","생산 건물을 넉넉히 지어서 병력 보충이 빨랐어. 이게 빠른무한의 기본기야.")
    if up_n==0:
        T("warn","up","업그레이드 없음","공격·방어 업그레이드가 하나도 없어. 빠른무한은 풀업 화력 싸움이라 1업만 차이나도 교전이 크게 갈려. 가스 올리자마자 업글부터 돌리자.")
    elif up_n<=2:
        T("tip","up","업그레이드 "+str(up_n)+"개 (첫 "+str(up1)+")","업그레이드가 적은 편이야. 병력 뽑는 것과 동시에 업글을 계속 돌리면 같은 병력으로도 화력이 확 올라가.")
    else:
        T("good","up","업그레이드 "+str(up_n)+"개","업그레이드를 꾸준히 돌렸네. 풀업 지향 좋아.")
    wt=COACH_WIN_TECH[race]; have_wt=[wt[n] for n in wt if n in units]
    if top:
        share=top[1]*COACH_SUPPLY.get(top[0],1)/army if army else 0
        topkr=COACH_UKR.get(top[0],top[0])
        if share>=.7 and not have_wt:
            recs=", ".join(list(wt.values())[:2])
            T("tip","comp",topkr+" 일변도","병력이 "+topkr+" 위주("+("%.0f"%(share*100))+"%)인데 상위 테크가 없어. 병력을 다 채우기 전에 "+recs+" 같은 게임체인저를 섞으면, 같은 인구수로도 광역기·한방 화력이 생겨서 한타가 뒤집혀.")
        elif have_wt:
            T("good","comp","테크 확보: "+", ".join(have_wt),"상위 테크 유닛을 확보했네. 빠른무한 후반은 이런 게임체인저 유무로 갈려. 좋은 판단이야.")
    if not have_wt:
        recs=", ".join(list(wt.values())[:3])
        T("tip","tech","상위 테크 추천","이번 판엔 "+COACH_RACEKR[race]+"의 결정타 유닛("+recs+")이 안 보였어. 물량이 갖춰지면 그 인구를 "+recs+"로 바꿔주는 게 '물량 다음 할 일'이야.")
    if army>=170:
        T("good","army","대군 운영 ~"+str(round(army))+"서플","병력 규모가 컸어(누적 추정 "+str(round(army))+"). 빠른무한은 물량을 빨리 채우고 바로 진출하는 게 중요해 — 꽉 채운 채 가만히 있으면 손해니, 풀업+상위테크 갖춰지면 바로 들어가자.")
    if len(series)>=3:
        body=series[:-1] if len(series)>3 else series
        med=sorted(body)[len(body)//2] if body else 0
        dip=[(i,v) for i,v in enumerate(body) if med>0 and v<med*0.55]
        if dip:
            i,v=dip[0]
            T("tip","apm",str(i)+"분에 손이 멈춤","이 구간 APM이 평소("+str(med)+")의 절반 아래로 떨어졌어. 교전에 집중하다 생산이 끊겼을 가능성이 커. 부대지정+생산 단축키로 싸우면서 뽑기를 연습하면 이 공백이 사라져.")
    if apm and eapm and apm-eapm>=70:
        T("tip","apm","APM "+str(apm)+" / 유효 "+str(eapm),"실제 명령(EAPM)에 비해 전체 APM이 꽤 높아 — 같은 곳 반복클릭이 많다는 뜻. 손은 빠르니, 그 손을 생산·멀티 분배에 쓰면 실질 효율이 올라가.")
    return timings, pts
def coach_report(a):
    base=[]
    for p in a.get("players",[]):
        unames=[u["name"] for u in p.get("units",[])]
        race=_coach_race(p.get("race"), unames); build=p.get("build",[])
        base.append({"prod":sum(1 for b in build if b.get("name") in COACH_PROD[race])})
    out=[]
    for i,p in enumerate(a.get("players",[])):
        peers=[b for j,b in enumerate(base) if j!=i]
        tm,pts=coach_player(p,peers)
        out.append({"id":p.get("id"),"name":p.get("name"),"race":p.get("race"),"timings":tm,"points":pts})
    return out

def _len_sec(l):
    try: m, s = l.split(":"); return int(m)*60+int(s)
    except Exception: return 0

RACE_KO = {"ran": "테란", "zerg": "저그", "toss": "프로토스"}

def add_comment(mid, author, body):
    if sb_enabled(): return sb_add_comment(mid, author, body)
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    c = db(); cur = c.execute("INSERT INTO comments(match_id,author,body,created) VALUES(?,?,?,?)",
                              (mid, author, body, ts)); c.commit()
    cid = cur.lastrowid; c.close()
    return {"id": cid, "author": author, "body": body, "created": ts}
def get_comments(mid):
    if sb_enabled(): return sb_get_comments(mid)
    c = db(); rows = c.execute("SELECT id,author,body,created FROM comments WHERE match_id=? ORDER BY id ASC",
                               (mid,)).fetchall(); c.close()
    return [dict(r) for r in rows]
def comment_counts(ids):
    if sb_enabled(): return sb_comment_counts(ids)
    if not ids: return {}
    c = db(); q = ",".join("?" * len(ids))
    out = dict(c.execute(f"SELECT match_id,COUNT(*) FROM comments WHERE match_id IN ({q}) GROUP BY match_id",
                         ids).fetchall()); c.close()
    return out
def bump_like(mid, delta):
    if sb_enabled(): return sb_like(mid, delta)
    c = db(); c.execute("UPDATE matches SET likes=MAX(0,COALESCE(likes,0)+?) WHERE id=?", (delta, mid)); c.commit()
    n = c.execute("SELECT COALESCE(likes,0) FROM matches WHERE id=?", (mid,)).fetchone(); c.close()
    return n[0] if n else 0
def bump_view(mid):
    if sb_enabled(): return sb_view(mid)
    c = db(); c.execute("UPDATE matches SET views=COALESCE(views,0)+1 WHERE id=?", (mid,)); c.commit(); c.close()

# ===================== Supabase 클라우드 (DB + Storage) =====================
# config 의 "supabase" 를 채우면 자동으로 켜짐. 비어 있으면 전부 로컬(SQLite)로 동작.
def sb_cfg(): return CFG.get("supabase") or {}
def sb_enabled():
    s = sb_cfg(); return bool(s.get("url") and (s.get("service_key") or s.get("anon_key")))
def sb_writable():
    """업로드(쓰기) 가능 = url + (service_role 또는 anon 키). anon은 RLS 정책 범위 내에서 쓰기."""
    s = sb_cfg(); return bool(s.get("url") and (s.get("service_key") or s.get("anon_key")))
def cloud_state():
    """('cloud'|'readonly'|'local')"""
    s = sb_cfg()
    if s.get("url") and (s.get("service_key") or s.get("anon_key")): return "cloud"
    return "local"
def _sb_base(): return (sb_cfg().get("url") or "").rstrip("/")
def _sb_key(write=False):
    s = sb_cfg()
    return (s.get("service_key") or s.get("anon_key")) if write else (s.get("anon_key") or s.get("service_key"))
def _sb_h(write=False, body_json=True):
    k = _sb_key(write); h = {"apikey": k, "Authorization": "Bearer " + (k or "")}
    if body_json: h["Content-Type"] = "application/json"
    return h
def _sb_bucket(): return sb_cfg().get("bucket") or "media"
def sb_upload(local, path, ctype):
    """Supabase Storage 업로드 → 공개 URL (버킷이 public 이어야 함)."""
    import requests
    base = _sb_base(); bk = _sb_bucket(); k = _sb_key(write=True)
    with open(local, "rb") as f:
        r = requests.post("%s/storage/v1/object/%s/%s" % (base, bk, path), data=f,
                          headers={"apikey": k, "Authorization": "Bearer " + k,
                                   "Content-Type": ctype, "x-upsert": "true"}, timeout=(10, 3600))
    if r.status_code not in (200, 201):
        raise RuntimeError("storage %s: %s" % (r.status_code, r.text[:200]))
    return "%s/storage/v1/object/public/%s/%s" % (base, bk, path)
def sb_insert_match(row):
    import requests
    r = requests.post(_sb_base() + "/rest/v1/matches",
                      headers={**_sb_h(write=True), "Prefer": "resolution=merge-duplicates,return=minimal"},
                      data=json.dumps(row, ensure_ascii=False).encode("utf-8"), timeout=60)
    if r.status_code not in (200, 201, 204):
        raise RuntimeError("insert %s: %s" % (r.status_code, r.text[:200]))
def _sb_get(path):
    import requests
    r = requests.get(_sb_base() + "/rest/v1/" + path, headers=_sb_h(), timeout=30)
    r.raise_for_status(); return r
def _sb_norm(d):
    if isinstance(d.get("analysis"), (dict, list)): d["analysis"] = json.dumps(d["analysis"], ensure_ascii=False)
    if not isinstance(d.get("players"), list):
        try: d["players"] = json.loads(d.get("players") or "[]")
        except Exception: d["players"] = []
    return d
def sb_get_matches(limit=24, offset=0):
    return [_sb_norm(x) for x in _sb_get("matches?select=*&order=uploaded.desc&limit=%d&offset=%d" % (limit, offset)).json()]
def sb_get_match(mid):
    rows = _sb_get("matches?id=eq.%s&select=*&limit=1" % mid).json()
    return _sb_norm(rows[0]) if rows else None
def sb_count_matches():
    import requests
    r = requests.get(_sb_base() + "/rest/v1/matches?select=id",
                     headers={**_sb_h(body_json=False), "Prefer": "count=exact", "Range": "0-0"}, timeout=30)
    cr = r.headers.get("content-range", "")
    try: return int(cr.split("/")[-1])
    except Exception:
        try: return len(r.json())
        except Exception: return 0
def sb_stats():
    rows = _sb_get("matches?select=length_sec,won").json()
    n = len(rows); tsec = sum(int(x.get("length_sec") or 0) for x in rows)
    rated = [x for x in rows if x.get("won") is not None]; w = sum(1 for x in rated if x.get("won"))
    return n, tsec, ("%d%%" % round(100*w/len(rated)) if rated else "—")
def sb_set_analysis(mid, js):
    import requests
    val = None
    if js:
        try: val = json.loads(js) if isinstance(js, str) else js
        except Exception: val = None
    requests.patch(_sb_base() + "/rest/v1/matches?id=eq.%s" % mid,
                   headers={**_sb_h(write=True), "Prefer": "return=minimal"},
                   data=json.dumps({"analysis": val}, ensure_ascii=False).encode("utf-8"), timeout=30)
def sb_get_comments(mid):
    return _sb_get("comments?match_id=eq.%s&select=id,author,body,created&order=created.asc" % mid).json()
def sb_add_comment(mid, author, body):
    import requests
    r = requests.post(_sb_base() + "/rest/v1/comments",
                      headers={**_sb_h(write=False), "Prefer": "return=representation"},
                      data=json.dumps({"match_id": mid, "author": author, "body": body}, ensure_ascii=False).encode("utf-8"), timeout=30)
    try: return r.json()[0]
    except Exception:
        return {"author": author, "body": body, "created": datetime.datetime.now().isoformat(timespec="seconds")}
def sb_comment_counts(ids):
    if not ids: return {}
    rows = _sb_get("comments?match_id=in.(%s)&select=match_id" % ",".join(ids)).json()
    out = {}
    for r in rows: out[r["match_id"]] = out.get(r["match_id"], 0) + 1
    return out
def sb_like(mid, delta):
    import requests
    r = requests.post(_sb_base() + "/rest/v1/rpc/like_match", headers=_sb_h(),
                      data=json.dumps({"mid": mid, "delta": delta}), timeout=30)
    try: return int(r.json())
    except Exception: return 0
def sb_view(mid):
    import requests
    try: requests.post(_sb_base() + "/rest/v1/rpc/bump_view", headers=_sb_h(), data=json.dumps({"mid": mid}), timeout=15)
    except Exception: pass
def sb_player_games(name):
    rows = sb_get_matches(limit=300, offset=0)
    return [r for r in rows if any((p.get("name") == name) for p in (r.get("players") or []))]

def sync_existing_to_cloud(log_fn=None):
    """로컬(SQLite)에 쌓인 기존 경기들을 Supabase 로 업로드. 이미 올라간 건 건너뜀."""
    lg = log_fn or log
    if not sb_writable():
        if sb_cfg().get("url") and sb_cfg().get("anon_key"):
            lg("⚠ Supabase service_role 키가 비어있어요 → config.json 의 supabase.service_key 에 넣고 재시작하세요.")
        else:
            lg("Supabase 설정이 없어요. config.json 의 supabase 를 먼저 채워주세요.")
        return (0, 0, 0)
    rebuild_db_from_recordings(lg)   # 폴더엔 있는데 DB엔 없는 경기 먼저 복구
    c = db()
    try: rows = c.execute("SELECT * FROM matches ORDER BY id ASC").fetchall()
    finally: c.close()
    lg(f"기존 경기 {len(rows)}개 확인 — Supabase 로 업로드 시작…")
    done = skipped = failed = 0
    for r in rows:
        d = _row(r); mid = d.get("id")
        if not mid: continue
        v = d.get("video") or ""
        if v.startswith("http"): skipped += 1; continue           # 이미 클라우드 URL
        try:
            if sb_get_match(mid): skipped += 1; continue           # 이미 등록됨
        except Exception: pass
        vlocal = os.path.join(UPLOAD_DIR, v) if v else None
        if not (vlocal and os.path.isfile(vlocal)):
            lg(f"  · 건너뜀(영상 파일 없음): {d.get('map') or mid}"); skipped += 1; continue
        tlocal = os.path.join(UPLOAD_DIR, d.get("thumb")) if d.get("thumb") else None
        rlocal = os.path.join(UPLOAD_DIR, d.get("replay")) if d.get("replay") else None
        try:
            lg(f"  · 업로드 중: {d.get('map') or mid} ({(d.get('video_size') or 0)/1048576:.0f}MB)…")
            video_url = sb_upload(vlocal, f"videos/{mid}.mp4", "video/mp4")
            thumb_url = sb_upload(tlocal, f"thumbs/{mid}.jpg", "image/jpeg") if (tlocal and os.path.isfile(tlocal)) else None
            replay_url = sb_upload(rlocal, f"replays/{mid}.rep", "application/octet-stream") if (rlocal and os.path.isfile(rlocal)) else None
            analysis = None
            if d.get("analysis"):
                try: analysis = json.loads(d["analysis"])
                except Exception: analysis = None
            if analysis is None and rlocal and os.path.isfile(rlocal):
                try:
                    analysis = extract_analysis(rlocal)
                    try: analysis["highlights"] = compute_highlights(analysis)
                    except Exception: pass
                except Exception: pass
            sb_insert_match({
                "id": mid, "uploader": d.get("uploader"),
                "uploaded": d.get("uploaded") or datetime.datetime.now().isoformat(timespec="seconds"),
                "video": video_url, "thumb": thumb_url, "replay": replay_url,
                "video_size": d.get("video_size") or 0, "map": d.get("map"), "matchup": d.get("matchup"),
                "length": d.get("length"), "length_sec": d.get("length_sec") or 0,
                "type": d.get("type"), "winner": d.get("winner"), "saver": d.get("saver"),
                "np": d.get("np") or len(d.get("players") or []), "players": d.get("players") or [],
                "won": (bool(d["won"]) if d.get("won") is not None else None), "analysis": analysis})
            done += 1; lg(f"    ✓ 완료: {d.get('map') or mid}")
        except Exception as e:
            failed += 1; lg(f"    ✗ 실패({mid}): {e}")
    lg(f"기존 경기 업로드 끝 — 완료 {done} · 건너뜀 {skipped} · 실패 {failed}")
    return (done, skipped, failed)


def _gid_time(gid):
    try:
        return datetime.datetime.strptime((gid or "")[:15], "%Y%m%d-%H%M%S").isoformat(timespec="seconds")
    except Exception:
        return datetime.datetime.now().isoformat(timespec="seconds")

def rebuild_db_from_recordings(log_fn=None):
    """recordings/ 또는 uploads/ 폴더에 영상은 있는데 DB에 없는 경기를 스캔해 복구(+옛 위치는 uploads로 정규화)."""
    lg = log_fn or log
    try:
        c = db()
        try: have = {row[0] for row in c.execute("SELECT id FROM matches").fetchall()}
        finally: c.close()
    except Exception:
        have = set()
    found = added = moved = 0; seen = set()
    for srcdir in (REC_DIR, UPLOAD_DIR):
        if not os.path.isdir(srcdir): continue
        for name in sorted(os.listdir(srcdir)):
            d = os.path.join(srcdir, name)
            if not os.path.isdir(d) or not os.path.isfile(os.path.join(d, "game.mp4")): continue
            gid = name
            if gid in seen: continue
            seen.add(gid); found += 1
            if gid in have: continue
            target = os.path.join(UPLOAD_DIR, gid)
            if os.path.abspath(d) != os.path.abspath(target):
                if os.path.exists(target):
                    if not os.path.isfile(os.path.join(target, "game.mp4")): continue
                    d = target
                else:
                    try: shutil.move(d, target); d = target; moved += 1
                    except Exception as e:
                        lg(f"  · 폴더 이동 실패({gid}): {e}"); continue
            video = os.path.join(d, "game.mp4"); rep = os.path.join(d, "replay.rep"); thumb = os.path.join(d, "thumb.jpg")
            try: size = os.path.getsize(video)
            except Exception: size = 0
            meta = {}
            if os.path.isfile(rep) and SCREP:
                try: meta = parse_rep(rep)
                except Exception as e: lg(f"  · 리플레이 분석 실패({gid}): {e}")
            if not os.path.isfile(thumb):
                try: make_thumb(video, thumb)
                except Exception: pass
            players = meta.get("players") or []; saver = meta.get("saver"); winner = meta.get("winner")
            sp = next((p for p in players if p.get("name") == saver), None)
            won = (1 if sp.get("team") == winner else 0) if (sp and winner) else None
            try:
                con = db()
                con.execute("INSERT OR REPLACE INTO matches (id,uploader,uploaded,video,replay,thumb,video_size,map,matchup,length,length_sec,type,winner,saver,np,players,won,analysis) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (gid, saver, _gid_time(gid), gid + "/game.mp4",
                     (gid + "/replay.rep" if os.path.isfile(rep) else None),
                     (gid + "/thumb.jpg" if os.path.isfile(thumb) else None),
                     size, meta.get("map"), meta.get("matchup"), meta.get("length"),
                     _len_sec(meta.get("length") or ""), meta.get("type"), winner, saver,
                     len(players), json.dumps(players, ensure_ascii=False), won, None))
                con.commit(); con.close()
                have.add(gid); added += 1
                lg(f"  · 복구: {meta.get('map') or gid} ({size/1048576:.0f}MB)")
            except Exception as e:
                lg(f"  · DB 복구 실패({gid}): {e}")
    if found:
        lg(f"폴더 복구 — 발견 {found} · 새로 추가 {added} · 이동 {moved}")
    return added


def player_games(name):
    if sb_enabled(): return sb_player_games(name)
    c = db(); rows = c.execute("SELECT * FROM matches ORDER BY id DESC").fetchall(); c.close()
    out = []
    for r in rows:
        d = _row(r)
        if any(p.get("name") == name for p in (d.get("players") or [])): out.append(d)
    return out

# ----- R2 (Cloudflare, S3 호환) : 큰 영상은 여기로 직접 -----
def _boto3():
    try:
        import boto3; return boto3
    except ImportError:
        log("boto3 설치 중…")
        _run([sys.executable, "-m", "pip", "install", "-q", "boto3", "--break-system-packages"])
        import boto3; return boto3
def r2_cfg(): return CFG.get("r2") or {}
def r2_enabled():
    r = r2_cfg()
    return bool(r.get("account_id") and r.get("bucket") and r.get("access_key_id") and r.get("secret_access_key"))
def r2_client():
    r = r2_cfg(); b = _boto3()
    return b.client("s3", endpoint_url=f"https://{r['account_id']}.r2.cloudflarestorage.com",
                    aws_access_key_id=r["access_key_id"], aws_secret_access_key=r["secret_access_key"],
                    region_name="auto")
def r2_public(key):
    base = (r2_cfg().get("public_base_url") or "").rstrip("/")
    return f"{base}/{key}" if base else key
def r2_upload(local, key, ctype):
    r2_client().upload_file(local, r2_cfg()["bucket"], key, ExtraArgs={"ContentType": ctype})
    return r2_public(key)
def r2_presign_put(key, ctype, expires=3600):
    return r2_client().generate_presigned_url("put_object",
        Params={"Bucket": r2_cfg()["bucket"], "Key": key, "ContentType": ctype}, ExpiresIn=expires)

def _insert_match(gid, video, replay, thumb, size, uploader, meta):
    players = meta.get("players") or []; saver = meta.get("saver"); winner = meta.get("winner")
    sp = next((p for p in players if p.get("name") == saver), None)
    won = (1 if sp.get("team") == winner else 0) if (sp and winner) else None
    c = db()
    c.execute("INSERT OR REPLACE INTO matches (id,uploader,uploaded,video,replay,thumb,video_size,map,matchup,length,length_sec,type,winner,saver,np,players,won,analysis) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (gid, uploader or saver, datetime.datetime.now().isoformat(timespec="seconds"),
         video, replay, thumb, size or 0,
         meta.get("map"), meta.get("matchup"), meta.get("length"), _len_sec(meta.get("length") or ""),
         meta.get("type"), winner, saver, len(players),
         json.dumps(players, ensure_ascii=False), won, None))
    c.commit(); c.close()
    tag = " [R2]" if (video or "").startswith("http") else ""
    log(f"✓ 등록됨: {meta.get('map') or '게임'} ({(size or 0)/1048576:.0f}MB) by {uploader or saver or '?'}{tag}")

def _trim_lead(video_path, game_len_sec, lead=6.0):
    """로비/로딩 구간을 잘라 카운트다운(게임 시작 ~6초 전)부터 시작하게. 게임은 영상 끝에서 game_len_sec 길이라 끝에서 역산(-sseof)."""
    if not (FFMPEG and video_path and game_len_sec): return
    try:
        keep = float(game_len_sec) + lead
        tmp = video_path + ".trim.mp4"
        r = _run([FFMPEG, "-y", "-loglevel", "error", "-sseof", f"-{keep:.2f}",
                  "-i", video_path, "-c", "copy", "-avoid_negative_ts", "make_zero", tmp],
                 capture_output=True)
        if r.returncode == 0 and os.path.isfile(tmp) and os.path.getsize(tmp) > 1024:
            os.replace(tmp, video_path)
            log("영상 앞 로비/로딩을 잘라 카운트다운부터 시작하도록 정리했어")
        else:
            try: os.remove(tmp)
            except OSError: pass
    except Exception as e:
        log(f"영상 트림 건너뜀(원본 유지): {e}")

def ingest(video_path, rep_path, uploader=None):
    if not video_path or not os.path.isfile(video_path) or os.path.getsize(video_path) < 10000:
        log("영상이 비어있어 등록 생략."); return
    gid = datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
    size = os.path.getsize(video_path)
    base = os.path.join(UPLOAD_DIR, gid); os.makedirs(base, exist_ok=True)
    # .rep(작음)은 항상 로컬 보관 — 분석/다운로드용
    rdst = None; meta = {}
    if rep_path and os.path.isfile(rep_path):
        rdst = os.path.join(base, "replay.rep"); shutil.copy(rep_path, rdst); meta = parse_rep(rdst)
    replay_ref = f"{gid}/replay.rep" if rdst else None
    # 리플레이가 없거나(메뉴·대기 화면) 분석할 선수 정보가 없으면 = 게임이 아님 → 저장하지 않고 폐기(용량 낭비 방지)
    if not (rdst and (meta.get("players"))):
        secs = ""
        try: secs = f"({os.path.getsize(video_path)/1048576:.0f}MB)"
        except Exception: pass
        log(f"리플레이가 없는 녹화 {secs} 는 게임이 아니라서 저장하지 않고 버립니다.")
        try:
            if video_path and os.path.isfile(video_path): os.remove(video_path)
        except OSError: pass
        try:
            import shutil as _sh2; _sh2.rmtree(base, ignore_errors=True)
        except Exception: pass
        return
    # 너무 짧은 게임(초반에 나간 게임 등)은 저장하지 않음
    _gsec = _len_sec(meta.get("length") or "")
    if _gsec and _gsec < CFG.get("min_game_sec", 120):
        log(f"게임이 너무 짧아({meta.get('length')}) 저장하지 않고 버립니다 — 초반에 끝난 게임으로 보입니다.")
        try:
            if video_path and os.path.isfile(video_path): os.remove(video_path)
        except OSError: pass
        try:
            import shutil as _sh3; _sh3.rmtree(base, ignore_errors=True)
        except Exception: pass
        return
    # 영상 앞 로비/로딩을 잘라 카운트다운(0:00)부터 보이게
    try:
        _gl = _len_sec(meta.get("length") or "")
        if _gl and video_path and os.path.isfile(video_path): _trim_lead(video_path, _gl)
    except Exception: pass
    if sb_writable():
        tmp_thumb = os.path.join(base, "thumb.jpg"); has_thumb = make_thumb(video_path, tmp_thumb)
        analysis = None
        try:
            if rdst:
                analysis = extract_analysis(rdst)
                try: analysis["highlights"] = compute_highlights(analysis)
                except Exception: pass
        except Exception as e:
            log(f"분석 실패(계속 진행): {e}")
        try:
            video_url = sb_upload(video_path, f"videos/{gid}.mp4", "video/mp4")
            thumb_url = sb_upload(tmp_thumb, f"thumbs/{gid}.jpg", "image/jpeg") if has_thumb else None
            replay_url = sb_upload(rdst, f"replays/{gid}.rep", "application/octet-stream") if rdst else None
            players = meta.get("players") or []; saver = meta.get("saver"); winner = meta.get("winner")
            sp = next((p for p in players if p.get("name") == saver), None)
            won = (sp.get("team") == winner) if (sp and winner is not None) else None
            sb_insert_match({
                "id": gid, "uploader": uploader or saver,
                "uploaded": datetime.datetime.now().isoformat(timespec="seconds"),
                "video": video_url, "thumb": thumb_url, "replay": replay_url,
                "video_size": size or 0, "map": meta.get("map"), "matchup": meta.get("matchup"),
                "length": meta.get("length"), "length_sec": _len_sec(meta.get("length") or ""),
                "type": meta.get("type"), "winner": winner, "saver": saver,
                "np": len(players), "players": players, "won": won, "analysis": analysis})
            for p in (video_path, tmp_thumb):
                try: os.remove(p)
                except OSError: pass
            log(f"☁ Supabase 등록: {meta.get('map') or '게임'} ({(size or 0)/1048576:.0f}MB) by {uploader or saver or '?'}")
            return
        except Exception as e:
            log(f"Supabase 업로드/저장 실패: {e} — 로컬에 보관합니다.")
    if r2_enabled():
        tmp_thumb = os.path.join(base, "thumb.jpg"); has_thumb = make_thumb(video_path, tmp_thumb)
        try:
            video_ref = r2_upload(video_path, f"videos/{gid}.mp4", "video/mp4")
            thumb_ref = r2_upload(tmp_thumb, f"thumbs/{gid}.jpg", "image/jpeg") if has_thumb else None
        except Exception as e:
            log(f"R2 업로드 실패: {e}"); return
        for p in (video_path, tmp_thumb):
            try: os.remove(p)
            except OSError: pass
        _insert_match(gid, video_ref, replay_ref, thumb_ref, size, uploader, meta)
    else:
        vdst = os.path.join(base, "game.mp4"); shutil.move(video_path, vdst)
        thumb = os.path.join(base, "thumb.jpg"); has_thumb = make_thumb(vdst, thumb)
        _insert_match(gid, f"{gid}/game.mp4", replay_ref,
                      (f"{gid}/thumb.jpg" if has_thumb else None), size, uploader, meta)

# ===================== 5. 갤러리 서버 (ENCORE UI) =====================
app = Flask(__name__)
import logging; logging.getLogger("werkzeug").setLevel(logging.ERROR)

def make_thumb(video, out):
    if not FFMPEG: return False
    for ts in ("120", "60", "20", "5", "1", "0.5"):
        try:
            _run([FFMPEG, "-y", "-loglevel", "error", "-ss", ts, "-i", video,
                            "-frames:v", "1", "-vf", "scale=640:-2", out], timeout=30)
            if os.path.isfile(out) and os.path.getsize(out) > 2000:
                return True
        except Exception:
            pass
    return False

def esc(s): return html.escape(str(s)) if s is not None else ""
def _team_color(players, t):
    cs = [p.get("color") for p in players if p.get("team") == t]
    return cs[0] if cs else "#7c8a99"

def _media_url(v):
    if not v: return ""
    return v if v.startswith("http") else "/media/" + v

def _game_view(r):
    players = r.get("players") or []
    saver = r.get("saver"); winner = r.get("winner")
    sp = next((p for p in players if p.get("name") == saver), None)
    won = (sp.get("team") == winner) if (sp and winner) else None
    return {"map": r.get("map") or "게임 영상", "matchup": r.get("matchup") or "",
            "length": r.get("length") or "", "np": len(players) or 0,
            "winner": winner, "players": players, "me": saver, "won": won,
            "date": (r.get("uploaded") or "")[:10],
            "video_url": _media_url(r.get("video")),
            "thumb_url": _media_url(r.get("thumb")) if r.get("thumb") else None,
            "rep_url": (_media_url(r["replay"]) + "?dl=1") if r.get("replay") else None,
            "id": r.get("id"), "match_url": "/match/" + (r.get("id") or ""), "uploader": r.get("uploader"),
            "likes": r.get("likes") or 0, "views": r.get("views") or 0, "uploaded": r.get("uploaded") or ""}

def _roster(g, t, compact=False):
    rows = ""
    for p in [x for x in g["players"] if x.get("team") == t]:
        me = "me" if p.get("name") == g.get("me") else ""
        apm = "" if compact else f'<span class="ap">{p.get("apm") or 0}<i>apm</i></span>'
        rc = (p.get("race") or "?")[0].upper()
        rows += (f'<li class="prow {me}"><span class="cc" style="background:{esc(p.get("color"))}"></span>'
                 f'<a class="pn pnl" href="/player/{quote(p.get("name") or "")}">{esc(p.get("name")) or "—"}</a>'
                 f'<span class="rb r-{esc(p.get("race"))}">{rc}</span>{apm}</li>')
    return rows

def _teams(g, compact=False):
    w = g.get("winner")
    def one(t):
        wc = "is-win" if w == t else ""
        tag = '<span class="wtag">WIN</span>' if w == t else ""
        return (f'<div class="team {wc}"><div class="thead"><span class="tnum">TEAM {t}</span>{tag}</div>'
                f'<ul class="roster">{_roster(g, t, compact)}</ul></div>')
    return f'{one(1)}<div class="vsbar"><span>VS</span></div>{one(2)}'

def _resbadge(g, big=False):
    w = g.get("won"); cls = "win" if w is True else ("loss" if w is False else "na")
    txt = "승리" if w is True else ("패배" if w is False else "기록")
    return f'<span class="resbadge {cls} {"big" if big else ""}">{txt}</span>'

def _poster(g, big=False):
    c1, c2 = _team_color(g["players"], 1), _team_color(g["players"], 2)
    pa = f' poster="{esc(g["thumb_url"])}"' if g.get("thumb_url") else ""
    inner = f'<video controls preload="metadata"{pa} src="{esc(g["video_url"])}"></video>'
    return (f'<div class="poster {"big" if big else ""}" style="--c1:{c1};--c2:{c2}">'
            f'<div class="pscan"></div><div class="pgrid"></div>{inner}{_resbadge(g, big)}'
            f'<div class="pmeta"><span class="mu">{esc(g["matchup"])}</span>'
            f'<span class="pln">◷ {esc(g["length"])}</span></div></div>')

_IC_PLAY='<svg class="ic" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.14v13.72a1 1 0 0 0 1.52.86l11.43-6.86a1 1 0 0 0 0-1.72L9.52 4.28A1 1 0 0 0 8 5.14Z"/></svg>'
_IC_CLOCK='<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7.5V12l3.2 1.9"/></svg>'
_IC_HEART='<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20.5C6.5 16.5 3 13 3 9.2 3 6.6 5 4.5 7.6 4.5c1.7 0 3.2.9 4.4 2.6 1.2-1.7 2.7-2.6 4.4-2.6C19 4.5 21 6.6 21 9.2c0 3.8-3.5 7.3-9 11.3Z"/></svg>'
_IC_EYE='<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="2.5"/></svg>'
_IC_TROPHY='<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 4h10v5a5 5 0 0 1-10 0V4ZM7 6H4v1a3 3 0 0 0 3 3M17 6h3v1a3 3 0 0 1-3 3M9 17h6M12 14v3M9 21h6"/></svg>'
_IC_BOOKMARK='<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 4h12a1 1 0 0 1 1 1v15l-7-4-7 4V5a1 1 0 0 1 1-1Z"/></svg>'
_IC_FILTER='<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h16M7 12h10M10 18h4"/></svg>'
_IC_CHEV='<svg class="cv" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>'

def _ago(iso):
    if not iso: return ""
    try:
        from datetime import datetime
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        now = datetime.now(d.tzinfo) if d.tzinfo else datetime.now()
        sx = (now - d).total_seconds()
    except Exception:
        return str(iso)[:10]
    if sx < 60: return "방금"
    if sx < 3600: return f"{int(sx//60)}분 전"
    if sx < 86400: return f"{int(sx//3600)}시간 전"
    if sx < 604800: return f"{int(sx//86400)}일 전"
    return str(iso)[:10]

def _stat(v, k, acc=False):
    return f'<div class="stat"><div class="v {"acc" if acc else ""}">{v}</div><div class="k">{k}</div></div>'

def _dots(g, t):
    cs = [p.get("color") or "#555" for p in g["players"] if p.get("team") == t][:4]
    return '<span class="dots">' + "".join(f'<i style="background:{esc(c)}"></i>' for c in cs) + '</span>'

def _restag(g):
    w = g.get("won")
    if w is True:  return f'<span class="res w">{_IC_TROPHY}승리</span>'
    if w is False: return '<span class="res l">패배</span>'
    return '<span class="res n">기록됨</span>'

def _tags(g):
    n = g.get("np") or 0
    mu = f'<span class="tag">{esc(g["matchup"])}</span>' if g.get("matchup") else ""
    return f'<span class="tag acc">{n//2}v{n//2}</span>{mu}'

def _thumb_attr(g):
    if g.get("thumb_url"):
        return f' style="background:#000 center/cover no-repeat url(&quot;{esc(g["thumb_url"])}&quot;)"', ""
    return "", f'<div class="wm">{esc(g["map"])}</div>'

def _card(g, idx=0):
    st, wm = _thumb_attr(g)
    who = esc(g.get("me") or g.get("uploader") or "?")
    return (f'<div class="card" data-map="{esc(g["map"])}" data-href="{esc(g["match_url"])}">'
            f'<div class="thumb"{st}>{wm}{_restag(g)}'
            f'<button class="bm">{_IC_BOOKMARK}</button>'
            f'<span class="dur">{_IC_CLOCK}{esc(g["length"])}</span>'
            f'<div class="play"><span>{_IC_PLAY}</span></div></div>'
            f'<div class="cbody"><div class="cmap">{esc(g["map"])}</div><div class="ctags">{_tags(g)}</div>'
            f'<div class="teams">{_dots(g,1)}<span class="vs">vs</span>{_dots(g,2)}</div>'
            f'<div class="cfoot"><span class="up">{who}</span><span class="sp"></span>'
            f'<span class="m">{_IC_HEART}{g.get("likes",0)}</span><span class="m">{_IC_EYE}{g.get("views",0)}</span>'
            f'<span>{esc(_ago(g.get("uploaded")))}</span></div></div></div>')

def _feat(g):
    st, wm = _thumb_attr(g)
    n = g.get("np") or 0
    who = esc(g.get("me") or g.get("uploader") or "?")
    return (f'<div class="feat" data-href="{esc(g["match_url"])}">'
            f'<div class="ft"{st}>{wm}'
            f'<button class="bm">{_IC_BOOKMARK}</button>'
            f'<span class="dur">{_IC_CLOCK}{esc(g["length"])}</span><div class="play">{_IC_PLAY}</div></div>'
            f'<div class="fb"><div class="eb"><span class="dd"></span>방금 올라온 경기</div><h2>{esc(g["map"])}</h2>'
            f'<div class="ctags">{_tags(g)}<span class="tag">{n}인전</span></div>'
            f'<div class="teams">{_dots(g,1)}<span class="vs">vs</span>{_dots(g,2)}</div>'
            f'<div class="cfoot" style="margin-top:2px"><span class="up">{who}</span><span class="sp"></span>'
            f'<span class="m">{_IC_HEART}{g.get("likes",0)}</span><span class="m">{_IC_EYE}{g.get("views",0)}</span></div></div></div>')

def _archive_head():
    return ('<div class="head"><div class="eb">Brood War Archive</div>'
            '<h1>경기 아카이브</h1>'
            '<p class="desc">PC방 불빛 아래 밤을 지새우던 스무 살. 크루와 함께 <b>그때 그 명경기를 영상으로</b> 다시 만납니다.<br>다시 보고 싶은 명경기를 골라보세요.</p></div>')

def _toolbar(stats_html):
    tools = (f'<div class="tools"><button class="ctrl"><span class="lbl">정렬</span><span>최신순</span>{_IC_CHEV}</button>'
             f'<button class="ctrl">{_IC_FILTER}필터</button></div>')
    return f'<div class="toolbar"><div class="stats">{stats_html}</div>{tools}</div>'

def _player_hero(name, av, games, wr, avg, rc):
    return (f'<section class="phero"><a class="pback" href="/">‹ 아카이브</a>'
            f'<div class="prow"><div class="phav">{esc(av)}</div>'
            f'<div><div class="pey">Player Profile</div><h1 class="pname">{esc(name)}</h1></div></div>'
            f'<div class="pstats">{_stat(games,"경기")}{_stat(wr,"승률",True)}{_stat(avg,"평균 APM")}'
            f'<div class="stat"><div class="v" style="font-size:15px;font-weight:600">{esc(rc)}</div><div class="k">종족</div></div></div></section>')

PAGE = r"""<!doctype html><html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ENCORE — Brood War Archive</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/sun-typeface/SUIT@2/fonts/variable/woff2/SUIT-Variable.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/sun-typeface/SUITE@2/fonts/variable/woff2/SUITE-Variable.css">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{
 --bg:#0C0D10;--surface:#131519;--surface2:#181B21;--hover:#1D2128;--well:#0E0F13;
 --ink:#ECEEF2;--ink2:#C5C9D0;--dim:#9AA0AA;--faint:#636872;
 --line:#1F232B;--line2:#2C313B;
 --acc:#3D8BFF;--acc-ink:#62A1FF;--acc-soft:rgba(61,139,255,.12);--acc-line:rgba(61,139,255,.34);
 --win:#3D8BFF;--loss:#E8694C;--gold:#E0B441;--blue:#5BA3E0;--violet:#C07BE0;
 --h-battle:#F0703C;--h-tech:#3D8BFF;--h-expand:#C07BE0;
 --r-ran:#5BA3E0;--r-zerg:#C07BE0;--r-toss:#E0B441;
 --fd:'SUIT Variable','Apple SD Gothic Neo','Malgun Gothic',system-ui,sans-serif;
 --fh:'SUITE Variable','SUIT Variable',sans-serif;
 --fm:'IBM Plex Mono',ui-monospace,monospace;
 --r1:10px;--r2:14px;--r3:18px;--sh:0 16px 40px -20px rgba(0,0,0,.72);
}
*{box-sizing:border-box}html,body{margin:0}
body{background:var(--bg);color:var(--ink);font-family:var(--fd);font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased;letter-spacing:.005em}
a{color:inherit;text-decoration:none}svg{display:block}
.ic{width:1em;height:1em;flex-shrink:0}
::-webkit-scrollbar{width:10px;height:10px}::-webkit-scrollbar-thumb{background:var(--line2);border-radius:6px;border:3px solid var(--bg)}
.wrap{max-width:1180px;margin:0 auto;padding:0 28px 120px}

.bar{position:sticky;top:0;z-index:50;background:var(--bg);border-bottom:1px solid var(--line)}.bar.scrolled{box-shadow:0 6px 22px rgba(0,0,0,.4)}
.bar.scrolled{border-color:var(--line)}
.bar-in{max-width:1180px;margin:0 auto;padding:14px 28px;display:flex;align-items:center;gap:18px}
.brand{display:flex;align-items:center;gap:10px}
.brand .gem{width:19px;height:19px;border-radius:6px;background:linear-gradient(140deg,#62A1FF,#2563c9);box-shadow:0 0 0 1px rgba(255,255,255,.06) inset,0 4px 12px -3px rgba(61,139,255,.5);position:relative}
.brand .gem::after{content:"";position:absolute;inset:4px;border-radius:3px;background:linear-gradient(140deg,rgba(255,255,255,.25),transparent)}
.brand .lgmk{width:20px;height:20px;color:var(--ink)}
.brand b{font-family:var(--fh);font-weight:800;font-size:17px;letter-spacing:.2em}
.nav{display:flex;gap:2px;margin-left:16px}
.nav a{font-family:var(--fd);font-weight:600;font-size:14px;color:var(--dim);padding:8px 14px;border-radius:var(--r1);transition:.15s}
.nav a.on{color:var(--ink);background:var(--surface)}.nav a:hover{color:var(--ink)}
.bar .sp{flex:1}
.search{display:flex;align-items:center;gap:9px;background:var(--surface);border:1px solid var(--line);border-radius:var(--r1);padding:9px 14px;width:248px;transition:.15s}
.search:focus-within{border-color:var(--acc-line);box-shadow:0 0 0 3px var(--acc-soft)}
.search .ic{width:15px;height:15px;color:var(--faint)}
.search input{background:none;border:0;outline:0;color:var(--ink);font-family:var(--fd);font-size:14px;width:100%}
.search input::placeholder{color:var(--faint)}
.live{display:inline-flex;align-items:center;gap:8px;font-family:var(--fm);font-size:12px;color:var(--dim);background:var(--surface);border:1px solid var(--line);padding:9px 13px;border-radius:100px}
.live .d{width:6px;height:6px;border-radius:50%;background:var(--acc);box-shadow:0 0 0 3px var(--acc-soft)}

.head{padding:44px 0 30px}
.head .eb{font-family:var(--fm);font-size:11px;letter-spacing:.26em;color:var(--acc);text-transform:uppercase;margin-bottom:16px}
.head h1{font-family:var(--fh);font-weight:800;font-size:clamp(34px,5vw,52px);margin:0;letter-spacing:-.025em;color:#F7F4EE;line-height:1}
.head .desc{font-family:var(--fd);font-size:16px;line-height:1.62;color:var(--ink2);margin:18px 0 0;max-width:600px}
.head .desc b{color:var(--ink);font-weight:600}

.toolbar{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:24px;padding-bottom:20px;border-bottom:1px solid var(--line)}
.stats{display:flex;gap:0}
.stat{padding:0 20px;border-left:1px solid var(--line)}
.stat:first-child{padding-left:0;border-left:0}
.stat .v{font-family:var(--fh);font-weight:800;font-size:21px;line-height:1;font-variant-numeric:tabular-nums}
.stat .v.acc{color:var(--acc-ink)}.stat .v small{font-size:12px;color:var(--dim);font-weight:600;margin-left:1px}
.stat .k{font-family:var(--fm);font-size:10px;letter-spacing:.09em;color:var(--faint);text-transform:uppercase;margin-top:7px}
.tools{display:flex;align-items:center;gap:9px}
.ctrl{display:inline-flex;align-items:center;gap:9px;font-family:var(--fd);font-weight:600;font-size:13.5px;color:var(--ink2);background:var(--surface);border:1px solid var(--line);padding:10px 14px;border-radius:var(--r1);cursor:pointer;transition:.15s}
.ctrl:hover{border-color:var(--line2);color:var(--ink);background:var(--hover)}
.ctrl .lbl{color:var(--faint);font-weight:500}
.ctrl .ic{width:15px;height:15px;color:var(--dim)}
.ctrl .cv{width:14px;height:14px;color:var(--faint)}

.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(286px,1fr));gap:20px}

.feat{grid-column:1/-1;display:grid;grid-template-columns:1.6fr 1fr;background:var(--surface);border:1px solid var(--line);border-radius:var(--r3);overflow:hidden;margin-bottom:4px;cursor:pointer;transition:.17s}
.feat:hover{border-color:var(--line2)}
.feat .ft{position:relative;aspect-ratio:16/9;background:radial-gradient(120% 100% at 50% 0,#1a201b,#0a0b08)}
.feat .ft .wm{position:absolute;inset:0;display:grid;place-items:center;font-family:var(--fh);font-weight:800;font-size:34px;color:rgba(241,238,231,.07);text-align:center;padding:0 24px;letter-spacing:-.01em}
.feat .ft .play{position:absolute;left:26px;bottom:26px;width:56px;height:56px;border-radius:50%;display:grid;place-items:center;background:rgba(70,190,136,.13);border:1px solid var(--acc-line);transition:.2s}
.feat:hover .ft .play{background:rgba(70,190,136,.22);transform:scale(1.05)}
.feat .ft .play .ic{width:22px;height:22px;color:var(--acc);margin-left:3px}
.dur{position:absolute;right:14px;bottom:14px;display:inline-flex;align-items:center;gap:6px;font-family:var(--fm);font-size:11.5px;color:var(--ink);background:rgba(6,6,4,.76);padding:5px 9px;border-radius:7px;backdrop-filter:blur(4px);font-variant-numeric:tabular-nums}
.dur .ic{width:12px;height:12px;color:var(--dim)}
.bm{position:absolute;right:12px;top:12px;width:32px;height:32px;border-radius:50%;display:grid;place-items:center;background:rgba(6,6,4,.6);border:1px solid rgba(255,255,255,.08);backdrop-filter:blur(4px);transition:.15s;z-index:3}
.bm .ic{width:15px;height:15px;color:var(--ink2)}
.bm:hover{background:rgba(6,6,4,.85)}.bm:hover .ic{color:var(--acc)}
.bm.on{background:var(--acc-soft);border-color:var(--acc-line)}.bm.on .ic{color:var(--acc);fill:var(--acc)}
.feat .fb{padding:32px 34px;display:flex;flex-direction:column;justify-content:center;gap:16px}
.feat .fb .eb{font-family:var(--fm);font-size:11px;letter-spacing:.2em;color:var(--acc);text-transform:uppercase;display:flex;align-items:center;gap:8px}
.feat .fb .eb .dd{width:6px;height:6px;border-radius:50%;background:var(--acc);box-shadow:0 0 0 3px var(--acc-soft)}
.feat .fb h2{font-family:var(--fh);font-weight:800;font-size:31px;margin:0;line-height:1.05;letter-spacing:-.02em}

.card{position:relative;background:var(--surface);border:1px solid var(--line);border-radius:var(--r2);overflow:hidden;cursor:pointer;transition:.16s;display:flex;flex-direction:column}
.card:hover{border-color:var(--line2);transform:translateY(-4px);box-shadow:var(--sh)}
.thumb{position:relative;aspect-ratio:16/9;background:radial-gradient(120% 100% at 50% 0,#191e1a,#0b0c09);overflow:hidden}
.thumb .wm{position:absolute;inset:0;display:grid;place-items:center;font-family:var(--fh);font-weight:800;font-size:clamp(20px,2.4vw,27px);color:rgba(241,238,231,.07);text-align:center;padding:0 16px;letter-spacing:-.01em}
.thumb .play{position:absolute;inset:0;display:grid;place-items:center;opacity:0;transition:.2s}
.card:hover .thumb .play{opacity:1}
.thumb .play span{width:50px;height:50px;border-radius:50%;background:rgba(70,190,136,.18);border:1px solid var(--acc-line);display:grid;place-items:center;backdrop-filter:blur(3px)}
.thumb .play .ic{width:20px;height:20px;color:var(--acc);margin-left:2px}
.res{position:absolute;left:12px;top:12px;display:inline-flex;align-items:center;gap:5px;font-family:var(--fm);font-size:10px;font-weight:600;letter-spacing:.04em;padding:5px 9px;border-radius:7px;backdrop-filter:blur(4px)}
.res .ic{width:11px;height:11px}
.res.w{color:var(--acc-ink);background:rgba(70,190,136,.16);border:1px solid var(--acc-line)}
.res.n{color:var(--ink2);background:rgba(6,6,4,.66);border:1px solid rgba(255,255,255,.07)}
.cbody{padding:15px 16px 16px;display:flex;flex-direction:column;gap:12px;flex:1}
.cmap{font-family:var(--fh);font-weight:800;font-size:18px;line-height:1.18;letter-spacing:-.012em;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ctags{display:flex;gap:6px;flex-wrap:wrap}
.tag{font-family:var(--fm);font-size:11px;color:var(--dim);background:var(--well);border:1px solid var(--line);padding:4px 9px;border-radius:6px;font-variant-numeric:tabular-nums}
.tag.acc{color:var(--acc-ink);background:var(--acc-soft);border-color:var(--acc-line)}
.teams{display:flex;align-items:center;gap:8px}
.dots{display:flex;gap:4px}
.dots i{width:10px;height:10px;border-radius:50%;display:inline-block;box-shadow:0 0 0 1.5px var(--surface)}
.vs{font-family:var(--fm);font-size:10.5px;color:var(--faint)}
.cfoot{display:flex;align-items:center;gap:12px;margin-top:auto;padding-top:6px;font-family:var(--fm);font-size:11.5px;color:var(--faint);font-variant-numeric:tabular-nums}
.cfoot .up{color:var(--dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cfoot .sp{flex:1}
.cfoot .m{display:inline-flex;align-items:center;gap:4px}.cfoot .m .ic{width:12px;height:12px}

@media(max-width:760px){.feat{grid-template-columns:1fr}.stats{display:none}.search,.nav{display:none}.toolbar{flex-direction:column;align-items:stretch}}
.ftr{margin-top:72px;padding-top:30px;border-top:1px solid var(--line);display:flex;justify-content:space-between;gap:30px;flex-wrap:wrap}.ftr-brand{display:flex;align-items:center;gap:9px;margin-bottom:13px}.ftr-brand .lgmk{width:18px;height:18px;color:var(--ink)}.ftr-brand b{font-family:var(--fh);font-weight:800;font-size:15px;letter-spacing:.18em}.ftr-l p{margin:5px 0;font-size:13px;line-height:1.6;color:var(--dim)}.ftr-by{font-family:var(--fd);font-size:13px;color:var(--dim);margin-top:13px!important}.ftr-by b{color:var(--ink2);font-weight:700}.ftr-by .hdl{font-family:var(--fm);font-size:12px;color:var(--faint)}.ftr-links{display:flex;flex-direction:column;gap:10px;font-size:13.5px}.ftr-links a{color:var(--dim);transition:.15s}.ftr-links a:hover{color:var(--ink)}.res.l{color:var(--loss);background:rgba(232,105,76,.15);border:1px solid color-mix(in srgb,var(--loss) 40%,transparent)}.empty{grid-column:1/-1;display:grid;place-items:center;padding:72px 20px}.ebox{max-width:430px;text-align:center}.ebox h2{font-family:var(--fh);font-weight:800;font-size:22px;margin:0 0 10px;color:var(--ink2)}.ebox p{color:var(--dim);font-size:14.5px;line-height:1.7;margin:0}.ebox b{color:var(--ink)}.phero{background:var(--surface);border:1px solid var(--line);border-radius:var(--r3);padding:26px 30px;margin:30px 0 26px}.pback{display:inline-flex;font-family:var(--fm);font-size:12px;color:var(--dim);margin-bottom:18px}.pback:hover{color:var(--ink)}.prow{display:flex;align-items:center;gap:18px;margin-bottom:22px}.phav{width:60px;height:60px;border-radius:16px;background:var(--acc-soft);border:1px solid var(--acc-line);display:grid;place-items:center;font-family:var(--fh);font-weight:800;font-size:26px;color:var(--acc-ink)}.pey{font-family:var(--fm);font-size:11px;letter-spacing:.22em;color:var(--acc);text-transform:uppercase;margin-bottom:6px}.pname{font-family:var(--fh);font-weight:800;font-size:clamp(26px,4vw,34px);margin:0;letter-spacing:-.02em}.pstats{display:flex;gap:0;flex-wrap:wrap}.pstats .stat{padding:0 22px;border-left:1px solid var(--line)}.pstats .stat:first-child{padding-left:0;border-left:0}.pager{grid-column:1/-1;display:flex;justify-content:center;align-items:center;gap:14px;margin-top:12px}.pgl{font-family:var(--fm);font-size:12px;color:var(--acc-ink);border:1px solid var(--acc-line);padding:8px 15px;border-radius:8px}.pgl.off{color:var(--faint);border-color:var(--line)}.pgn{font-family:var(--fm);font-size:12px;color:var(--faint)}</style></head><body>
<div class="bar" id="bar"><div class="bar-in">
 <div class="brand"><svg class="lgmk" viewBox="0 0 32 32" fill="currentColor"><rect x="3.5" y="20" width="6" height="8" rx="1.6"/><rect x="13" y="12.5" width="6" height="15.5" rx="1.6"/><rect x="22.5" y="5" width="6" height="23" rx="1.6"/></svg><b>ENCORE</b></div>
 <nav class="nav"><a class="on" href="/">아카이브</a><a href="/about">만든이</a><a href="/manual">매뉴얼</a><a href="/download">다운로드</a></nav>
 <span class="sp"></span>
 <div class="search"><span class="ic"><svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.2-3.2"/></svg></span><input id="q" placeholder="맵 · 아이디 검색"></div>
 <span class="live"><span class="d"></span>녹화 대기 중</span>
</div></div>
<div class="wrap">
<main id="view" data-page="archive">
__TOP__
 <div class="grid">__CARDS__</div>
</main>
 <footer class="ftr"><div class="ftr-l"><div class="ftr-brand"><svg class="lgmk" viewBox="0 0 32 32" fill="currentColor"><rect x="3.5" y="20" width="6" height="8" rx="1.6"/><rect x="13" y="12.5" width="6" height="15.5" rx="1.6"/><rect x="22.5" y="5" width="6" height="23" rx="1.6"/></svg><b>ENCORE</b></div><p>스무 살의 우리에게 — 다시, 브루드워.</p><p class="ftr-by">만든이 <b>최성호</b> · <span class="hdl">veatbox</span></p></div></footer>
</div>
<script>
addEventListener('scroll',()=>document.getElementById('bar').classList.toggle('scrolled',scrollY>8));
document.querySelectorAll('.card,.feat').forEach(el=>{el.addEventListener('click',e=>{const bm=e.target.closest('.bm');if(bm){bm.classList.toggle('on');return;}const h=el.dataset.href;if(h)location.href=h;});});
const q=document.getElementById('q');
if(q)q.addEventListener('input',()=>{const t=q.value.trim().toLowerCase();document.querySelectorAll('.card').forEach(c=>{const m=(c.dataset.map||'').toLowerCase();c.style.display=(!t||m.includes(t))?'':'none';});});
</script></body></html>"""

PAGE_SIZE = 24

@app.get("/")
def gallery():
    pg = max(1, int(request.args.get("page", 1) or 1))
    total = count_matches()
    rows = get_matches(PAGE_SIZE, (pg - 1) * PAGE_SIZE)
    games = [_game_view(r) for r in rows]
    cc = comment_counts([g["id"] for g in games])
    for g in games: g["comments"] = cc.get(g["id"], 0)
    n, tsec, wr = stats_global()
    stats = (_stat(n, "경기") + _stat(f"{tsec//3600}h {(tsec%3600)//60}m", "기록") + _stat(wr, "승률", True))
    top = _archive_head() + _toolbar(stats)
    if games:
        feat = _feat(games[0]) if pg == 1 else ""
        rest = games[1:] if pg == 1 else games
        cards = feat + "".join(_card(g, i) for i, g in enumerate(rest))
        pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
        if pages > 1:
            prev = f'<a class="pgl" href="/?page={pg-1}">‹ 이전</a>' if pg > 1 else '<span class="pgl off">‹ 이전</span>'
            nxt = f'<a class="pgl" href="/?page={pg+1}">다음 ›</a>' if pg < pages else '<span class="pgl off">다음 ›</span>'
            cards += f'<div class="pager">{prev}<span class="pgn">{pg} / {pages}</span>{nxt}</div>'
    else:
        cards = ('<div class="empty"><div class="ebox"><h2>대기 중</h2>'
                 '<p>이 창은 켜둔 채로 <b>스타크래프트를 실행</b>해 보세요.<br>'
                 '게임이 끝날 때마다 여기에 자동으로 등록됩니다.</p></div></div>')
    page = PAGE.replace("__TOP__", top).replace("__CARDS__", cards)
    return Response(page, mimetype="text/html")

MATCH_TEMPLATE = r"""<!doctype html><html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ · ENCORE</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/sun-typeface/SUIT@2/fonts/variable/woff2/SUIT-Variable.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/sun-typeface/SUITE@2/fonts/variable/woff2/SUITE-Variable.css">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{
 --bg:#0C0D10;--surface:#131519;--surface2:#181B21;--hover:#1D2128;--well:#0E0F13;
 --ink:#ECEEF2;--ink2:#C5C9D0;--dim:#9AA0AA;--faint:#636872;
 --line:#1F232B;--line2:#2C313B;
 --acc:#3D8BFF;--acc-ink:#62A1FF;--acc-soft:rgba(61,139,255,.12);--acc-line:rgba(61,139,255,.34);
 --win:#3D8BFF;--loss:#E8694C;--gold:#E0B441;--blue:#5BA3E0;--violet:#C07BE0;
 --h-battle:#F0703C;--h-tech:#3D8BFF;--h-expand:#C07BE0;
 --r-ran:#5BA3E0;--r-zerg:#C07BE0;--r-toss:#E0B441;
 --fd:'SUIT Variable','Apple SD Gothic Neo','Malgun Gothic',system-ui,sans-serif;
 --fh:'SUITE Variable','SUIT Variable',sans-serif;
 --fm:'IBM Plex Mono',ui-monospace,monospace;
 --r1:9px;--r2:13px;--r3:17px;
 --sh:0 12px 32px -18px rgba(0,0,0,.7);
}
*{box-sizing:border-box}
html,body{margin:0}
body{background:var(--bg);color:var(--ink);font-family:var(--fd);font-size:15px;line-height:1.55;
 -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;font-feature-settings:"ss01","cv01";letter-spacing:.005em}
a{color:inherit;text-decoration:none}
svg{display:block}
.mono{font-family:var(--fm);font-variant-numeric:tabular-nums}
::selection{background:var(--acc-soft)}
::-webkit-scrollbar{width:10px;height:10px}::-webkit-scrollbar-thumb{background:var(--line2);border-radius:6px;border:3px solid var(--bg)}::-webkit-scrollbar-track{background:transparent}
.ic{width:1em;height:1em;flex-shrink:0}

.wrap{max-width:1180px;margin:0 auto;padding:0 28px 110px}

/* ── top bar ── */
.bar{position:sticky;top:0;z-index:50;background:var(--bg);border-bottom:1px solid var(--line)}.bar.scrolled{box-shadow:0 6px 22px rgba(0,0,0,.4)}
.bar.scrolled{border-color:var(--line)}
.bar-in{max-width:1180px;margin:0 auto;padding:14px 28px;display:flex;align-items:center;gap:16px}
.brand{display:flex;align-items:center;gap:10px}
.brand .gem{width:18px;height:18px;border-radius:6px;background:linear-gradient(140deg,#62A1FF,#2563c9);
 box-shadow:0 0 0 1px rgba(255,255,255,.06) inset,0 4px 12px -3px rgba(61,139,255,.5);position:relative}
.brand .gem::after{content:"";position:absolute;inset:4px;border-radius:3px;background:linear-gradient(140deg,rgba(255,255,255,.25),transparent)}
.brand .lgmk{width:20px;height:20px;color:var(--ink)}
.brand b{font-family:var(--fh);font-weight:800;font-size:16px;letter-spacing:.2em}
.crumb{display:flex;align-items:center;gap:9px;font-family:var(--fm);font-size:12px;color:var(--faint)}
.crumb a{color:var(--dim);transition:color .15s}.crumb a:hover{color:var(--ink)}
.crumb .sep{opacity:.5}
.bar .sp{flex:1}
.live{display:inline-flex;align-items:center;gap:8px;font-family:var(--fm);font-size:12px;color:var(--dim);
 background:var(--surface);border:1px solid var(--line);padding:7px 12px;border-radius:100px}
.live .d{width:6px;height:6px;border-radius:50%;background:var(--acc);box-shadow:0 0 0 3px var(--acc-soft)}
.btn{display:inline-flex;align-items:center;gap:8px;font-family:var(--fd);font-weight:600;font-size:13.5px;
 padding:9px 15px;border-radius:var(--r1);cursor:pointer;transition:.15s;border:1px solid transparent;white-space:nowrap}
.btn .ic{width:16px;height:16px}
.btn.ghost{background:var(--surface);border-color:var(--line);color:var(--ink2)}
.btn.ghost:hover{border-color:var(--line2);background:var(--hover);color:var(--ink)}
.btn:focus-visible{outline:none;box-shadow:0 0 0 3px var(--acc-soft)}

/* ── hero ── */
.hero{padding:34px 0 24px}
.eyebrow{font-family:var(--fm);font-weight:500;font-size:11px;letter-spacing:.26em;color:var(--acc);text-transform:uppercase;margin-bottom:15px}
.title{font-family:var(--fh);font-weight:800;font-size:clamp(30px,4.6vw,44px);line-height:1.03;letter-spacing:-.022em;margin:0;color:#F3F0E9}
.meta{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:18px}
.chip{display:inline-flex;align-items:center;gap:7px;font-family:var(--fd);font-weight:500;font-size:13.5px;
 padding:7px 12px;border-radius:var(--r1);background:var(--surface);border:1px solid var(--line);color:var(--ink2)}
.chip .ic{width:14px;height:14px;color:var(--faint)}
.chip.acc{background:var(--acc-soft);border-color:var(--acc-line);color:var(--acc-ink)}
.chip.win{background:var(--acc-soft);border-color:var(--acc-line);color:var(--acc-ink)}
.chip.win .ic{color:var(--acc)}
.chip b{font-family:var(--fm);font-weight:600;font-variant-numeric:tabular-nums;color:var(--ink)}

/* ── video ── */
.stage{position:relative;aspect-ratio:16/9;max-height:760px;border-radius:var(--r3);overflow:hidden;
 background:#0A0A08;border:1px solid var(--line2);box-shadow:0 40px 90px -52px #000}
.stage video{width:100%;height:100%;object-fit:contain;background:#000;display:block}
.vwrap{position:absolute;inset:0}
.vplay{position:absolute;inset:0;border:0;background:rgba(8,9,11,.30);display:grid;place-items:center;cursor:pointer;transition:.2s;padding:0}
.vplay:hover{background:rgba(8,9,11,.16)}
.vplay svg{width:74px;height:74px;color:#fff;background:rgba(61,139,255,.94);border-radius:50%;padding:24px;box-sizing:border-box;box-shadow:0 14px 44px -10px rgba(0,0,0,.7);transition:.2s;margin-left:3px}
.vplay:hover svg{transform:scale(1.05)}
.poster{position:absolute;inset:0;display:grid;place-items:center;background:
 radial-gradient(120% 100% at 50% 0,#1a201b 0%,#0c0d0a 70%)}
.poster .pcol{text-align:center}
.poster .play{width:72px;height:72px;border-radius:50%;display:grid;place-items:center;margin:0 auto 18px;
 background:rgba(70,190,136,.1);border:1px solid var(--acc-line);transition:.2s}
.poster .play .ic{width:26px;height:26px;color:var(--acc);margin-left:3px}
.poster:hover .play{background:rgba(70,190,136,.16);transform:scale(1.04)}
.poster .pm{font-family:var(--fm);font-size:12px;letter-spacing:.16em;color:var(--faint);text-transform:uppercase}
.poster .pmap{font-family:var(--fh);font-weight:800;font-size:21px;color:rgba(235,232,224,.32);margin-top:8px}

/* ── section frame ── */
.sec{padding-top:52px}
.sechead{display:flex;align-items:center;gap:13px;margin-bottom:20px}
.sechead h2{font-family:var(--fh);font-weight:800;font-size:20px;letter-spacing:-.015em;margin:0}
.sechead .meta-r{margin-left:auto;display:flex;align-items:center;gap:16px}
.sechead .hint{font-family:var(--fm);font-size:11.5px;color:var(--faint)}
.legend{display:flex;gap:15px;font-family:var(--fm);font-size:11.5px;color:var(--dim)}
.legend i{display:inline-flex;align-items:center;gap:6px;font-style:normal}
.legend .ic{width:13px;height:13px}

/* ── highlight timeline ── */
.tl{position:relative;height:70px;margin:6px 6px 0;user-select:none}
.tl-rail{position:absolute;left:0;right:0;top:44px;height:4px;background:var(--line2);border-radius:3px;overflow:hidden}
.tl-fill{position:absolute;left:0;top:0;bottom:0;width:0;background:var(--acc);opacity:.55;border-radius:3px}
.tl-head{position:absolute;top:37px;width:2px;height:18px;background:var(--ink);border-radius:2px;transform:translateX(-1px);transition:left .08s linear;box-shadow:0 0 6px rgba(235,232,224,.5)}
.mk{position:absolute;top:30px;transform:translateX(-50%);cursor:pointer;z-index:2;display:flex;flex-direction:column;align-items:center}
.mk::before{content:"";position:absolute;left:-11px;right:-11px;top:-10px;bottom:-16px}
.mk .pin{width:11px;height:11px;border-radius:50%;background:var(--bg);border:2px solid currentColor;transition:.15s}
.mk .stem{width:1.5px;height:11px;background:currentColor;opacity:.4;margin-top:2px}
.mk:hover{z-index:6}.mk:hover .pin{transform:scale(1.35);background:currentColor}
.mk .tip{position:absolute;bottom:24px;left:50%;transform:translateX(-50%) translateY(4px);white-space:nowrap;
 background:var(--surface2);border:1px solid var(--line2);border-radius:var(--r1);padding:8px 11px;
 opacity:0;pointer-events:none;transition:.16s;box-shadow:var(--sh)}
.mk:hover .tip{opacity:1;transform:translateX(-50%) translateY(0)}
.mk .tip .tt{display:flex;align-items:center;gap:7px}
.mk .tip .ic{width:13px;height:13px;color:currentColor}
.mk .tip b{font-family:var(--fm);font-size:12px;color:var(--ink);font-weight:600}
.mk .tip s{font-family:var(--fd);font-weight:500;font-size:12.5px;text-decoration:none;color:var(--dim);margin-left:18px;display:block;margin-top:2px}
.tl-times{display:flex;justify-content:space-between;font-family:var(--fm);font-size:11px;color:var(--faint);margin:8px 6px 0}
.kb{color:var(--h-battle)}.kt{color:var(--h-tech)}.ke{color:var(--h-expand)}

.moments{display:flex;gap:8px;overflow-x:auto;padding:10px 4px 4px;scroll-snap-type:x proximity}
.moment{flex:0 0 auto;min-width:106px;background:var(--surface);border:1px solid var(--line);border-radius:var(--r2);
 padding:9px 11px 10px;cursor:pointer;transition:.16s;scroll-snap-align:start}
.moment:hover{border-color:var(--line2);background:var(--hover);transform:translateY(-3px);box-shadow:var(--sh)}
.moment .top{display:flex;align-items:center;justify-content:space-between}
.moment .mt{font-family:var(--fm);font-weight:600;font-size:15px;color:var(--ink);letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.moment .ico{width:18px;height:18px;border-radius:6px;display:grid;place-items:center;background:color-mix(in srgb,currentColor 14%,transparent)}
.moment .ico .ic{width:11px;height:11px;color:currentColor}
.moment .mlab{font-family:var(--fd);font-weight:600;font-size:12px;color:var(--ink);margin-top:7px}
.moment .mwho{font-family:var(--fm);font-size:11px;color:var(--dim);margin-top:4px;display:flex;align-items:center;gap:5px}
.moment .mwho .ic{width:12px;height:12px;color:var(--faint)}
.note{font-family:var(--fm);font-size:11.5px;color:var(--faint);margin:12px 6px 0;display:flex;align-items:center;gap:7px}
.note .ic{width:13px;height:13px}

/* ── analysis ── */
.seg{display:inline-flex;gap:2px;padding:3px;background:var(--surface);border:1px solid var(--line);border-radius:var(--r1);margin-bottom:22px}
.seg button{font-family:var(--fd);font-weight:600;font-size:13.5px;color:var(--dim);padding:9px 18px;border:0;background:transparent;border-radius:7px;cursor:pointer;transition:.15s}
.seg button:hover{color:var(--ink)}
.seg button.on{background:var(--hover);color:var(--ink);box-shadow:0 0 0 1px var(--line2)}

.split{display:block}.nav{display:flex;gap:2px;margin-left:16px}.nav a{font-family:var(--fd);font-weight:600;font-size:14px;color:var(--dim);padding:8px 14px;border-radius:9px;transition:.15s}.nav a.on{color:var(--ink);background:var(--surface)}.nav a:hover{color:var(--ink)}.ftr{margin-top:64px;padding-top:30px;border-top:1px solid var(--line);display:flex;justify-content:space-between;gap:30px;flex-wrap:wrap}.ftr-brand{display:flex;align-items:center;gap:9px;margin-bottom:13px}.ftr-brand .lgmk{width:18px;height:18px;color:var(--ink)}.ftr-brand b{font-family:var(--fh);font-weight:800;font-size:15px;letter-spacing:.18em}.ftr-l p{margin:5px 0;font-size:13px;line-height:1.6;color:var(--dim)}.ftr-by{font-family:var(--fd);font-size:13px;color:var(--dim);margin-top:13px}.ftr-by b{color:var(--ink2);font-weight:700}.ftr-by .hdl{font-family:var(--fm);font-size:12px;color:var(--faint)}.ftr-links{display:flex;flex-direction:column;gap:10px;font-size:13.5px}.ftr-links a{color:var(--dim);transition:.15s}.ftr-links a:hover{color:var(--ink)}
.rail{display:flex;flex-wrap:wrap;gap:14px;margin-bottom:20px}
.rteam{flex:1 1 260px;min-width:0;background:var(--well);border:1px solid var(--line);border-radius:var(--r2);padding:13px 15px}
.rteam .rt{font-family:var(--fm);font-size:11.5px;letter-spacing:.16em;color:var(--faint);margin-bottom:12px;display:flex;align-items:center;gap:8px;text-transform:uppercase}
.rteam .rt.win{color:var(--acc)} .rteam .rt .w{display:inline-flex;align-items:center;gap:4px;font-size:10px;background:var(--acc-soft);padding:2px 7px;border-radius:5px}
.rteam .rt .w .ic{width:11px;height:11px}
.pl{display:flex;flex-wrap:wrap;gap:8px}
.pchip{display:flex;align-items:center;gap:10px;padding:12px 14px;border-radius:var(--r1);cursor:pointer;border:1px solid var(--line);background:var(--surface);transition:.13s;position:relative;flex:1 1 170px;min-width:0}
.pchip:hover{border-color:var(--line2)}
.pchip.sel{background:var(--acc-soft);border-color:var(--acc-line)}
.pchip.sel::before{content:"";position:absolute;left:0;top:9px;bottom:9px;width:2.5px;border-radius:2px;background:var(--acc)}
.pchip .cc{width:9px;height:9px;border-radius:50%;flex-shrink:0}
.pchip .rt{font-family:var(--fm);font-weight:700;font-size:10px;width:19px;height:19px;border-radius:6px;display:grid;place-items:center;flex-shrink:0}
.rt.r-ran{background:color-mix(in srgb,var(--r-ran) 16%,transparent);color:var(--r-ran)}
.rt.r-zerg{background:color-mix(in srgb,var(--r-zerg) 16%,transparent);color:var(--r-zerg)}
.rt.r-toss{background:color-mix(in srgb,var(--r-toss) 16%,transparent);color:var(--r-toss)}
.pchip .pn{font-family:var(--fd);font-weight:600;font-size:15px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink2)}
.pchip.sel .pn,.pchip:hover .pn{color:var(--ink)}
.pchip.me .pn{font-weight:700}
.pchip .meb{font-family:var(--fm);font-size:9px;letter-spacing:.06em;color:var(--acc);background:var(--acc-soft);padding:2px 5px;border-radius:4px;flex-shrink:0}
.pchip .ap{font-family:var(--fm);font-size:13.5px;color:var(--dim);flex-shrink:0;font-variant-numeric:tabular-nums}

.panel{background:var(--surface);border:1px solid var(--line);border-radius:var(--r3);overflow:hidden}
.phead{display:flex;align-items:center;gap:13px;padding:22px 26px}
.phead .cc{width:24px;height:24px;border-radius:7px;flex-shrink:0;box-shadow:0 0 0 1px rgba(0,0,0,.3) inset}
.phead .nm{font-family:var(--fh);font-weight:800;font-size:27px;letter-spacing:-.01em}
.phead .sub{font-family:var(--fm);font-size:12.5px;color:var(--dim);margin-top:2px}
.phead .prof{margin-left:auto;display:inline-flex;align-items:center;gap:6px;font-family:var(--fd);font-weight:600;font-size:12.5px;color:var(--dim);border:1px solid var(--line);padding:8px 13px;border-radius:var(--r1);transition:.15s}
.phead .prof:hover{border-color:var(--line2);color:var(--ink)}.phead .prof .ic{width:13px;height:13px}
.statline{display:flex;flex-wrap:wrap;gap:30px;padding:0 26px 12px}.snote{display:flex;align-items:center;gap:7px;font-family:var(--fm);font-size:11.5px;color:var(--faint);padding:0 26px 20px}.snote .ic{width:14px;height:14px;flex-shrink:0;opacity:.8}
.stat .v{font-family:var(--fh);font-weight:800;font-size:25px;line-height:1;letter-spacing:-.01em;font-variant-numeric:tabular-nums}
.stat .v.acc{color:var(--acc-ink)}
.stat .k{font-family:var(--fm);font-size:11.5px;letter-spacing:.1em;color:var(--faint);text-transform:uppercase;margin-top:8px}
.cols{display:grid;grid-template-columns:1.08fr 1fr;border-top:1px solid var(--line)}
.col{padding:22px 26px}.col.l{border-right:1px solid var(--line)}
.ch{font-family:var(--fm);font-size:12px;letter-spacing:.14em;color:var(--faint);text-transform:uppercase;margin-bottom:15px;display:flex;align-items:center;gap:9px}
.ch .lg{margin-left:auto;display:flex;gap:11px;letter-spacing:0}
.ch .lg i{font-style:normal;display:inline-flex;gap:5px;align-items:center;color:var(--dim)}
.ch .lg .d{width:7px;height:7px;border-radius:50%}
.bo{max-height:520px;overflow-y:auto;padding-right:6px;margin-right:-6px}
.brow{display:flex;align-items:center;gap:12px;padding:8px 10px;border-radius:8px;transition:.1s}
.brow:hover{background:var(--hover)}
.brow .bt{font-family:var(--fm);font-size:13px;color:var(--faint);width:46px;flex-shrink:0;font-variant-numeric:tabular-nums}
.brow .bd{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.brow .bn{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:15.5px;color:var(--ink)}
.brow .bc{font-family:var(--fm);font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--faint);flex-shrink:0}
.cd-building{color:var(--blue)}.cd-morph{color:var(--violet)}.cd-upgrade{color:var(--gold)}.cd-tech{color:var(--acc)}
.units{display:flex;flex-direction:column;gap:12px;margin-bottom:30px}
.urow{display:flex;align-items:center;gap:12px;font-size:15px}
.urow .un{width:130px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink2)}
.ubar{flex:1;height:6px;background:var(--line);border-radius:4px;overflow:hidden}
.ubar span{display:block;height:100%;background:var(--acc);opacity:.85;border-radius:4px}
.urow .uc{font-family:var(--fm);font-weight:600;font-size:14px;width:30px;text-align:right;flex-shrink:0;font-variant-numeric:tabular-nums}
.urow .uf{font-family:var(--fm);font-size:12px;color:var(--faint);width:46px;text-align:right;flex-shrink:0}
.spark{display:flex;align-items:flex-end;gap:3px;height:68px}
.spark b{flex:1;background:var(--acc);opacity:.8;border-radius:2px 2px 0 0;min-height:2px;display:block;transition:.2s}
.spark:hover b{opacity:.45}.spark b:hover{opacity:1}
.sparkx{display:flex;justify-content:space-between;font-family:var(--fm);font-size:11px;color:var(--faint);margin-top:8px}
.thl{display:flex;flex-wrap:wrap;gap:7px;margin-top:11px}
.thl span{font-family:var(--fm);font-size:12px;color:var(--dim);background:var(--well);border:1px solid var(--line);padding:5px 10px;border-radius:7px}.coach{margin-top:30px;border-top:1px solid var(--line);padding-top:24px}.coachh{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.cnote{font-family:var(--fm);font-size:11px;color:var(--faint);font-weight:400;letter-spacing:0}.cfacts{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 18px}.cfacts span{font-family:var(--fm);font-size:13px;color:var(--dim);background:var(--well);border:1px solid var(--line);padding:8px 12px;border-radius:8px}.cfacts b{color:var(--ink);font-weight:600}.ccards{display:grid;gap:11px}.ccard{border:1px solid var(--line);border-radius:12px;padding:14px 16px;background:var(--surface)}.ccard .cct{display:flex;align-items:center;gap:9px;margin-bottom:7px}.ccard .cci{display:inline-flex;color:var(--dim)}.ccard .cci .ic{width:17px;height:17px}.ccard .cct b{font-weight:700;font-size:15.5px;color:var(--ink)}.ccard p{margin:0;font-size:14.5px;line-height:1.7;color:var(--ink2)}.ccard.cg{border-color:var(--acc-line);background:var(--acc-soft)}.ccard.cg .cci{color:var(--acc-ink)}.ccard.cg .cct b{color:var(--acc-ink)}.ccard.cw{border-color:rgba(232,105,76,.42);background:rgba(232,105,76,.09)}.ccard.cw .cci{color:var(--loss)}.ccard.cw .cct b{color:var(--loss)}.cnone{color:var(--faint);font-size:13px;padding:6px 2px}

/* compare */
.cmp{display:flex;gap:12px;overflow-x:auto;padding-bottom:14px}
.cmpc{flex:0 0 244px;background:var(--surface);border:1px solid var(--line);border-radius:var(--r2);overflow:hidden;display:flex;flex-direction:column}
.cmpc.sel{border-color:var(--acc-line)}
.cmph{display:flex;align-items:center;gap:9px;padding:13px 14px;border-bottom:1px solid var(--line);cursor:pointer;transition:.12s}
.cmph:hover{background:var(--hover)}
.cmph .cc{width:9px;height:9px;border-radius:50%;flex-shrink:0}
.cmph .rt{font-family:var(--fm);font-weight:700;font-size:9px;width:17px;height:17px;border-radius:5px;display:grid;place-items:center;flex-shrink:0}
.cmph .nm{font-family:var(--fd);font-weight:600;font-size:13.5px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cmph .w{margin-left:auto;color:var(--acc)}.cmph .w .ic{width:14px;height:14px}
.cmpb{padding:8px;overflow-y:auto;max-height:540px}
.cmprow{display:flex;align-items:center;gap:9px;padding:6px 8px;border-radius:7px;font-size:13px}
.cmprow .bt{font-family:var(--fm);font-size:11px;color:var(--faint);width:38px;flex-shrink:0;font-variant-numeric:tabular-nums}
.cmprow .bd{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.cmprow .bn{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink2)}

/* community */
.comm{margin-top:56px;border-top:1px solid var(--line);padding-top:34px}
.comm-h{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px}
.comm-h h2{font-family:var(--fh);font-weight:800;font-size:20px;margin:0;letter-spacing:-.015em}
.like{display:inline-flex;align-items:center;gap:8px;font-family:var(--fm);font-size:13.5px;color:var(--dim);
 background:var(--surface);border:1px solid var(--line);padding:9px 15px;border-radius:100px;cursor:pointer;transition:.15s;font-variant-numeric:tabular-nums}
.like .ic{width:15px;height:15px;transition:.18s}
.like:hover{border-color:color-mix(in srgb,var(--loss) 45%,transparent);color:#ee9482}
.like.on{color:var(--loss);border-color:color-mix(in srgb,var(--loss) 50%,transparent);background:color-mix(in srgb,var(--loss) 9%,transparent)}
.like.on .ic{transform:scale(1.15);fill:var(--loss)}
.cform{display:grid;grid-template-columns:170px 1fr auto;gap:10px;margin-bottom:8px}
.ci,.ct{font-family:var(--fd);font-size:14.5px;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:var(--r1);padding:12px 14px;transition:.15s}
.ct{font-family:var(--fd)}
.ci::placeholder,.ct::placeholder{color:var(--faint)}
.ci:focus,.ct:focus{outline:none;border-color:var(--acc-line);box-shadow:0 0 0 3px var(--acc-soft)}
.ct{resize:vertical;min-height:46px;line-height:1.5}
.cs{font-family:var(--fd);font-weight:700;font-size:14px;color:#0c130e;background:var(--acc);border:0;border-radius:var(--r1);padding:0 22px;cursor:pointer;transition:.15s}
.cs:hover{background:#54cf97}.cs:focus-visible{outline:none;box-shadow:0 0 0 3px var(--acc-soft)}
.clist{margin-top:14px}
.crow{display:flex;gap:13px;padding:16px 0;border-top:1px solid var(--line)}
.cav{width:36px;height:36px;border-radius:10px;flex-shrink:0;display:grid;place-items:center;font-family:var(--fh);font-weight:800;font-size:15px;color:#0c130e}
.cmeta{display:flex;align-items:center;gap:9px;margin-bottom:5px}
.cau{font-family:var(--fd);font-weight:700;font-size:14.5px}
.cpart{font-family:var(--fm);font-size:10.5px;padding:2px 8px;border-radius:5px;display:inline-flex;gap:5px;align-items:center}.cpart .d{width:6px;height:6px;border-radius:50%}
.ctime{font-family:var(--fm);font-size:11.5px;color:var(--faint)}
.cbody{font-size:14.5px;color:var(--ink2);line-height:1.65}

@media(max-width:920px){.cols{grid-template-columns:1fr}.col.l{border-right:0;border-bottom:1px solid var(--line)}}
@media(max-width:560px){.wrap{padding:0 18px 80px}.bar-in{padding:12px 18px}.statline{gap:24px}.cform{grid-template-columns:1fr}}
</style></head><body>

<div class="bar" id="bar"><div class="bar-in">
 <div class="brand"><svg class="lgmk" viewBox="0 0 32 32" fill="currentColor"><rect x="3.5" y="20" width="6" height="8" rx="1.6"/><rect x="13" y="12.5" width="6" height="15.5" rx="1.6"/><rect x="22.5" y="5" width="6" height="23" rx="1.6"/></svg><b>ENCORE</b></div>
 <nav class="nav"><a class="on" href="/">아카이브</a><a href="/about">만든이</a><a href="/manual">매뉴얼</a><a href="/download">다운로드</a></nav>
 <span class="sp"></span>
 <span id="dlslot"></span>
 <span class="live"><span class="d"></span>대기 중</span>
</div></div>

<div class="wrap">
 <div class="hero">
  <div class="eyebrow">Match Analysis</div>
  <h1 class="title" id="map"></h1>
  <div class="meta" id="meta"></div>
 </div>

 <div class="stage" id="stage"></div>

 <section class="sec" id="hlsec">
  <div class="sechead"><h2>하이라이트</h2>
   <div class="meta-r"><span class="hint">점 또는 카드를 누르면 그 장면으로 이동</span>
    <span class="legend" id="legend"></span></div></div>
  <div class="tl" id="tl"></div>
  <div class="tl-times"><span>0:00</span><span id="tlend"></span></div>
  <div class="moments" id="moments"></div>
  <div class="note" id="hlnote"></div>
 </section>

 <section class="sec">
  <div class="seg"><button class="on" data-v="one">선수별 상세</button><button data-v="cmp">전체 빌드 비교</button></div>
  <div id="oneview"><div class="split"><div class="rail" id="rail"></div><div class="panel" id="panel"></div></div></div>
  <div id="cmpview" hidden><div class="cmp" id="cmp"></div></div>
 </section>

 <section class="comm">
  <div class="comm-h"><h2>코멘트</h2>
   <button class="like" id="like"><span class="ic" id="lhic"></span><span id="lc">4</span></button></div>
  <div class="cform">
   <input class="ci" id="cau" maxlength="24" placeholder="스타 아이디">
   <textarea class="ct" id="cb" maxlength="600" rows="2" placeholder="이 경기에 한마디 남겨보세요"></textarea>
   <button class="cs" id="csend">등록</button></div>
  <div class="clist" id="clist"></div>
 </section>
<footer class="ftr"><div class="ftr-l"><div class="ftr-brand"><svg class="lgmk" viewBox="0 0 32 32" fill="currentColor"><rect x="3.5" y="20" width="6" height="8" rx="1.6"/><rect x="13" y="12.5" width="6" height="15.5" rx="1.6"/><rect x="22.5" y="5" width="6" height="23" rx="1.6"/></svg><b>ENCORE</b></div><p>스무 살의 우리에게 — 다시, 브루드워.</p><p class="ftr-by">만든이 <b>최성호</b> · <span class="hdl">veatbox</span></p></div><div class="ftr-links"><a href="/">아카이브</a><a href="/about">만든이</a><a href="/manual">매뉴얼</a><a href="/download">다운로드</a></div></footer>
</div>

<script>
const DATA=__DATA__;const VIDEO=__VIDEO__;const COMMENTS=__COMMENTS__;const MID=__MID__;const LIKES0=__LIKES__;const COACH=__COACH__;
const I={
 play:'<svg class="ic" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.14v13.72a1 1 0 0 0 1.52.86l11.43-6.86a1 1 0 0 0 0-1.72L9.52 4.28A1 1 0 0 0 8 5.14Z"/></svg>',
 download:'<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12m0 0 4.5-4.5M12 15l-4.5-4.5M4 21h16"/></svg>',
 clock:'<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7.5V12l3.2 1.9"/></svg>',
 swords:'<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 17.5 21 11V4h-7l-6.5 6.5M14.5 17.5 11 21l-2-2 3.5-3.5M14.5 17.5l-5-5M3 4l6.5 6.5M9.5 10.5 6 14l2 2 3.5-3.5M6 14l-3 3.5L4 21h3l.5-1"/></svg>',
 beaker:'<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3h6M10 3v6l-5.2 8.5A2 2 0 0 0 6.5 21h11a2 2 0 0 0 1.7-3.5L14 9V3M7.5 14h9"/></svg>',
 expand:'<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3m8 0h3a2 2 0 0 0 2-2v-3"/></svg>',
 trophy:'<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 4h10v5a5 5 0 0 1-10 0V4ZM7 6H4v1a3 3 0 0 0 3 3M17 6h3v1a3 3 0 0 1-3 3M9 17h6M12 14v3M9 21h6"/></svg>',
 heart:'<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20.5C6.5 16.5 3 13 3 9.2 3 6.6 5 4.5 7.6 4.5c1.7 0 3.2.9 4.4 2.6 1.2-1.7 2.7-2.6 4.4-2.6C19 4.5 21 6.6 21 9.2c0 3.8-3.5 7.3-9 11.3Z"/></svg>',
 user:'<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="3.5"/><path d="M5 20c0-3.3 3.1-5.5 7-5.5s7 2.2 7 5.5"/></svg>',
 arrowUR:'<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17 17 7M8 7h9v9"/></svg>',
 info:'<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></svg>'
};
const KICON={battle:I.swords,tech:I.beaker,expand:I.expand};
const KCLASS={battle:'kb',tech:'kt',expand:'ke'};
const RACE={ran:'테란',zerg:'저그',toss:'프로토스'};
const RID=r=>({ran:'T',zerg:'Z',toss:'P'}[r]||(r||'?').slice(0,1).toUpperCase());
const CAT={building:'건물',morph:'변환',upgrade:'업글',tech:'테크'};
const meta=DATA.meta,players=DATA.players;
const fmt=s=>Math.floor(s/60)+':'+String(s%60).padStart(2,'0');
const totalSec=(()=>{const p=(meta.length||'0:0').split(':');return (+p[0])*60+(+p[1]||0)||1;})();

addEventListener('scroll',()=>document.getElementById('bar').classList.toggle('scrolled',scrollY>8));
document.getElementById('map').textContent=meta.map||'리플레이';
const np=players.length;
document.getElementById('meta').innerHTML=
 `<span class="chip acc"><b>${np/2|0}</b> vs <b>${np/2|0}</b></span>`+
 (meta.matchup?`<span class="chip mono">${meta.matchup}</span>`:'')+
 `<span class="chip">${I.clock}<b>${meta.length||''}</b></span>`+
 (meta.winner?`<span class="chip win">${I.trophy}Team ${meta.winner} 승`:'');

if(VIDEO){const isHttp=/^https?:/.test(VIDEO);const sep=VIDEO.indexOf('?')<0?'?':'&';const dlhref=VIDEO+sep+(isHttp?'download':'dl=1');document.getElementById('dlslot').innerHTML=`<a class="btn ghost" href="${dlhref}"${isHttp?'':' download'}>${I.download}영상 다운로드</a>`;}

const stage=document.getElementById('stage');
let OFF=0;  // 메뉴 오프셋(영상 길이 - 게임 길이) = 영상에서 게임이 시작되는 지점
stage.innerHTML=VIDEO?`<div class="vwrap"><video id="vid" controls playsinline preload="metadata" src="${VIDEO}"></video><button class="vplay" id="vplay" aria-label="재생"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.14v13.72a1 1 0 0 0 1.52.86l11.43-6.86a1 1 0 0 0 0-1.72L9.52 4.28A1 1 0 0 0 8 5.14Z"/></svg></button></div>`
 :`<div class="poster"><div class="pcol"><div class="play">${I.play}</div><div class="pm">Recorded Replay</div><div class="pmap">${meta.map||''}</div></div></div>`;
const vid=document.getElementById('vid');const vplay=document.getElementById('vplay');
function hideOverlay(){if(vplay)vplay.style.display='none';}
if(vid){
 vid.addEventListener('loadedmetadata',()=>{if(vid.duration&&isFinite(vid.duration)){OFF=Math.max(0,vid.duration-totalSec);if(OFF>1){try{vid.currentTime=Math.max(0,OFF-6);}catch(e){}}}});
 if(vplay)vplay.addEventListener('click',()=>{vid.play().catch(()=>{});});
 vid.addEventListener('play',hideOverlay);
}
const seek=s=>{if(!vid)return;const go=()=>{hideOverlay();try{vid.currentTime=Math.max(0,Math.min((vid.duration||1e9),s+OFF));}catch(e){}vid.play().catch(()=>{});vid.scrollIntoView({behavior:'smooth',block:'center'});};if(vid.readyState>=1){go();}else{vid.addEventListener('loadedmetadata',go,{once:true});}};

// legend
document.getElementById('legend').innerHTML=
 `<i class="kb">${I.swords}교전</i><i class="kt">${I.beaker}테크</i><i class="ke">${I.expand}확장</i>`;
document.getElementById('hlnote').innerHTML=I.info+'교전은 전원 분당 활동량(APM) 피크로 추정한 값이라 실제 전투와 다를 수 있어요.';

// timeline + moments
const HL=DATA.highlights||[];
document.getElementById('tlend').textContent=meta.length||fmt(totalSec);
if(HL.length){
 const tl=document.getElementById('tl');
 tl.innerHTML='<div class="tl-rail"><div class="tl-fill" id="tlfill"></div></div><div class="tl-head" id="tlhead" style="left:0"></div>';
 HL.forEach(h=>{const x=Math.max(.5,Math.min(99.5,h.sec/totalSec*100));
  const m=document.createElement('div');m.className='mk '+KCLASS[h.kind];m.style.left=x+'%';
  m.innerHTML=`<div class="tip"><div class="tt">${KICON[h.kind]}<b>${h.t||fmt(h.sec)}</b></div><s>${h.label}${h.who?' · '+h.who:''}</s></div><div class="pin"></div><div class="stem"></div>`;
  m.onclick=()=>seek(h.sec);tl.appendChild(m);});
 document.getElementById('moments').innerHTML=HL.map(h=>
  `<div class="moment ${KCLASS[h.kind]}" data-s="${h.sec}">
    <div class="top"><span class="mt">${h.t||fmt(h.sec)}</span><span class="ico">${KICON[h.kind]}</span></div>
    <div class="mlab">${h.label}</div>
    <div class="mwho">${h.who?I.user+'<span>'+h.who+'</span>':'<span style="color:var(--faint)">전장 전체</span>'}</div>
   </div>`).join('');
 document.querySelectorAll('.moment').forEach(el=>el.onclick=()=>seek(+el.dataset.s));
 const upd=()=>{const v=document.getElementById('vid');if(!v||!v.duration)return;const gt=Math.max(0,Math.min(totalSec,v.currentTime-OFF));const p=gt/totalSec*100;
  document.getElementById('tlfill').style.width=p+'%';document.getElementById('tlhead').style.left=p+'%';};
 const v0=document.getElementById('vid');if(v0)v0.addEventListener('timeupdate',upd);
}else{document.getElementById('hlsec').style.display='none';}

// rail
function pchip(p){const me=p.name===meta.saver;
 return `<div class="pchip ${me?'me':''}" data-id="${p.id}"><span class="cc" style="background:${p.color}"></span>
  <span class="rt r-${p.race}">${RID(p.race)}</span><span class="pn">${p.name||'—'}</span>${me?'<span class="meb">나</span>':''}
  <span class="ap">${p.apm||0}</span></div>`;}
const rail=document.getElementById('rail');
[1,2].forEach(t=>{const tp=players.filter(p=>p.team===t);if(!tp.length)return;const win=meta.winner===t;
 rail.insertAdjacentHTML('beforeend',`<div class="rteam"><div class="rt ${win?'win':''}">TEAM ${t}${win?'<span class="w">'+I.trophy+'WIN</span>':''}</div><div class="pl">${tp.map(pchip).join('')}</div></div>`);});

// detail
const CIC={gas:'<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3s5 5.5 5 9a5 5 0 0 1-10 0c0-3.5 5-9 5-9Z"/></svg>',prod:'<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 21V10l6 4v-4l6 4V5h6v16H3Z"/></svg>',up:'<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V6m0 0-6 6m6-6 6 6"/></svg>',comp:'<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.5"/></svg>',tech:I.beaker,army:'<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l7 3v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3Z"/></svg>',apm:'<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l2 6 4-14 2 8h6"/></svg>'};
const TONEC={good:'cg',tip:'ct',warn:'cw'};
function coachBlock(p){
 const cr=(typeof COACH!=='undefined'?COACH:[]).find(c=>c.id===p.id);if(!cr)return'';
 const t=cr.timings;
 const facts=`<div class="cfacts"><span>일꾼 <b>${t.workers}</b></span><span>멀티 <b>${t.tcount}</b></span><span>생산건물 <b>${t.prod}</b></span><span>업글 <b>${t.up_n}</b></span><span>총생산 <b>~${t.total_supply||t.army}</b></span></div>`;
 const cards=(cr.points||[]).map(pt=>`<div class="ccard ${TONEC[pt.tone]||'ct'}"><div class="cct"><span class="cci">${CIC[pt.k]||I.info}</span><b>${pt.t}</b></div><p>${pt.x}</p></div>`).join('')||'<div class="cnone">코치 포인트가 없어요 — 깔끔한 한 판!</div>';
 return `<div class="coach"><div class="ch coachh">코치 리포트 <span class="cnote">실제 리플레이 기반 · 빠른무한 기준</span></div>${facts}<div class="ccards">${cards}</div></div>`;
}
function detail(p){const s=p.summary;
 const stat=(v,k,acc)=>`<div class="stat"><div class="v ${acc?'acc':''}">${v??'—'}</div><div class="k">${k}</div></div>`;
 const bo=p.build.map(b=>`<div class="brow cd-${b.cat}"><span class="bt">${b.t}</span><span class="bd" style="background:currentColor"></span><span class="bn">${b.name||''}</span><span class="bc">${CAT[b.cat]||''}</span></div>`).join('')||'<div style="color:var(--faint);padding:8px;font-size:14px">기록 없음</div>';
 const mu=Math.max(1,...p.units.map(u=>u.n));
 const un=p.units.slice(0,10).map(u=>`<div class="urow"><span class="un">${u.name}</span><span class="ubar"><span style="width:${u.n/mu*100}%"></span></span><span class="uc">${u.n}</span><span class="uf">${u.first||''}</span></div>`).join('')||'<div style="color:var(--faint);font-size:14px">기록 없음</div>';
 const ma=Math.max(1,...p.apm_series);
 const sp=p.apm_series.map(v=>`<b style="height:${v/ma*100}%" title="${v} apm"></b>`).join('');
 const th=p.townhalls.length?`<div class="thl">${p.townhalls.map(t=>`<span>${t.t} ${t.name.replace('Command Center','CC').replace('Hatchery','해처리').replace('Nexus','넥서스')}</span>`).join('')}</div>`:'';
 const lg=`<span class="lg"><i><span class="d" style="background:var(--blue)"></span>건물</i><i><span class="d" style="background:var(--violet)"></span>변환</i><i><span class="d" style="background:var(--gold)"></span>업글</i><i><span class="d" style="background:var(--acc)"></span>테크</i></span>`;
 return `<div class="phead"><span class="cc" style="background:${p.color}"></span><div><div class="nm">${p.name||'—'}</div><div class="sub">${RACE[p.race]||''} · Team ${p.team}</div></div><a class="prof" href="/player/${encodeURIComponent(p.name||'')}">프로필${I.arrowUR}</a></div>
  <div class="statline">${stat(RACE[p.race]||'?','종족')}${stat(p.apm||0,'APM',1)}${stat(p.eapm||0,'EAPM')}${stat(s.buildings,'건물')}${stat(s.prod,'생산건물',1)}${stat(s.units,'유닛')}${stat(p.total_supply||'—','총 생산')}${stat(s.supply200||'—','200 도달')}</div><div class="snote">${I.info}<span>총 생산은 누적 생산 보급, 200 도달은 추정 (둘 다 전사 미반영)</span></div>
  <div class="cols"><div class="col l"><div class="ch">빌드오더${lg}</div><div class="bo">${bo}</div></div>
   <div class="col"><div class="ch">유닛 구성</div><div class="units">${un}</div>
    <div class="ch">분당 APM</div><div class="spark">${sp}</div><div class="sparkx"><span>0:00</span><span>${meta.length||''}</span></div>
    ${th?'<div class="ch" style="margin-top:26px">타운홀 타이밍</div>'+th:''}</div></div>${coachBlock(p)}`;}
let cur=null;
function sel(id){cur=id;document.querySelectorAll('.pchip').forEach(c=>c.classList.toggle('sel',+c.dataset.id===id));
 document.querySelectorAll('.cmpc').forEach(c=>c.classList.toggle('sel',+c.dataset.id===id));
 document.getElementById('panel').innerHTML=detail(players.find(x=>x.id===id));}
document.querySelectorAll('.pchip').forEach(c=>c.onclick=()=>{sel(+c.dataset.id);view('one');});

document.getElementById('cmp').innerHTML=[1,2].map(t=>players.filter(p=>p.team===t).map(p=>{const win=meta.winner===p.team;
 const rows=p.build.map(b=>`<div class="cmprow cd-${b.cat}"><span class="bt">${b.t}</span><span class="bd" style="background:currentColor"></span><span class="bn">${b.name||''}</span></div>`).join('')||'<div style="color:var(--faint);padding:9px">기록 없음</div>';
 return `<div class="cmpc" data-id="${p.id}"><div class="cmph" data-id="${p.id}"><span class="cc" style="background:${p.color}"></span><span class="rt r-${p.race}">${RID(p.race)}</span><span class="nm">${p.name||'—'}</span>${win?'<span class="w">'+I.trophy+'</span>':''}</div><div class="cmpb">${rows}</div></div>`;}).join('')).join('');
document.querySelectorAll('.cmph').forEach(h=>h.onclick=()=>{sel(+h.dataset.id);view('one');});

function view(v){document.querySelectorAll('.seg button').forEach(b=>b.classList.toggle('on',b.dataset.v===v));
 document.getElementById('oneview').hidden=v!=='one';document.getElementById('cmpview').hidden=v!=='cmp';}
document.querySelectorAll('.seg button').forEach(b=>b.onclick=()=>view(b.dataset.v));
const meP=players.find(p=>p.name===meta.saver)||players[0];if(meP)sel(meP.id);

// community
document.getElementById('lhic').innerHTML=I.heart;
function pcol(n){const p=players.find(x=>x.name===n);return p?p.color:'#322D24';}
function cesc(t){return(t==null?'':String(t)).replace(/[&<>"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));}
function rel(iso){const d=new Date(iso),sx=(Date.now()-d)/1000;if(isNaN(sx))return'';
 if(sx<60)return'방금';if(sx<3600)return Math.floor(sx/60)+'분 전';if(sx<86400)return Math.floor(sx/3600)+'시간 전';
 if(sx<604800)return Math.floor(sx/86400)+'일 전';return d.toISOString().slice(0,10);}
function crow(c){const col=pcol(c.author);const part=players.find(x=>x.name===c.author)?`<span class="cpart" style="color:${col};background:${col}1f"><span class="d" style="background:${col}"></span>참가자</span>`:'';
 return `<div class="crow"><div class="cav" style="background:${col}">${cesc((c.author||'?')[0].toUpperCase())}</div><div><div class="cmeta"><span class="cau">${cesc(c.author)}</span>${part}<span class="ctime">${rel(c.created)}</span></div><div class="cbody">${cesc(c.body)}</div></div></div>`;}
let comments=COMMENTS||[];const clist=document.getElementById('clist');
function paintC(){clist.innerHTML=comments.length?comments.map(crow).join(''):'<div style="color:var(--faint);font-size:14px;padding:6px 0">첫 코멘트를 남겨보세요.</div>';}
paintC();
let likes=LIKES0||0,liked=false;try{liked=localStorage.getItem('liked_'+MID)==='1';}catch(e){}
const like=document.getElementById('like'),lc=document.getElementById('lc');
function paintL(){lc.textContent=likes;like.classList.toggle('on',liked);}
paintL();
like.onclick=()=>{liked=!liked;likes+=liked?1:-1;if(likes<0)likes=0;paintL();
 try{localStorage.setItem('liked_'+MID,liked?'1':'0');}catch(e){}
 fetch('/api/match/'+MID+'/like',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({delta:liked?1:-1})}).then(r=>r.json()).then(j=>{if(typeof j.likes==='number'){likes=j.likes;paintL();}}).catch(()=>{});};
const cau=document.getElementById('cau');try{cau.value=localStorage.getItem('sc_id')||'';}catch(e){}
document.getElementById('csend').onclick=()=>{const author=cau.value.trim(),body=document.getElementById('cb').value.trim();if(!author||!body)return;
 try{localStorage.setItem('sc_id',author);}catch(e){}
 comments=comments.concat({author,body,created:new Date().toISOString()});paintC();document.getElementById('cb').value='';
 fetch('/api/match/'+MID+'/comments',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({author,body})}).then(r=>r.json()).then(j=>{if(j.comment){comments[comments.length-1]=j.comment;paintC();}}).catch(()=>{});};
</script></body></html>"""

@app.get("/match/<mid>")
def match_page(mid):
    r = get_match(mid)
    if not r: abort(404)
    a = None
    if r.get("analysis"):
        try: a = json.loads(r["analysis"])
        except Exception: a = None
    if a is None:
        repf = os.path.join(UPLOAD_DIR, r["replay"]) if r.get("replay") else None
        if repf and os.path.isfile(repf) and SCREP:
            try:
                a = extract_analysis(repf); set_analysis(mid, json.dumps(a, ensure_ascii=False))
            except Exception as e:
                log(f"분석 실패: {e}"); a = None
    vurl = _media_url(r.get("video")) if r.get("video") else None
    if a is None:
        return Response("<body style='font-family:monospace;color:#cfe0f0;background:#0b0e13;padding:48px'>"
                        "분석 데이터를 만들 수 없어요 (리플레이 또는 screp 없음). "
                        "<a href='/' style='color:#ff9d3c'>← 돌아가기</a></body>", mimetype="text/html")
    bump_view(mid)
    try: a["highlights"] = compute_highlights(a)
    except Exception: a["highlights"] = []
    try: coach = coach_report(a)
    except Exception as e:
        log("코치 분석 실패: %s" % e); coach = []
    coach_json = json.dumps(coach, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    data = json.dumps(a, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    pn = {p.get("name") for p in (r.get("players") or [])}
    cs = get_comments(mid)
    for cm in cs: cm["participant"] = cm["author"] in pn
    page = (MATCH_TEMPLATE.replace("__TITLE__", esc(a["meta"].get("map") or "Match"))
                          .replace("__BACK__", "/")
                          .replace("__DATA__", data)
                          .replace("__VIDEO__", (f'"{vurl}"' if vurl else "null"))
                          .replace("__MID__", json.dumps(mid))
                          .replace("__LIKES__", str(r.get("likes") or 0))
                          .replace("__COMMENTS__", json.dumps(cs, ensure_ascii=False).replace("</", "<\\/"))
                          .replace("__COACH__", coach_json))
    return Response(page, mimetype="text/html")

@app.post("/api/match/<mid>/like")
def api_like(mid):
    if not get_match(mid): abort(404)
    try: delta = int((request.get_json(silent=True) or {}).get("delta", 1))
    except Exception: delta = 1
    return jsonify(likes=bump_like(mid, 1 if delta >= 0 else -1))

@app.get("/api/match/<mid>/comments")
def api_comments_get(mid):
    m = get_match(mid)
    if not m: abort(404)
    pn = {p.get("name") for p in (m.get("players") or [])}
    cs = get_comments(mid)
    for cm in cs: cm["participant"] = cm["author"] in pn
    return jsonify(comments=cs)

@app.post("/api/match/<mid>/comments")
def api_comments_post(mid):
    m = get_match(mid)
    if not m: abort(404)
    j = request.get_json(silent=True) or {}
    author = (j.get("author") or "").strip()[:24]
    body = (j.get("body") or "").strip()[:600]
    if not author or not body: return jsonify(error="이름과 내용을 입력하세요"), 400
    cm = add_comment(mid, author, body)
    cm["participant"] = author in {p.get("name") for p in (m.get("players") or [])}
    return jsonify(comment=cm)

@app.get("/player/<name>")
def player_page(name):
    rows = player_games(name)
    games = [_game_view(r) for r in rows]
    cc = comment_counts([g["id"] for g in games])
    wins = rated = tsec = 0; apms = []; races = Counter()
    for g, r in zip(games, rows):
        me = next((p for p in r["players"] if p.get("name") == name), None)
        g["me"] = name; g["comments"] = cc.get(g["id"], 0)
        if me:
            if me.get("race"): races[me["race"]] += 1
            if me.get("apm"): apms.append(me["apm"])
            if r.get("winner"):
                rated += 1; won = (me.get("team") == r["winner"]); g["won"] = won; wins += 1 if won else 0
            else: g["won"] = None
        tsec += _len_sec(g["length"])
    wr = f"{round(100*wins/rated)}%" if rated else "—"
    avg = round(sum(apms)/len(apms)) if apms else 0
    rc = " · ".join(f"{RACE_KO.get(k,k)} {v}" for k, v in races.most_common()) or "—"
    av = (name[:1] or "?").upper()
    cards = "".join(_card(g, i) for i, g in enumerate(games)) or \
        '<div class="empty"><div class="ebox"><h2>경기 없음</h2><p>이 아이디로 등록된 경기가 아직 없어요.</p></div></div>'
    top = _player_hero(name, av, len(games), wr, avg, rc)
    page = PAGE.replace("__TOP__", top).replace("__CARDS__", cards)
    return Response(page, mimetype="text/html")

@app.post("/api/presign")
def api_presign():
    j = request.get_json(silent=True) or request.form or {}
    if j.get("key") != CFG.get("upload_key", ""): return jsonify(error="bad key"), 401
    if not r2_enabled(): return jsonify(error="r2 not enabled"), 409
    gid = datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
    vkey, tkey = f"videos/{gid}.mp4", f"thumbs/{gid}.jpg"
    return jsonify(gid=gid,
        video_put=r2_presign_put(vkey, "video/mp4"), video_url=r2_public(vkey),
        thumb_put=r2_presign_put(tkey, "image/jpeg"), thumb_url=r2_public(tkey))

@app.post("/api/register")
def api_register():
    if request.form.get("key") != CFG.get("upload_key", ""): return jsonify(error="bad key"), 401
    gid = request.form.get("gid") or (datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2))
    uploader = (request.form.get("uploader") or "").strip() or None
    video_url = request.form.get("video_url") or ""
    thumb_url = request.form.get("thumb_url") or None
    try: size = int(request.form.get("size") or 0)
    except Exception: size = 0
    meta = {}; replay_ref = None
    rf = request.files.get("replay")
    if rf and rf.filename:
        base = os.path.join(UPLOAD_DIR, gid); os.makedirs(base, exist_ok=True)
        rdst = os.path.join(base, "replay.rep"); rf.save(rdst); meta = parse_rep(rdst)
        replay_ref = f"{gid}/replay.rep"
    _insert_match(gid, video_url, replay_ref, thumb_url, size, uploader, meta)
    return jsonify(ok=True)

@app.post("/upload")
def upload():
    if request.form.get("key") != CFG.get("upload_key", ""):
        return jsonify(error="bad key"), 401
    if "video" not in request.files:
        return jsonify(error="no video"), 400
    uploader = (request.form.get("uploader") or "").strip() or None
    vf = request.files["video"]; rf = request.files.get("replay")
    tmp = os.path.join(REC_DIR, "incoming"); os.makedirs(tmp, exist_ok=True)
    vpath = os.path.join(tmp, f"u_{datetime.datetime.now():%Y%m%d%H%M%S%f}.mp4"); vf.save(vpath)
    rpath = None
    if rf and rf.filename:
        rpath = vpath + ".rep"; rf.save(rpath)
    ingest(vpath, rpath, uploader=uploader)
    if rpath and os.path.isfile(rpath):
        try: os.remove(rpath)
        except OSError: pass
    return jsonify(ok=True)

@app.get("/media/<path:rel>")
def media(rel):
    full = os.path.normpath(os.path.join(UPLOAD_DIR, rel))
    if not full.startswith(UPLOAD_DIR) or not os.path.isfile(full): abort(404)
    return send_file(full, as_attachment=(request.args.get("dl") == "1"),
                     download_name=os.path.basename(full) if request.args.get("dl") == "1" else None)

@app.get("/health")
def health(): return jsonify(ok=True, screp=bool(SCREP), games=count_matches())

@app.get("/status")
def api_status():
    return jsonify(rec=REC_STATE.get("rec", False), text=REC_STATE.get("text", "대기 중"),
                   game=REC_STATE.get("game"), games=count_matches())

@app.get("/get")
def page_get():
    f = os.path.join(WEB_DIR, "download.html")
    if not os.path.isfile(f):
        return Response("설치 페이지를 찾을 수 없어요 (web/download.html). <a href='/'>홈으로</a>", mimetype="text/html")
    return send_file(f)

ABOUT_PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>만든이 · ENCORE</title><link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/sun-typeface/SUIT@2/fonts/variable/woff2/SUIT-Variable.css"><link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/sun-typeface/SUITE@2/fonts/variable/woff2/SUITE-Variable.css"><link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&display=swap" rel="stylesheet"><style>:root{--bg:#0C0D10;--surface:#131519;--surface2:#181B21;--well:#0E0F13;--ink:#ECEEF2;--ink2:#C5C9D0;--dim:#9AA0AA;--faint:#636872;--line:#1F232B;--line2:#2C313B;--acc:#3D8BFF;--acc-ink:#62A1FF;--acc-soft:rgba(61,139,255,.12);--acc-line:rgba(61,139,255,.34);--r1:9px;--r2:13px;--r3:17px;--fd:'SUIT Variable','Apple SD Gothic Neo','Malgun Gothic',system-ui,sans-serif;--fh:'SUITE Variable','SUIT Variable',sans-serif;--fm:'IBM Plex Mono',ui-monospace,monospace}*{box-sizing:border-box}html,body{margin:0}body{background:var(--bg);color:var(--ink);font-family:var(--fd);font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased;letter-spacing:.005em}a{color:inherit;text-decoration:none}svg{display:block}::-webkit-scrollbar{width:10px;height:10px}::-webkit-scrollbar-thumb{background:var(--line2);border-radius:6px;border:3px solid var(--bg)}.wrap{max-width:1180px;margin:0 auto;padding:0 28px 120px}.bar{position:sticky;top:0;z-index:50;background:var(--bg);border-bottom:1px solid var(--line)}.bar.scrolled{box-shadow:0 6px 22px rgba(0,0,0,.4)}.bar-in{max-width:1180px;margin:0 auto;padding:14px 28px;display:flex;align-items:center;gap:18px}.brand{display:flex;align-items:center;gap:10px}.brand .lgmk{width:20px;height:20px;color:var(--ink)}.brand b{font-family:var(--fh);font-weight:800;font-size:17px;letter-spacing:.2em}.nav{display:flex;gap:2px;margin-left:16px}.nav a{font-family:var(--fd);font-weight:600;font-size:14px;color:var(--dim);padding:8px 14px;border-radius:9px;transition:.15s}.nav a.on{color:var(--ink);background:var(--surface)}.nav a:hover{color:var(--ink)}.bar .sp{flex:1}.live{display:inline-flex;align-items:center;gap:8px;font-family:var(--fm);font-size:12px;color:var(--dim);background:var(--surface);border:1px solid var(--line);padding:9px 13px;border-radius:100px}.live .d{width:6px;height:6px;border-radius:50%;background:var(--acc);box-shadow:0 0 0 3px var(--acc-soft)}.ftr{margin-top:74px;padding-top:30px;border-top:1px solid var(--line)}.ftr-brand{display:flex;align-items:center;gap:9px;margin-bottom:13px}.ftr-brand .lgmk{width:18px;height:18px;color:var(--ink)}.ftr-brand b{font-family:var(--fh);font-weight:800;font-size:15px;letter-spacing:.18em}.ftr p{margin:5px 0;font-size:13px;line-height:1.6;color:var(--dim)}.ftr-by{font-family:var(--fd);font-size:13px;color:var(--dim);margin-top:13px}.ftr-by b{color:var(--ink2);font-weight:700}.ftr-by .hdl{font-family:var(--fm);font-size:12px;color:var(--faint)}@media(max-width:760px){.nav{display:none}.live{display:none}}.ahero{padding:58px 0 6px}.aey{font-family:var(--fm);font-size:11px;letter-spacing:.3em;color:var(--acc);margin-bottom:16px}.atitle{font-family:var(--fh);font-weight:800;font-size:clamp(38px,6vw,62px);letter-spacing:-.03em;margin:0;line-height:1.04;color:#F7F4EE}.alead{font-family:var(--fh);font-weight:700;font-size:clamp(18px,2.4vw,23px);line-height:1.7;color:var(--ink2);margin:24px 0 0;max-width:840px;letter-spacing:-.01em}.scene{margin:50px 0 0;max-width:920px}.snaps{display:flex;gap:22px;justify-content:center;align-items:flex-start;flex-wrap:wrap;max-width:920px;margin:50px auto 0}.snap{flex:0 1 290px;max-width:330px}.snap .scap{justify-content:center;text-align:center}.snap .scap::before{display:none}.scene .pic{position:relative;width:100%;border-radius:4px;border:8px solid #E9E2D0;background:#E9E2D0;box-shadow:0 14px 38px rgba(0,0,0,.55),0 2px 5px rgba(0,0,0,.4);overflow:hidden}.scene .pic img{display:block;width:100%;height:auto;filter:saturate(.86) sepia(.12) contrast(1.06) brightness(.95)}
.scene .pic>svg{display:block;width:100%;height:auto;filter:saturate(.68) sepia(.27) contrast(1.07) brightness(.93)}
.scene .pic::before{content:"";position:absolute;inset:0;pointer-events:none;opacity:.42;mix-blend-mode:overlay;background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.82' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>")}
.scene .pic::after{content:"";position:absolute;inset:0;pointer-events:none;background:radial-gradient(ellipse 125% 105% at 50% 42%,rgba(40,26,8,0) 48%,rgba(34,20,6,.55) 100%)}.scap{font-family:var(--fm);font-size:12px;color:var(--faint);margin:13px 0 0;letter-spacing:.02em;display:flex;align-items:center;gap:9px}.scap::before{content:'';width:16px;height:1px;background:var(--line2);flex-shrink:0}.story{max-width:840px;margin:42px 0 0}.story p{font-size:17px;line-height:1.92;color:var(--ink2);margin:0 0 22px}.story .em{font-family:var(--fh);font-weight:700;font-size:clamp(19px,2.6vw,24px);line-height:1.65;color:var(--ink);letter-spacing:-.01em;margin-bottom:26px}.story b{color:var(--acc-ink);font-weight:700}.thanks{max-width:840px;margin:58px 0 0;background:var(--surface);border:1px solid var(--line);border-radius:18px;padding:32px 30px}.tlabel{font-family:var(--fm);font-size:11px;letter-spacing:.28em;color:var(--acc);margin-bottom:16px}.thanks p{font-size:16px;line-height:2;color:var(--ink2);margin:0}.thanks .dim{color:var(--faint);font-size:14.5px}.sign{max-width:840px;margin:36px 0 0;display:flex;align-items:center;gap:15px}.sign .sbar{width:32px;height:32px;color:var(--ink);opacity:.9;flex-shrink:0}.sby{font-family:var(--fd);font-weight:700;font-size:15px;color:var(--ink2)}.sby .hdl{font-family:var(--fm);font-weight:500;font-size:13px;color:var(--faint);margin-left:4px}.syr{font-family:var(--fm);font-size:11.5px;color:var(--faint);margin-top:4px}</style></head><body><div class="bar"><div class="bar-in"><a class="brand" href="/"><svg class="lgmk" viewBox="0 0 32 32" fill="currentColor"><rect x="3.5" y="20" width="6" height="8" rx="1.6"/><rect x="13" y="12.5" width="6" height="15.5" rx="1.6"/><rect x="22.5" y="5" width="6" height="23" rx="1.6"/></svg><b>ENCORE</b></a><nav class="nav"><a href="/">아카이브</a><a class="on" href="/about">만든이</a><a href="/manual">매뉴얼</a><a href="/download">다운로드</a></nav><span class="sp"></span><span class="live"><span class="d"></span>녹화 대기 중</span></div></div><div class="wrap"><main id="view" data-page="about"><section class="ahero"><div class="aey">THE STORY</div><h1 class="atitle">한 판만 더.</h1><p class="alead">PC방 불빛 아래, 라면 한 젓가락에 어택땅 한 번.<br>그 시절의 밤은, 아직 끝나지 않았습니다.</p></section><div class="scene"><div class="pic"><img src="/asset/tourney.jpg" alt="스타크래프트 게임왕 선발대회" loading="lazy"></div><p class="scap">스타크래프트 게임왕 선발대회 · 그땐 모두가 선수였다</p></div><div class="snaps"><div class="snap"><div class="pic"><img src="/asset/crt2.jpg" alt="CRT에 뜬 스타크래프트 로딩 화면" loading="lazy"></div><p class="scap">로딩 화면이 뜨던 그 순간</p></div><div class="snap"><div class="pic"><img src="/asset/crt3.jpg" alt="CRT로 즐기던 스타크래프트 한 판" loading="lazy"></div><p class="scap">그리고, 한 판</p></div></div><div class="story"><p class="em">스무 살, 우리는 매일 밤 PC방에 모였습니다.</p><p>한 시간에 천 원. 자리부터 맡아두고, 컵라면에 콜라 한 캔. 옆자리 친구와 팀 짜서 빠른무한 한 판. <b>어택땅 한 번에 환호하고, GG 한 번에 무너지던</b> 그 밤들이었죠.</p><p>스타리그를 보며 따라 하던 빌드, 친구 몰래 연습한 컨트롤. 새벽 세 시, 사장님 눈치를 보면서도 우리는 또 ‘<b>한 판만 더</b>’를 외쳤습니다.</p></div><div class="scene"><div class="pic"><img src="/asset/boxes.jpg" alt="모아둔 스타크래프트·브루드워 패키지" loading="lazy"></div><p class="scap">집 한켠에 모아둔 그 시절의 패키지들</p></div><div class="scene"><div class="pic"><svg viewBox="0 0 680 238" xmlns="http://www.w3.org/2000/svg" fill="none"><defs><radialGradient id="rg" cx="50%" cy="84%" r="72%"><stop offset="0" stop-color="rgba(224,80,62,.36)"/><stop offset="1" stop-color="rgba(224,80,62,0)"/></radialGradient></defs><rect width="680" height="238" fill="#0A0D12"/><ellipse cx="340" cy="220" rx="370" ry="150" fill="url(#rg)"/><g stroke="#2C313B" stroke-width="1.4"><line x1="74" y1="42" x2="74" y2="118"/><line x1="606" y1="42" x2="606" y2="118"/></g><g fill="#181B21" stroke="#2C313B"><rect x="52" y="26" width="44" height="16" rx="3"/><rect x="584" y="26" width="44" height="16" rx="3"/></g><g fill="rgba(255,235,180,.5)"><circle cx="60" cy="34" r="1.6"/><circle cx="68" cy="34" r="1.6"/><circle cx="76" cy="34" r="1.6"/><circle cx="84" cy="34" r="1.6"/><circle cx="592" cy="34" r="1.6"/><circle cx="600" cy="34" r="1.6"/><circle cx="608" cy="34" r="1.6"/><circle cx="616" cy="34" r="1.6"/></g><g transform="translate(340,70)"><circle r="33" fill="#ECEEF2" stroke="#9AA0AA" stroke-width="1.4"/><polygon points="0,-13 12,-4 8,11 -8,11 -12,-4" fill="#15191F"/><path d="M0,-33 L0,-13 M12,-4 L31,-12 M8,11 L20,28 M-8,11 L-20,28 M-12,-4 L-31,-12" stroke="#9AA0AA" stroke-width="1.2"/></g><text x="340" y="150" font-family="SUITE Variable,SUIT Variable,sans-serif" font-weight="800" font-size="40" fill="#E0503E" text-anchor="middle" letter-spacing="6">2002</text><text x="340" y="173" font-family="IBM Plex Mono,monospace" font-size="11" fill="#C5C9D0" text-anchor="middle" letter-spacing="4">대 한 민 국</text><g fill="#E0503E"><circle cx="299" cy="187" r="3"/><circle cx="317" cy="187" r="3"/><circle cx="335" cy="187" r="3"/><circle cx="351" cy="187" r="3"/><circle cx="365" cy="187" r="3"/></g><g transform="translate(60,210)"><circle cx="0" cy="0" r="4.3" fill="#E0503E"/><path d="M-4.5 6 q4.5 5 9 0 l1.5 18 h-12 z" fill="#E0503E"/><path d="M-3.5 6 L-9 -4 M3.5 6 L9 -4" stroke="#E0503E" stroke-width="2.3" stroke-linecap="round"/></g><g transform="translate(104,214)"><circle cx="0" cy="0" r="4.3" fill="#A6392C"/><path d="M-4.5 6 q4.5 5 9 0 l1.5 18 h-12 z" fill="#A6392C"/><path d="M-3.5 6 L-9 -4 M3.5 6 L9 -4" stroke="#A6392C" stroke-width="2.3" stroke-linecap="round"/></g><g transform="translate(148,212)"><circle cx="0" cy="0" r="4.3" fill="#E0503E"/><path d="M-4.5 6 q4.5 5 9 0 l1.5 18 h-12 z" fill="#E0503E"/><path d="M-3.5 6 L-9 -4 M3.5 6 L9 -4" stroke="#E0503E" stroke-width="2.3" stroke-linecap="round"/></g><g transform="translate(192,210)"><circle cx="0" cy="0" r="4.3" fill="#A6392C"/><path d="M-4.5 6 q4.5 5 9 0 l1.5 18 h-12 z" fill="#A6392C"/><path d="M-3.5 6 L-9 -4 M3.5 6 L9 -4" stroke="#A6392C" stroke-width="2.3" stroke-linecap="round"/></g><g transform="translate(236,214)"><circle cx="0" cy="0" r="4.3" fill="#E0503E"/><path d="M-4.5 6 q4.5 5 9 0 l1.5 18 h-12 z" fill="#E0503E"/><path d="M-3.5 6 L-9 -4 M3.5 6 L9 -4" stroke="#E0503E" stroke-width="2.3" stroke-linecap="round"/></g><g transform="translate(280,212)"><circle cx="0" cy="0" r="4.3" fill="#A6392C"/><path d="M-4.5 6 q4.5 5 9 0 l1.5 18 h-12 z" fill="#A6392C"/><path d="M-3.5 6 L-9 -4 M3.5 6 L9 -4" stroke="#A6392C" stroke-width="2.3" stroke-linecap="round"/></g><g transform="translate(324,210)"><circle cx="0" cy="0" r="4.3" fill="#E0503E"/><path d="M-4.5 6 q4.5 5 9 0 l1.5 18 h-12 z" fill="#E0503E"/><path d="M-3.5 6 L-9 -4 M3.5 6 L9 -4" stroke="#E0503E" stroke-width="2.3" stroke-linecap="round"/></g><g transform="translate(368,214)"><circle cx="0" cy="0" r="4.3" fill="#A6392C"/><path d="M-4.5 6 q4.5 5 9 0 l1.5 18 h-12 z" fill="#A6392C"/><path d="M-3.5 6 L-9 -4 M3.5 6 L9 -4" stroke="#A6392C" stroke-width="2.3" stroke-linecap="round"/></g><g transform="translate(412,212)"><circle cx="0" cy="0" r="4.3" fill="#E0503E"/><path d="M-4.5 6 q4.5 5 9 0 l1.5 18 h-12 z" fill="#E0503E"/><path d="M-3.5 6 L-9 -4 M3.5 6 L9 -4" stroke="#E0503E" stroke-width="2.3" stroke-linecap="round"/></g><g transform="translate(456,210)"><circle cx="0" cy="0" r="4.3" fill="#A6392C"/><path d="M-4.5 6 q4.5 5 9 0 l1.5 18 h-12 z" fill="#A6392C"/><path d="M-3.5 6 L-9 -4 M3.5 6 L9 -4" stroke="#A6392C" stroke-width="2.3" stroke-linecap="round"/></g><g transform="translate(500,214)"><circle cx="0" cy="0" r="4.3" fill="#E0503E"/><path d="M-4.5 6 q4.5 5 9 0 l1.5 18 h-12 z" fill="#E0503E"/><path d="M-3.5 6 L-9 -4 M3.5 6 L9 -4" stroke="#E0503E" stroke-width="2.3" stroke-linecap="round"/></g><g transform="translate(544,212)"><circle cx="0" cy="0" r="4.3" fill="#A6392C"/><path d="M-4.5 6 q4.5 5 9 0 l1.5 18 h-12 z" fill="#A6392C"/><path d="M-3.5 6 L-9 -4 M3.5 6 L9 -4" stroke="#A6392C" stroke-width="2.3" stroke-linecap="round"/></g><g transform="translate(588,210)"><circle cx="0" cy="0" r="4.3" fill="#E0503E"/><path d="M-4.5 6 q4.5 5 9 0 l1.5 18 h-12 z" fill="#E0503E"/><path d="M-3.5 6 L-9 -4 M3.5 6 L9 -4" stroke="#E0503E" stroke-width="2.3" stroke-linecap="round"/></g></svg></div><p class="scap">2002년 여름 · 거리는 온통 붉은색이었다</p></div><div class="story"><p>그해 여름엔 온 나라가 붉은 티셔츠를 입었습니다. 광장에 모여 ‘대~한민국’을 외치고, 골이 터질 때마다 모르는 사람과 얼싸안던 — <b>그런 시절이, 우리에게 있었습니다.</b></p><p>그리고 우리는 어느새 마흔을 넘겼습니다. 각자의 자리에서 바쁘게 살아가지만, 가끔은 그 밤들이 사무치게 그립습니다.</p></div><div class="scene"><div class="pic"><svg viewBox="0 0 640 380" xmlns="http://www.w3.org/2000/svg" fill="none"><defs><linearGradient id="scr" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#10192A"/><stop offset="1" stop-color="#0A0D12"/></linearGradient><radialGradient id="glow" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="rgba(61,139,255,.20)"/><stop offset="1" stop-color="rgba(61,139,255,0)"/></radialGradient></defs><ellipse cx="475" cy="200" rx="190" ry="150" fill="url(#glow)"/><rect x="44" y="46" width="172" height="150" rx="7" fill="#0B0E14" stroke="#2C313B" stroke-width="1.5"/><line x1="130" y1="46" x2="130" y2="196" stroke="#222732"/><line x1="44" y1="121" x2="216" y2="121" stroke="#222732"/><circle cx="182" cy="78" r="13" fill="rgba(61,139,255,.12)" stroke="rgba(61,139,255,.34)"/><circle cx="74" cy="72" r="1.6" fill="#9AA0AA"/><circle cx="98" cy="150" r="1.2" fill="#636872"/><circle cx="160" cy="100" r="1.3" fill="#636872"/><rect x="0" y="312" width="640" height="68" fill="#131519"/><line x1="0" y1="312" x2="640" y2="312" stroke="#2C313B"/><rect x="356" y="120" width="244" height="158" rx="11" fill="#0C0D10" stroke="#2C313B" stroke-width="2"/><rect x="371" y="135" width="214" height="128" rx="4" fill="url(#scr)"/><rect x="430" y="214" width="24" height="34" rx="3" fill="#3D8BFF"/><rect x="466" y="190" width="24" height="58" rx="3" fill="#3D8BFF"/><rect x="502" y="162" width="24" height="86" rx="3" fill="#62A1FF"/><rect x="468" y="278" width="20" height="22" fill="#2C313B"/><rect x="438" y="299" width="80" height="9" rx="3" fill="#2C313B"/><rect x="372" y="318" width="180" height="36" rx="7" fill="#181B21" stroke="#2C313B"/><g opacity=".95"><path d="M251 312 h46 l-5 -36 h-36 z" fill="#181B21" stroke="#2C313B"/><ellipse cx="274" cy="276" rx="18" ry="4.5" fill="rgba(61,139,255,.12)" stroke="rgba(61,139,255,.34)"/><path d="M267 266 q-5 -9 2 -16 M281 266 q5 -9 -2 -16" stroke="#636872" stroke-width="2" stroke-linecap="round" fill="none" opacity=".7"/></g></svg></div><p class="scap">그리고 지금 — ENCORE가 그 밤을 다시 기록합니다</p></div><div class="story"><p class="em">ENCORE는 그 시절을 위해 만들었습니다.</p><p>다시 모인 크루의 명경기를, 흐릿한 기억이 아니라 <b>선명한 영상</b>으로 남기려고. 켜두기만 하면 알아서 녹화되고 분석돼, 갤러리에 차곡차곡 쌓입니다.</p><p>오늘 밤도 ‘한 판만 더’를 외치는 모든 아재들에게. 다시, 스무 살.</p></div><section class="thanks"><div class="tlabel">SPECIAL THANKS</div><p>스타크래프트를 사랑하는 모든 아재들에게.<br>그리고 함께 빠른무한을 돌려준 우리 크루에게.<br><span class="dim">당신들이 있어, 그 시절이 빛났습니다.</span></p></section><div class="sign"><svg class="sbar" viewBox="0 0 32 32" fill="currentColor"><rect x="3.5" y="20" width="6" height="8" rx="1.6"/><rect x="13" y="12.5" width="6" height="15.5" rx="1.6"/><rect x="22.5" y="5" width="6" height="23" rx="1.6"/></svg><div><div class="sby">만든이 · 최성호 <span class="hdl">veatbox</span></div><div class="syr">2026 — 브루드워를 사랑하는 마음으로</div></div></div></main><footer class="ftr"><div class="ftr-brand"><svg class="lgmk" viewBox="0 0 32 32" fill="currentColor"><rect x="3.5" y="20" width="6" height="8" rx="1.6"/><rect x="13" y="12.5" width="6" height="15.5" rx="1.6"/><rect x="22.5" y="5" width="6" height="23" rx="1.6"/></svg><b>ENCORE</b></div><p>스무 살의 우리에게 — 다시, 브루드워.</p><p class="ftr-by">만든이 <b>최성호</b> · <span class="hdl">veatbox</span></p></footer></div></body></html>"""

@app.get("/about")
def page_about():
    return Response(ABOUT_PAGE, mimetype="text/html")

@app.get("/asset/<path:name>")
def page_asset(name):
    f = os.path.join(WEB_DIR, "img", name)
    if not os.path.isfile(f): abort(404)
    return send_file(f)

@app.get("/manual")
def page_manual():
    f = os.path.join(WEB_DIR, "manual.html")
    if not os.path.isfile(f):
        return Response("메뉴얼을 찾을 수 없어요 (web/manual.html). <a href='/'>홈으로</a>", mimetype="text/html")
    return send_file(f)

@app.get("/download")
def page_download():
    f = os.path.join(WEB_DIR, "download.html")
    if not os.path.isfile(f):
        return Response("다운로드 페이지를 찾을 수 없어요 (web/download.html). <a href='/'>홈으로</a>", mimetype="text/html")
    return send_file(f)

@app.get("/app.zip")
def app_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(HERE):
            dirs[:] = [d for d in dirs if d not in ("data", "__pycache__", ".git", "incoming")]
            for fn in files:
                if fn == "config.json" or fn.endswith(".pyc"): continue
                full = os.path.join(root, fn); rel = os.path.relpath(full, HERE)
                z.write(full, os.path.join("sc_auto_recorder", rel))
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name="sc_auto_recorder.zip")

def run_server(port):
    app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False)

# ===================== 6. 녹화기 (ffmpeg) =====================
_ENC_CACHE = None
_ENC_IS_SW = False   # 소프트웨어(libx264) 인코딩 여부 → 다운스케일 판단에 사용
def _encoder_args():
    """인코더 자동 선택. NVENC는 '실제로 인코딩 되는지'까지 테스트 — 목록엔 있어도 런타임 실패면 libx264로."""
    global _ENC_CACHE, _ENC_IS_SW
    if _ENC_CACHE is not None: return _ENC_CACHE
    pref = (CFG.get("encoder") or "auto").lower()
    have = ""
    try:
        have = _run([FFMPEG, "-hide_banner", "-encoders"],
                              capture_output=True, text=True, timeout=15).stdout or ""
    except Exception: pass
    def _nvenc_ok():
        # 256x256 같은 초소형은 NVENC가 거부할 수 있어 720p로 테스트. 실패하면 진짜 에러를 보여줌.
        try:
            r = _run([FFMPEG, "-hide_banner", "-loglevel", "error",
                                "-f", "lavfi", "-i", "color=c=black:s=1280x720:r=30:d=1",
                                "-c:v", "h264_nvenc", "-pix_fmt", "yuv420p", "-f", "null", "-"],
                               capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                errs = [l for l in (r.stderr or "").splitlines() if l.strip()]
                if errs: log("  NVENC 오류: " + "  /  ".join(errs[-2:]))
                return False
            return True
        except Exception as e:
            log(f"  NVENC 테스트 예외: {e}")
            return False
    if pref == "nvenc":
        use_nvenc = True
    elif pref in ("x264", "libx264", "software", "cpu"):
        use_nvenc = False
    else:  # auto — 실제 인코딩 테스트
        use_nvenc = ("h264_nvenc" in have) and _nvenc_ok()
        if ("h264_nvenc" in have) and not use_nvenc:
            log("  NVENC가 목록엔 있지만 실제 인코딩에 실패 → 소프트웨어(libx264)로 전환")
    if use_nvenc:
        _ENC_IS_SW = False
        _ENC_CACHE = ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "20"]; name = "NVENC (NVIDIA 하드웨어)"
    else:
        _ENC_IS_SW = True
        preset = (CFG.get("preset") or "auto").lower()
        if preset in ("auto", ""): preset = "superfast"   # 소프트웨어는 게임 끊김 방지 위해 가벼운 프리셋
        _ENC_CACHE = ["-c:v", "libx264", "-preset", preset, "-crf", "25"]; name = f"libx264 (소프트웨어, {preset})"
    log(f"인코더: {name}")
    return _ENC_CACHE

def _target_height(src_h=0):
    """소프트웨어 인코딩이면 부하를 줄이려 다운스케일할 목표 높이. None이면 원본 유지."""
    _encoder_args()  # _ENC_IS_SW 확정
    pref = str(CFG.get("scale") or "auto").lower()
    if pref in ("source", "원본", "full", "native", "off", "0"): return None
    if pref in ("1080", "1080p"): th = 1080
    elif pref in ("720", "720p"): th = 720
    elif pref in ("480", "480p"): th = 480
    elif pref in ("1440", "1440p"): th = 1440
    else:  # auto: 소프트웨어면 720p로, 하드웨어(NVENC)면 원본
        th = 720 if _ENC_IS_SW else None
    if th is None: return None
    if src_h and src_h <= th: return None   # 업스케일 금지
    return th

def _scale_vf(src_h=0):
    """(-vf 인자 리스트, filter_complex 체인에 붙일 문자열) 반환. 다운스케일 불필요하면 둘 다 비움."""
    th = _target_height(src_h)
    if not th: return [], ""
    expr = f"scale=-2:'min({th},ih)':flags=fast_bilinear"
    return ["-vf", expr], "," + expr

class Recorder:
    # ddagrab = Desktop Duplication API. 윈10/11에선 '전체화면(독점)'도 잡힙니다.
    # gdigrab = 옛날 GDI 방식. 전체화면 독점에선 검은 화면이라 보조용.
    def __init__(self, fps):
        self.fps = fps; self.proc = None; self.path = None
        self.mode = "ddagrab"; self.output_idx = 0; self.verified = False; self.warned_black = False
        self.backend = "ffmpeg"; self.verified_backend = None
        self._wgc_control = None; self._wgc_state = None
        self._t_start = 0.0; self.last_seconds = 0.0   # 직전 녹화 길이(초) — 메뉴 클립/실제 게임 구분용
        self._aud = None; self._vt0 = None   # 오디오(WASAPI 루프백) 상태 + 영상 첫 프레임 시각
    def _cmd(self, out, mode, output_idx=0):
        enc = _encoder_args()
        vf, chain = _scale_vf(0)   # 데스크톱 높이를 모르므로 min() 식이 런타임에 처리(업스케일 안 함)
        tail = [*enc, "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]
        if mode == "ddagrab":
            return [FFMPEG, "-y", "-loglevel", "error",
                    "-filter_complex", f"ddagrab=output_idx={output_idx}:framerate={self.fps},hwdownload,format=bgra{chain}", *tail]
        return [FFMPEG, "-y", "-loglevel", "error", "-f", "gdigrab",
                "-framerate", str(self.fps), "-i", "desktop", *vf, *tail]
    def _spawn(self, mode, output_idx=0):
        self.path = os.path.join(REC_DIR, f"clip_{datetime.datetime.now():%Y%m%d_%H%M%S}.mp4")
        self.proc = subprocess.Popen(self._cmd(self.path, mode, output_idx),
                      stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self._vt0 = time.time()
    def _alive(self):
        return self.proc is not None and self.proc.poll() is None
    def _capturing(self, secs=3.0, floor=40000):
        # 녹화 파일이 실제로 커지면 = 화면이 잡히는 것. 검은 화면이면 거의 안 커짐.
        try: s0 = os.path.getsize(self.path)
        except OSError: s0 = 0
        time.sleep(secs)
        try: s1 = os.path.getsize(self.path)
        except OSError: s1 = 0
        return (s1 - s0) >= floor
    def _kill(self):
        if self.proc:
            try: self.proc.terminate(); self.proc.wait(timeout=5)
            except Exception:
                try: self.proc.kill()
                except Exception: pass
        self.proc = None
        try:  # 빈(검은) 클립은 삭제
            if self.path and os.path.isfile(self.path) and os.path.getsize(self.path) < 40000:
                os.remove(self.path)
        except OSError: pass
    def _recording(self):
        if self.backend == "wgc":
            st = self._wgc_state or {}
            ft = st.get("feeder")
            return bool(ft and ft.is_alive())   # 피더 스레드가 죽으면 녹화가 끊긴 것
        return self._alive()

    def _start_audio(self):
        """시스템 사운드(게임 소리)를 WASAPI 루프백으로 WAV에 병렬 녹음.
        Windows 내장 기능이라 Stereo Mix·가상케이블 없이 어떤 PC에서도 동작.
        실패하면 무음으로 진행(영상 녹화는 영향 없음)."""
        self._stop_audio(discard=True); self._vt0 = None
        self.audio_path = os.path.join(REC_DIR, f"audio_{datetime.datetime.now():%Y%m%d_%H%M%S}.wav")
        box = {"stop": threading.Event(), "t0": None, "thread": None, "ok": False, "path": self.audio_path}
        def worker():
            try:
                import pyaudiowpatch as pa, wave
            except Exception as e:
                log(f"  (소리) pyaudiowpatch 미설치 → 무음 녹화. 설치: pip install pyaudiowpatch ({e})"); return
            p = stream = wf = None
            try:
                p = pa.PyAudio()
                try:
                    dev = p.get_default_wasapi_loopback()           # 기본 출력장치의 루프백
                except Exception:
                    wi = p.get_host_api_info_by_type(pa.paWASAPI)   # 폴백: 직접 탐색
                    spk = p.get_device_info_by_index(wi["defaultOutputDevice"]); dev = None
                    for lb in p.get_loopback_device_info_generator():
                        if spk.get("name","") in lb.get("name",""): dev = lb; break
                    if dev is None: raise RuntimeError("WASAPI 루프백 장치를 찾지 못함")
                ch = int(dev.get("maxInputChannels") or 2) or 2
                rate = int(dev.get("defaultSampleRate") or 48000) or 48000
                wf = wave.open(box["path"], "wb"); wf.setnchannels(ch); wf.setsampwidth(2); wf.setframerate(rate)
                stream = p.open(format=pa.paInt16, channels=ch, rate=rate, input=True,
                                input_device_index=dev["index"], frames_per_buffer=2048)
                box["t0"] = time.time(); box["ok"] = True
                log(f"  ♪ 소리 녹음 시작 ({str(dev.get('name','?'))[:26]} · {rate}Hz {ch}ch)")
                while not box["stop"].is_set():
                    try: wf.writeframes(stream.read(2048, exception_on_overflow=False))
                    except Exception: break
            except Exception as e:
                log(f"  (소리) 캡처 실패 → 무음 녹화: {e}")
            finally:
                for fn in (lambda: stream and stream.stop_stream(), lambda: stream and stream.close(),
                           lambda: wf and wf.close(), lambda: p and p.terminate()):
                    try: fn()
                    except Exception: pass
        t = threading.Thread(target=worker, daemon=True); box["thread"] = t; t.start()
        self._aud = box

    def _stop_audio(self, discard=False):
        box = self._aud; self._aud = None
        if not box: return (None, None)
        try: box["stop"].set()
        except Exception: pass
        th = box.get("thread")
        if th:
            try: th.join(timeout=8)
            except Exception: pass
        path = box.get("path"); t0 = box.get("t0")
        if discard:
            try:
                if path and os.path.isfile(path): os.remove(path)
            except OSError: pass
            return (None, None)
        return (path if box.get("ok") else None, t0)

    def _finalize(self):
        """영상 클립 + 병렬 녹음한 소리를 합쳐 최종 mp4. 소리 없으면 영상만 그대로."""
        vid = self.path if (self.path and os.path.isfile(self.path)) else None
        wav, at0 = self._stop_audio()
        if not vid:
            try:
                if wav and os.path.isfile(wav): os.remove(wav)
            except OSError: pass
            return None
        if not (wav and os.path.isfile(wav) and os.path.getsize(wav) > 2000):
            return vid                                  # 소리 없음 → 영상만(기존 동작)
        if not FFMPEG:
            return vid
        try:
            out = (vid[:-4] if vid.lower().endswith(".mp4") else vid) + "_av.mp4"
            voff = 0.0
            if self._vt0 and at0 and self._vt0 > at0:
                voff = min(10.0, self._vt0 - at0)       # 영상이 늦게 시작한 만큼 소리 앞부분을 잘라 싱크
            cmd = [FFMPEG, "-y", "-loglevel", "error"]
            if voff > 0.05: cmd += ["-ss", f"{voff:.3f}"]
            cmd += ["-i", wav, "-i", vid, "-map", "1:v:0", "-map", "0:a:0",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", "-shortest", out]
            _run(cmd, timeout=900)
            if os.path.isfile(out) and os.path.getsize(out) > 40000:
                for f in (vid, wav):
                    try: os.remove(f)
                    except OSError: pass
                self.path = out; log("■ 소리 합치기 완료"); return out
            log("  (소리) 합치기 결과가 비어 영상만 사용")
            try:
                if os.path.isfile(out): os.remove(out)
            except OSError: pass
            return vid
        except Exception as e:
            log(f"  (소리) 합치기 실패 → 영상만: {e}"); return vid

    def _start_wgc(self, verify=True):
        """WGC(OBS식)로 프레임을 받아 ffmpeg로 인코딩. 정지화면이어도 직전 프레임을 고정 fps로 계속 먹임(전체화면 게임도 잡힘)."""
        try:
            from windows_capture import WindowsCapture
        except ImportError:
            try:
                log("WGC 엔진 설치 중(windows-capture)…")
                _run([sys.executable, "-m", "pip", "install", "-q", "windows-capture", "--break-system-packages"], timeout=240)
                from windows_capture import WindowsCapture
            except Exception as e:
                log(f"  WGC 사용 불가(설치 실패: {e})"); return False
        try:
            import numpy as _np
        except Exception as e:
            log(f"  WGC 사용 불가(numpy 없음: {e})"); return False
        self.path = os.path.join(REC_DIR, f"clip_{datetime.datetime.now():%Y%m%d_%H%M%S}.mp4")
        enc = _encoder_args(); pathx = self.path; fps = self.fps
        shared = {"buf": None, "wh": None, "n": 0, "err": None}
        stop_ev = threading.Event(); proc_box = {"p": None}
        try:
            cap = WindowsCapture(cursor_capture=None, draw_border=None, monitor_index=1, window_name=None)
        except Exception as e:
            log(f"  WGC 초기화 실패: {e}"); return False

        @cap.event
        def on_frame_arrived(frame, capture_control):
            if stop_ev.is_set():
                try: capture_control.stop()
                except Exception: pass
                return
            try:
                shared["buf"] = frame.frame_buffer          # numpy 처리는 피더에서 (콜백은 최대한 단순하게)
                shared["wh"] = (frame.width, frame.height)
                shared["n"] = shared.get("n", 0) + 1
            except Exception as e:
                if shared.get("err") is None: shared["err"] = repr(e)

        @cap.event
        def on_closed():
            pass

        def feeder():
            t0 = time.time()
            while shared["buf"] is None and time.time() - t0 < 3.0 and not stop_ev.is_set():
                time.sleep(0.05)
            if shared["buf"] is None: return            # 프레임이 하나도 안 옴 = 캡처 실패
            w, h = shared["wh"]
            vf, _chain = _scale_vf(h)
            cmd = [FFMPEG, "-y", "-loglevel", "error",
                   "-f", "rawvideo", "-pixel_format", "bgra", "-video_size", f"{w}x{h}", "-framerate", str(fps),
                   "-i", "pipe:", *vf, *enc, "-pix_fmt", "yuv420p", "-movflags", "+faststart", pathx]
            if vf: log(f"  소프트웨어 부하↓: {h}p 캡처 → {_target_height(h)}p 로 인코딩")
            errlog = os.path.join(REC_DIR, "wgc_ffmpeg.log")
            try: _ef = open(errlog, "w", encoding="utf-8", errors="replace")
            except Exception: _ef = subprocess.DEVNULL
            try:
                p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                     stderr=_ef, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except Exception:
                return
            proc_box["p"] = p; self._vt0 = time.time()
            interval = 1.0 / max(1, fps); nxt = time.time()
            while not stop_ev.is_set():
                b = shared["buf"]
                if b is not None:
                    try:
                        if b.shape[1] != w: b = b[:, :w]            # 스트라이드 보정
                        p.stdin.write(_np.ascontiguousarray(b).tobytes())
                    except Exception: break
                nxt += interval; d = nxt - time.time()
                if d > 0: time.sleep(d)
                else: nxt = time.time()
            try: p.stdin.close()
            except Exception: pass
            try: p.wait(timeout=15)
            except Exception:
                try: p.terminate()
                except Exception: pass

        try:
            control = cap.start_free_threaded()
        except Exception as e:
            log(f"  WGC 시작 실패: {e}"); return False
        ft = threading.Thread(target=feeder, daemon=True); ft.start()
        self._wgc_control = control
        self._wgc_state = {"stop": stop_ev, "feeder": ft, "proc_box": proc_box}
        self.backend = "wgc"
        if not verify:
            log("● 녹화 시작 (WGC)"); return True
        # --- WGC 검증 ---
        # WGC는 프레임 카운터로 '화면 잡힘'을 직접 확인할 수 있다. 파일 크기는 ffmpeg가 쓰는 중인지 확인용.
        # (NVENC는 첫 키프레임을 측정 전에 쓰고 정적 화면에선 이후 증가가 작아, '델타 40KB' 방식은 오판함 → 절대 크기로 판단)
        def _fflog():
            try:
                _lp = os.path.join(REC_DIR, "wgc_ffmpeg.log")
                if os.path.isfile(_lp):
                    _ls = [l for l in open(_lp, encoding="utf-8", errors="replace").read().strip().splitlines() if l.strip()]
                    return " | ".join(_ls[-3:])
            except Exception: pass
            return ""
        def _sz():
            try: return os.path.getsize(self.path)
            except OSError: return 0
        time.sleep(3.5)   # NVENC 첫 키프레임 + 인코딩 시작 시간 확보
        n1 = shared.get("n", 0)
        pp = proc_box.get("p"); alive = (pp is not None and pp.poll() is None)
        ferr = _fflog()
        ok = (n1 >= 15) and alive and (not ferr)   # 프레임 들어옴 + ffmpeg 정상 동작
        if ok and _sz() >= 8000:
            log("● 녹화 시작 (WGC — 화면 캡처 정상 확인)"); return True
        if ok:                                       # 파일이 아직 작으면(정적 화면) 잠깐 더 대기 후 재확인
            time.sleep(2.5)
            if _sz() >= 8000:
                log("● 녹화 시작 (WGC — 화면 캡처 정상 확인)"); return True
        stop_ev.set()
        try: control.stop()
        except Exception: pass
        try: ft.join(timeout=5)
        except Exception: pass
        self.backend = "ffmpeg"; self._wgc_control = None; self._wgc_state = None
        log("  WGC 캡처 안 됨 (받은 프레임:{}개, ffmpeg:{}, 파일:{}B, 에러:{}) → 다른 방식 시도".format(
            n1, "동작중" if alive else "종료됨", _sz(), ferr or "없음"))
        return False

    def start(self):
        if self._recording(): return True
        self._t_start = time.time()   # 새 클립 시작 시각
        self._start_audio()   # 시스템 사운드 병렬 녹음(백엔드 무관, PC 안 탐)
        capmode = (CFG.get("capture") or "auto").lower()
        # 검증된 방식 빠른 재시작
        if self.verified:
            try:
                if self.verified_backend == "wgc":
                    if self._start_wgc(verify=False): return True
                else:
                    self._spawn(self.mode, self.output_idx); time.sleep(1.0)
                    if self._alive():
                        log(f"● 녹화 시작 ({'모니터 '+str(self.output_idx) if self.mode=='ddagrab' else 'gdigrab'})"); return True
            except Exception: pass
            self.verified = False
        # 1순위: WGC (auto/wgc) — 전체화면도 잡히는 OBS식 엔진
        if capmode in ("auto", "wgc"):
            try:
                if self._start_wgc(verify=True):
                    self.verified = True; self.verified_backend = "wgc"; return True
            except Exception as e:
                log(f"WGC 오류: {e}")
            if capmode == "wgc":
                log("  WGC 실패 → ddagrab/gdigrab 폴백")
        # 2순위: ddagrab(모니터 0/1/2) → gdigrab
        ci = CFG.get("output_idx", "auto")
        if isinstance(ci, int) or (isinstance(ci, str) and ci.isdigit()):
            candidates = [("ddagrab", int(ci)), ("gdigrab", 0)]
        else:
            candidates = [("ddagrab", 0), ("ddagrab", 1), ("ddagrab", 2), ("gdigrab", 0)]
        for mode, idx in candidates:
            try:
                self._spawn(mode, idx); time.sleep(2.0)
                if not self._alive():
                    continue
                if self._capturing():
                    self.mode = mode; self.output_idx = idx; self.backend = "ffmpeg"
                    self.verified = True; self.verified_backend = "ffmpeg"; self.warned_black = False
                    log(f"● 녹화 시작 ({'모니터 '+str(idx) if mode=='ddagrab' else 'gdigrab'}) — 화면 캡처 정상 확인")
                    return True
                self._kill()
            except Exception as e:
                log(f"녹화 시작 오류({mode} #{idx}): {e}"); self._kill()
        if not self.warned_black:
            self.warned_black = True
            log("[!] 화면 캡처를 확인 못 했어요(검은 화면일 수 있음). 그래도 녹화는 계속합니다.")
            log("    • 먼저 한 판 하고 localhost:8000 에서 영상 확인 (메뉴 정지화면 오탐일 수 있음)")
            log("    • config.json 의 \"capture\" 를 \"wgc\" 로 바꾸거나, 스타를 '창 모드(전체 화면)'로 해보세요")
        try:
            self._spawn("ddagrab", 0); time.sleep(1.0); self.mode = "ddagrab"; self.output_idx = 0; self.backend = "ffmpeg"
            return self._alive()
        except Exception:
            self.proc = None; return False
    def stop(self):
        self.last_seconds = (time.time() - self._t_start) if self._t_start else 0.0
        if self.backend == "wgc":
            st = self._wgc_state or {}
            ev = st.get("stop")
            if ev: ev.set()
            try:
                if self._wgc_control: self._wgc_control.stop()
            except Exception: pass
            ft = st.get("feeder")
            if ft:
                try: ft.join(timeout=20)   # 피더가 ffmpeg stdin 닫고 마무리
                except Exception: pass
            self.backend = "ffmpeg"; self._wgc_control = None; self._wgc_state = None
            log("■ 녹화 종료")
            return self._finalize()
        if not self.proc: return None
        p = self.proc; self.proc = None
        try:
            if p.poll() is None:
                try: p.stdin.write(b"q"); p.stdin.flush()
                except Exception: pass
                try: p.wait(timeout=12)
                except subprocess.TimeoutExpired: p.terminate()
        except Exception: pass
        log("■ 녹화 종료")
        return self._finalize()

def sc_running(name):
    n = name.lower()
    for p in psutil.process_iter(["name"]):
        try:
            if (p.info["name"] or "").lower() == n: return True
        except (psutil.NoSuchProcess, psutil.AccessDenied): pass
    return False

def list_reps(d):
    if not os.path.isdir(d): return {}
    out = {}
    for f in glob.glob(os.path.join(d, "**", "*.rep"), recursive=True):
        try: out[f] = os.path.getmtime(f)
        except OSError: pass
    return out

PENDING_PATH = os.path.join(DATA_DIR, "pending.json")
def _load_pending():
    if os.path.isfile(PENDING_PATH):
        try: return json.load(open(PENDING_PATH, encoding="utf-8"))
        except Exception: return []
    return []
def _save_pending(q): json.dump(q, open(PENDING_PATH, "w", encoding="utf-8"))
def _post(video, rep):
    sv = CFG.get("server", {}) or {}; url = (sv.get("url", "") or "").rstrip("/") + "/upload"; key = sv.get("api_key", "")
    files = {"video": ("game.mp4", open(video, "rb"), "video/mp4")}
    if rep and os.path.isfile(rep): files["replay"] = ("replay.rep", open(rep, "rb"), "application/octet-stream")
    try:
        r = requests.post(url, files=files, data={"key": key, "uploader": CFG.get("username") or ""}, timeout=(10, 1800))
        return r.status_code == 200
    finally:
        for f in files.values():
            try: f[1].close()
            except Exception: pass
def _post_r2(video, rep):
    sv = CFG.get("server", {}) or {}; base = (sv.get("url", "") or "").rstrip("/"); key = sv.get("api_key", "")
    pr = requests.post(base + "/api/presign", json={"key": key}, timeout=30)
    if pr.status_code == 409: return None          # 서버에 R2 미설정 → 레거시로
    if pr.status_code != 200: return False
    info = pr.json(); size = os.path.getsize(video)
    tmp_thumb = os.path.join(REC_DIR, "up_thumb.jpg"); has_thumb = make_thumb(video, tmp_thumb)
    with open(video, "rb") as f:
        if requests.put(info["video_put"], data=f, headers={"Content-Type": "video/mp4"},
                        timeout=(10, 3600)).status_code not in (200, 201): return False
    if has_thumb and info.get("thumb_put"):
        try:
            with open(tmp_thumb, "rb") as f:
                requests.put(info["thumb_put"], data=f, headers={"Content-Type": "image/jpeg"}, timeout=(10, 600))
        except Exception: pass
    files = {}
    if rep and os.path.isfile(rep): files["replay"] = ("replay.rep", open(rep, "rb"), "application/octet-stream")
    data = {"key": key, "uploader": CFG.get("username") or "", "gid": info["gid"],
            "video_url": info["video_url"], "thumb_url": info.get("thumb_url") or "", "size": str(size)}
    try:
        rr = requests.post(base + "/api/register", data=data, files=files, timeout=120)
    finally:
        for fo in files.values():
            try: fo[1].close()
            except Exception: pass
    return rr.status_code == 200

def _put_file(url, path, ctype):
    with open(path, "rb") as f:
        r = requests.put(url, data=f, headers={"Content-Type": ctype}, timeout=(10, 3600))
    if r.status_code not in (200, 201):
        raise RuntimeError(f"R2 PUT 실패 {r.status_code}")

def _cloud_send(video, rep):
    """영상·썸네일·.rep 를 R2로 직접, 메타+분석을 Supabase Edge Function 으로. 성공 시 True (영상 삭제 포함)."""
    if not video or not os.path.isfile(video): return True
    cl = CFG.get("cloud") or {}; url = (cl.get("function_url", "") or "").rstrip("/"); key = cl.get("upload_key", "")
    user = CFG.get("username") or ""
    meta = parse_rep(rep) if (rep and os.path.isfile(rep)) else {}
    try: analysis = extract_analysis(rep) if (rep and os.path.isfile(rep) and SCREP) else None
    except Exception: analysis = None
    pr = requests.post(url, json={"key": key, "action": "presign"}, timeout=30)
    if pr.status_code != 200: return False
    info = pr.json(); gid = info["gid"]; size = os.path.getsize(video)
    tmp_thumb = os.path.join(REC_DIR, "up_thumb.jpg"); has_thumb = make_thumb(video, tmp_thumb)
    _put_file(info["video_put"], video, "video/mp4")
    if has_thumb: _put_file(info["thumb_put"], tmp_thumb, "image/jpeg")
    if rep and os.path.isfile(rep): _put_file(info["rep_put"], rep, "application/octet-stream")
    players = meta.get("players") or []; saver = meta.get("saver"); winner = meta.get("winner")
    sp = next((p for p in players if p.get("name") == saver), None)
    won = (sp.get("team") == winner) if (sp and winner) else None
    row = {"id": gid, "uploader": user or saver,
           "uploaded": datetime.datetime.now().isoformat(timespec="seconds"),
           "video": info["video_url"], "thumb": (info["thumb_url"] if has_thumb else None),
           "replay": (info["rep_url"] if (rep and os.path.isfile(rep)) else None), "video_size": size,
           "map": meta.get("map"), "matchup": meta.get("matchup"), "length": meta.get("length"),
           "length_sec": _len_sec(meta.get("length") or ""), "type": meta.get("type"),
           "winner": winner, "saver": saver, "np": len(players),
           "players": players, "won": won, "analysis": analysis}
    rr = requests.post(url, json={"key": key, "action": "register", "match": row}, timeout=60)
    if rr.status_code != 200: return False
    try: os.remove(video)
    except OSError: pass
    return True

def upload_cloud(video, rep):
    if os.path.isfile(video): log(f"↑ 클라우드 업로드 중… ({os.path.getsize(video)/1048576:.0f}MB)")
    try:
        if _cloud_send(video, rep):
            log("✓ 클라우드 등록 완료"); return
        log("✗ 업로드 실패 → 대기열")
    except Exception as e:
        log(f"✗ 클라우드 업로드 실패({e}) → 대기열")
    q = _load_pending(); q.append({"v": video, "r": rep}); _save_pending(q)

def upload_remote(video, rep):
    if not video or not os.path.isfile(video): return
    sv = CFG.get("server", {}) or {}
    log(f"↑ 업로드 중… ({os.path.getsize(video)/1048576:.0f}MB → {sv.get('url','')})")
    try:
        res = _post_r2(video, rep)        # R2 직접 업로드 시도
        if res is None: res = _post(video, rep)   # 서버에 R2 미설정 → 서버 경유
        if res:
            log("✓ 업로드 완료")
            try: os.remove(video)
            except OSError: pass
        else:
            log("✗ 업로드 실패 → 대기열"); q = _load_pending(); q.append({"v": video, "r": rep}); _save_pending(q)
    except Exception as e:
        log(f"✗ 업로드 실패({e}) → 대기열"); q = _load_pending(); q.append({"v": video, "r": rep}); _save_pending(q)
def _flush_pending():
    q = _load_pending()
    if not q: return
    still = []
    for it in q:
        if not os.path.isfile(it.get("v") or ""): continue
        try:
            if (CFG.get("cloud") or {}).get("function_url"):
                if not _cloud_send(it["v"], it.get("r")): still.append(it)   # 성공 시 내부에서 삭제
            else:
                ok = _post_r2(it["v"], it.get("r"))
                if ok is None: ok = _post(it["v"], it.get("r"))
                if ok:
                    try: os.remove(it["v"])
                    except OSError: pass
                else: still.append(it)
        except Exception: still.append(it)
    _save_pending(still)
def _dispatch(video, rep):
    if (CFG.get("cloud") or {}).get("function_url"): upload_cloud(video, rep)
    elif CFG.get("mode") == "recorder": upload_remote(video, rep)
    else: ingest(video, rep, uploader=(CFG.get("username") or None))

def recorder_loop(cfg):
    proc = cfg["starcraft_process"]; autosave = cfg["replay_autosave_dir"]
    poll = float(cfg.get("poll_seconds", 4)); rec = Recorder(int(cfg.get("fps", FPS)))
    known = list_reps(autosave); was = False; active = False
    try: ensure_audio()
    except Exception: pass
    log("준비 완료. 스타를 켜면 자동으로 녹화가 시작됩니다. (이 창은 켜둔 채로 두세요)")
    while True:
        try:
            run = sc_running(proc)
            if run and not was:
                log("스타크래프트 감지됨."); known = list_reps(autosave); active = rec.start()
            if run:
                if not rec._recording():
                    if active: log("녹화 스트림이 끊겨 자동으로 다시 시작합니다.")
                    active = rec.start()
                cur = list_reps(autosave); new = [f for f in cur if f not in known]
                if new:
                    newest = max(new, key=lambda f: cur[f])
                    log(f"한 판 종료 감지: {os.path.basename(newest)}")
                    time.sleep(1.5)
                    vid = rec.stop(); active = False
                    threading.Thread(target=_dispatch, args=(vid, newest), daemon=True).start()
                    known = cur
                    if sc_running(proc): active = rec.start()
            if not run and was:
                log("스타크래프트 종료됨.")
                vid = rec.stop(); active = False; rec.verified = False
                cur = list_reps(autosave); new = [f for f in cur if f not in known]
                if vid and new:
                    newest = max(new, key=lambda f: cur[f])
                    threading.Thread(target=_dispatch, args=(vid, newest), daemon=True).start()
                elif vid and os.path.isfile(vid):
                    # 리플레이가 없으면(메뉴·대기 화면 등) 게임이 아니므로 저장하지 않고 폐기 — 용량 낭비 방지
                    log(f"  리플레이가 없는 녹화({rec.last_seconds:.0f}초)는 게임이 아니라 저장하지 않고 버립니다.")
                    try: os.remove(vid)
                    except OSError: pass
                known = cur; log("대기 상태.")
            # 웹 표시용 실시간 상태 갱신
            if run and rec._recording():
                REC_STATE.update(rec=True, text="녹화 중")
            elif run:
                REC_STATE.update(rec=False, text="스타크래프트 감지됨")
            else:
                REC_STATE.update(rec=False, text="대기 중 — 스타를 켜면 자동 시작")
            if CFG.get('mode') == 'recorder' or (CFG.get('cloud') or {}).get('function_url'): _flush_pending()
            was = run; time.sleep(poll)
        except KeyboardInterrupt:
            log("종료합니다."); rec.stop(); break
        except Exception:
            log("오류:\n" + traceback.format_exc()); time.sleep(poll)

# ===================== main =====================
def start_server(port, block=False):
    try:
        from waitress import serve
        target = lambda: serve(app, host="0.0.0.0", port=port, threads=8)
    except Exception:
        target = lambda: app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False)
    if block: target()
    else: threading.Thread(target=target, daemon=True).start()

_MUTEX = None
def _single_instance():
    """이미 실행 중이면 False (자동 실행 + 수동 더블클릭 겹침 방지)."""
    global _MUTEX
    if sys.platform != "win32": return True
    try:
        import ctypes
        _MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False, "ENCORE_Recorder_SingleInstance")
        return ctypes.windll.kernel32.GetLastError() != 183   # 183 = ERROR_ALREADY_EXISTS
    except Exception:
        return True

def _autostart_cmd():
    """자동 실행에 등록할 명령. 빌드된 .exe(frozen)일 때만 반환 (개발 모드는 등록 안 함)."""
    if getattr(sys, "frozen", False):
        return '"%s"' % os.path.abspath(sys.executable)
    return None

def set_autostart(enable):
    """윈도우 시작 시 자동 실행 등록/해제 (HKCU Run). 실패해도 앱엔 영향 없음."""
    if sys.platform != "win32": return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE)
        if enable:
            cmd = _autostart_cmd()
            if not cmd: winreg.CloseKey(key); return False
            winreg.SetValueEx(key, "ENCORE", 0, winreg.REG_SZ, cmd)
            log("윈도우 시작 시 자동 실행 등록됨 (끄려면 config.json 의 autostart 를 false 로)")
        else:
            try: winreg.DeleteValue(key, "ENCORE")
            except FileNotFoundError: pass
        winreg.CloseKey(key)
        return True
    except Exception as e:
        log(f"자동 실행 설정 건너뜀: {e}")
        return False

def is_autostart():
    if sys.platform != "win32": return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_QUERY_VALUE)
        v, _ = winreg.QueryValueEx(key, "ENCORE"); winreg.CloseKey(key)
        return bool(v)
    except Exception:
        return False

def _apply_autostart(cfg):
    """frozen .exe 에서만, config 값에 맞춰 자동 실행 등록/해제."""
    if not getattr(sys, "frozen", False): return
    want = bool(cfg.get("autostart", True))
    if want != is_autostart():
        set_autostart(want)

def _hide_console():
    if sys.platform != "win32": return
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd: ctypes.windll.user32.ShowWindow(hwnd, 0)   # SW_HIDE
    except Exception: pass

def run_gui(cfg, url):
    """아주 작은 상태 표시줄. 평소엔 상태만, 문제가 있을 때만 로그가 펼쳐진다."""
    import tkinter as tk
    BG="#0F1013"; INK="#ECEEF2"; DIM="#9AA0AA"; FAINT="#636872"
    JADE="#3D8BFF"; REC="#E8694C"; AMB="#E0B441"; LINE="#23272E"; KOR="Malgun Gothic"
    W = 332
    root = tk.Tk(); root.title("ENCORE"); root.configure(bg=BG)
    root.geometry(f"{W}x112"); root.resizable(False, True)
    st = {"open": False}

    head = tk.Frame(root, bg=BG); head.pack(fill="x", padx=14, pady=(10,0))
    mk = tk.Canvas(head, width=17, height=13, bg=BG, highlightthickness=0); mk.pack(side="left", pady=(2,0))
    mk.create_rectangle(0,8,4,13, fill=INK, outline=""); mk.create_rectangle(6,4,10,13, fill=INK, outline=""); mk.create_rectangle(13,0,17,13, fill=INK, outline="")
    tk.Label(head, text="ENCORE", bg=BG, fg=INK, font=(KOR,9,"bold")).pack(side="left", padx=(6,0))
    games_lbl = tk.Label(head, text="", bg=BG, fg=FAINT, font=("Consolas",9)); games_lbl.pack(side="right")
    _cs = cloud_state()
    _cmap = {"cloud": (JADE, "☁ 클라우드"), "readonly": (AMB, "⚠ 키 필요"), "local": (FAINT, "● 로컬")}
    _cc, _ct = _cmap[_cs]
    tk.Label(head, text=_ct, bg=BG, fg=_cc, font=(KOR,8,"bold")).pack(side="right", padx=(0,10))

    midf = tk.Frame(root, bg=BG); midf.pack(fill="x", padx=14, pady=(6,0))
    dot = tk.Canvas(midf, width=12, height=12, bg=BG, highlightthickness=0); dot.pack(side="left", pady=(5,0))
    did = dot.create_oval(1,1,11,11, fill=FAINT, outline="")
    stx = tk.Frame(midf, bg=BG); stx.pack(side="left", padx=(9,0))
    status_lbl = tk.Label(stx, text="시작 중…", bg=BG, fg=INK, font=(KOR,15,"bold"), anchor="w"); status_lbl.pack(anchor="w")
    sub_lbl = tk.Label(stx, text="", bg=BG, fg=DIM, font=(KOR,8), anchor="w"); sub_lbl.pack(anchor="w")

    logwrap = tk.Frame(root, bg=BG)
    errbar = tk.Label(logwrap, text="", bg="#3A1E18", fg="#ffb4a6", font=(KOR,8), anchor="w",
                      padx=9, pady=5, justify="left", wraplength=W-40)
    logtxt = tk.Text(logwrap, bg="#0C0D10", fg=DIM, font=("Consolas",8), bd=0, padx=9, pady=7,
                     height=9, wrap="word", state="disabled")

    foot = tk.Frame(root, bg=BG); foot.pack(side="bottom", fill="x", padx=14, pady=(0,9))
    def link(parent, text, cmd, color=DIM):
        l = tk.Label(parent, text=text, bg=BG, fg=color, font=(KOR,8), cursor="hand2")
        l.bind("<Button-1>", lambda e: cmd())
        l.bind("<Enter>", lambda e: l.config(fg=INK)); l.bind("<Leave>", lambda e: l.config(fg=color))
        return l
    def open_gallery():
        try: webbrowser.open(url)
        except Exception: pass
    def open_folder():
        try:
            if sys.platform == "win32": os.startfile(REC_DIR)
        except Exception: pass
    def do_quit():
        try: root.destroy()
        except Exception: pass
        os._exit(0)
    def set_log(open_):
        st["open"] = open_
        if open_:
            root.geometry(f"{W}x318"); logwrap.pack(fill="both", expand=True, padx=11, pady=(2,7))
            if LAST_ERR.get("msg"): errbar.config(text="\u26a0 " + LAST_ERR["msg"]); errbar.pack(fill="x", pady=(0,5))
            else: errbar.pack_forget()
            logtxt.pack(fill="both", expand=True); logtog.config(text="닫기 \u25b4")
        else:
            logwrap.pack_forget(); root.geometry(f"{W}x112"); logtog.config(text="로그 \u25be")
    def toggle_log(): set_log(not st["open"])
    logtog = link(foot, "로그 \u25be", toggle_log, FAINT); logtog.pack(side="right")
    link(foot, "종료", do_quit).pack(side="right", padx=(0,10))
    link(foot, "갤러리", open_gallery, JADE).pack(side="left")
    tk.Label(foot, text="·", bg=BG, fg=LINE, font=(KOR,8)).pack(side="left", padx=5)
    link(foot, "폴더", open_folder).pack(side="left")
    if sb_enabled():
        def do_sync():
            set_log(True); threading.Thread(target=lambda: sync_existing_to_cloud(), daemon=True).start()
        tk.Label(foot, text="·", bg=BG, fg=LINE, font=(KOR,8)).pack(side="left", padx=5)
        link(foot, "업로드", do_sync, JADE).pack(side="left")
    root.protocol("WM_DELETE_WINDOW", do_quit)

    def _prep_and_run():
        global FFMPEG, SCREP
        try:
            if not FFMPEG: FFMPEG = ensure_ffmpeg()
            if not SCREP: SCREP = ensure_screp()
        except Exception as e:
            log(f"도구 준비 중 문제: {e}")
        if not FFMPEG:
            log("\u26a0 ffmpeg 준비 실패 — 인터넷 연결 확인 후 다시 실행해 주세요."); return
        try: rebuild_db_from_recordings()
        except Exception as e: log(f"폴더 복구 건너뜀: {e}")
        recorder_loop(cfg)
    threading.Thread(target=_prep_and_run, daemon=True).start()

    def poll():
        appended = False
        for _ in range(150):
            try: line = GUI_Q.get_nowait()
            except Exception: break
            if st["open"]:
                logtxt.config(state="normal"); logtxt.insert("end", line + "\n"); appended = True
        if appended:
            n = int(logtxt.index("end-1c").split(".")[0])
            if n > 300: logtxt.delete("1.0", f"{n-300}.0")
            logtxt.see("end"); logtxt.config(state="disabled")
        if REC_STATE.get("recording"):
            dot.itemconfig(did, fill=REC); status_lbl.config(text="녹화 중", fg=REC); sub_lbl.config(text="게임 화면 녹화 중")
        elif REC_STATE.get("ready"):
            dot.itemconfig(did, fill=JADE); status_lbl.config(text="대기 중", fg=INK); sub_lbl.config(text="스타 켜면 자동 녹화")
        else:
            dot.itemconfig(did, fill=AMB); status_lbl.config(text="준비 중…", fg=INK); sub_lbl.config(text="최초 실행 — 도구 준비 중 (1~2분)")
        try:
            n = count_matches(); e = (REC_STATE.get("encoder") or "").split()
            games_lbl.config(text=(f"경기 {n} · {e[0]}" if e else f"경기 {n}"))
        except Exception: pass
        if LAST_ERR.get("msg") and (time.time() - LAST_ERR.get("t", 0) < 8):
            if not st["open"]: set_log(True)
            else: errbar.config(text="\u26a0 " + LAST_ERR["msg"])
        root.after(500, poll)

    try: root.update()
    except Exception: pass
    if sys.platform == "win32": _hide_console()   # py.exe 로 돌려도 콘솔창 숨김
    poll()
    try: root.mainloop()
    except Exception as ex: log(f"GUI 창 종료: {ex}")

def _print_status():
    s = sb_cfg(); st = cloud_state()
    print("\n" + "=" * 50)
    print("  ENCORE 상태 점검")
    print("=" * 50)
    print(f"  데이터 폴더 : {DATA_DIR}")
    print(f"  리플레이  : {CFG.get('replay_autosave_dir') or '(없음)'}")
    try:
        _c = db(); _n = _c.execute("SELECT COUNT(*) FROM matches").fetchone()[0]; _c.close()
        print(f"  로컬 경기  : {_n}개 (matches.db)")
    except Exception: pass
    print("-" * 50)
    print(f"  Supabase URL : {s.get('url') or '(없음)'}")
    print(f"  anon_key     : {'있음' if s.get('anon_key') else '없음'}")
    print(f"  service_key  : {'있음' if s.get('service_key') else '없음  ← 업로드하려면 필요'}")
    print(f"  bucket       : {s.get('bucket') or 'media'}")
    verdict = {"cloud": "☁ 클라우드 ON (업로드 가능)",
               "readonly": "⚠ 읽기전용 (service_key 입력 필요)",
               "local": "● 로컬 전용"}[st]
    print(f"\n  → {verdict}")
    if s.get("url") and (s.get("service_key") or s.get("anon_key")):
        print("\n  Supabase 연결 테스트 중...")
        try:
            import requests
            r = requests.get(_sb_base() + "/rest/v1/matches?select=id&limit=1", headers=_sb_h(), timeout=12)
            if r.status_code < 300:
                print("  ✓ 연결 OK — matches 테이블 읽기 성공")
                try:
                    r2 = requests.get(_sb_base() + "/rest/v1/matches?select=id",
                                      headers={**_sb_h(), "Prefer": "count=exact", "Range": "0-0"}, timeout=12)
                    cr = r2.headers.get("content-range", "")
                    if "/" in cr: print(f"    ☁ 클라우드 저장된 경기: {cr.split('/')[-1]}개")
                except Exception: pass
                if s.get("service_key"):
                    try:
                        rb = requests.get(_sb_base() + "/storage/v1/bucket/" + (_sb_bucket()),
                                          headers=_sb_h(write=True), timeout=12)
                        if rb.status_code < 300: print(f"  ✓ Storage 버킷 '{_sb_bucket()}' 접근 OK (업로드 준비됨)")
                        else: print(f"  ✗ 버킷 접근 실패: HTTP {rb.status_code} — 버킷 이름/키 확인")
                    except Exception as e: print(f"  ✗ 버킷 테스트 오류: {e}")
            else:
                print(f"  ✗ 연결 실패: HTTP {r.status_code} — {r.text[:140]}")
                print("    (키가 틀렸거나 테이블이 없을 수 있어요. schema.sql 실행했는지 확인)")
        except Exception as e:
            print(f"  ✗ 연결 테스트 오류: {e}")
    print("=" * 50)

def main():
    global FFMPEG, SCREP, CFG
    cfg = load_or_make_config(); CFG = cfg; init_db()
    try: _apply_autostart(cfg)
    except Exception: pass
    if "--sync-existing" in sys.argv or cfg.get("mode") == "sync":
        try: SCREP = ensure_screp()
        except Exception: pass
        sync_existing_to_cloud(); 
        try: input("\n끝났어요. 엔터로 종료...")
        except Exception: pass
        return
    if "--status" in sys.argv or "--check" in sys.argv:
        _print_status()
        try: input("\n엔터로 종료...")
        except Exception: pass
        return
    if "--rebuild-db" in sys.argv or cfg.get("mode") == "rebuild":
        try: SCREP = ensure_screp()
        except Exception: pass
        try: FFMPEG = ensure_ffmpeg()
        except Exception: pass
        n = rebuild_db_from_recordings()
        print(f"\n복구 완료: {n}개 경기를 DB에 추가했어요.")
        try: input("엔터로 종료...")
        except Exception: pass
        return
    # 이미 실행 중이면(자동 실행 + 수동 실행 겹침) 갤러리만 열고 종료
    if not _single_instance():
        try: webbrowser.open(cfg.get("gallery_url") or f"http://localhost:{cfg.get('port',8000)}")
        except Exception: pass
        return
    try: _LOGFILE["p"] = os.path.join(DATA_DIR, "recorder.log")
    except Exception: pass
    mode = cfg.get("mode", "all")
    use_gui = (mode == "all" and sys.platform == "win32" and cfg.get("ui", "window") != "console")
    print("=" * 56); print(f"  스타크래프트 자동 녹화/아카이브 — 모드: {mode}"); print("=" * 56)
    _cst = cloud_state()
    if _cst == "cloud":
        log(f"☁ 클라우드 ON — Supabase({_sb_base()}) 에 저장·공유됩니다.")
    elif _cst == "readonly":
        log("⚠ 클라우드 읽기전용 — config.json 의 supabase.service_key 가 비어있어요. 채우고 재시작하면 업로드가 켜져요.")
    else:
        log("● 로컬 모드 — 이 PC에만 저장됩니다. (config.json 의 supabase 를 채우면 클라우드 ON)")
    if mode in ("all", "recorder"):
        log(f"리플레이 폴더: {cfg['replay_autosave_dir']}")
        if not os.path.isdir(cfg["replay_autosave_dir"]):
            log("⚠ 리플레이 폴더를 못 찾았어요. 스타에서 리플레이를 한 번 저장하면 폴더가 생깁니다.")
        if not use_gui:               # GUI면 창부터 띄우고 백그라운드에서 받음(첫 실행이 멈춘 듯 안 보이게)
            FFMPEG = ensure_ffmpeg()
            if not FFMPEG:
                _safe_input("\nffmpeg가 없어 녹화를 할 수 없어요. 엔터로 종료..."); return
    cloud_on = bool((cfg.get("cloud") or {}).get("function_url"))
    if (mode in ("all", "server") or cloud_on) and not use_gui:
        SCREP = ensure_screp()        # 클라우드 모드: 클라이언트가 리플레이를 직접 분석
        if not FFMPEG: FFMPEG = ensure_ffmpeg()
    port = cfg["port"]; url = f"http://localhost:{port}"
    if cloud_on:
        log("클라우드 모드: 영상은 R2로, 메타+분석은 Supabase 로 직접 업로드합니다.")
        g = cfg.get("gallery_url") or ""
        if g:
            log(f"갤러리 → {g}")
            try: webbrowser.open(g)
            except Exception: pass
        print("-" * 56); recorder_loop(cfg); return
    if mode == "server":
        log(f"중앙 서버 가동 → {url}  (같은 네트워크의 다른 PC는 이 컴퓨터 IP:{port} 로 접속)")
        log(f"업로드 키(클라이언트 config 의 server.api_key 에 넣기): {cfg.get('upload_key')}")
        start_server(port, block=True); return
    if mode == "all":
        start_server(port, block=False); time.sleep(1.0)
        log(f"갤러리 → {url}")
        try: webbrowser.open(url)
        except Exception: pass
        # 보기 좋은 상태창(GUI). 윈도우 + tkinter 가능하면 GUI로, 아니면 콘솔로.
        if sys.platform == "win32" and (cfg.get("ui", "window") != "console"):
            try:
                import tkinter  # noqa: F401  (가용성 확인)
                run_gui(cfg, url); return
            except Exception as e:
                log(f"GUI 사용 불가({e}) → 콘솔 모드로 계속")
    if mode in ("all", "recorder"):
        if not FFMPEG: FFMPEG = ensure_ffmpeg()
        print("-" * 56); recorder_loop(cfg)

if __name__ == "__main__":
    main()
