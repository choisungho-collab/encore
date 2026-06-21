-- 리플레이 캐스트 — Supabase(Postgres) 스키마
-- Supabase 대시보드 → SQL Editor 에 붙여넣고 Run 한 번이면 끝.

-- ========== 경기 ==========
create table if not exists public.matches (
  id          text primary key,                  -- gid (예: 20260620-120000-aa11)
  uploader    text,
  uploaded    timestamptz default now(),
  video       text,                              -- R2 공개 URL
  thumb       text,                              -- R2 공개 URL
  replay      text,                              -- R2 공개 URL (.rep 다운로드)
  video_size  bigint  default 0,
  map         text,
  matchup     text,
  length      text,
  length_sec  int     default 0,
  type        text,
  winner      int,
  saver       text,
  np          int     default 0,
  players     jsonb   default '[]'::jsonb,        -- [{name,race,team,apm,...}]
  won         boolean,
  analysis    jsonb,                              -- 빌드오더/유닛/APM (녹화기가 미리 계산)
  views       int     default 0,
  likes       int     default 0
);
create index if not exists matches_uploaded_idx on public.matches (uploaded desc);
create index if not exists matches_players_gin  on public.matches using gin (players);
-- 플레이어 프로필 조회:  select * from matches where players @> '[{"name":"몽정구"}]'::jsonb

-- ========== 댓글 ==========
create table if not exists public.comments (
  id        bigint generated always as identity primary key,
  match_id  text references public.matches(id) on delete cascade,
  author    text not null,
  body      text not null,
  created   timestamptz default now()
);
create index if not exists comments_match_idx on public.comments (match_id, created);

-- ========== RLS (행 보안) ==========
alter table public.matches  enable row level security;
alter table public.comments enable row level security;

-- 누구나 읽기
create policy "matches read"  on public.matches  for select using (true);
create policy "comments read" on public.comments for select using (true);

-- 댓글은 누구나 작성(길이 제한). 경기 INSERT 정책은 없음 → 익명키로는 못 넣고,
-- Edge Function(service_role 키)만 경기를 등록함(서비스 키는 RLS 우회).
create policy "comments insert" on public.comments for insert
  with check (char_length(author) between 1 and 40 and char_length(body) between 1 and 2000);

-- ========== 좋아요/조회수 (원자적 증가) ==========
create or replace function public.like_match(mid text, delta int default 1)
returns int language sql security definer set search_path = public as $$
  update public.matches set likes = greatest(0, likes + delta) where id = mid returning likes;
$$;

create or replace function public.bump_view(mid text)
returns int language sql security definer set search_path = public as $$
  update public.matches set views = views + 1 where id = mid returning views;
$$;

grant execute on function public.like_match(text, int) to anon, authenticated;
grant execute on function public.bump_view(text)      to anon, authenticated;
