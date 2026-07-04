/* ENCORE 자유게시판 — 읽기 공개, 작성/수정/삭제는 로그인 본인만(EAuth 세션 토큰) */
(function () {
  async function sbGet(p) { var r = await fetch(SB + "/rest/v1/" + p, { headers: H }); if (!r.ok) throw new Error(r.status); return r.json(); }
  function esc(s){ return (s==null?'':String(s)).replace(/[&<>"]/g,function(c){return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]);}); }
  function nl2(s){ return esc(s).replace(/\n/g,'<br>'); }
  function rel(iso){
    if(!iso) return '';
    var t=new Date(iso).getTime(); if(isNaN(t)) return '';
    var d=(Date.now()-t)/1000;
    if(d<60) return '방금 전';
    if(d<3600) return Math.floor(d/60)+'분 전';
    if(d<86400) return Math.floor(d/3600)+'시간 전';
    if(d<172800) return '어제';
    var x=new Date(iso), p=function(n){return (n<10?'0':'')+n;};
    return (x.getMonth()+1)+'.'+p(x.getDate());
  }
  function token(){ var s=EAuth.session(); return s && s.token; }
  function avChar(nm){ return (String(nm||'?').trim()[0]||'?').toUpperCase(); }

  var root, me=null, posts=[];

  /* ── 목록 ── */
  function listHTML(){
    var canWrite=!!me;
    var tb='<div class="bd-tb"><span class="bd-cnt">전체 <b>'+posts.length+'</b></span>'
      + (canWrite
          ? '<button class="bd-write" id="bdWrite">＋ 글쓰기</button>'
          : '<span class="bd-guest"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>글을 쓰려면 <a href="manual.html" class="bd-lk">레코더에서 로그인</a></span>')
      + '</div>';
    var compose=canWrite ? '<div class="bd-form" id="bdForm" hidden>'
      + '<div class="bd-ft">새 글</div>'
      + '<input id="bdTitle" class="bd-in" maxlength="200" placeholder="제목">'
      + '<textarea id="bdBody" class="bd-ta" placeholder="내용을 입력하세요"></textarea>'
      + '<div class="bd-row"><button class="bd-g" id="bdCancel">취소</button><button class="bd-a" id="bdSubmit">등록</button></div>'
      + '</div>' : '';
    var list=posts.length ? posts.map(postCardHTML).join('')
      : '<div class="bd-empty">아직 글이 없어요'+(canWrite?' — 첫 글을 남겨보세요.':'.')+'</div>';
    return tb + compose + '<div class="bd-list">'+list+'</div>';
  }
  function postCardHTML(p){
    var mine=me && String(p.author_puuid)===String(me.puuid);
    return '<div class="bd-post" data-id="'+esc(p.id)+'">'
      + '<div class="bd-pt">'+esc(p.title)+'</div>'
      + '<div class="bd-meta"><span class="bd-who"><i></i>'+esc(p.author_name)+'</span>'
      +   '<span class="bd-dot">·</span><span>'+rel(p.created)+'</span>'
      +   (mine?'<span class="bd-badge">내 글</span>':'')+'</div>'
      + '<div class="bd-body2">'+esc(p.body)+'</div>'
      + '<div class="bd-pfoot"><span class="bd-stat">조회 '+(p.views||0)+'</span></div>'
      + '</div>';
  }

  /* ── 상세 + 댓글 ── */
  async function openDetail(id, doBump){
    var p=posts.find(function(x){return String(x.id)===String(id);});
    if(!p) { render(); return; }
    if(doBump){ try{ await EAuth.sbRpc('bump_post_view',{p_post_id:p.id}); p.views=(p.views||0)+1; }catch(e){} }
    var comments=[];
    try{ comments=await sbGet('post_comments?select=*&post_id=eq.'+encodeURIComponent(p.id)+'&order=created.asc'); }catch(e){ comments=[]; }
    root.innerHTML=detailHTML(p,comments);
    wireDetail(p);
    window.scrollTo(0,0);
  }
  function detailHTML(p,comments){
    var mine=me && String(p.author_puuid)===String(me.puuid);
    var edited=p.updated && p.created && (new Date(p.updated)-new Date(p.created)>1500);
    var head='<button class="bd-back" id="bdBack">← 목록</button>'
      + '<article class="bd-detail">'
      + '<h1 class="bd-dt">'+esc(p.title)+'</h1>'
      + '<div class="bd-meta"><span class="bd-who"><span class="bd-av">'+avChar(p.author_name)+'</span>'+esc(p.author_name)+'</span>'
      +   '<span class="bd-dot">·</span><span>'+rel(p.created)+(edited?' · 수정됨':'')+'</span>'
      +   '<span class="bd-dot">·</span><span>조회 '+(p.views||0)+'</span>'
      +   (mine?'<span class="bd-pact"><button class="bd-g sm" id="bdEdit">수정</button><button class="bd-g sm del" id="bdDel">삭제</button></span>':'')+'</div>'
      + '<div class="bd-dbody">'+nl2(p.body)+'</div>'
      + '</article>';
    var clist=comments.length ? comments.map(commentHTML).join('') : '<div class="bd-noc">아직 댓글이 없어요.</div>';
    var cform=me ? '<div class="bd-cform"><textarea id="bdCmtBody" class="bd-cta" placeholder="댓글 달기"></textarea><button class="bd-a" id="bdCmtSubmit">등록</button></div>'
      : '<div class="bd-cguest">댓글을 쓰려면 <a href="manual.html" class="bd-lk">레코더에서 로그인</a></div>';
    return head + '<section class="bd-cmts"><div class="bd-ch">댓글 <b>'+comments.length+'</b></div>'+cform+'<div class="bd-clist">'+clist+'</div></section>';
  }
  function commentHTML(c){
    var mine=me && String(c.author_puuid)===String(me.puuid);
    return '<div class="bd-cmt">'
      + '<div class="bd-cmeta"><span class="bd-who sm"><i></i>'+esc(c.author_name)+'</span><span class="bd-dot">·</span><span>'+rel(c.created)+'</span>'
      +   (mine?'<button class="bd-cdel" data-cid="'+esc(c.id)+'">삭제</button>':'')+'</div>'
      + '<div class="bd-cbody">'+nl2(c.body)+'</div></div>';
  }

  /* ── 이벤트 ── */
  function wireList(){
    var w=document.getElementById('bdWrite'), f=document.getElementById('bdForm');
    if(w) w.onclick=function(){ if(f){ f.hidden=!f.hidden; if(!f.hidden){var t=document.getElementById('bdTitle'); if(t)t.focus();} } };
    var cancel=document.getElementById('bdCancel'); if(cancel) cancel.onclick=function(){ if(f)f.hidden=true; };
    var submit=document.getElementById('bdSubmit');
    if(submit) submit.onclick=async function(){
      var t=(document.getElementById('bdTitle').value||'').trim(), b=(document.getElementById('bdBody').value||'').trim();
      if(!t||!b){ alert('제목과 내용을 입력하세요.'); return; }
      submit.disabled=true;
      try{ await EAuth.sbRpc('create_post',{p_token:token(),p_title:t,p_body:b}); await reload(); }
      catch(e){ alert('등록 실패: '+(e&&e.message||e)); submit.disabled=false; }
    };
    var list=root.querySelector('.bd-list');
    if(list) list.addEventListener('click', function(e){
      var card=e.target.closest('.bd-post'); if(!card) return;
      openDetail(card.getAttribute('data-id'), true);
    });
  }
  function wireDetail(p){
    var back=document.getElementById('bdBack'); if(back) back.onclick=function(){ render(); window.scrollTo(0,0); };
    var del=document.getElementById('bdDel');
    if(del) del.onclick=async function(){
      if(!confirm('이 글을 삭제할까요? 댓글도 함께 지워집니다.')) return;
      try{ await EAuth.sbRpc('delete_post',{p_token:token(),p_post_id:p.id}); await reload(); }
      catch(e){ alert('삭제 실패: '+(e&&e.message||e)); }
    };
    var edit=document.getElementById('bdEdit'); if(edit) edit.onclick=function(){ openEdit(p); };
    var cs=document.getElementById('bdCmtSubmit');
    if(cs) cs.onclick=async function(){
      var b=(document.getElementById('bdCmtBody').value||'').trim(); if(!b) return;
      cs.disabled=true;
      try{ await EAuth.sbRpc('create_post_comment',{p_token:token(),p_post_id:p.id,p_body:b}); await openDetail(p.id); }
      catch(e){ alert('댓글 실패: '+(e&&e.message||e)); cs.disabled=false; }
    };
    var clist=root.querySelector('.bd-clist');
    if(clist) clist.addEventListener('click', async function(e){
      var db=e.target.closest('.bd-cdel'); if(!db) return;
      if(!confirm('댓글을 삭제할까요?')) return;
      try{ await EAuth.sbRpc('delete_post_comment',{p_token:token(),p_comment_id:db.getAttribute('data-cid')}); await openDetail(p.id); }
      catch(e2){ alert('삭제 실패'); }
    });
  }
  function openEdit(p){
    root.innerHTML='<button class="bd-back" id="bdBack2">← 취소</button>'
      + '<div class="bd-form open"><div class="bd-ft">글 수정</div>'
      + '<input id="edTitle" class="bd-in" maxlength="200" value="'+esc(p.title)+'">'
      + '<textarea id="edBody" class="bd-ta">'+esc(p.body)+'</textarea>'
      + '<div class="bd-row"><button class="bd-g" id="edCancel">취소</button><button class="bd-a" id="edSave">저장</button></div></div>';
    document.getElementById('bdBack2').onclick=function(){ openDetail(p.id); };
    document.getElementById('edCancel').onclick=function(){ openDetail(p.id); };
    document.getElementById('edSave').onclick=async function(){
      var t=(document.getElementById('edTitle').value||'').trim(), b=(document.getElementById('edBody').value||'').trim();
      if(!t||!b){ alert('제목과 내용을 입력하세요.'); return; }
      try{
        await EAuth.sbRpc('update_post',{p_token:token(),p_post_id:p.id,p_title:t,p_body:b});
        var i=posts.findIndex(function(x){return String(x.id)===String(p.id);});
        if(i>=0){ posts[i].title=t; posts[i].body=b; posts[i].updated=new Date().toISOString(); p=posts[i]; }
        await openDetail(p.id);
      }catch(e){ alert('수정 실패: '+(e&&e.message||e)); }
    };
  }

  /* ── 렌더/로드/부트 ── */
  function render(){ if(!root) return; root.innerHTML=listHTML(); wireList(); }
  async function reload(){ try{ posts=await sbGet('posts?select=*&order=created.desc&limit=200'); }catch(e){ posts=[]; } render(); }
  async function boot(who){ me=who||null; root=document.getElementById('boardRoot'); if(!root) return; await reload(); }

  var booted=false;
  function once(w){ if(booted) return; booted=true; boot(w); }
  document.addEventListener('eauth:ready', function(ev){ once(ev.detail); });
  window.addEventListener('load', function(){ if(!booted && typeof window.__eauth_me!=='undefined') once(window.__eauth_me); });
})();
