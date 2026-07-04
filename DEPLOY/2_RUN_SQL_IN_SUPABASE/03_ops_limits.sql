-- ════════════════════════════════════════════════════════════════════
-- 03_ops_limits.sql — 운영 보호장치 (기기별 업로드 쿼터 + 에러 로그)
--   Supabase → SQL Editor 에서 Run. 여러 번 실행해도 안전. 기존 것 안 건드리고 새 것만 추가.
--   storage.js 가 서명 발급 '전에' check_upload_quota / log_error 를 호출한다.
--
--   기본 한도: 시간당 12회 · 하루 200회 · 하루 20GB · 파일당 6GB
--   (숫자는 아래 함수 상단에서 조정)
-- ════════════════════════════════════════════════════════════════════

-- ── 업로드 이벤트 (rate limit 계산용) ────────────────────────────────
create table if not exists public.upload_events (
  id         bigint generated always as identity primary key,
  puuid      text not null,
  bytes      bigint not null default 0,
  created_at timestamptz not null default now()
);
create index if not exists idx_upload_events_puuid_time
  on public.upload_events (puuid, created_at desc);

-- ── 에러 로그 (모니터링, 관리자에서 조회) ────────────────────────────
create table if not exists public.error_log (
  id         bigint generated always as identity primary key,
  source     text,
  message    text,
  meta       jsonb,
  created_at timestamptz not null default now()
);
create index if not exists idx_error_log_time on public.error_log (created_at desc);

-- ── 업로드 쿼터 검사 (통과 시 이벤트를 같은 트랜잭션에 기록) ──────────
create or replace function public.check_upload_quota(p_puuid text, p_bytes bigint default 0)
returns jsonb language plpgsql security definer set search_path = public as $$
declare
  max_per_hour  int    := 12;
  max_per_day   int    := 200;
  max_bytes_day bigint := 20000000000;   -- 20 GB / day
  max_bytes_one bigint := 6000000000;    -- 6 GB / file
  n_hour int; n_day int; b_day bigint;
begin
  if p_puuid is null or length(p_puuid) < 1 then
    return jsonb_build_object('ok', false, 'reason', 'bad puuid');
  end if;
  if coalesce(p_bytes,0) > max_bytes_one then
    return jsonb_build_object('ok', false, 'reason', 'file too large');
  end if;

  select count(*) into n_hour from upload_events
    where puuid = p_puuid and created_at > now() - interval '1 hour';
  select count(*), coalesce(sum(bytes),0) into n_day, b_day from upload_events
    where puuid = p_puuid and created_at > now() - interval '24 hours';

  if n_hour >= max_per_hour then
    return jsonb_build_object('ok', false, 'reason', 'hourly limit', 'used_hour', n_hour);
  end if;
  if n_day >= max_per_day then
    return jsonb_build_object('ok', false, 'reason', 'daily limit', 'used_day', n_day);
  end if;
  if b_day + coalesce(p_bytes,0) > max_bytes_day then
    return jsonb_build_object('ok', false, 'reason', 'daily bytes limit', 'used_bytes_day', b_day);
  end if;

  insert into upload_events(puuid, bytes) values (p_puuid, coalesce(p_bytes,0));
  return jsonb_build_object('ok', true, 'reason', 'ok',
    'used_hour', n_hour + 1, 'used_bytes_day', b_day + coalesce(p_bytes,0));
end; $$;

-- ── 에러 기록 (Netlify Functions 가 호출, 30일 자동 정리) ─────────────
create or replace function public.log_error(p_source text, p_message text, p_meta jsonb default '{}'::jsonb)
returns void language plpgsql security definer set search_path = public as $$
begin
  insert into error_log(source, message, meta)
  values (left(coalesce(p_source,'?'),40), left(coalesce(p_message,''),500), coalesce(p_meta,'{}'::jsonb));
  delete from error_log where created_at < now() - interval '30 days';
end; $$;

-- ── 오래된 업로드 이벤트 정리 (수동/크론) ────────────────────────────
create or replace function public.prune_upload_events()
returns void language plpgsql security definer set search_path = public as $$
begin
  delete from upload_events where created_at < now() - interval '2 days';
end; $$;

-- ── RLS: 이 테이블들은 서버(service_role)만. anon/authenticated 차단(정책 0개) ──
alter table public.upload_events enable row level security;
alter table public.error_log     enable row level security;

-- check_upload_quota / log_error 는 storage.js 가 service_key 로 호출 → 별도 grant 불필요.
-- (직접 anon 호출을 막고 싶으면 아래 주석 해제)
-- revoke execute on function public.check_upload_quota(text,bigint) from public;
-- revoke execute on function public.log_error(text,text,jsonb) from public;
