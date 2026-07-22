/* ══ ENCORE 웹 버전 — 배포 확인용. 파일 전달 시마다 +1 ══ */
window.ENCORE_WEB_VER = 'v006';
try{console.info('%cENCORE web ' + window.ENCORE_WEB_VER, 'color:#8fa8d8;font-weight:600');}catch(e){}
document.addEventListener('DOMContentLoaded', function(){try{
  var by = document.querySelector('.ftr-by');
  if(by && !by.querySelector('.webver')){
    var sp = document.createElement('span'); sp.className = 'webver';
    sp.textContent = window.ENCORE_WEB_VER; by.appendChild(sp);
  }
}catch(e){}});

/* ENCORE 로그인/세션 모듈 — 모든 페이지에서 공통 사용.
 *  사용법:  <script src="encore-auth.js"></script>  로 불러오고
 *           const me = await EAuth.initAuth();   // #code 소비 + 토큰검증 → 세션 or null
 *  ★ ENCORE 자기 Supabase 프로젝트 키. (myPENTA 키 아님)
 */
(function () {
  var SB_URL  = 'https://luljnalcnxfyxmlgoxbc.supabase.co';
  var SB_ANON = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx1bGpuYWxjbnhmeXhtbGdveGJjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODIwMDU1NDIsImV4cCI6MjA5NzU4MTU0Mn0.WhPOfWiOlokOHVZLmffIKKTDpQunhxwwwJOd6CSoC2k';
  var SB_REST = SB_URL + '/rest/v1';

  function sbHeaders(extra) {
    var h = { apikey: SB_ANON, Authorization: 'Bearer ' + SB_ANON };
    for (var k in (extra || {})) h[k] = extra[k];
    return h;
  }
  async function sbRpc(fn, body) {
    var r = await fetch(SB_REST + '/rpc/' + fn, {
      method: 'POST',
      headers: sbHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body || {})
    });
    if (!r.ok) throw new Error('supabase rpc ' + fn + ' ' + r.status);
    var t = await r.text();
    try { return JSON.parse(t); } catch (e) { return t; }
  }

  var SESS_KEY = 'encore_session';
  function _read()  { try { return JSON.parse(localStorage.getItem(SESS_KEY) || 'null'); } catch (e) { return null; } }
  function _write(s){ try { if (s) localStorage.setItem(SESS_KEY, JSON.stringify(s)); else localStorage.removeItem(SESS_KEY); } catch (e) {} }

  function session() { return _read(); }                  // {token,puuid,name,icon} | null
  function puuid()   { var s = _read(); return s && s.puuid; }

  async function loginWithCode(code) {
    var r = await sbRpc('exchange_login_code', { p_code: code });   // {token,puuid,name,icon}
    if (r && r.token) { _write(r); return r; }
    return null;
  }
  async function whoami() {
    var s = _read(); if (!s || !s.token) return null;
    try {
      var r = await sbRpc('session_whoami', { p_token: s.token });
      if (r && r.puuid) { var ns = { token: s.token, puuid: r.puuid, name: r.name, icon: r.icon }; _write(ns); return ns; }
      _write(null); return null;                          // 만료/무효 → 정리
    } catch (e) { return s; }                             // 네트워크 오류면 캐시 유지
  }
  async function logout() {
    var s = _read();
    if (s && s.token) { try { await sbRpc('end_session', { p_token: s.token }); } catch (e) {} }
    _write(null);
  }

  // 페이지 로드시: #code 있으면 소비(→토큰, URL에서 제거), 그 뒤 토큰 검증. 세션 반환.
  async function initAuth() {
    try {
      var m = (location.hash || '').match(/[#&]code=([^&]+)/);
      if (m) {
        var code = decodeURIComponent(m[1]);
        try { history.replaceState(null, '', location.pathname + location.search); } catch (e) { location.hash = ''; }
        try { await loginWithCode(code); } catch (e) {}
      }
    } catch (e) {}
    return await whoami();
  }

  // 소유자 전용 동작 (매치 PK 는 id)
  async function deleteMatch(id) { var s = _read(); if (!s || !s.token) throw new Error('not logged in'); return sbRpc('delete_match', { p_token: s.token, p_match_id: id }); }
  async function setMyName(name) { var s = _read(); if (!s || !s.token) throw new Error('not logged in'); return sbRpc('set_my_name',  { p_token: s.token, p_name: name }); }

  window.EAuth = {
    sbRpc: sbRpc, session: session, puuid: puuid,
    loginWithCode: loginWithCode, whoami: whoami, logout: logout, initAuth: initAuth,
    deleteMatch: deleteMatch, setMyName: setMyName
  };
})();

/* ============================================================
 *  헤더 계정 UI — 모든 페이지 공통. encore-auth.js 만 넣으면 자동 동작.
 *   · 검색·"클라우드 연결됨" 칩 제거
 *   · 로그아웃: 오른쪽 끝 "로그인" 칩(클릭 시 안내 팝오버, 코드 입력 없음)
 *   · 로그인: "이름 ◆" 계정 칩(→ me.html) + 네비에 "나의 게임" 추가
 * ============================================================ */
(function () {
  function E(tag, attrs, html) {
    var e = document.createElement(tag);
    if (attrs) for (var k in attrs) { if (k === 'class') e.className = attrs[k]; else e.setAttribute(k, attrs[k]); }
    if (html != null) e.innerHTML = html;
    return e;
  }
  function esc(s){ return (s==null?'':String(s)).replace(/[&<>"]/g,function(c){return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]);}); }

  function popover(anchor) {
    var ex = document.getElementById('eauth-pop'); if (ex) { ex.remove(); return; }
    var p = E('div', { id: 'eauth-pop', 'class': 'eauth-pop' },
      '<h4>로그인</h4><p>ENCORE 레코더에서 <b>[갤러리 열기]</b>를 누르면 이 브라우저가 <b>자동으로 로그인</b>됩니다.<br><span class="dim">(녹화한 스타 이름이 그대로 계정이 됩니다.)</span></p><a class="eauth-dl" href="download.html">레코더 다운로드</a>');
    document.body.appendChild(p);
    var r = anchor.getBoundingClientRect();
    p.style.top = (r.bottom + window.scrollY + 8) + 'px';
    p.style.right = Math.max(12, (window.innerWidth - r.right)) + 'px';
    setTimeout(function () {
      document.addEventListener('click', function close(ev) {
        if (!p.contains(ev.target) && ev.target !== anchor) { p.remove(); document.removeEventListener('click', close); }
      });
    }, 0);
  }
  function addMyGamesNav() {
    var here = (location.pathname.split('/').pop() || '').toLowerCase() === 'me.html';
    var navs = document.querySelectorAll('.bar .nav, .bar .mnav');
    for (var i = 0; i < navs.length; i++) {
      if (navs[i].querySelector('[data-me]')) continue;
      var a = E('a', { href: 'me.html', 'data-me': '1' }, '나의 게임');
      if (here) a.className = 'on';
      navs[i].appendChild(a);
    }
  }
  function render(bar, me) {
    var old = bar.querySelector('.eauth-login, .eauth-acct'); if (old) old.remove();
    if (me && me.puuid) {
      var nm = me.name || me.puuid;
      var av = (String(nm).trim()[0] || '?').toUpperCase();
      var c = E('a', { 'class': 'eauth-acct', href: 'me.html' }, esc(nm) + '<span class="av">' + esc(av) + '</span>');
      bar.appendChild(c);
      addMyGamesNav();
    } else {
      var l = E('button', { 'class': 'eauth-login', type: 'button' }, '<span class="k">&#8594;]</span>로그인');
      l.onclick = function () { popover(l); };
      bar.appendChild(l);
    }
  }
  async function mount() {
    var bar = document.querySelector('.bar-in'); if (!bar) return;
    var rm = bar.querySelectorAll('.search, .live');
    for (var i = 0; i < rm.length; i++) rm[i].remove();
    if (!bar.querySelector('.sp')) bar.appendChild(E('span', { 'class': 'sp' }));
    var cached = EAuth.session();
    var cm = (cached && cached.puuid) ? cached : null;
    render(bar, cm);                         // 캐시된 세션으로 즉시 렌더 (whoami 왕복 대기·깜빡임 없음)
    window.__eauth_me = cm;
    var me = null;
    try { me = await EAuth.initAuth(); } catch (e) {}      // 배경에서 검증/갱신 + #code 소비
    var sig = function (x) { return (x && x.puuid) ? (x.puuid + '|' + (x.name || '') + '|' + (x.icon || '')) : ''; };
    if (sig(me) !== sig(cm)) render(bar, me);              // 신원이 실제로 바뀐 경우에만 다시 렌더
    window.__eauth_me = me || null;
    try { document.dispatchEvent(new CustomEvent('eauth:ready', { detail: me })); } catch (e) {}
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount); else mount();
})();
