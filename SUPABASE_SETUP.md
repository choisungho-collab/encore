#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""캡처 진단 — 각 방식이 실제로 왜 안 되는지 에러를 그대로 보여줌.
스타크래프트를 켠 상태(평소 안 되는 그 모드, 전체화면)에서 실행하세요."""
import sys, os, subprocess, time, shutil

if sys.platform == "win32":
    try: os.system("chcp 65001 >nul 2>&1")
    except Exception: pass
    for _s in (sys.stdout, sys.stderr):
        try: _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass

HERE = os.path.dirname(os.path.abspath(__file__))
FFMPEG = os.path.join(HERE, "ffmpeg.exe")
if not os.path.isfile(FFMPEG):
    FFMPEG = shutil.which("ffmpeg") or "ffmpeg"

def line(): print("=" * 64)
line(); print(" 캡처 진단 — 스타를 켠 상태(전체화면)에서 실행하세요"); line()
print("FFMPEG:", FFMPEG)

# ---------- 인코더 ----------
try:
    enc = subprocess.run([FFMPEG, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=25).stdout or ""
    print("인코더:  NVENC =", ("h264_nvenc" in enc), " | libx264 =", ("libx264" in enc),
          " | AMF =", ("h264_amf" in enc), " | QSV =", ("h264_qsv" in enc))
except Exception as e:
    print("인코더 확인 실패:", e)

# ---------- 열린 창 제목 (스타 창 찾기) ----------
sc_titles = []
try:
    import ctypes
    user32 = ctypes.windll.user32
    titles = []
    def _cb(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                b = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, b, n + 1)
                if b.value.strip(): titles.append(b.value)
        return True
    PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(PROC(_cb), 0)
    sc_titles = [t for t in titles if any(k in t.lower() for k in ("star", "brood", "craft", "스타"))]
    print("\n[열린 창] 스타 관련 창:", sc_titles if sc_titles else "(못 찾음)")
    print("[열린 창] 전체(앞 15개):", titles[:15])
except Exception as e:
    print("창 목록 실패:", e)

# ---------- ffmpeg 기반 캡처 (stderr 그대로 출력) ----------
def test_ff(label, inargs):
    print("\n--- [%s] 3초 테스트 ---" % label)
    out = os.path.join(HERE, "diag_%s.mp4" % label.replace(" ", "_"))
    cmd = [FFMPEG, "-y", "-t", "3"] + inargs + ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", out]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        size = os.path.getsize(out) if os.path.isfile(out) else 0
        verdict = "✅ 캡처됨!" if size > 60000 else "❌ 비어있음(검은화면/실패)"
        print("  종료코드 %s | 파일 %d bytes  %s" % (r.returncode, size, verdict))
        msg = (r.stderr or "").strip()
        if msg:
            print("  ffmpeg 메시지:")
            for l in msg.splitlines()[-6:]:
                print("     " + l)
    except Exception as e:
        print("  실행 실패:", e)
    finally:
        try: os.remove(out)
        except OSError: pass

for idx in (0, 1):
    test_ff("ddagrab 모니터%d" % idx, ["-filter_complex", "ddagrab=output_idx=%d:framerate=30,hwdownload,format=bgra" % idx])
test_ff("gdigrab", ["-f", "gdigrab", "-framerate", "30", "-i", "desktop"])

# ---------- WGC (windows-capture) ----------
print("\n--- [WGC] 모니터/창별 프레임 수신 테스트 ---")
try:
    from windows_capture import WindowsCapture
    def wgc_count(seconds=3, **kw):
        cnt = {"n": 0, "err": None, "dims": None}
        try:
            cap = WindowsCapture(cursor_capture=None, draw_border=None, **kw)
        except Exception as e:
            return ("시작실패: " + repr(e)), cnt
        @cap.event
        def on_frame_arrived(frame, capture_control):
            cnt["n"] += 1
            if cnt["dims"] is None:
                try: cnt["dims"] = (frame.width, frame.height, tuple(frame.frame_buffer.shape))
                except Exception as e: cnt["err"] = repr(e)
        @cap.event
        def on_closed():
            pass
        try:
            ctrl = cap.start_free_threaded()
        except Exception as e:
            return ("start_free_threaded 실패: " + repr(e)), cnt
        time.sleep(seconds)
        try: ctrl.stop()
        except Exception: pass
        return "ok", cnt

    for mi in (1, 0, 2):
        st, cnt = wgc_count(3, monitor_index=mi, window_name=None)
        print("  monitor_index=%d → 상태:%s | 프레임:%d | dims:%s | 콜백예외:%s"
              % (mi, st, cnt["n"], cnt["dims"], cnt["err"]))
    if sc_titles:
        for t in sc_titles[:2]:
            st, cnt = wgc_count(3, monitor_index=None, window_name=t)
            print("  window_name=%r → 상태:%s | 프레임:%d | dims:%s" % (t, st, cnt["n"], cnt["dims"]))
except Exception:
    import traceback
    print("WGC 테스트 자체 실패:")
    traceback.print_exc()

print("\n"); line()
print(" 진단 끝 — 이 창 전체를 캡처해서 보내주세요 (스크롤 위/아래 다)")
line()
try: input("\n엔터를 누르면 종료...")
except Exception: pass
