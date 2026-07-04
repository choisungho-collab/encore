-- ============================================================
--  ENCORE 관리자 콘솔 — encore-admin.sql  (아이디/비밀번호 로그인)
--  Supabase 대시보드 → SQL Editor 에 붙여넣고 Run 한 번.
--  · 일반 사용자 로그인(레코더 방식)과 완전히 분리된 관리자 전용 인증입니다.
--  · 레코더 없이 아무 브라우저/폰에서나 admin.html 에서 로그인할 수 있습니다.
--  · 여러 번 실행해도 안전(idempotent).
--
--  ★★★ 실행 전 아래 [1] 의 비밀번호를 원하는 값으로 바꾸세요. ★★★
--      실행 후에는 DB 에 bcrypt 해시만 남습니다(평문 저장 안 함).
--      이 SQL 파일은 로컬에만 보관하거나, 실행 후 비밀번호 부분을 지워 두세요.
-- ============================================================

create extension if not exists pgcrypto with schema extensions;

-- ── 관리자 계정 테이블 (RLS 정책 0개 = anon 직접접근 전면 차단) ──
create table if not exists public.admin_accounts (
  username    text primary key,
  pw_hash     text not null,
  token       text,
  token_seen  timestamptz,
  created     timestamptz default now()
);
create unique index if not exists admin_accounts_token_idx
  on public.admin_accounts (token) where token is not null;
alter table public.admin_accounts enable row level security;

-- ── [1] 최초 관리자 계정 ─────────────────────────────────────
--  아이디는 'veatbox', 비밀번호는 아래 'CHANGE_ME_비밀번호' 를 바꾸세요.
--  이미 같은 아이디가 있으면 건드리지 않습니다(비번 변경은 아래 [2] 참고).
insert into public.admin_accounts (username, pw_hash)
values ('veatbox', extensions.crypt('CHANGE_ME_비밀번호', extensions.gen_salt('bf')))
on conflict (username) do nothing;

-- ── [2] (선택) 이미 만든 계정의 비밀번호를 바꾸려면, 아래 두 줄의
--        주석(--)을 풀고 새 비밀번호로 바꿔 Run 하세요.
-- update public.admin_accounts
--   set pw_hash = extensions.crypt('새_비밀번호', extensions.gen_salt('bf')) where username = 'veatbox';

-- ── 로그인: 아이디+비밀번호 → 세션 토큰 발급. 실패 시 null. ──
create or replace function public.admin_login(p_user text, p_pw text)
returns jsonb language plpgsql security definer set search_path = public, extensions as $$
declare a record; tok text;
begin
  select * into a from admin_accounts where username = lower(p_user);
  if not found then return null; end if;
  if crypt(p_pw, a.pw_hash) <> a.pw_hash then return null; end if;   -- 비번 불일치
  tok := encode(gen_random_bytes(24), 'hex');
  update admin_accounts set token = tok, token_seen = now() where username = a.username;
  return jsonb_build_object('token', tok, 'username', a.username);
end; $$;

-- ── 토큰 검증 (admin.html 진입/새로고침 시) ──
create or replace function public.admin_whoami(p_token text)
returns jsonb language plpgsql security definer set search_path = public as $$
declare a record;
begin
  if p_token is null or p_token = '' then return null; end if;
  select * into a from admin_accounts where token = p_token;
  if not found then return null; end if;
  update admin_accounts set token_seen = now() where username = a.username;
  return jsonb_build_object('username', a.username, 'is_admin', true);
end; $$;

-- ── 로그아웃 ──
create or replace function public.admin_logout(p_token text)
returns void language sql security definer set search_path = public as $$
  update admin_accounts set token = null where token = p_token;
$$;

-- ── 비밀번호 변경 (콘솔에서, 현재 비번 확인 후) ──
create or replace function public.admin_set_password(p_token text, p_old text, p_new text)
returns boolean language plpgsql security definer set search_path = public, extensions as $$
declare a record;
begin
  select * into a from admin_accounts where token = p_token;
  if not found then return false; end if;
  if crypt(p_old, a.pw_hash) <> a.pw_hash then return false; end if;
  update admin_accounts set pw_hash = crypt(p_new, gen_salt('bf')) where username = a.username;
  return true;
end; $$;

-- ── 삭제: 유효한 관리자 토큰이면 소유자 무관 삭제. 반환=삭제된 행 수. ──
--    comments 는 FK on delete cascade 로 함께 삭제. 스토리지 파일은 레코더 주기 청소가 회수.
create or replace function public.admin_delete_matches(p_token text, p_ids text[])
returns int language plpgsql security definer set search_path = public as $$
declare a record; n int;
begin
  select * into a from admin_accounts where token = p_token;
  if not found then raise exception 'not admin'; end if;
  delete from matches where id = any(p_ids);
  get diagnostics n = row_count;
  return n;
end; $$;

grant execute on function
  public.admin_login(text, text),
  public.admin_whoami(text),
  public.admin_logout(text),
  public.admin_set_password(text, text, text),
  public.admin_delete_matches(text, text[])
  to anon, authenticated;

-- ── 확인용 — Run 후 이 줄에 아이디 1개(veatbox)가 보이면 정상 ──
select username, (token is not null) as logged_in, created from public.admin_accounts;
