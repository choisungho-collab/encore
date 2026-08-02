# -*- coding: utf-8 -*-
"""
ENCORE 벤치마크 인제스터 — 고수 rep 팩을 배치 분석해 bench 테이블로.
사용법:  python bench_ingest.py <rep폴더> [출처태그]
  예)    python bench_ingest.py C:\\reps\\고수팩1 "빨무클랜A"
요구:    sc_recorder.py 와 같은 폴더에서 실행 (screp 포함 동일 환경)
"""
import os, sys, json, hashlib, urllib.request

SB   = "https://luljnalcnxfyxmlgoxbc.supabase.co"
ANON = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx1bGpuYWxjbnhmeXhtbGdveGJjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODIwMDU1NDIsImV4cCI6MjA5NzU4MTU0Mn0.WhPOfWiOlokOHVZLmffIKKTDpQunhxwwwJOd6CSoC2k"

def post(row):
    req = urllib.request.Request(
        SB + "/rest/v1/bench",
        data=json.dumps(row).encode("utf-8"),
        headers={"apikey": ANON, "Authorization": "Bearer " + ANON,
                 "Content-Type": "application/json", "Prefer": "resolution=ignore-duplicates"},
        method="POST")
    urllib.request.urlopen(req, timeout=30).read()

def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    folder = sys.argv[1]
    src = sys.argv[2] if len(sys.argv) > 2 else os.path.basename(folder.rstrip("\\/"))
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import sc_recorder as sr
    ok = fail = 0
    reps = [f for f in os.listdir(folder) if f.lower().endswith(".rep")]
    print(f"[bench] {len(reps)}개 rep · 출처={src}")
    for i, fn in enumerate(reps, 1):
        p = os.path.join(folder, fn)
        try:
            a = sr.extract_analysis(p)
            if not a or not a.get("players"): raise RuntimeError("분석 실패")
            a = sr._slim_cloud_analysis(a)
            with open(p, "rb") as fh:
                rid = hashlib.sha1(fh.read()).hexdigest()[:16]
            meta = a.get("meta") or {}
            ps = a.get("players") or []
            c1 = sum(1 for q in ps if q.get("team") == 1)
            c2 = sum(1 for q in ps if q.get("team") == 2)
            row = {"id": rid, "src": src, "map": meta.get("map"),
                   "length_sec": int(sr._s2(meta.get("length") or "0:0")) if hasattr(sr, "_s2") else None,
                   "fmt": max(c1, c2),
                   "players": [{"name": q.get("name"), "race": q.get("race"), "team": q.get("team"),
                                "apm": q.get("apm")} for q in ps],
                   "analysis": a}
            post(row); ok += 1
            print(f"  [{i}/{len(reps)}] ✓ {fn}  {meta.get('map','?')} {meta.get('length','?')} {max(c1,c2)}:{max(c1,c2)}")
        except Exception as e:
            fail += 1; print(f"  [{i}/{len(reps)}] ✗ {fn}: {e}")
    print(f"[bench] 완료 — 성공 {ok} / 실패 {fail}. 이제 Claude에게 '프로 기준 보정' 요청하세요.")

if __name__ == "__main__":
    main()
