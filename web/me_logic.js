/* ===== me.html — 나의 게임 / 내 프로필 ===== */
(function () {
  async function sbGet(p) { var r = await fetch(SB + "/rest/v1/" + p, { headers: H }); if (!r.ok) throw new Error(r.status); return r.json(); }
  function esc2(s) { return (s == null ? "" : String(s)).replace(/[&<>"]/g, function (c) { return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]); }); }
  var ESC = (typeof esc === "function") ? esc : esc2;
  var FD = (typeof fdate === "function") ? fdate : function (x) { return x ? String(x).slice(0, 16).replace("T", " ") : ""; };

  var root, me = null, games = [];

  function avChar(nm) { return (String(nm || "?").trim()[0] || "?").toUpperCase(); }

  function guardHTML() {
    return '<div class="meguard"><div class="phav">?</div>'
      + '<h2>로그인이 필요해요</h2>'
      + '<p>ENCORE 레코더에서 <b>[갤러리 열기]</b>를 누르면 이 브라우저가 자동으로 로그인됩니다.<br>(녹화한 스타 이름이 그대로 계정이 됩니다.)</p>'
      + '<a class="medl" href="download.html">레코더 다운로드</a></div>';
  }

  function heroHTML() {
    var nm = me.name || me.puuid || "계정";
    return '<div class="mehero"><div class="merow">'
      + '<div class="phav">' + ESC(avChar(nm)) + '</div>'
      + '<div><div class="pname">' + ESC(nm) + '</div>'
      + '<div class="psub"><span class="k">&#9670;</span> ENCORE 계정 · 내가 올린 경기 <b id="meCount">' + games.length + '</b></div></div>'
      + '<div class="meacts"><button class="mbtn" id="btnRename">표시 이름 변경</button>'
      + '<button class="mbtn warn" id="btnLogout">로그아웃</button></div>'
      + '</div></div>'
      + '<div class="sechead">내가 올린 경기 <small>삭제는 여기서만 — 본인 경기만 보입니다</small></div>'
      + '<div class="megrid" id="meGrid"></div>';
  }

  function cardHTML(g) {
    var n = (g.np / 2 | 0);
    var bg = g.thumb ? ' style="background-image:url(\'' + ESC(g.thumb) + '\')"' : '';
    return '<div class="mcard" data-id="' + ESC(g.id) + '">'
      + '<a class="mthumb" href="match.html?id=' + encodeURIComponent(g.id || "") + '"' + bg + '>'
      + '<span class="mmu">' + ESC(g.map || "경기") + '</span>'
      + (g.length ? '<span class="mdur">' + ESC(g.length) + '</span>' : '')
      + '</a><div class="mcbody">'
      + '<div class="mtags"><span class="mtag">' + n + 'v' + n + '</span>'
      + (g.matchup ? '<span class="mtag">' + ESC(g.matchup) + '</span>' : '') + '</div>'
      + '<div class="mcfoot"><span class="mm">&#9829; ' + (g.likes || 0) + '</span>'
      + '<span class="mm">&#128065; ' + (g.views || 0) + '</span>'
      + '<button class="mdel" data-id="' + ESC(g.id) + '">삭제</button></div>'
      + '<div class="mcdate">' + ESC(FD(g.uploaded)) + '</div></div></div>';
  }

  function renderGrid() {
    var grid = document.getElementById("meGrid"); if (!grid) return;
    if (!games.length) { grid.innerHTML = '<div class="meempty">아직 올린 경기가 없어요. 레코더로 한 판 녹화하면 여기에 쌓입니다.</div>'; return; }
    grid.innerHTML = games.map(cardHTML).join("");
  }

  function updateCount() { var c = document.getElementById("meCount"); if (c) c.textContent = games.length; }

  function wireHero() {
    var rn = document.getElementById("btnRename");
    if (rn) rn.onclick = async function () {
      var nm = prompt("표시 이름을 입력하세요", me.name || ""); if (nm == null) return; nm = nm.trim(); if (!nm) return;
      try { await EAuth.setMyName(nm); me.name = nm; document.querySelector(".mehero .pname").textContent = nm; }
      catch (e) { alert("이름 변경 실패: " + (e && e.message || e)); }
    };
    var lo = document.getElementById("btnLogout");
    if (lo) lo.onclick = async function () { try { await EAuth.logout(); } catch (e) {} location.href = "index.html"; };
    var grid = document.getElementById("meGrid");
    if (grid) grid.addEventListener("click", async function (e) {
      var b = e.target.closest(".mdel"); if (!b) return;
      var id = b.getAttribute("data-id");
      if (!confirm("이 경기를 삭제할까요? 되돌릴 수 없습니다.")) return;
      b.disabled = true; b.textContent = "삭제 중…";
      try {
        await EAuth.deleteMatch(id);
        var card = b.closest(".mcard"); if (card) card.remove();
        games = games.filter(function (g) { return String(g.id) !== String(id); });
        updateCount(); if (!games.length) renderGrid();
      } catch (e) { alert("삭제 실패: " + (e && e.message || e)); b.disabled = false; b.textContent = "삭제"; }
    });
  }

  async function boot(who) {
    root = document.getElementById("meRoot"); if (!root) return;
    me = who || null;
    if (!me || !me.puuid) { root.innerHTML = guardHTML(); return; }
    try { games = await sbGet("matches?select=*&owner_puuid=eq." + encodeURIComponent(me.puuid) + "&order=uploaded.desc&limit=300"); }
    catch (e) { games = []; }
    if (!Array.isArray(games)) games = [];
    root.innerHTML = heroHTML();
    renderGrid(); wireHero();
  }

  var booted = false;
  function once(w) { if (booted) return; booted = true; boot(w); }
  document.addEventListener("eauth:ready", function (ev) { once(ev.detail); });
  window.addEventListener("load", function () { if (!booted && typeof window.__eauth_me !== "undefined") once(window.__eauth_me); });
})();
