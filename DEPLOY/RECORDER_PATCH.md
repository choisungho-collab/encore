# 레코더 패치 — sc_recorder.py 서명 업로드 전환 (service_key 클라이언트에서 제거)

목표: 녹화기가 더 이상 `service_key` 를 갖지 않고, **Netlify 서명 프록시(/api/storage)** 로
1회용 업로드 URL 을 받아 Storage 에 직접 PUT → 그다음 **RPC(`upload_match`)** 로 경기 행을 등록.
서명/RPC 가 실패하면 기존 방식으로 폴백하므로 **무중단**으로 바꿀 수 있음.

> 적용 순서 주의(README 참고): **레코더 배포 → 그 다음 SQL(02_security)**.
> SQL 이 먼저 돌면 구버전 레코더의 직접 업로드가 막힘.

---

## 1) 헬퍼 추가 (아무 곳, 예: `sb_upload` 바로 위)

```python
def _gallery_origin():
    return (CFG.get("gallery_url") or "https://encorestar.netlify.app/").rstrip("/")

def _my_ident():
    """(puuid, device_secret) — 서명 업로드/소유 등록에 쓰는 신원. puuid 없으면 (None, secret)."""
    try:
        pu = (_identity_load() or {}).get("puuid")
    except Exception:
        pu = None
    return pu, device_secret()
```

## 2) `sb_upload` 교체 (현재 service_key 로 직접 올리는 함수)

**아래로 통째 교체:**

```python
def sb_upload(local, path, ctype):
    """서명 프록시(/api/storage)로 1회용 URL 받아 Storage 에 PUT → 공개 URL.
       service_key 불필요. 실패 시(구 배포 등) 레거시 직접 업로드로 폴백."""
    import requests, os
    pu, secret = _my_ident()
    size = 0
    try: size = os.path.getsize(local)
    except Exception: pass
    if pu:   # 표준 경로: 서명 업로드
        try:
            pr = requests.post(_gallery_origin() + "/api/storage",
                               json={"action": "sign-upload", "puuid": pu, "secret": secret,
                                     "paths": [path], "bytes": size}, timeout=30)
            if pr.status_code == 429:
                raise RuntimeError("upload limit reached: " + (pr.text or "")[:120])
            pr.raise_for_status()
            items = (pr.json() or {}).get("items") or []
            if items and items[0].get("uploadUrl"):
                up = items[0]["uploadUrl"]; pub = items[0].get("publicUrl") or ""
                with open(local, "rb") as f:
                    ur = requests.put(up, data=f, headers={"Content-Type": ctype}, timeout=(10, 3600))
                if ur.status_code in (200, 201):
                    return pub or ("%s/storage/v1/object/public/%s/%s" % (_sb_base(), _sb_bucket(), path))
                raise RuntimeError("signed PUT %s: %s" % (ur.status_code, (ur.text or "")[:160]))
        except Exception as e:
            log(f"signed upload failed ({e}) — trying legacy…")
    # 레거시 폴백: config 에 service_key 가 있을 때만 (구 배포 호환). 없으면 실패.
    k = (sb_cfg().get("service_key") or "").strip()
    if not k:
        raise RuntimeError("no signed route and no service_key — deploy netlify/functions/storage.js "
                           "and set SUPABASE_SERVICE_KEY in Netlify env")
    with open(local, "rb") as f:
        r = requests.post("%s/storage/v1/object/%s/%s" % (_sb_base(), _sb_bucket(), path), data=f,
                          headers={"apikey": k, "Authorization": "Bearer " + k,
                                   "Content-Type": ctype, "x-upsert": "true"}, timeout=(10, 3600))
    if r.status_code not in (200, 201):
        raise RuntimeError("storage %s: %s" % (r.status_code, r.text[:200]))
    return "%s/storage/v1/object/public/%s/%s" % (_sb_base(), _sb_bucket(), path)
```

## 3) `sb_insert_match` 교체 (경기 행 등록 → RPC 로)

**아래로 통째 교체:**

```python
def sb_insert_match(row):
    """경기 행 등록. service_key 직접 insert 대신 RPC.
       기기 신원이 있으면 upload_match(소유 등록), 없거나 실패하면 upload_match_anon(폴백)."""
    sv = (row.get("saver") or "").strip()
    if sv:
        row.setdefault("owner_puuid", sv.lower())   # (서버가 owner 를 다시 지정하지만 참고용으로 유지)
        try: claim_identity(sv)                      # 이 기기 = 이 이름 (멱등)
        except Exception: pass
    pu, secret = _my_ident()
    if pu:
        try:
            _sb_rpc("upload_match", {"p_puuid": pu, "p_secret": secret, "p_row": row}, timeout=60)
            return
        except Exception as e:
            log(f"upload_match failed ({e}) — trying anon…")
    _sb_rpc("upload_match_anon", {"p_row": row}, timeout=60)
```

> `_sb_rpc` 는 이미 anon 키로 호출함(위 RPC 들은 security definer 라 anon 실행 허용). service_key 불필요.

## 4) (선택) 업로드 자가진단 추가 — 콘솔에서 상태 확인

```python
def upload_selftest():
    import requests
    try:
        r = requests.post(_gallery_origin() + "/api/storage", json={"action": "ping"}, timeout=10)
        if r.status_code == 200 and (r.json() or {}).get("ok"):
            log("Cloud upload self-test: OK ✓  (signed route /api/storage is live)")
            return True
    except Exception:
        pass
    log("⚠ signed route /api/storage 없음 → netlify/functions/storage.js + netlify.toml 배포, "
        "Netlify env(SUPABASE_SERVICE_KEY) 설정 필요. (설정 전엔 로컬 보관/재시도)")
    return False
```
`main()` 클라우드 켜진 분기에서 한 번 호출해 주면 됨(예: `if cloud_state()=='cloud': upload_selftest()`).

---

## config.json 정리
- `supabase.service_key` 는 **비워도 됨**(서명 경로에선 불필요). 구 배포 호환용으로만 남겨둠.
- `gallery_url` 을 실제 사이트로: `"gallery_url": "https://encorestar.netlify.app"`.

## 무엇이 바뀌나 (요약)
- 영상/썸네일/리플레이 업로드: **서명 URL 로만** → 클라이언트에 service_key 불필요.
- 경기 등록: `upload_match` RPC(기기 검증 → 소유행) → 남의 경기 못 덮음.
- 쿼터 초과 시 429 로 거부(로컬 보관 후 재시도 큐로). 스토리지 폭탄/스팸 차단.
