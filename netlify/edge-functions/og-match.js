// netlify/edge-functions/og-match.js
// 카카오/페북/트위터 등 '링크 스크래퍼'에게만 경기 정보를 담은 OG 메타를 동적으로 심는다.
// 일반 브라우저 요청은 그대로 통과(passthrough) — 체감 속도 영향 0.
const SB = "https://luljnalcnxfyxmlgoxbc.supabase.co";
const ANON = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx1bGpuYWxjbnhmeXhtbGdveGJjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODIwMDU1NDIsImV4cCI6MjA5NzU4MTU0Mn0.WhPOfWiOlokOHVZLmffIKKTDpQunhxwwwJOd6CSoC2k";   // 공개 anon 키 (웹 JS에 이미 노출된 값과 동일)
const BOT = /kakaotalk|scrap|facebookexternalhit|twitterbot|slackbot|discordbot|telegrambot|whatsapp|linkedinbot|line/i;

export default async (request, context) => {
  try {
    const url = new URL(request.url);
    const id = url.searchParams.get("id");
    const ua = request.headers.get("user-agent") || "";
    if (!id || !(BOT.test(ua) || url.searchParams.has("og"))) return context.next();

    const [res, page] = await Promise.all([
      fetch(SB + "/rest/v1/matches?id=eq." + encodeURIComponent(id) +
            "&select=map,length,players,winner,saver,thumb&limit=1",
            { headers: { apikey: ANON, authorization: "Bearer " + ANON } }),
      context.next(),
    ]);
    if (!res.ok) return page;
    const rows = await res.json();
    const m = rows && rows[0];
    if (!m) return page;

    let ps = m.players;
    if (typeof ps === "string") { try { ps = JSON.parse(ps); } catch (_e) { ps = []; } }
    ps = Array.isArray(ps) ? ps : [];
    const ini = (p) => ({ ran: "테", zerg: "저", toss: "프" }[p.race] || "?");
    const t1 = ps.filter((p) => p.team === 1), t2 = ps.filter((p) => p.team === 2);
    const comp = t1.length && t2.length ? t1.map(ini).join("") + " vs " + t2.map(ini).join("") : "";
    const title = [m.map || "경기", comp, m.length].filter(Boolean).join(" · ");
    const win = m.winner ? " · TEAM " + m.winner + " 승" : "";
    const desc = (t1.map((p) => p.name).join(" ") + " vs " + t2.map((p) => p.name).join(" ")) +
                 win + (m.saver ? " · " + m.saver + " 시점" : "") + " — ENCORE 다시보기";
    const img = m.thumb || "https://encorestar.netlify.app/og.png";
    const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");

    let html = await page.text();
    html = html
      .replace(/<title>[^<]*<\/title>/, "<title>" + esc(title) + " — ENCORE</title>")
      .replace(/(<meta property="og:title" content=")[^"]*(")/, "" + esc(title) + "")
      .replace(/(<meta property="og:description" content=")[^"]*(")/, "" + esc(desc) + "")
      .replace(/(<meta property="og:image" content=")[^"]*(")/, "" + esc(img) + "");
    if (!/property="og:url"/.test(html))
      html = html.replace("</head>", '<meta property="og:url" content="' + esc(url.origin + url.pathname + "?id=" + id) + '"></head>');

    return new Response(html, { headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "public, max-age=300",
    }});
  } catch (_e) { return context.next(); }
};
