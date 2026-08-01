// netlify/edge-functions/og-match.js  (v2)
// '링크 스크래퍼'(카카오 스크랩봇·페북·트위터 등)에게만 경기 정보 OG 메타를 동적으로 심는다.
// 카카오/라인 '인앱 브라우저'(사람)는 봇이 아니므로 그대로 통과. 어떤 실패에도 원본 통과.
const SB = "https://luljnalcnxfyxmlgoxbc.supabase.co";
const ANON = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx1bGpuYWxjbnhmeXhtbGdveGJjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODIwMDU1NDIsImV4cCI6MjA5NzU4MTU0Mn0.WhPOfWiOlokOHVZLmffIKKTDpQunhxwwwJOd6CSoC2k"; // 공개 anon 키 (아래 주입)
// 스크래퍼만: kakaotalk-scrap / facebookexternalhit / *bot / whatsapp / daum ...  (인앱 UA 'KAKAOTALK', 'Line/'는 제외)
const BOT = /scrap|facebookexternalhit|twitterbot|slackbot|discordbot|telegrambot|whatsapp|linkedinbot|kakaostory|daum|yeti|googlebot|bingbot|applebot|petalbot/i;

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
    const t1 = ps.filter((p) => String(p.team) === "1"), t2 = ps.filter((p) => String(p.team) === "2");
    const comp = t1.length && t2.length ? t1.map(ini).join("") + " vs " + t2.map(ini).join("") : "";
    const title = [m.map || "경기", comp, m.length].filter(Boolean).join(" · ");
    const win = m.winner ? " · TEAM " + m.winner + " 승" : "";
    const desc = (t1.map((p) => p.name).join(" ") + " vs " + t2.map((p) => p.name).join(" ")) +
                 win + (m.saver ? " · " + m.saver + " 시점" : "") + " — ENCORE 다시보기";
    const img = m.thumb || "https://encorestar.netlify.app/og.png";
    const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");

    let html = await page.text();
    // 콜백 치환: 치환문자열의 $ 특수의미를 원천 배제 (지난 사고의 원인)
    html = html
      .replace(/<title>[^<]*<\/title>/, () => "<title>" + esc(title) + " — ENCORE</title>")
      .replace(/(<meta property="og:title" content=")[^"]*(")/, (mm, a, b) => a + esc(title) + b)
      .replace(/(<meta property="og:description" content=")[^"]*(")/, (mm, a, b) => a + esc(desc) + b)
      .replace(/(<meta property="og:image" content=")[^"]*(")/, (mm, a, b) => a + esc(img) + b);
    if (!/property="og:url"/.test(html)) {
      const ogu = '<meta property="og:url" content="' + esc(url.origin + url.pathname + "?id=" + id) + '"></head>';
      html = html.replace("</head>", () => ogu);
    }
    return new Response(html, { headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "public, max-age=300",
    }});
  } catch (_e) { return context.next(); }
};
