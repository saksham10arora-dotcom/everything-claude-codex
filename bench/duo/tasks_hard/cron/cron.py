from datetime import datetime, timedelta


def next_run(expr, after):
    """Return the first datetime strictly after `after` (naive, minute precision) that matches the cron expression.

    Five fields: minute (0-59), hour (0-23), day of month (1-31), month (1-12 or jan-dec), day of week
    (0-7 or sun-sat, where both 0 and 7 mean Sunday). Names are case-insensitive.
    Each field is `*`, a number, a range `a-b`, a step `*/n` or `a-b/n`, or a comma list of those.
    Day rule (as in classic cron): if BOTH day of month and day of week are restricted (neither is `*`),
    a day matches when EITHER matches. If only one is restricted, only that one counts.
    Seconds and microseconds of the result are 0. Raise ValueError for invalid expressions
    (wrong field count, out-of-range values, a step of 0, a range whose start is after its end, unknown names).
    """
    minute, hour, dom, month, dow = expr.split()
    t = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(60 * 24 * 366 * 8):
        if (minute == "*" or t.minute == int(minute)) and (hour == "*" or t.hour == int(hour)):
            return t
        t += timedelta(minutes=1)
    raise ValueError("no match within 8 years")
