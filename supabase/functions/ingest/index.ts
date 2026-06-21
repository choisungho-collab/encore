// 리플레이 캐스트 — 인게스트 Edge Function
// 역할 두 가지:
//   action:"presign"  → R2 업로드용 1회성 URL 발급 (R2 비밀키는 여기에만 있음)
//   action:"register" → 녹화기가 만든 경기 행(분석 포함)을 Postgres 에 저장 (service_role 키 사용)
// 클라이언트는 공유 upload_key 만 가지면 됨.
//
// 배포:  supabase functions deploy ingest --no-verify-jwt
// 시크릿(아래)은 R2 관련만 설정. SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 는 자동 주입됨.

import { AwsClient } from "npm:aws4fetch@1.0.20";
import { createClient } from "npm:@supabase/supabase-js@2";

const env = (k: string) => Deno.env.get(k) ?? "";
const UPLOAD_KEY  = env("UPLOAD_KEY");
const R2_ACCOUNT  = env("R2_ACCOUNT_ID");
const R2_BUCKET   = env("R2_BUCKET");
const R2_PUBLIC   = env("R2_PUBLIC_BASE_URL").replace(/\/+$/, "");
const R2_ENDPOINT = `https://${R2_ACCOUNT}.r2.cloudflarestorage.com`;

const r2 = new AwsClient({
  accessKeyId: env("R2_ACCESS_KEY_ID"),
  secretAccessKey: env("R2_SECRET_ACCESS_KEY"),
  service: "s3",
  region: "auto",
});

const cors: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, content-type, apikey, x-client-info",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const json = (b: unknown, status = 200) =>
  new Response(JSON.stringify(b), { status, headers: { ...cors, "content-type": "application/json" } });

// content-type 은 서명하지 않음 → 클라이언트 PUT 의 Content-Type 헤더가 그대로 저장됨
async function presignPut(key: string, expires = 3600): Promise<string> {
  const u = new URL(`${R2_ENDPOINT}/${R2_BUCKET}/${key}`);
  u.searchParams.set("X-Amz-Expires", String(expires));
  const signed = await r2.sign(new Request(u.toString(), { method: "PUT" }), { aws: { signQuery: true } });
  return signed.url;
}

function gid(): string {
  const d = new Date(), p = (n: number) => String(n).padStart(2, "0");
  const stamp = `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
  return `${stamp}-${Math.random().toString(16).slice(2, 6)}`;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST")    return json({ error: "POST only" }, 405);

  let body: any;
  try { body = await req.json(); } catch { return json({ error: "bad json" }, 400); }
  if (body?.key !== UPLOAD_KEY)  return json({ error: "bad key" }, 401);

  try {
    if (body.action === "presign") {
      const g = gid();
      return json({
        gid: g,
        video_put: await presignPut(`videos/${g}.mp4`), video_url: `${R2_PUBLIC}/videos/${g}.mp4`,
        thumb_put: await presignPut(`thumbs/${g}.jpg`), thumb_url: `${R2_PUBLIC}/thumbs/${g}.jpg`,
        rep_put:   await presignPut(`reps/${g}.rep`),   rep_url:   `${R2_PUBLIC}/reps/${g}.rep`,
      });
    }

    if (body.action === "register") {
      const m = body.match;
      if (!m?.id) return json({ error: "no match.id" }, 400);
      const sb = createClient(env("SUPABASE_URL"), env("SUPABASE_SERVICE_ROLE_KEY"), {
        auth: { persistSession: false },
      });
      const { error } = await sb.from("matches").upsert(m, { onConflict: "id" });
      if (error) return json({ error: error.message }, 500);
      return json({ ok: true });
    }

    return json({ error: "unknown action" }, 400);
  } catch (e) {
    return json({ error: String(e) }, 500);
  }
});
