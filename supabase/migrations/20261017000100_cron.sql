-- Refresh analytics every 10 minutes with pg_cron.
-- Kept separate so the main schema still applies if pg_cron isn't enabled.
-- If this fails: Supabase dashboard > Database > Extensions > enable pg_cron, then re-run.
create extension if not exists pg_cron with schema pg_catalog;

select cron.schedule('refresh-analytics', '*/10 * * * *', $$select public.refresh_analytics()$$);
