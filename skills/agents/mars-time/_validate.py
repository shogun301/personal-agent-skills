"""Assert mars_time accuracy against documented anchors and round-trips."""
from datetime import datetime, timezone
import mars_time as mt

# Piqueux et al. (2015) / Clancy convention Ls=0 (N. vernal equinox) dates.
KNOWN = {
    24: "1998-07-14", 25: "2000-05-31", 26: "2002-04-18", 27: "2004-03-05",
    28: "2006-01-21", 29: "2007-12-09", 30: "2009-10-26", 31: "2011-09-13",
    32: "2013-07-31", 33: "2015-06-18", 34: "2017-05-05", 35: "2019-03-23",
    36: "2021-02-07", 37: "2022-12-26", 38: "2024-11-12",
}

print("== Ls near documented MY start dates (should be ~0 or ~360) ==")
worst = 0.0
for my, d in sorted(KNOWN.items()):
    dt = datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    ls = mt.ls_from_utc(dt)
    err = min(ls, 360 - ls)
    worst = max(worst, err)
    my_calc, sol, _ = mt.mars_year_and_sol(dt)
    print(f"MY{my} {d}: Ls={ls:7.3f} (err {err:5.3f})  calcMY={my_calc} sol={sol:6.2f}")
print(f"worst Ls error at date-granularity anchors: {worst:.3f} deg")
assert worst < 0.5, f"documented MY-start residual too large: {worst:.3f} deg"


def angular_error(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)

print("\n== round-trip: MY/Ls -> UTC -> MY/Ls ==")
for my, ls in [(36, 90.0), (37, 251.4), (34, 0.0), (35, 180.0), (38, 359.0)]:
    dt = mt.utc_from_my_ls(my, ls)
    my2, sol2, ls2 = mt.mars_year_and_sol(dt)
    print(f"MY{my} Ls{ls:6.2f} -> {dt.strftime('%Y-%m-%d %H:%M')} UTC "
          f"-> MY{my2} Ls{ls2:7.3f} sol{sol2:6.2f}")
    assert my2 == my, f"MY/Ls boundary round-trip changed MY{my} to MY{my2}"
    assert angular_error(ls2, ls) < 0.001, (
        f"MY{my} Ls round-trip error: requested {ls}, got {ls2}"
    )

print("\n== round-trip: MY/sol -> UTC -> MY/sol ==")
for my, sol in [(36, 1.0), (37, 300.0), (35, 668.0)]:
    dt = mt.utc_from_my_sol(my, sol)
    my2, sol2, ls2 = mt.mars_year_and_sol(dt)
    print(f"MY{my} sol{sol:6.1f} -> {dt.strftime('%Y-%m-%d %H:%M')} UTC "
          f"-> MY{my2} sol{sol2:7.2f} Ls{ls2:7.2f}")
    assert my2 == my, f"MY/sol boundary round-trip changed MY{my} to MY{my2}"
    assert abs(sol2 - sol) < 0.001, (
        f"MY{my} sol round-trip error: requested {sol}, got {sol2}"
    )

print("\n== spot: Curiosity landing 2012-08-06 05:17:57 UTC (expect ~MY31 Ls~150.8) ==")
dt = datetime(2012, 8, 6, 5, 17, 57, tzinfo=timezone.utc)
my, sol, ls = mt.mars_year_and_sol(dt)
print(f"MY{my} Ls={ls:.3f} sol={sol:.2f}")
assert my == 31, f"Curiosity landing expected MY31, got MY{my}"
assert abs(ls - 150.8) < 0.2, f"Curiosity landing Ls mismatch: {ls:.3f}"

print("\nPASS: all Mars-time validation assertions succeeded")
