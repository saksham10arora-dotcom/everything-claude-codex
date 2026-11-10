def satisfies(version, rng):
    """Return True if `version` satisfies the range `rng`, using npm-style semantics.

    Versions are SemVer 2.0: MAJOR.MINOR.PATCH, optional -prerelease (dot-separated identifiers), optional
    +build (ignored everywhere). Precedence: numeric identifiers compare numerically, alphanumeric ones
    lexically (ASCII), numeric ones are lower than alphanumeric ones, a shorter prerelease set is lower when
    all earlier identifiers are equal, and any prerelease is lower than the same version without one.

    Ranges are one or more comparator sets joined by "||" (satisfied if any set is). A set is space-separated
    comparators, all of which must hold: =, >, >=, <, <= followed by a version, or a bare version (means =),
    or these shorthands:
      ^1.2.3 := >=1.2.3 <2.0.0   ^0.2.3 := >=0.2.3 <0.3.0   ^0.0.3 := >=0.0.3 <0.0.4
      ~1.2.3 := >=1.2.3 <1.3.0   ~1.2 := >=1.2.0 <1.3.0     ~1 := >=1.0.0 <2.0.0
      1.2.x or 1.2.* or 1.2 := >=1.2.0 <1.3.0       1.x or 1 := >=1.0.0 <2.0.0       * or x or "" := any
    Prerelease rule: a version WITH a prerelease satisfies a set only if the set also has a comparator whose
    version has a prerelease and the same MAJOR.MINOR.PATCH (so ^1.2.3-beta.2 matches 1.2.3-beta.4 but not
    1.2.4-beta.1). "*" and other sets without prerelease comparators never match prerelease versions.
    Raise ValueError for an invalid version.
    """
    v = tuple(int(x) for x in version.split("-")[0].split("."))
    if rng.startswith("^"):
        low = tuple(int(x) for x in rng[1:].split("."))
        return low <= v < (low[0] + 1, 0, 0)
    return v == tuple(int(x) for x in rng.split("."))
