/* encore-common.js — 전 페이지 공유 설정·유틸 (index/match/player 공통)
   주의: 이 스크립트를 각 페이지의 다른 인라인 <script>보다 먼저 로드할 것. */
const SB="https://luljnalcnxfyxmlgoxbc.supabase.co";
const KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx1bGpuYWxjbnhmeXhtbGdveGJjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODIwMDU1NDIsImV4cCI6MjA5NzU4MTU0Mn0.WhPOfWiOlokOHVZLmffIKKTDpQunhxwwwJOd6CSoC2k";
const H={apikey:KEY,Authorization:"Bearer "+KEY,"Content-Type":"application/json"};
function esc(s){return (s==null?"":String(s)).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
function mapName(s){return String(s==null?"":s).replace(/[\u25A0-\u25FF\u2605\u2606\u2666\u2662\u203B\u2726\u2727\u2731\u2736\u2737\u2756]/g," ").replace(/\s{2,}/g," ").trim();}
function parseTS(iso){if(!iso)return null;const s=String(iso).trim();const hasTz=/[zZ]$|[+\-]\d\d:?\d\d$/.test(s);const d=new Date(hasTz?s:s+"+09:00");return isNaN(d.getTime())?null:d;}
function fdate(iso){const d=parseTS(iso);if(!d)return iso?String(iso).slice(0,16).replace("T"," "):"";const p=n=>String(n).padStart(2,"0");return `${d.getFullYear()}.${p(d.getMonth()+1)}.${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;}
function ago(iso){const d=parseTS(iso);if(!d)return iso?String(iso).slice(0,10):"";const sx=(Date.now()-d.getTime())/1000;if(sx<60)return "방금";if(sx<3600)return Math.floor(sx/60)+"분 전";if(sx<86400)return Math.floor(sx/3600)+"시간 전";if(sx<604800)return Math.floor(sx/86400)+"일 전";return String(iso).slice(0,10);}

/* ── 같은 경기(여러 시점) 묶기 ──────────────────────────────────────────
   같은 한 판을 여러 명이 각자 녹화하면 매치가 N개로 중복된다. 이를 하나로 묶는다.
   레코더 group_key가 있으면 그것으로 정확히 묶고, 없으면 맵+정렬된 플레이어 이름이
   같고 길이가 ±4초 이내인 매치를 같은 경기로 본다(같은 게임이라도 누가 먼저 나가느냐에
   따라 리플레이 종료 프레임이 1~2초 흔들리므로 길이를 키에 못 박지 않는다). */
function _playersOf(m){
  let ps = m && m.players;
  if (typeof ps === "string") { try { ps = JSON.parse(ps); } catch (e) { ps = null; } }
  if (!Array.isArray(ps)) {
    let a = m && m.analysis;
    if (typeof a === "string") { try { a = JSON.parse(a || "{}"); } catch (e) { a = {}; } }
    ps = (a && a.players) || [];
  }
  return Array.isArray(ps) ? ps : [];
}
function _lenSec(v){
  if (v == null) return 0;
  if (typeof v === "number") return v;
  const m = String(v).trim().split(":");
  if (m.length >= 2 && m.length <= 3) { let s = 0; for (let i = 0; i < m.length; i++) s = s * 60 + (+m[i] || 0); return s; }
  return (+v || 0);
}
function _len(m){ const s = m && m.length_sec, n = (typeof s === "number") ? s : parseFloat(s); return (isFinite(n) && n > 0) ? n : _lenSec(m && m.length); }
// 맵+이름까지만 (길이는 뺀다)
function baseKeyOf(m){
  if (m && m.group_key) return "g:" + String(m.group_key);
  const names = _playersOf(m).map(p => (p && p.name) ? String(p.name) : "").filter(Boolean).sort().join(",");
  return "h:" + ((m && m.map) || "") + "|" + names;
}
// 두 매치가 같은 경기인가
function sameGame(a, b){
  if (a && b && a.group_key && b.group_key) return String(a.group_key) === String(b.group_key);
  if (baseKeyOf(a) !== baseKeyOf(b)) return false;
  const sa = a && a.saver, sb = b && b.saver;
  if (sa && sb && sa === sb) return false;   // 한 판 = 한 저장자: 같은 사람이 저장한 두 행은 서로 다른 판
  const la = _len(a), lb = _len(b);
  if (!la || !lb) return false;   // 길이 불명이면 같은 경기로 단정하지 않음(다른 경기 뒤섞임 방지)
  return Math.abs(la - lb) <= 6;
}
// 매치 배열 → 같은 경기끼리 묶은 인덱스 그룹들의 배열
function clusterMatches(rows){
  const byBase = {};
  rows.forEach((r, i) => { const k = baseKeyOf(r); (byBase[k] = byBase[k] || []).push(i); });
  const out = [];
  Object.keys(byBase).forEach(k => {
    const idxs = byBase[k];
    const parent = {}; idxs.forEach(i => parent[i] = i);
    const find = x => { while (parent[x] !== x) { parent[x] = parent[parent[x]]; x = parent[x]; } return x; };
    for (let a = 0; a < idxs.length; a++) for (let b = a + 1; b < idxs.length; b++) {
      if (sameGame(rows[idxs[a]], rows[idxs[b]])) { const ra = find(idxs[a]), rb = find(idxs[b]); if (ra !== rb) parent[ra] = rb; }
    }
    const g = {}; idxs.forEach(i => { const r = find(i); (g[r] = g[r] || []).push(i); });
    Object.keys(g).forEach(r => out.push(g[r]));
  });
  return out;
}

/* ── 종족 아이콘 · 라인업 (전 페이지 공용) ───────────────────────────── */
const RACE_SVG={
  ran:'<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.4 L20 7 V17 L12 21.6 L4 17 V7 Z"/></svg>',
  zerg:'<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.2 C8.4 6 6.4 11 7.4 16.6 C7.9 19.6 9.4 21 11 20 C11.5 19.6 11.5 18 12 18 C12.5 18 12.5 19.6 13 20 C14.6 21 16.1 19.6 16.6 16.6 C17.6 11 15.6 6 12 2.2 Z"/></svg>',
  toss:'<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2 L14.2 9.8 L22 12 L14.2 14.2 L12 22 L9.8 14.2 L2 12 L9.8 9.8 Z"/></svg>'
};
function raceKey(race){const r=(race||'').toLowerCase();if(r.indexOf('terr')>=0||r==='ran'||r==='t')return 'ran';if(r.indexOf('zerg')>=0||r==='z')return 'zerg';if(r.indexOf('toss')>=0||r.indexOf('prot')>=0||r==='p')return 'toss';return 'unk';}
function raceIcon(race){return RACE_SVG[raceKey(race)]||'';}
function raceChip(race){const k=raceKey(race);return '<span class="ric '+k+'">'+(({ran:'T',zerg:'Z',toss:'P'})[k]||'?')+'</span>';}
function lineup(g,forceNames){const ps=g.players||[];const ts=[];ps.forEach(p=>{if(!ts.some(x=>String(x)===String(p.team)))ts.push(p.team);});if(ts.length<2)return '';const myp=ps.find(p=>p.name===g.me);let a=ts[0],b=ts[1];if(myp&&String(myp.team)===String(ts[1])){a=ts[1];b=ts[0];}const tA=ps.filter(p=>String(p.team)===String(a)),tB=ps.filter(p=>String(p.team)===String(b));const wA=(g.winner!=null&&String(g.winner)===String(a)),wB=(g.winner!=null&&String(g.winner)===String(b));const big=(!forceNames)&&(tA.length>2||tB.length>2);
  const names=(arr,win,r)=>'<div class="lnteam'+(win?' win':'')+(r?' r':'')+'">'+arr.slice(0,4).map(p=>'<div class="lnpl">'+raceChip(p.race)+'<span class="lnnm">'+esc(p.name||'—')+'</span></div>').join('')+'</div>';
  const comp=(arr,win,r)=>{const ic='<span class="lnics">'+arr.map(p=>raceChip(p.race)).join('')+'</span>';const w=win?'<span class="lnwin">WIN</span>':'';return '<div class="lncomp'+(r?' r':'')+'">'+(r?ic+w:w+ic)+'</div>';};
  const A=big?comp(tA,wA,false):names(tA,wA,false);const B=big?comp(tB,wB,true):names(tB,wB,true);
  return '<div class="lineup'+(big?' comp':'')+'">'+A+'<span class="lnvs">VS</span>'+B+'</div>';}

/* ── 로딩 스켈레톤 카드 (전 페이지 공용) ── */
function skelCards(n){var h='';for(var i=0;i<(n||8);i++){h+='<div class="card skel"><div class="skel-thumb"></div><div class="cbody"><div class="skel-row"><span class="skel-ic"></span><span class="skel-line f1"></span><span class="skel-ic"></span></div><div class="skel-row sk-foot"><span class="skel-line" style="width:32%"></span><span class="skel-line ml" style="width:16%"></span></div></div></div>';}return h;}

/* ── 랭킹 리더보드 스켈레톤 (stats용) ── */
function skelHall(){var row='<div class="skel-row" style="padding:9px 0"><span class="skel-ic" style="width:14px;height:14px"></span><span class="skel-ic"></span><span class="skel-line f1"></span><span class="skel-line" style="width:34px"></span></div>';var c='<div class="hcard skel"><div class="skel-line" style="width:44%;height:13px;margin:2px 0 16px"></div>'+row+row+row+row+row+'</div>';return '<div class="hall"><div class="hall-h"><span class="skel-line" style="width:120px;height:18px;display:inline-block"></span></div><div class="hgrid">'+c+c+c+c+'</div></div>';}
