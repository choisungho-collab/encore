-- ════════════════════════════════════════════════════════════════════
-- 02_security.sql — RLS 하드닝 + 매치 등록 RPC(소유행 보호) + 삭제(스토리지 정리)
--   Supabase → SQL Editor 에서 Run. 여러 번 실행해도 안전.
--
-- ★ 실행 순서 (중요): 이 SQL '전에' 반드시
--     1) Netlify 환경변수(SUPABASE_URL / SUPABASE_SERVICE_KEY / SUPABASE_BUCKET) 등록
--     2) netlify/functions/storage.js 배포(push)
--     3) 서명 업로드 지원되는 새 레코더(sc_recorder) 배포
--   이 SQL 이 anon 직접 insert/업로드를 차단하므로, 순서 어기면 구버전 레코더 업로드가 즉시 막힘.
-- ════════════════════════════════════════════════════════════════════

-- ── matches 소유/그룹 컬럼 보강 (없으면 추가) ────────────────────────
alter table public.matches add column if not exists owner_puuid text;
alter table public.matches add column if not exists preview     text;
alter table public.matches add column if not exists group_key   text;
create index if not exists matches_owner_idx on public.matches(owner_puuid);

drop function if exists public.upload_match(text, text, jsonb);
drop function if exists public.upload_match_anon(jsonb);
drop function if exists public.delete_match(text, text);
drop function if exists public._ingest_match(jsonb, text);

-- ── 공통 검증 + upsert (내부 전용) ───────────────────────────────────
--   소유행 보호: 남이 소유(owner_puuid)한 행은 익명/타인이 절대 덮어쓰지 못함.
create or replace function public._ingest_match(p_row jsonb, p_owner text)
returns text language plpgsql security definer set search_path = public as $$
begin
  if p_row is null or length(p_row::text) > 400000 then raise exception 'row too large'; end if;
  if coalesce(p_row->>'id','') !~ '^[A-Za-z0-9._-]{8,140}$' then raise exception 'bad id'; end if;
  if coalesce(p_row->>'video','') not like 'http%' then raise exception 'bad video url'; end if;
  if jsonb_typeof(coalesce(p_row->'players','[]'::jsonb)) is distinct from 'array'
     or jsonb_array_length(coalesce(p_row->'players','[]'::jsonb)) > 12 then raise exception 'bad players'; end if;

  insert into matches(
    id, uploader, uploaded, video, thumb, replay, preview, video_size,
    map, matchup, length, length_sec, type, winner, saver, np,
    players, won, analysis, group_key, owner_puuid)
  values(
    p_row->>'id', p_row->>'uploader',
    coalesce(nullif(p_row->>'uploaded','')::timestamptz, now()),
    p_row->>'video', p_row->>'thumb', p_row->>'replay', p_row->>'preview',
    nullif(p_row->>'video_size','')::bigint,
    p_row->>'map', p_row->>'matchup', p_row->>'length',
    nullif(p_row->>'length_sec','')::int, p_row->>'type',
    nullif(p_row->>'winner','')::int, p_row->>'saver',
    nullif(p_row->>'np','')::int,
    coalesce(p_row->'players','[]'::jsonb),
    nullif(p_row->>'won','')::boolean,
    p_row->'analysis', p_row->>'group_key', p_owner)
  on conflict (id) do update set
    video=excluded.video, thumb=excluded.thumb, replay=excluded.replay, preview=excluded.preview,
    players=excluded.players, analysis=excluded.analysis, won=excluded.won,
    video_size=excluded.video_size, uploaded=excluded.uploaded,
    length=excluded.length, length_sec=excluded.length_sec, winner=excluded.winner,
    map=excluded.map, matchup=excluded.matchup, np=excluded.np, saver=excluded.saver
  where matches.owner_puuid is null or matches.owner_puuid = p_owner;   -- 남의 소유 행은 못 덮음
  return p_row->>'id';
end; $$;
revoke execute on function public._ingest_match(jsonb, text) from public;   -- 직접 호출 차단

-- ── 소유 등록: 기기 검증 통과 시 owner 지정 (레코더 기본 경로) ────────
create or replace function public.upload_match(p_puuid text, p_secret text, p_row jsonb)
returns text language plpgsql security definer set search_path = public as $$
begin
  if not verify_device(p_puuid, p_secret) then raise exception 'unauthorized device'; end if;
  return _ingest_match(p_row, p_puuid);
end; $$;

-- ── 익명 폴백: owner 없음. (신원 미확립 첫 판 등) 소유행은 위 where 로 보호됨 ──
create or replace function public.upload_match_anon(p_row jsonb)
returns text language plpgsql security definer set search_path = public as $$
begin
  return _ingest_match(p_row, null);
end; $$;

-- ── matches 직접 insert 정책 제거 (있으면). 이후 등록은 위 RPC 로만 ──
drop policy if exists "matches insert" on public.matches;
drop policy if exists m_ins on public.matches;

-- ── Storage: anon 직접 업로드/수정 금지, 읽기만 공개 ─────────────────
--   업로드는 Netlify 서명 프록시(storage.js)가 발급한 1회용 서명 URL 로만.
drop policy if exists s_ins on storage.objects;
drop policy if exists s_upd on storage.objects;
drop policy if exists s_sel on storage.objects;
create policy s_sel on storage.objects for select to anon, authenticated using (true);

-- ── 본인 매치 삭제 + 스토리지 파일 정리 (video/thumb/replay/preview) ──
create or replace function public.delete_match(p_token text, p_match_id text)
returns void language plpgsql security definer set search_path = public, storage as $$
declare pu text; r record; bk text := 'media'; k text; key text;
begin
  select puuid into pu from sessions where token = p_token;
  if pu is null then raise exception 'not logged in'; end if;
  for r in select video, thumb, replay, preview from matches
           where id = p_match_id and owner_puuid = pu loop
    foreach k in array array[r.video, r.thumb, r.replay, r.preview] loop
      if k is not null and position('/object/public/'||bk||'/' in k) > 0 then
        key := split_part(k, '/object/public/'||bk||'/', 2);
        if length(key) > 0 then delete from storage.objects where bucket_id = bk and name = key; end if;
      end if;
    end loop;
  end loop;
  delete from matches where id = p_match_id and owner_puuid = pu;
end; $$;

grant execute on function
  public.upload_match(text, text, jsonb),
  public.upload_match_anon(jsonb),
  public.delete_match(text, text)
  to anon, authenticated;

-- 확인용: select policyname from pg_policies where tablename='matches';  → insert 정책 없어야 정상
