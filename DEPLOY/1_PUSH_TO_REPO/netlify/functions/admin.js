// ENCORE — 관리자 API (운영자 전용)
// 인증: ID/PW 로그인(action:'login') → 12시간 HMAC 세션 토큰 → 이후 요청은 x-admin-token 헤더.
//  - 비밀번호·세션키는 Netlify 환경변수에만(ADMIN_ID / ADMIN_PW). DB/브라우저에 원본 비번 없음.
//  - 무상태라 IP 잠금은 없음. 실패 시 650ms 지연으로 무차별 대입만 늦춤.
//
// actions (POST /api/admin):
//   { action:'login', id, pw }                 → { token, exp }
//   { action:'stats' }                         → 매치/유저/세션 수, 영상 용량, 최근 7일 업로드
//   { action:'errors', limit? }                → 최근 에러 로그
//   { action:'matches', q?, limit?, before? }  → 최근 매치(같은 경기 group_key 로 묶음)
//   { action:'delete-match', id }              → 그 매치 1개 + 스토리지 파일 삭제
//   { action:'delete-match', groupKey }        → 같은 경기(멀티 시점) 통째 삭제
//   { action:'orphan-scan' }                   → matches 미참조 스토리지 파일 목록
//   { action:'orphan-clean', paths:[...] }     → 고아 파일 일괄 삭제(회당 최대 200)
//
// 필요한 Netlify 환경변수: SUPABASE_URL, SUPABASE_SERVICE_KEY, ADMIN_ID, ADMIN_PW, (선택) SUPABASE_BUCKET

const crypto = require('crypto');

const SB_URL = (process.env.SUPABASE_URL || '').replace(/\/+$/, '');
const SB_KEY = process.env.SUPABASE_SERVICE_KEY || '';
const BUCKET = process.env.SUPABASE_BUCKET || 'media';
const ADMIN_ID = process.env.ADMIN_ID || '';
const ADMIN_PW = process.env.ADMIN_PW || '';
const SESS_SECRET = process.env.ADMIN_SESSION_SECRET || ('encore.' + ADMIN_PW);
const SESS_TTL_MS = 12 * 3600 * 1000;

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, X-Admin-Token'
};
const PATH_RE = /^(videos|thumbs|replays|previews|clips)\/[A-Za-z0-9._\/-]{1,180}\.(mp4|jpg|rep)$/;

function reply(statusCode, obj) {
  return { statusCode, headers: { ...CORS, 'Content-Type': 'application/json' }, body: JSON.stringify(obj) };
}
function sbH(extra) {
  return { 'Authorization': 'Bearer ' + SB_KEY, 'apikey': SB_KEY, 'Content-Type': 'application/json', ...(extra || {}) };
}
function safeEq(x, y) {
  const a = crypto.createHash('sha256').update(String(x)).digest();
  const b = crypto.createHash('sha256').update(String(y)).digest();
  return crypto.timingSafeEqual(a, b);
}
function signSession(exp) {
  const mac = crypto.createHmac('sha256', SESS_SECRET).update('adm.' + exp).digest('base64url');
  return exp + '.' + mac;
}
function sessionOk(tok) {
  const parts = String(tok || '').split('.');
  if (parts.length !== 2) return false;
  const exp = parseInt(parts[0], 10);
  if (!isFinite(exp) || Date.now() > exp) return false;
  return safeEq(signSession(exp), parts[0] + '.' + parts[1]);
}
const sleep = ms => new Promise(res => setTimeout(res, ms));
function keyFromUrl(u) {
  const mark = '/object/public/' + BUCKET + '/';
  const i = (u || '').indexOf(mark);
  return i < 0 ? null : u.slice(i + mark.length);
}

async function countOf(table, filter) {
  const r = await fetch(SB_URL + '/rest/v1/' + table + '?select=id' + (filter || ''), {
    headers: sbH({ 'Prefer': 'count=exact', 'Range': '0-0' })
  });
  const cr = r.headers.get('content-range') || '';
  const n = parseInt(cr.split('/')[1], 10);
  return isFinite(n) ? n : 0;
}
async function listStorage(prefix) {
  const out = [];
  for (let page = 0; page < 20; page++) {
    const r = await fetch(SB_URL + '/storage/v1/object/list/' + BUCKET, {
      method: 'POST', headers: sbH(),
      body: JSON.stringify({ prefix, limit: 1000, offset: page * 1000, sortBy: { column: 'name', order: 'asc' } })
    });
    if (!r.ok) throw new Error('storage list ' + r.status);
    const j = await r.json();
    for (const o of (j || [])) {
      if (o && o.id) out.push({ path: prefix + '/' + o.name, size: (o.metadata && o.metadata.size) || 0, created: o.created_at || '' });
    }
    if (!j || j.length < 1000) break;
  }
  return out;
}
async function allMatchRefs() {
  const refs = new Set();
  for (let page = 0; page < 40; page++) {
    const from = page * 1000, to = from + 999;
    const r = await fetch(SB_URL + '/rest/v1/matches?select=video,thumb,replay,preview', { headers: sbH({ 'Range': from + '-' + to }) });
    if (!r.ok) throw new Error('matches read ' + r.status);
    const rows = await r.json();
    for (const row of rows) {
      ['video', 'thumb', 'replay', 'preview'].forEach(f => { const k = keyFromUrl(row[f]); if (k) refs.add(k); });
    }
    if (rows.length < 1000) break;
  }
  return refs;
}
async function storageDelete(paths) {
  const r = await fetch(SB_URL + '/storage/v1/object/' + BUCKET, {
    method: 'DELETE', headers: sbH(), body: JSON.stringify({ prefixes: paths })
  });
  if (!r.ok) throw new Error('storage delete ' + r.status + ': ' + (await r.text()).slice(0, 160));
}

exports.handler = async (event) => {
  if (event.httpMethod === 'OPTIONS') return { statusCode: 204, headers: CORS, body: '' };
  if (event.httpMethod !== 'POST') return reply(405, { error: 'POST only' });
  if (!SB_URL || !SB_KEY) return reply(500, { error: 'server not configured (SUPABASE_URL / SUPABASE_SERVICE_KEY)' });
  if (!ADMIN_ID || !ADMIN_PW) return reply(500, { error: 'ADMIN_ID / ADMIN_PW not set on server' });

  let body;
  try { body = JSON.parse(event.body || '{}'); } catch (_) { return reply(400, { error: 'bad json' }); }

  if (body.action === 'login') {
    const okId = safeEq(body.id || '', ADMIN_ID);
    const okPw = safeEq(body.pw || '', ADMIN_PW);
    if (!(okId && okPw)) { await sleep(650); return reply(401, { error: 'wrong id or password' }); }
    const exp = Date.now() + SESS_TTL_MS;
    return reply(200, { token: signSession(exp), exp });
  }

  if (!sessionOk(event.headers['x-admin-token'] || event.headers['X-Admin-Token'])) {
    return reply(401, { error: 'session expired or invalid' });
  }

  try {
    if (body.action === 'stats') {
      const weekAgo = new Date(Date.now() - 7 * 86400000).toISOString();
      const [nMatch, nIdent, nSess, nWeek] = await Promise.all([
        countOf('matches'), countOf('identities'), countOf('sessions'),
        countOf('matches', '&uploaded=gte.' + encodeURIComponent(weekAgo))
      ]);
      let vidBytes = 0, vidRows = 0;
      for (let page = 0; page < 40; page++) {
        const from = page * 1000, to = from + 999;
        const r = await fetch(SB_URL + '/rest/v1/matches?select=video_size', { headers: sbH({ 'Range': from + '-' + to }) });
        const rows = r.ok ? await r.json() : [];
        for (const row of rows) { vidBytes += (row.video_size || 0); vidRows++; }
        if (rows.length < 1000) break;
      }
      return reply(200, { matches: nMatch, identities: nIdent, sessions: nSess, uploads7d: nWeek, videoBytes: vidBytes, videoRows: vidRows });
    }

    if (body.action === 'errors') {
      const limit = Math.min(Math.max(parseInt(body.limit, 10) || 50, 1), 200);
      const r = await fetch(SB_URL + '/rest/v1/error_log?select=id,source,message,meta,created_at&order=created_at.desc&limit=' + limit, { headers: sbH() });
      return reply(200, { errors: r.ok ? await r.json() : [] });
    }

    if (body.action === 'matches') {
      const limit = Math.min(Math.max(parseInt(body.limit, 10) || 60, 1), 200);
      let url = SB_URL + '/rest/v1/matches?select=id,group_key,uploader,uploaded,video_size,owner_puuid,map,matchup,length,won'
              + '&order=uploaded.desc&limit=' + (limit * 4);
      const q = String(body.q || '').slice(0, 60).replace(/[%,()]/g, '');
      if (q) url += '&or=(uploader.ilike.*' + encodeURIComponent(q) + '*,map.ilike.*' + encodeURIComponent(q) + '*)';
      if (body.before) url += '&uploaded=lt.' + encodeURIComponent(String(body.before).slice(0, 40));
      const r = await fetch(url, { headers: sbH() });
      if (!r.ok) throw new Error('matches ' + r.status);
      const rows = await r.json();

      const groups = new Map();   // 같은 경기(group_key, 없으면 id) 로 묶어 멀티 시점을 한 줄로
      for (const row of rows) {
        const key = row.group_key || row.id;
        let g = groups.get(key);
        if (!g) { g = { key, uploaded: row.uploaded, map: row.map || '', matchup: row.matchup || '', length: row.length || '', totalBytes: 0, povs: [] }; groups.set(key, g); }
        g.povs.push({ id: row.id, uploader: row.uploader || '', owner: !!row.owner_puuid, bytes: row.video_size || 0, won: row.won });
        g.totalBytes += (row.video_size || 0);
        if (row.uploaded > g.uploaded) g.uploaded = row.uploaded;
      }
      const out = Array.from(groups.values()).sort((a, b) => (a.uploaded < b.uploaded ? 1 : -1)).slice(0, limit);
      const cursor = out.length ? out[out.length - 1].uploaded : null;
      return reply(200, { groups: out, cursor, hasMore: rows.length >= limit * 4 });
    }

    if (body.action === 'delete-match') {
      let filter, label;
      if (body.groupKey) {
        const gk = String(body.groupKey);
        if (!/^[A-Za-z0-9._:-]{1,200}$/.test(gk)) return reply(400, { error: 'bad groupKey' });
        filter = 'group_key=eq.' + encodeURIComponent(gk); label = gk;
      } else {
        const id = String(body.id || '');
        if (!/^[A-Za-z0-9._-]{8,140}$/.test(id)) return reply(400, { error: 'bad id' });
        filter = 'id=eq.' + encodeURIComponent(id); label = id;
      }
      const r = await fetch(SB_URL + '/rest/v1/matches?select=video,thumb,replay,preview&' + filter, { headers: sbH() });
      const rows = r.ok ? await r.json() : [];
      if (!rows.length) return reply(404, { error: 'not found' });
      const paths = [];
      for (const row of rows) ['video', 'thumb', 'replay', 'preview'].forEach(f => { const k = keyFromUrl(row[f]); if (k) paths.push(k); });
      if (paths.length) await storageDelete(paths);
      const d = await fetch(SB_URL + '/rest/v1/matches?' + filter, { method: 'DELETE', headers: sbH() });
      if (!d.ok) throw new Error('row delete ' + d.status);
      return reply(200, { ok: true, removedRows: rows.length, removedFiles: paths });
    }

    if (body.action === 'orphan-scan') {
      const [vids, thumbs, reps, prevs, refs] = await Promise.all([
        listStorage('videos'), listStorage('thumbs'), listStorage('replays'), listStorage('previews'), allMatchRefs()
      ]);
      const all = vids.concat(thumbs, reps, prevs);
      const orphans = all.filter(o => !refs.has(o.path) && !o.path.startsWith('_selftest'));
      const bytes = orphans.reduce((a, o) => a + (o.size || 0), 0);
      return reply(200, { orphans: orphans.slice(0, 2000), totalBytes: bytes, scanned: all.length });
    }

    if (body.action === 'orphan-clean') {
      const paths = Array.isArray(body.paths) ? body.paths.slice(0, 200) : [];
      if (!paths.length) return reply(400, { error: 'no paths' });
      for (const p of paths) if (typeof p !== 'string' || !PATH_RE.test(p)) return reply(400, { error: 'path not allowed: ' + String(p).slice(0, 80) });
      const refs = await allMatchRefs();   // 안전핀: 참조 중이면 지우지 않음
      const safe = paths.filter(p => !refs.has(p));
      if (safe.length) await storageDelete(safe);
      return reply(200, { ok: true, removed: safe.length, skipped: paths.length - safe.length });
    }

    return reply(400, { error: 'unknown action' });
  } catch (e) {
    return reply(502, { error: String((e && e.message) || e).slice(0, 240) });
  }
};
