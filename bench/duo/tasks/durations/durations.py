def parse_duration(text):
    """Parse a human duration into whole seconds.

    Units: d (days), h (hours), m (minutes), s (seconds). Parts may be separated by spaces ("1h 30m")
    or written together ("1h30m"). Each unit may appear at most once and units must go from largest to
    smallest ("30m1h" is invalid). Numbers are non-negative integers. Surrounding whitespace is ignored
    and units are case-insensitive ("2H" is 7200).
    Raise ValueError for anything else: empty strings, unknown units, missing numbers, decimals,
    repeated or out-of-order units.
    """
    total = 0
    for part in text.split():
        n, unit = int(part[:-1]), part[-1]
        total += n * {"h": 3600, "m": 60, "s": 1}[unit]
    return total
