-- usage_events: per-user action tracking for the 包租公 admin dashboard
-- Run this in Supabase SQL Editor (project nvavwcvxmzksadpbtafs)

create table if not exists public.usage_events (
  id          bigserial primary key,
  user_id     uuid references auth.users(id) on delete cascade,
  user_email  text,
  event       text not null,        -- 'recommend' | 'morning_brief' | 'review' | 'login' | 'first_login'
  metadata    jsonb default '{}'::jsonb,
  created_at  timestamptz default now()
);

create index if not exists usage_events_user_created_idx
  on public.usage_events(user_id, created_at desc);

create index if not exists usage_events_event_created_idx
  on public.usage_events(event, created_at desc);

create index if not exists usage_events_created_idx
  on public.usage_events(created_at desc);

-- RLS: writes/reads only via service_role from our backend.
-- Service role bypasses RLS automatically, so enabling RLS + no public policies = locked down.
alter table public.usage_events enable row level security;

-- Optional fallback: allow users to insert their own events (we don't use this today,
-- but keeps the door open for direct client logging without server hop).
drop policy if exists "users_insert_own" on public.usage_events;
create policy "users_insert_own" on public.usage_events
  for insert
  to authenticated
  with check (auth.uid() = user_id);
