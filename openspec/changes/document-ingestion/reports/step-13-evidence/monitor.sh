#!/bin/sh
# Samples the worker's database sessions and cgroup counters every ~0.5 s until the stop file exists.
export MSYS_NO_PATHCONV=1
S="$1"; OUT="$S/g13_monitor.csv"; : > "$OUT"
WIP=$(docker inspect g13-worker --format '{{(index .NetworkSettings.Networks "g13-net").IPAddress}}')
echo "ts,worker_sessions,worker_idle_in_tx,worker_max_xact_age_ms,worker_active,mem_current,mem_peak,cpu_usec" >> "$OUT"
while [ ! -f "$S/g13_monitor.stop" ]; do
  T=$(date +%s.%N)
  Q=$(docker exec g13-db psql -U g13 -d g13 -tA -F, -c "select count(*), count(*) filter (where state like 'idle in transaction%'), coalesce(round(max(extract(epoch from now()-xact_start))*1000),0), count(*) filter (where state='active') from pg_stat_activity where client_addr='$WIP' and datname='g13'" 2>/dev/null)
  C=$(docker exec g13-worker sh -c 'echo $(cat /sys/fs/cgroup/memory.current),$(cat /sys/fs/cgroup/memory.peak),$(grep usage_usec /sys/fs/cgroup/cpu.stat | cut -d" " -f2)' 2>/dev/null)
  echo "$T,$Q,$C" >> "$OUT"
  sleep 0.3
done
