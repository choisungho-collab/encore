-- ════════════════════════════════════════════════════════════════════
-- 01_identity.sql — ENCORE 사용자 신원/세션 (레코더 발급코드 → 브라우저 자동로그인)
--   Supabase → SQL Editor 에 붙여넣고 Run. 여러 번 실행해도 안전(idempotent).
--   레코더(claim_identity/issue_login_code)와 웹(exchange_login_code/session_whoami/
--   end_session/set_my_name/delete_match)이 호출하는 RPC 를 이 파일이 정의한다.
--   ★ ENCORE 레포에 원래 없던 계층 — 이걸로 실서비스 DB 를 소스로 재현 가능해짐.
--
--   ⚠ 이미 라이브 DB 에 identities/sessions 계열이 '다른 컬럼명'으로 존재한다면,
--      이 파일을 그대로 돌리기 전에 컬럼을 대조하세요(README STEP 3 주의 참고).
--      새로 시작하는 경우엔 이 파일이 완결형입니다.
-- ════════════════════════════════════════════════════════════════════

create extension if not exists pgcrypto with schema extensions;

-- ── 테이블 ───────────────────────────────────────────────────────────
create table if not exists public.identities (
  puuid          text primary key,               -- = lower(name) (레코더 규칙과 동일)
  name           text,
  icon           text,
  device_secrets text[] not null default '{}',   -- 기기 비밀키의 sha256 hex 해시 배열(멀티기기)
  created        timestamptz default now()
);
create table if not exists public.login_codes (
  code    text primary key,
  puuid   text references public.identities(puuid) on delete cascade,
  created timestamptz default now()
);
create table if not exists public.sessions (
  token   text primary key,
  puuid   text references public.identities(puuid) on delete cascade,
  created timestamptz default now(),
  seen    timestamptz default now()
);
create index if not exists idx_sessions_puuid on public.sessions(puuid);

-- RLS on, 정책 0개 = anon/authenticated 직접접근 차단. 아래 security definer 함수로만.
alter table public.identities  enable row level security;
alter table public.login_codes enable row level security;
alter table public.sessions    enable row level security;

-- ── 기기 등록/바인딩 (레코더가 판 저장 시 호출, 멱등) ─────────────────
create or replace function public.claim_identity(p_name text, p_secret text)
returns jsonb language plpgsql security definer set search_path = public, extensions as $$
declare nm text; pu text; h text;
begin
  nm := btrim(coalesce(p_name,''));
  if nm = '' or coalesce(p_secret,'') = '' or length(p_secret) < 16 then return null; end if;
  pu := lower(nm);
  h  := encode(digest(p_secret, 'sha256'), 'hex');
  insert into identities(puuid, name) values (pu, nm)
    on conflict (puuid) do update set name = excluded.name;
  update identities set device_secrets = array_append(device_secrets, h)
    where puuid = pu and not (h = any(device_secrets));
  return jsonb_build_object('puuid', pu);
end; $$;

-- ── 기기 비밀키 검증 (Netlify 서명 프록시 storage.js 가 service_key 로 호출) ──
create or replace function public.verify_device(p_puuid text, p_secret text)
returns boolean language plpgsql security definer set search_path = public, extensions as $$
declare h text; ok boolean;
begin
  if p_puuid is null or p_secret is null or length(p_secret) < 16 then return false; end if;
  h := encode(digest(p_secret, 'sha256'), 'hex');
  select (h = any(device_secrets)) into ok from identities where puuid = p_puuid;
  return coalesce(ok, false);
end; $$;

-- ── 1회용 로그인 코드 발급 (레코더가 자기 코드 문자열 전달) ────────────
create or replace function public.issue_login_code(p_secret text, p_code text)
returns void language plpgsql security definer set search_path = public, extensions as $$
declare pu text; h text;
begin
  if coalesce(p_secret,'') = '' or coalesce(p_code,'') = '' then return; end if;
  h := encode(digest(p_secret, 'sha256'), 'hex');
  select puuid into pu from identities where h = any(device_secrets) limit 1;
  if pu is null then return; end if;
  delete from login_codes where created < now() - interval '30 minutes';   -- 만료 코드 정리
  insert into login_codes(code, puuid) values (p_code, pu)
    on conflict (code) do update set puuid = excluded.puuid, created = now();
end; $$;

-- ── 코드 교환 → 세션 발급 (브라우저: #code=... 소비) ──────────────────
create or replace function public.exchange_login_code(p_code text)
returns jsonb language plpgsql security definer set search_path = public, extensions as $$
declare pu text; nm text; ic text; tok text;
begin
  if coalesce(p_code,'') = '' then return null; end if;
  select puuid into pu from login_codes where code = p_code and created > now() - interval '30 minutes';
  if pu is null then return null; end if;
  delete from login_codes where code = p_code;                  -- 1회용 소비
  select name, icon into nm, ic from identities where puuid = pu;
  tok := encode(gen_random_bytes(24), 'hex');
  insert into sessions(token, puuid) values (tok, pu);
  return jsonb_build_object('token', tok, 'puuid', pu, 'name', nm, 'icon', ic);
end; $$;

-- ── 세션 확인 ────────────────────────────────────────────────────────
create or replace function public.session_whoami(p_token text)
returns jsonb language plpgsql security definer set search_path = public as $$
declare pu text; nm text; ic text;
begin
  if coalesce(p_token,'') = '' then return null; end if;
  select puuid into pu from sessions where token = p_token;
  if pu is null then return null; end if;
  update sessions set seen = now() where token = p_token;
  select name, icon into nm, ic from identities where puuid = pu;
  return jsonb_build_object('puuid', pu, 'name', nm, 'icon', ic);
end; $$;

-- ── 로그아웃 ─────────────────────────────────────────────────────────
create or replace function public.end_session(p_token text)
returns void language sql security definer set search_path = public as $$
  delete from sessions where token = p_token;
$$;

-- ── 이름 변경 (본인) ─────────────────────────────────────────────────
create or replace function public.set_my_name(p_token text, p_name text)
returns jsonb language plpgsql security definer set search_path = public as $$
declare pu text; nm text;
begin
  select puuid into pu from sessions where token = p_token;
  if pu is null then return null; end if;
  nm := btrim(coalesce(p_name,''));
  if nm = '' or length(nm) > 40 then return null; end if;
  update identities set name = nm where puuid = pu;
  return jsonb_build_object('puuid', pu, 'name', nm);
end; $$;

grant execute on function
  public.claim_identity(text, text),
  public.verify_device(text, text),
  public.issue_login_code(text, text),
  public.exchange_login_code(text),
  public.session_whoami(text),
  public.end_session(text),
  public.set_my_name(text, text)
  to anon, authenticated;

-- 확인용: select verify_device('없는사람','1234567890abcdef');  → false 여야 정상
