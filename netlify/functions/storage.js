// ENCORE 서명 업로드 프록시
// 레코더(sc_recorder.py)가 이 라우트로 1회용 업로드 URL을 받아 Supabase Storage 에 직접 PUT 한다.
// service_role 키는 서버(여기)에만 두고 클라이언트/레코더엔 노출하지 않는다.
//
// 필요한 Netlify 환경변수:
//   SUPABASE_URL           예) https://luljnalcnxfyxmlgoxbc.supabase.co
//   SUPABASE_SERVICE_KEY   Supabase → Project Settings → API → service_role secret
//   SUPABASE_BUCKET        (선택) 기본 "media"
//
// 처리하는 action:
//   { action:"ping" }                                  → { ok:true }  (레코더 자가진단용)
//   { action:"sign-upload", paths:[...], bytes, ... }  → { items:[{ path, uploadUrl, publicUrl }] }

const SUPABASE_URL = (process.env.SUPABASE_URL || "https://luljnalcnxfyxmlgoxbc.supabase.co").replace(/\/+$/, "");
const SERVICE_KEY  = process.env.SUPABASE_SERVICE_KEY || "";
const BUCKET       = process.env.SUPABASE_BUCKET || "media";

// 판당 업로드 용량 상한(무한정 대용량 방지). 필요하면 조정.
const MAX_BYTES = 6 * 1024 * 1024 * 1024; // 6GB

const JSON_HEADERS = { "Content-Type": "application/json", "Cache-Control": "no-store" };

function reply(statusCode, obj) {
  return { statusCode, headers: JSON_HEADERS, body: JSON.stringify(obj) };
}

// path 안전화: 상위경로 이탈·백슬래시·중복 슬래시 제거, 허용 문자만.
function sanitizePath(p) {
  if (typeof p !== "string") return null;
  let s = p.trim().replace(/\\/g, "/").replace(/^\/+/, "").replace(/\/{2,}/g, "/");
  if (!s || s.includes("..") || s.length > 300) return null;
  if (!/^[A-Za-z0-9._\-/]+$/.test(s)) return null;
  return s;
}

async function signOne(rawPath) {
  const path = sanitizePath(rawPath);
  if (!path) return { path: rawPath, error: "bad path" };

  // Supabase Storage: 1회용 업로드 서명 URL 발급
  const r = await fetch(
    `${SUPABASE_URL}/storage/v1/object/upload/sign/${BUCKET}/${path}`,
    {
      method: "POST",
      headers: {
        apikey: SERVICE_KEY,
        Authorization: "Bearer " + SERVICE_KEY,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ upsert: true }),
    }
  );

  const text = await r.text();
  if (!r.ok) return { path, error: `sign ${r.status}: ${text.slice(0, 160)}` };

  let signedURL = "";
  try { signedURL = (JSON.parse(text) || {}).url || ""; } catch (_) {}
  if (!signedURL) return { path, error: "no signed url in response" };

  // 레코더는 이 uploadUrl 로 곧장 PUT 한다.
  return {
    path,
    uploadUrl: SUPABASE_URL + "/storage/v1" + signedURL,
    publicUrl: `${SUPABASE_URL}/storage/v1/object/public/${BUCKET}/${path}`,
  };
}

exports.handler = async (event) => {
  if (event.httpMethod !== "POST") return reply(405, { error: "POST only" });

  let body;
  try { body = JSON.parse(event.body || "{}"); }
  catch (_) { return reply(400, { error: "bad json" }); }

  const action = body.action || "";

  // 자가진단 — 키 설정 여부까지 알려준다.
  if (action === "ping") {
    return reply(200, { ok: true, configured: !!SERVICE_KEY, bucket: BUCKET });
  }

  if (action === "sign-upload") {
    if (!SERVICE_KEY) {
      return reply(500, { error: "SUPABASE_SERVICE_KEY not set in Netlify env" });
    }
    const paths = Array.isArray(body.paths) ? body.paths : [];
    if (!paths.length) return reply(400, { error: "paths required" });
    if (paths.length > 8) return reply(400, { error: "too many paths" });

    const bytes = Number(body.bytes || 0);
    if (bytes && bytes > MAX_BYTES) {
      return reply(429, { error: "file too large (" + Math.round(bytes / 1048576) + "MB)" });
    }

    try {
      const items = [];
      for (const p of paths) items.push(await signOne(p));
      const anyOk = items.some((it) => it.uploadUrl);
      if (!anyOk) return reply(502, { error: "sign failed", items });
      return reply(200, { items });
    } catch (e) {
      return reply(500, { error: "sign exception: " + (e && e.message ? e.message : String(e)) });
    }
  }

  return reply(400, { error: "unknown action: " + action });
};
