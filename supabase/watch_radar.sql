-- Watch Radar settings store with password-protected writes.
-- Apply once to a Supabase project. Reads are public (the site and the routine read them);
-- writes go through watch_radar_save(), which checks a bcrypt-hashed password that only
-- lives in watch_radar_secrets (no RLS policies = no direct access for anyone but the server).

create extension if not exists pgcrypto;

create table if not exists public.watch_radar_settings (
  id text primary key,                -- 'focus' | 'watchlist'
  data jsonb not null,
  updated_at timestamptz not null default now()
);
create table if not exists public.watch_radar_secrets (
  key text primary key,               -- 'password'
  hash text not null
);
alter table public.watch_radar_settings enable row level security;
alter table public.watch_radar_secrets enable row level security;
drop policy if exists "watch_radar public read" on public.watch_radar_settings;
create policy "watch_radar public read" on public.watch_radar_settings for select to anon, authenticated using (true);

create or replace function public.watch_radar_check(p_password text)
returns boolean language plpgsql security definer set search_path = public, extensions as $$
declare h text;
begin
  select hash into h from watch_radar_secrets where key = 'password';
  if h is null or crypt(p_password, h) <> h then perform pg_sleep(0.4); return false; end if;
  return true;
end $$;

create or replace function public.watch_radar_save(p_password text, p_id text, p_data jsonb)
returns jsonb language plpgsql security definer set search_path = public, extensions as $$
begin
  if not watch_radar_check(p_password) then raise exception 'wrong password' using errcode = '28000'; end if;
  if p_id not in ('focus', 'watchlist') then raise exception 'unknown setting %', p_id; end if;
  insert into watch_radar_settings (id, data, updated_at) values (p_id, p_data, now())
  on conflict (id) do update set data = excluded.data, updated_at = now();
  return jsonb_build_object('ok', true, 'id', p_id, 'updated_at', now());
end $$;

create or replace function public.watch_radar_set_password(p_old text, p_new text)
returns boolean language plpgsql security definer set search_path = public, extensions as $$
begin
  if length(coalesce(p_new, '')) < 8 then raise exception 'password must be at least 8 characters'; end if;
  if exists (select 1 from watch_radar_secrets where key = 'password') and not watch_radar_check(p_old) then
    raise exception 'wrong password' using errcode = '28000';
  end if;
  insert into watch_radar_secrets (key, hash) values ('password', crypt(p_new, gen_salt('bf', 10)))
  on conflict (key) do update set hash = excluded.hash;
  return true;
end $$;

revoke all on function public.watch_radar_check(text) from public;
revoke all on function public.watch_radar_save(text, text, jsonb) from public;
revoke all on function public.watch_radar_set_password(text, text) from public;
grant execute on function public.watch_radar_check(text) to anon, authenticated;
grant execute on function public.watch_radar_save(text, text, jsonb) to anon, authenticated;
grant execute on function public.watch_radar_set_password(text, text) to anon, authenticated;

-- ---------------------------------------------------------------------------
-- One-time: set the initial Watch Radar password. Replace CHANGE-ME before
-- running, then delete this line from the editor (do not commit a password).
-- select public.watch_radar_set_password(null, 'CHANGE-ME');
