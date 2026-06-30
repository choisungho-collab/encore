-- ============================================================
--  ENCORE 로그인 / 소유권 — 이름 기반(B2-N)
--  계정 키 = 정규화된 스타 인게임 이름(saver). 같은 이름 = 같은 계정(자동).
--  ▷ 기본: 게임 PC에서 자동(녹화한 본인 이름으로 태그·로그인). 코드 입력 없음.
--  ▷ 예외: 폰/다른 브라우저(클라 없이) 또는 2번째 PC 삭제권한 → 레코더가 주는 링크/코드.
--  ▷ A안 안전: "이미 등록된 이름"에 새 기기가 자동 합류 못 함 → 사칭-삭제 차단.
--      · 업로드 = 어디서나 됨(owner_puuid = 내 이름). · 삭제 = 소유 비밀키만.
--
--  Supabase SQL Editor에 전체 붙여넣고 RUN(전부 idempotent). pgcrypto 필수.
--  ENCORE 자기 프로젝트(luljnalcnxfyxmlgoxbc)에서만.
-- ============================================================

create extension if not exists pgcrypto with schema extensions;

-- ----- 계정(신원): 키=정규화 이름(puuid), 표시이름/아이콘 보유 -----
create table if not exists identities (
  puuid    text primary key,        -- 정규화된 이름 = lower(btrim(name))
  name     text,                    -- 표시 이름(원본 대소문자). set_my_name 으로 변경 가능
  icon     int,
  created  timestamptz default now(),
  updated  timestamptz default now()
);

-- ----- 소유 비밀키: 해시 → 그 계정(이름)의 '삭제 권한'을 가진 기기 -----
create table if not exists device_secrets (
  secret_hash text primary key,        -- sha256(기기 비밀키)
  puuid       text not null,           -- 이 기기가 '소유'(삭제 가능)한 계정(이름)
  label       text,
  created     timestamptz default now()
);
create index if not exists device_secrets_puuid_idx on device_secrets(puuid);

-- ----- PC 연결 코드 / 웹 로그인 코드 / 세션 (6자리·10분·1회용) -----
create table if not exists link_codes  ( code text primary key, puuid text not null, created timestamptz default now(), used boolean default false );
create table if not exists login_codes ( code text primary key, puuid text not null, created timestamptz default now(), used boolean default false );
create table if not exists sessions    ( token text primary key, puuid text not null, created timestamptz default now(), seen timestamptz default now() );

-- ----- matches 소유자(=정규화 이름) -----
alter table matches add column if not exists owner_puuid text;
create index if not exists matches_owner_idx on matches(owner_puuid);

-- ----- 시그니처 바뀐 함수는 먼저 DROP (42P13 방지) -----
drop function if exists register_identity(text,text,text,int);
drop function if exists upload_replay(text,text,jsonb);
drop function if exists upload_replay(text,jsonb);
drop function if exists issue_link_code(text,text);
drop function if exists issue_login_code(text,text,text);
drop function if exists claim_identity(text,text,int);

-- ============================================================
--  RPC — 전부 security definer. 검증은 "sha256(비밀키) → device_secrets.puuid = 소유 계정".
-- ============================================================

-- 신원 확립(TOFU). 키=정규화 이름. 반환 {puuid, owned}.
--  · 이름 미등록 → 이 기기가 소유자로 등록(owned:true)
--  · 이 기기가 이미 소유 → owned:true (표시이름은 유지)
--  · 다른 기기가 이미 소유 → owned:false (자동 합류 안 함 = A안 안전). 링크로만 합류.
create or replace function claim_identity(p_name text, p_secret text, p_icon int default null)
returns jsonb language plpgsql security definer set search_path = public, extensions as $$
declare pu text; h text; i_own boolean; owned_by_other boolean;
begin
  if p_name is null or btrim(p_name) = '' or p_secret is null or length(p_secret) < 16 then
    raise exception 'bad identity args';
  end if;
  pu := lower(btrim(p_name));
  h  := encode(digest(p_secret, 'sha256'), 'hex');
  i_own := exists (select 1 from device_secrets where secret_hash = h and puuid = pu);
  if i_own then
    update identities set updated = now() where puuid = pu;
    return jsonb_build_object('puuid', pu, 'owned', true);
  end if;
  owned_by_other := exists (select 1 from device_secrets where puuid = pu);
  -- 표시이름 행은 항상 보장(없을 때만 생성 — 기존 표시이름/커스텀 닉 보존)
  insert into identities(puuid, name, icon) values (pu, p_name, p_icon)
    on conflict (puuid) do nothing;
  if owned_by_other then
    return jsonb_build_object('puuid', pu, 'owned', false);   -- 사칭/2번째PC → 삭제권한 없음
  end if;
  -- 미등록 이름 → 이 기기를 소유자로 (비밀키가 다른 이름을 갖고 있었다면 현재 이름으로 이동)
  insert into device_secrets(secret_hash, puuid) values (h, pu)
    on conflict (secret_hash) do update set puuid = pu;
  return jsonb_build_object('puuid', pu, 'owned', true);
end; $$;

-- 업로드: 소유자 = saver 이름(정규화). 어디서나 됨(이름으로 그룹). 비밀키는 형식만 확인.
create or replace function upload_replay(p_secret text, p_row jsonb)
returns text language plpgsql security definer set search_path = public, extensions as $$
declare gid text; own text;
begin
  if p_secret is null or length(p_secret) < 16 then raise exception 'unauthorized'; end if;
  gid := p_row->>'id';
  own := lower(btrim(coalesce(p_row->>'saver', p_row->>'owner_puuid', '')));
  if own = '' then own := null; end if;
  insert into matches
    select * from jsonb_populate_record(
      null::matches,
      jsonb_build_object('likes',0,'views',0) || p_row || jsonb_build_object('owner_puuid', own))
  on conflict (id) do update set
    uploader=excluded.uploader, uploaded=excluded.uploaded, video=excluded.video, thumb=excluded.thumb,
    replay=excluded.replay, video_size=excluded.video_size, map=excluded.map, matchup=excluded.matchup,
    length=excluded.length, length_sec=excluded.length_sec, type=excluded.type, winner=excluded.winner,
    saver=excluded.saver, np=excluded.np, players=excluded.players, won=excluded.won,
    analysis=excluded.analysis, owner_puuid=excluded.owner_puuid
  where matches.owner_puuid is null or matches.owner_puuid = excluded.owner_puuid;
  return gid;
end; $$;

-- PC 연결 코드 발급(소유 기기에서). 비밀키가 소유한 계정으로 6자리 발급.
create or replace function issue_link_code(p_secret text)
returns text language plpgsql security definer set search_path = public, extensions as $$
declare acct text; c text; tries int := 0;
begin
  select puuid into acct from device_secrets where secret_hash = encode(digest(p_secret, 'sha256'), 'hex');
  if acct is null then raise exception 'unauthorized'; end if;
  delete from link_codes where created < now() - interval '10 minutes';
  loop
    c := lpad((floor(random()*1000000))::int::text, 6, '0');
    exit when not exists (select 1 from link_codes where code = c);
    tries := tries + 1; if tries > 80 then raise exception 'code gen failed'; end if;
  end loop;
  insert into link_codes(code, puuid) values (c, acct);
  return c;
end; $$;

-- PC 연결 코드 사용(새 기기). 이 기기 비밀키를 대상 계정의 소유자로 등록 + 옛 업로드 이전.
create or replace function redeem_link_code(p_code text, p_new_secret text, p_old_puuid text default null)
returns text language plpgsql security definer set search_path = public, extensions as $$
declare tgt text; h text; cur_acct text;
begin
  select puuid into tgt from link_codes where code = p_code and used = false and created > now() - interval '10 minutes';
  if tgt is null then raise exception 'invalid or expired code'; end if;
  update link_codes set used = true where code = p_code;
  h := encode(digest(p_new_secret, 'sha256'), 'hex');
  select puuid into cur_acct from device_secrets where secret_hash = h;
  if cur_acct is not null and cur_acct <> tgt then
    update matches set owner_puuid = tgt where owner_puuid = cur_acct;
  end if;
  insert into device_secrets(secret_hash, puuid) values (h, tgt)
    on conflict (secret_hash) do update set puuid = tgt;
  return tgt;
end; $$;

-- 웹 로그인 코드 발급(갤러리 열기). 소유 기기만.
create or replace function issue_login_code(p_secret text, p_code text)
returns void language plpgsql security definer set search_path = public, extensions as $$
declare acct text;
begin
  select puuid into acct from device_secrets where secret_hash = encode(digest(p_secret, 'sha256'), 'hex');
  if acct is null then raise exception 'unauthorized'; end if;
  delete from login_codes where created < now() - interval '10 minutes';
  insert into login_codes(code, puuid) values (p_code, acct)
    on conflict (code) do update set puuid = excluded.puuid, created = now(), used = false;
end; $$;

-- 코드 → 토큰 교환(웹)
create or replace function exchange_login_code(p_code text)
returns jsonb language plpgsql security definer set search_path = public, extensions as $$
declare r record; tok text; nm text; ic int;
begin
  select * into r from login_codes where code = p_code and used = false and created > now() - interval '10 minutes';
  if not found then raise exception 'invalid or expired code'; end if;
  update login_codes set used = true where code = p_code;
  tok := encode(gen_random_bytes(24), 'hex');
  insert into sessions(token, puuid) values (tok, r.puuid);
  select name, icon into nm, ic from identities where puuid = r.puuid;
  return jsonb_build_object('token', tok, 'puuid', r.puuid, 'name', nm, 'icon', ic);
end; $$;

-- 토큰 검증(매 페이지)
create or replace function session_whoami(p_token text)
returns jsonb language plpgsql security definer set search_path = public as $$
declare r record; nm text; ic int;
begin
  select * into r from sessions where token = p_token;
  if not found then return null; end if;
  update sessions set seen = now() where token = p_token;
  select name, icon into nm, ic from identities where puuid = r.puuid;
  return jsonb_build_object('puuid', r.puuid, 'name', nm, 'icon', ic);
end; $$;

create or replace function end_session(p_token text)
returns void language sql security definer set search_path = public as $$
  delete from sessions where token = p_token;
$$;

-- 소유자만 삭제 (matches PK = id, owner_puuid = 내 이름)
create or replace function delete_match(p_token text, p_match_id text)
returns void language plpgsql security definer set search_path = public as $$
declare pu text;
begin
  select puuid into pu from sessions where token = p_token;
  if pu is null then raise exception 'not logged in'; end if;
  delete from matches where id = p_match_id and owner_puuid = pu;
end; $$;

-- 표시 이름만 변경(키 puuid 는 불변)
create or replace function set_my_name(p_token text, p_name text)
returns void language plpgsql security definer set search_path = public as $$
declare pu text;
begin
  select puuid into pu from sessions where token = p_token;
  if pu is null then raise exception 'not logged in'; end if;
  update identities set name = p_name, updated = now() where puuid = pu;
end; $$;

-- ============================================================
--  RLS
-- ============================================================
alter table identities     enable row level security;   -- 정책 0개 = anon 직접접근 차단
alter table device_secrets enable row level security;
alter table link_codes     enable row level security;
alter table login_codes    enable row level security;
alter table sessions       enable row level security;

alter table matches enable row level security;
drop policy if exists m_sel on matches;
create policy m_sel on matches for select using (true);
drop policy if exists m_ins on matches;
create policy m_ins on matches for insert to anon, authenticated with check (owner_puuid is null);

grant select, insert on matches to anon, authenticated;
grant execute on function
  claim_identity(text,text,int), upload_replay(text,jsonb),
  issue_link_code(text), redeem_link_code(text,text,text),
  issue_login_code(text,text), exchange_login_code(text),
  session_whoami(text), end_session(text), delete_match(text,text), set_my_name(text,text)
  to anon, authenticated;
