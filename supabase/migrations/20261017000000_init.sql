-- Parking Monitor: initial schema (the "medium" 9-table design from project-context.xml)
-- Apply with:  supabase db push   (or paste into the Supabase SQL editor)

create extension if not exists postgis with schema extensions;

-- ---------------------------------------------------------------- tables

create table operator (
  operator_id  int primary key,
  name         text not null,
  pay_app      text not null                    -- ParkMobile | Passport
);

create table facility (
  facility_id  int primary key,
  operator_id  int not null references operator(operator_id),
  name         text not null,
  type         text not null check (type in ('garage','lot','street')),
  lat          double precision not null,
  lng          double precision not null
);

create table zone (
  zone_id          int primary key,
  facility_id      int not null references facility(facility_id),
  name             text not null,
  capacity         int not null check (capacity > 0),
  visitor_allowed  boolean not null default true,
  demand           real not null default 0.5,   -- simulator calibration only
  profile          text not null default 'daytime'
);

create table rate_rule (
  rule_id         serial primary key,
  zone_id         int not null references zone(zone_id) on delete cascade,
  day_of_week     smallint not null check (day_of_week between 0 and 6),  -- 0 = Sunday
  start_time      time not null,
  end_time        time not null,
  hourly_rate     numeric(5,2) not null,
  time_limit_min  int                            -- null = no limit
);

-- "session" is a SQL keyword, so the table is parking_session.
create table parking_session (
  session_id   bigserial primary key,
  zone_id      int not null references zone(zone_id) on delete cascade,
  start_time   timestamptz not null,
  paid_until   timestamptz not null,
  end_time     timestamptz,                      -- null = car still parked
  check (paid_until >= start_time)
);
create index parking_session_zone_time on parking_session (zone_id, start_time);
create index parking_session_active on parking_session (zone_id) where end_time is null;

create table destination (
  destination_id  int primary key,
  name            text not null,
  lat             double precision not null,
  lng             double precision not null
);

create table event (
  event_id             serial primary key,
  destination_id       int references destination(destination_id),
  name                 text not null,
  start_time           timestamptz not null,
  end_time             timestamptz not null,
  expected_attendance  int
);

create table impacts (
  event_id      int references event(event_id) on delete cascade,
  zone_id       int references zone(zone_id) on delete cascade,
  demand_boost  real not null default 0.3,      -- 0.3 = +30% demand
  primary key (event_id, zone_id)
);

create table zone_status (
  zone_id       int primary key references zone(zone_id) on delete cascade,
  occupied      int not null default 0,
  opening_soon  int not null default 0,
  updated_at    timestamptz not null default now()
);

-- ---------------------------------------------------------------- helpers

-- Walking minutes between two points (straight line x 1.3 detour, 80 m/min).
create or replace function walk_minutes(lat1 float8, lng1 float8, lat2 float8, lng2 float8)
returns int language sql immutable as $$
  select ceil(
    extensions.st_distance(
      extensions.st_setsrid(extensions.st_makepoint(lng1, lat1), 4326)::extensions.geography,
      extensions.st_setsrid(extensions.st_makepoint(lng2, lat2), 4326)::extensions.geography
    ) * 1.3 / 80.0
  )::int
$$;

-- Live status: recompute zone_status from sessions. Called by the simulator every tick.
create or replace function refresh_zone_status()
returns void language sql security definer set search_path = public as $$
  insert into zone_status (zone_id, occupied, opening_soon, updated_at)
  select z.zone_id,
         count(s.session_id) filter (where s.start_time <= now() and s.end_time is null),
         count(s.session_id) filter (where s.end_time is null
                                       and s.paid_until between now() and now() + interval '15 minutes'),
         now()
  from zone z
  left join parking_session s on s.zone_id = z.zone_id and s.end_time is null
  group by z.zone_id
  on conflict (zone_id) do update
    set occupied = excluded.occupied,
        opening_soon = excluded.opening_soon,
        updated_at = excluded.updated_at;
$$;

-- ---------------------------------------------------------------- analytics

-- Average occupancy by zone, day of week, hour (America/New_York).
create materialized view mv_hourly_occupancy as
with hours as (
  select s.zone_id,
         date_trunc('hour', h) as hour_ts
  from parking_session s
  cross join lateral generate_series(
      date_trunc('hour', s.start_time),
      coalesce(s.end_time, now()),
      interval '1 hour') as h
  where s.start_time > now() - interval '35 days'
),
counts as (
  select zone_id, hour_ts, count(*) as cars from hours group by 1, 2
)
select c.zone_id,
       extract(dow  from c.hour_ts at time zone 'America/New_York')::int as day_of_week,
       extract(hour from c.hour_ts at time zone 'America/New_York')::int as hour,
       round(avg(least(c.cars::numeric / z.capacity, 1)), 3) as avg_occupancy,
       count(*) as samples
from counts c join zone z using (zone_id)
group by 1, 2, 3;
create unique index on mv_hourly_occupancy (zone_id, day_of_week, hour);

-- Dwell time and turnover per zone.
create materialized view mv_dwell_turnover as
select s.zone_id,
       round(avg(extract(epoch from (s.end_time - s.start_time)) / 60)::numeric, 1) as avg_dwell_min,
       round(avg(case when s.end_time > s.paid_until then 1 else 0 end)::numeric, 3) as overstay_rate,
       round((count(*)::numeric / nullif(z.capacity, 0))
             / greatest(1, extract(epoch from (max(s.start_time) - min(s.start_time))) / 86400)::numeric, 2)
         as sessions_per_spot_per_day
from parking_session s join zone z using (zone_id)
where s.end_time is not null and s.start_time > now() - interval '35 days'
group by s.zone_id, z.capacity;
create unique index on mv_dwell_turnover (zone_id);

create or replace function refresh_analytics()
returns void language sql security definer set search_path = public as $$
  refresh materialized view concurrently mv_hourly_occupancy;
  refresh materialized view concurrently mv_dwell_turnover;
$$;

-- Simple prediction: historical avg for that hour-of-week x (1 + event boosts).
create or replace function predict_availability(p_zone_id int, p_at timestamptz)
returns table (zone_id int, expected_occupancy numeric, prob_available numeric, expected_open int)
language sql stable set search_path = public as $$
  with base as (
    select coalesce(max(m.avg_occupancy), 0.5) as occ
    from mv_hourly_occupancy m
    where m.zone_id = p_zone_id
      and m.day_of_week = extract(dow  from p_at at time zone 'America/New_York')::int
      and m.hour        = extract(hour from p_at at time zone 'America/New_York')::int
  ), boost as (
    select coalesce(sum(i.demand_boost), 0) as b
    from impacts i join event e using (event_id)
    where i.zone_id = p_zone_id and p_at between e.start_time - interval '1 hour' and e.end_time
  )
  select p_zone_id,
         round(least(base.occ * (1 + boost.b), 1)::numeric, 3),
         round(greatest(0, 1 - least(base.occ * (1 + boost.b), 1))::numeric, 3),
         floor(z.capacity * greatest(0, 1 - least(base.occ * (1 + boost.b), 1)))::int
  from base, boost, zone z where z.zone_id = p_zone_id
$$;

-- ---------------------------------------------------------------- security
-- Public read-only. Only the service role (FastAPI + simulator on Fly) writes.

do $$
declare t text;
begin
  foreach t in array array['operator','facility','zone','rate_rule','parking_session',
                           'destination','event','impacts','zone_status']
  loop
    execute format('alter table %I enable row level security', t);
    execute format('create policy "public read" on %I for select to anon, authenticated using (true)', t);
  end loop;
end $$;

grant select on mv_hourly_occupancy, mv_dwell_turnover to anon, authenticated;
revoke execute on function refresh_zone_status(), refresh_analytics() from public, anon, authenticated;

-- ---------------------------------------------------------------- realtime
alter publication supabase_realtime add table zone_status;
