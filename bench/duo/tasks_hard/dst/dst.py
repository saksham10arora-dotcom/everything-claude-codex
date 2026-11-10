from datetime import datetime, timedelta, timezone


def next_daily(hour, minute, tz, after):
    """Return the next time (an aware datetime in UTC) a job set for HH:MM local time runs, strictly after `after`.

    `tz` is an IANA zone name like "America/New_York"; `after` is an aware datetime (any zone).
    The job runs once per local calendar day at hour:minute local time.
    - If that local time does not exist on a day (clocks jump forward over it), the job runs at the first
      valid instant after the gap, i.e. the moment the clocks jump to (e.g. 03:00 when 02:00-03:00 is skipped).
    - If that local time happens twice on a day (clocks fall back), the job runs only once, at the FIRST
      occurrence (before the clocks go back).
    Use the standard library zoneinfo. Raise ValueError for an unknown zone or hour/minute out of range.
    """
    local = after.astimezone(timezone.utc)
    run = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if run <= local:
        run += timedelta(days=1)
    return run
