#!/usr/bin/env python3
"""
StarCraft 리플레이 아카이브 서버 (커뮤니티 사이트의 씨앗)
- 녹화 에이전트(agent.py)가 보낸 [게임 영상 + .rep] 를 받아서 저장
- .rep 은 screp 로 파싱해 메타데이터(맵/플레이어/종족/APM/승패) 추출
- 브라우저에서 갤러리로 보고, 영상 재생 + 리플레이 다운로드

실행:  python server.py
열기:  http://localhost:8000
"""
import os, json, shutil, subprocess, re, time, datetime, html
from flask import Flask, request, jsonify, send_file, abort, Response

# ----------------------- 설정 -----------------------
HERE       = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.environ.get("SC_DATA_DIR", os.path.join(HERE, "data"))
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
INDEX_PATH = os.path.join(DATA_DIR, "index.json")
API_KEY    = os.environ.get("SC_API_KEY", "change-me-please")   # 에이전트와 동일하게
PORT       = int(os.environ.get("SC_PORT", "8000"))
FPS        = 23.81

# screp 실행 파일 자동 탐지 (없으면 메타데이터 없이 영상만 저장 — 정상 동작)
def find_screp():
    for c in [os.environ.get("SCREP_PATH"),
              os.path.join(HERE, "screp.exe"), os.path.join(HERE, "screp"),
              os.path.join(HERE, "screp-bin"), "screp.exe", "screp",
              "/home/claude/work/screp-bin"]:
        if c and (os.path.isfile(c) or shutil.which(c)):
            return c
    return None
SCREP = find_screp()

os.makedirs(UPLOAD_DIR, exist_ok=True)
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024 * 1024  # 8GB 까지 허용

# ----------------------- 유틸 -----------------------
def load_index():
    if os.path.isfile(INDEX_PATH):
        try: return json.load(open(INDEX_PATH, encoding="utf-8"))
        except Exception: return []
    return []

def save_index(idx):
    json.dump(idx, open(INDEX_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def clean(s):
    return re.sub(r"[\x00-\x1f]", "", s).strip() if s else s

def parse_rep(path):
    """screp 로 .rep 파싱 → 메타데이터 dict. 실패하면 기본값."""
    meta = {"map": None, "length": None, "type": None, "matchup": None,
            "winner": None, "saver": None, "players": []}
    if not SCREP or not os.path.isfile(path):
        return meta
    try:
        out = subprocess.run([SCREP, path], capture_output=True, timeout=60).stdout
        d = json.loads(out)
    except Exception:
        return meta
    h = d.get("Header", {}) or {}
    comp = d.get("Computed", {}) or {}
    pdescs = {p["PlayerID"]: p for p in (comp.get("PlayerDescs") or [])}
    players = []
    for p in (h.get("Players") or []):
        pd = pdescs.get(p.get("ID"), {})
        players.append({
            "name": p.get("Name"),
            "race": (p.get("Race") or {}).get("ShortName"),
            "team": p.get("Team"),
            "apm": pd.get("APM"),
            "color": "#%06x" % ((p.get("Color") or {}).get("RGB", 8421504)),
        })
    frames = h.get("Frames", 0) or 0
    secs = frames / FPS
    meta.update({
        "map": clean(h.get("Map")),
        "length": "%d:%02d" % (secs // 60, secs % 60),
        "type": (h.get("Type") or {}).get("Name"),
        "winner": comp.get("WinnerTeam"),
        "saver": next((p.get("Name") for p in (h.get("Players") or [])
                       if p.get("ID") == comp.get("RepSaverPlayerID")), None),
        "players": players,
    })
    # 매치업 문자열 (팀별 종족)
    t1 = "".join((pl["race"] or "?")[0].upper() for pl in players if pl["team"] == 1)
    t2 = "".join((pl["race"] or "?")[0].upper() for pl in players if pl["team"] == 2)
    meta["matchup"] = f"{t1} vs {t2}" if t1 and t2 else None
    return meta

# ----------------------- 업로드 엔드포인트 -----------------------
@app.post("/upload")
def upload():
    if request.form.get("key") != API_KEY and request.headers.get("X-Api-Key") != API_KEY:
        return jsonify(error="bad api key"), 401
    if "video" not in request.files:
        return jsonify(error="no video file"), 400
    vid = request.files["video"]
    rep = request.files.get("replay")

    gid = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = os.path.join(UPLOAD_DIR, gid)
    os.makedirs(base, exist_ok=True)

    vext = os.path.splitext(vid.filename or "")[1].lower() or ".mp4"
    vname = "game" + vext
    vid.save(os.path.join(base, vname))

    rname = None
    meta = {}
    if rep and rep.filename:
        rname = "replay.rep"
        rpath = os.path.join(base, rname)
        rep.save(rpath)
        meta = parse_rep(rpath)

    record = {
        "id": gid,
        "uploaded": datetime.datetime.now().isoformat(timespec="seconds"),
        "video": f"{gid}/{vname}",
        "replay": f"{gid}/{rname}" if rname else None,
        "video_size": os.path.getsize(os.path.join(base, vname)),
        "orig_video_name": vid.filename,
        "orig_rep_name": rep.filename if rep else None,
        **meta,
    }
    idx = load_index()
    idx.append(record)
    save_index(idx)
    return jsonify(ok=True, id=gid, parsed=bool(meta.get("players")))

# ----------------------- 미디어 서빙 -----------------------
@app.get("/media/<path:rel>")
def media(rel):
    full = os.path.normpath(os.path.join(UPLOAD_DIR, rel))
    if not full.startswith(UPLOAD_DIR) or not os.path.isfile(full):
        abort(404)
    as_dl = request.args.get("dl") == "1"
    return send_file(full, as_attachment=as_dl,
                     download_name=os.path.basename(full) if as_dl else None)

# ----------------------- 갤러리 페이지 -----------------------
PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>전적 아카이브</title>
<link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#080b12;--panel:#101622;--line:#1b2735;--ink:#e8eff7;--dim:#8295a9;--faint:#586b80;--cyan:#4ad6c6;--win:#56e39c;--lose:#ff6f6f;
--fd:'Rajdhani',system-ui,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;--fm:'JetBrains Mono',ui-monospace,monospace;}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(1000px 500px at 70% -10%,rgba(74,214,198,.06),transparent 60%),var(--bg);color:var(--ink);font-family:var(--fm)}
.wrap{max-width:1100px;margin:0 auto;padding:24px 18px 60px}
header{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;padding-bottom:14px;border-bottom:1px solid var(--line);flex-wrap:wrap}
.ey{font-size:11px;letter-spacing:.3em;color:var(--cyan);text-transform:uppercase}
h1{font-family:var(--fd);font-weight:700;font-size:30px;margin:4px 0 0;letter-spacing:.01em}
.count{font-size:12px;color:var(--dim)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px;margin-top:20px}
.card{background:linear-gradient(180deg,var(--panel),#0c121c);border:1px solid var(--line);border-radius:8px;overflow:hidden}
video{width:100%;display:block;background:#000;aspect-ratio:16/9;object-fit:contain}
.body{padding:12px 13px}
.mtitle{font-family:var(--fd);font-weight:700;font-size:16px;letter-spacing:.01em;margin-bottom:2px;display:flex;justify-content:space-between;gap:8px;align-items:baseline}
.res{font-size:11px;letter-spacing:.1em;padding:2px 7px;border-radius:3px;flex-shrink:0}
.res.win{color:var(--win);background:color-mix(in srgb,var(--win) 12%,transparent)}
.res.lose{color:var(--lose);background:color-mix(in srgb,var(--lose) 12%,transparent)}
.sub{font-size:11px;color:var(--dim);margin-bottom:9px}
.players{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:10px}
.pl{display:flex;align-items:center;gap:4px;font-size:10.5px;color:var(--dim);background:#0a1019;border:1px solid var(--line);border-radius:3px;padding:2px 6px}
.dot{width:8px;height:8px;border-radius:2px}
.row{display:flex;gap:8px;align-items:center}
.dl{font-family:var(--fm);font-size:11px;color:var(--cyan);text-decoration:none;border:1px solid color-mix(in srgb,var(--cyan) 35%,transparent);padding:5px 10px;border-radius:4px}
.dl:hover{background:color-mix(in srgb,var(--cyan) 10%,transparent)}
.sz{font-size:10px;color:var(--faint);margin-left:auto}
.empty{margin-top:60px;text-align:center;color:var(--faint);line-height:1.7;font-size:13px}
.empty b{color:var(--dim)}
.foot{margin-top:40px;font-size:10.5px;color:var(--faint);text-align:center}
</style></head><body><div class="wrap">
<header><div><div class="ey">BROOD WAR · 자동 전적 아카이브</div><h1>__TITLE__</h1></div>
<div class="count">__COUNT__ 경기 · screp 파싱: __SCREP__</div></header>
__BODY__
<div class="foot">녹화 에이전트가 게임 끝날 때마다 자동 업로드합니다 · 영상은 실제 게임 화면, 리플레이는 .rep 원본</div>
</div></body></html>"""

def card_html(r):
    won = None
    if r.get("winner") and r.get("saver") and r.get("players"):
        sp = next((p for p in r["players"] if p["name"] == r["saver"]), None)
        if sp: won = (sp["team"] == r["winner"])
    res = ""
    if won is True:  res = '<span class="res win">승리</span>'
    elif won is False: res = '<span class="res lose">패배</span>'
    title = html.escape(r.get("map") or "리플레이")
    mu = r.get("matchup") or ""
    ln = r.get("length") or ""
    sub = " · ".join(x for x in [mu, ln, r.get("type")] if x) or r.get("uploaded", "")
    pls = ""
    for p in (r.get("players") or []):
        pls += (f'<span class="pl"><span class="dot" style="background:{html.escape(p.get("color") or "#888")}"></span>'
                f'{html.escape(p.get("name") or "—")}'
                f'<span style="color:var(--faint)">{(p.get("race") or "")[:1].upper()} · {p.get("apm") or 0}</span></span>')
    rep_btn = (f'<a class="dl" href="/media/{html.escape(r["replay"])}?dl=1">⬇ .rep</a>'
               if r.get("replay") else "")
    sz = f'{r.get("video_size",0)/1048576:.0f} MB'
    return f"""<div class="card">
  <video controls preload="metadata" src="/media/{html.escape(r['video'])}"></video>
  <div class="body">
    <div class="mtitle"><span>{title}</span>{res}</div>
    <div class="sub">{html.escape(sub)}</div>
    <div class="players">{pls}</div>
    <div class="row">{rep_btn}<span class="sz">{sz}</span></div>
  </div></div>"""

@app.get("/")
def gallery():
    idx = sorted(load_index(), key=lambda r: r.get("id", ""), reverse=True)
    if idx:
        body = '<div class="grid">' + "".join(card_html(r) for r in idx) + "</div>"
    else:
        body = ('<div class="empty">아직 업로드된 경기가 없어요.<br>'
                '<b>agent.py</b> 를 켜고 스타 한 판 하면 여기 자동으로 올라옵니다.</div>')
    page = (PAGE.replace("__TITLE__", "전적 아카이브")
                .replace("__COUNT__", str(len(idx)))
                .replace("__SCREP__", "켜짐" if SCREP else "꺼짐(메타데이터 없이 영상만)")
                .replace("__BODY__", body))
    return Response(page, mimetype="text/html")

@app.get("/health")
def health():
    return jsonify(ok=True, screp=bool(SCREP), games=len(load_index()))

if __name__ == "__main__":
    print(f"[server] data dir : {DATA_DIR}")
    print(f"[server] screp     : {SCREP or '(없음 - 영상만 저장)'}")
    print(f"[server] api key   : {API_KEY}")
    print(f"[server] open       → http://localhost:{PORT}")
    app.run(host="0.0.0.0", port=PORT, threaded=True)
