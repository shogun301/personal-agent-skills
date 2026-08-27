#!/usr/bin/env python3
"""
mars_time.py - Convert between Mars solar longitude (Ls), Mars Year (MY) /
sol-of-year, Mars Sol Date (MSD), and Earth UTC.

Algorithm: Allison & McEwen (2000), "A post-Pathfinder evaluation of
areocentric solar coordinates with improved timing recipes for Mars seasonal/
diurnal climate studies" (Planet. Space Sci. 48, 215-235), i.e. the NASA GISS
"Mars24" recipe. Mars Year numbering follows the Clancy et al. (2000) /
Piqueux et al. (2015) convention: MY1 begins at the Ls=0 crossing on
1955-04-11.

No third-party dependencies (pure standard library).

CLI examples:
  python mars_time.py now
  python mars_time.py from-utc 2019-03-23T00:00:00
  python mars_time.py from-utc 2026-08-25         (date only -> 00:00 UTC)
  python mars_time.py to-utc --my 36 --ls 90
  python mars_time.py to-utc --my 36 --sol 300
  python mars_time.py ls-to-utc --my 37 --ls 251.4
"""

import argparse
import math
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Time scales
# ---------------------------------------------------------------------------

# Leap seconds: (UTC date the value takes effect, TAI-UTC in seconds).
# TT = TAI + 32.184 s, so TT-UTC = (TAI-UTC) + 32.184.
# Table valid through the last IERS bulletin (37 s since 2017-01-01).
_LEAP_SECONDS = [
    (datetime(1972, 1, 1, tzinfo=timezone.utc), 10),
    (datetime(1972, 7, 1, tzinfo=timezone.utc), 11),
    (datetime(1973, 1, 1, tzinfo=timezone.utc), 12),
    (datetime(1974, 1, 1, tzinfo=timezone.utc), 13),
    (datetime(1975, 1, 1, tzinfo=timezone.utc), 14),
    (datetime(1976, 1, 1, tzinfo=timezone.utc), 15),
    (datetime(1977, 1, 1, tzinfo=timezone.utc), 16),
    (datetime(1978, 1, 1, tzinfo=timezone.utc), 17),
    (datetime(1979, 1, 1, tzinfo=timezone.utc), 18),
    (datetime(1980, 1, 1, tzinfo=timezone.utc), 19),
    (datetime(1981, 7, 1, tzinfo=timezone.utc), 20),
    (datetime(1982, 7, 1, tzinfo=timezone.utc), 21),
    (datetime(1983, 7, 1, tzinfo=timezone.utc), 22),
    (datetime(1985, 7, 1, tzinfo=timezone.utc), 23),
    (datetime(1988, 1, 1, tzinfo=timezone.utc), 24),
    (datetime(1990, 1, 1, tzinfo=timezone.utc), 25),
    (datetime(1991, 1, 1, tzinfo=timezone.utc), 26),
    (datetime(1992, 7, 1, tzinfo=timezone.utc), 27),
    (datetime(1993, 7, 1, tzinfo=timezone.utc), 28),
    (datetime(1994, 7, 1, tzinfo=timezone.utc), 29),
    (datetime(1996, 1, 1, tzinfo=timezone.utc), 30),
    (datetime(1997, 7, 1, tzinfo=timezone.utc), 31),
    (datetime(1999, 1, 1, tzinfo=timezone.utc), 32),
    (datetime(2006, 1, 1, tzinfo=timezone.utc), 33),
    (datetime(2009, 1, 1, tzinfo=timezone.utc), 34),
    (datetime(2012, 7, 1, tzinfo=timezone.utc), 35),
    (datetime(2015, 7, 1, tzinfo=timezone.utc), 36),
    (datetime(2017, 1, 1, tzinfo=timezone.utc), 37),
]


def _tt_minus_utc_seconds(dt_utc):
    """TT - UTC in seconds for a given UTC datetime."""
    if dt_utc >= _LEAP_SECONDS[0][0]:
        tai_utc = _LEAP_SECONDS[0][1]
        for eff, val in _LEAP_SECONDS:
            if dt_utc >= eff:
                tai_utc = val
            else:
                break
        return tai_utc + 32.184
    # Pre-1972: rough historical approximation (adequate; sub-arcminute Ls).
    return 32.184 + 9.0


def _julian_date_utc(dt_utc):
    """Julian Date from a UTC datetime (proleptic Gregorian)."""
    y, m = dt_utc.year, dt_utc.month
    d = (dt_utc.day
         + (dt_utc.hour + (dt_utc.minute + (dt_utc.second
            + dt_utc.microsecond / 1e6) / 60.0) / 60.0) / 24.0)
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return (math.floor(365.25 * (y + 4716))
            + math.floor(30.6001 * (m + 1))
            + d + b - 1524.5)


def _jdtt(dt_utc):
    return _julian_date_utc(dt_utc) + _tt_minus_utc_seconds(dt_utc) / 86400.0


# ---------------------------------------------------------------------------
# Mars24 areocentric solar longitude (Ls)
# ---------------------------------------------------------------------------

# Perturbers for the equation of center (Allison & McEwen 2000, Table).
_PBS = [
    (0.0071, 2.2353, 49.409),
    (0.0057, 2.7543, 168.173),
    (0.0039, 1.1177, 191.837),
    (0.0037, 15.7866, 21.736),
    (0.0021, 2.1354, 15.704),
    (0.0020, 2.4694, 95.528),
    (0.0018, 32.8493, 49.095),
]

MARS_TROPICAL_YEAR_DAYS = 686.9726   # Earth days between successive Ls=0
SOLS_PER_MARS_YEAR = 668.5991        # sols per Mars (tropical) year
SECONDS_PER_SOL = 88775.244          # length of a Mars solar day, s


def _ls_from_jdtt(jdtt):
    """Areocentric solar longitude Ls (degrees, 0-360) from JD(TT)."""
    dt = jdtt - 2451545.0
    m = math.radians((19.3871 + 0.52402073 * dt) % 360.0)          # anomaly
    alpha = 270.3871 + 0.524038496 * dt                            # FMS
    pbs = sum(a * math.cos(math.radians((0.985626 * dt / tau) + phi))
              for (a, tau, phi) in _PBS)
    nu_minus_m = ((10.691 + 3.0e-7 * dt) * math.sin(m)
                  + 0.6230 * math.sin(2 * m)
                  + 0.0500 * math.sin(3 * m)
                  + 0.0060 * math.sin(4 * m)
                  + 0.0007 * math.sin(5 * m)
                  + pbs)
    return (alpha + nu_minus_m) % 360.0


def ls_from_utc(dt_utc):
    return _ls_from_jdtt(_jdtt(dt_utc))


def mars_sol_date(dt_utc):
    """Mars Sol Date (MSD): sols since the Mars24 prime-meridian epoch."""
    jdtt = _jdtt(dt_utc)
    return (jdtt - 2405522.0028779) / 1.0274912517


# ---------------------------------------------------------------------------
# Mars Year & sol-of-year
# ---------------------------------------------------------------------------

_MY1_SEED = datetime(1955, 4, 11, tzinfo=timezone.utc)  # near MY1 Ls=0 crossing


def _find_ls0_crossing(seed_jdtt):
    """Refine to the JD(TT) of the Ls=0 crossing nearest seed_jdtt."""
    jd = seed_jdtt
    for _ in range(60):
        ls = _ls_from_jdtt(jd)
        # signed distance to nearest Ls=0, in degrees within (-180, 180]
        err = (ls + 180.0) % 360.0 - 180.0
        # ~0.524 deg of Ls per Earth day near Ls=0
        step = err / 0.524038496
        jd -= step
        if abs(step) < 1e-6:
            break
    return jd


# Anchor: JD(TT) of the MY1 Ls=0 crossing (computed once).
_MY1_JDTT = _find_ls0_crossing(_jdtt(_MY1_SEED))


def mars_year_and_sol(dt_utc):
    """Return (mars_year, sol_of_year, ls) for a UTC datetime.

    sol_of_year runs 1..~668, counting sols since the MY's Ls=0 crossing.
    """
    jdtt = _jdtt(dt_utc)
    n = round((jdtt - _MY1_JDTT) / MARS_TROPICAL_YEAR_DAYS)
    # locate the Ls=0 crossing that starts the year containing this date
    while True:
        start = _find_ls0_crossing(_MY1_JDTT + n * MARS_TROPICAL_YEAR_DAYS)
        nxt = _find_ls0_crossing(_MY1_JDTT + (n + 1) * MARS_TROPICAL_YEAR_DAYS)
        if jdtt < start - 1e-6:
            n -= 1
            continue
        if jdtt >= nxt - 1e-6:
            n += 1
            continue
        break
    my = n + 1
    days_since_start = jdtt - start          # Earth days (TT)
    sol_of_year = days_since_start / 1.0274912517 + 1.0
    return my, sol_of_year, _ls_from_jdtt(jdtt)


def _my_start_jdtt(my):
    """JD(TT) of the Ls=0 crossing that begins Mars Year `my`."""
    n = my - 1
    return _find_ls0_crossing(_MY1_JDTT + n * MARS_TROPICAL_YEAR_DAYS)


# ---------------------------------------------------------------------------
# Inverse: Mars coordinates -> UTC
# ---------------------------------------------------------------------------

def _utc_from_jdtt(jdtt, dt_hint):
    """Invert JD(TT) -> UTC datetime (iterate on TT-UTC)."""
    # first guess: treat as JD(UTC)
    def jd_to_dt(jd):
        jd = jd + 0.5
        z = math.floor(jd)
        f = jd - z
        if z < 2299161:
            a = z
        else:
            alpha = math.floor((z - 1867216.25) / 36524.25)
            a = z + 1 + alpha - math.floor(alpha / 4)
        b = a + 1524
        c = math.floor((b - 122.1) / 365.25)
        d = math.floor(365.25 * c)
        e = math.floor((b - d) / 30.6001)
        day = b - d - math.floor(30.6001 * e) + f
        month = e - 1 if e < 14 else e - 13
        year = c - 4716 if month > 2 else c - 4715
        di = int(day)
        frac = day - di
        # Preserve sub-second precision. Rounding to a whole second can place
        # an exact Ls=0 / sol-1 inverse result just before the year boundary,
        # causing the subsequent UTC -> MY conversion to report the prior MY.
        micros = round(frac * 86400.0 * 1_000_000.0)
        base = datetime(year, month, di, tzinfo=timezone.utc)
        return base + timedelta(microseconds=micros)

    guess = jd_to_dt(jdtt)  # ignores TT-UTC first
    for _ in range(4):
        offset = _tt_minus_utc_seconds(guess) / 86400.0
        guess = jd_to_dt(jdtt - offset)
    return guess


def utc_from_my_ls(my, ls):
    """UTC datetime for a given Mars Year and Ls (degrees)."""
    ls = ls % 360.0
    start = _my_start_jdtt(my)
    # initial guess: linear in Ls across the year
    jd = start + (ls / 360.0) * MARS_TROPICAL_YEAR_DAYS
    for _ in range(60):
        cur = _ls_from_jdtt(jd)
        err = (cur - ls + 180.0) % 360.0 - 180.0
        step = err / 0.524038496
        jd -= step
        if abs(step) < 1e-6:
            break
    return _utc_from_jdtt(jd, None)


def utc_from_my_sol(my, sol_of_year):
    """UTC datetime for a given Mars Year and sol-of-year (1-based)."""
    start = _my_start_jdtt(my)
    jd = start + (sol_of_year - 1.0) * 1.0274912517
    return _utc_from_jdtt(jd, None)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_utc(s):
    s = s.strip().replace("Z", "").replace("z", "")
    fmts = ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"]
    for f in fmts:
        try:
            return datetime.strptime(s, f).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise SystemExit(f"Could not parse UTC datetime: {s!r}")


def _report_from_utc(dt_utc):
    my, sol, ls = mars_year_and_sol(dt_utc)
    msd = mars_sol_date(dt_utc)
    print(f"UTC          : {dt_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"Solar long Ls: {ls:8.3f} deg   ({_season(ls)})")
    print(f"Mars Year    : MY{my}")
    print(f"Sol of year  : {sol:8.2f}  (of ~{SOLS_PER_MARS_YEAR:.1f})")
    print(f"Mars Sol Date: {msd:12.4f}")


def _season(ls):
    if ls < 90:
        s = "N. spring / S. autumn"
    elif ls < 180:
        s = "N. summer / S. winter"
    elif ls < 270:
        s = "N. autumn / S. spring"
    else:
        s = "N. winter / S. summer"
    if abs(ls - 0) < 1 or abs(ls - 360) < 1:
        s += "  [N vernal equinox]"
    elif abs(ls - 90) < 1:
        s += "  [N summer solstice]"
    elif abs(ls - 180) < 1:
        s += "  [N autumnal equinox]"
    elif abs(ls - 270) < 1:
        s += "  [N winter solstice]"
    return s


def main():
    p = argparse.ArgumentParser(description="Mars <-> Earth time converter")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("now", help="convert the current moment")

    p1 = sub.add_parser("from-utc", help="UTC -> Ls, MY, sol")
    p1.add_argument("datetime", help="e.g. 2026-08-25T14:30:00 or 2026-08-25")

    p2 = sub.add_parser("to-utc", help="MY + (Ls or sol) -> UTC")
    p2.add_argument("--my", type=int, required=True)
    p2.add_argument("--ls", type=float)
    p2.add_argument("--sol", type=float)

    p3 = sub.add_parser("ls-to-utc", help="alias of to-utc --my --ls")
    p3.add_argument("--my", type=int, required=True)
    p3.add_argument("--ls", type=float, required=True)

    a = p.parse_args()

    if a.cmd == "now":
        _report_from_utc(datetime.now(timezone.utc))
    elif a.cmd == "from-utc":
        _report_from_utc(_parse_utc(a.datetime))
    elif a.cmd in ("to-utc", "ls-to-utc"):
        if a.cmd == "ls-to-utc" or (a.ls is not None and a.sol is None):
            dt = utc_from_my_ls(a.my, a.ls)
            _report_from_utc(dt)
        elif a.sol is not None:
            dt = utc_from_my_sol(a.my, a.sol)
            _report_from_utc(dt)
        else:
            raise SystemExit("Provide --ls or --sol")


if __name__ == "__main__":
    main()
