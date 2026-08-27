---
name: mars-time
description: Convert between Mars solar longitude (Ls), Mars Year (MY) / sol-of-year, Mars Sol Date (MSD), and Earth UTC. Use whenever the user gives a Mars date/season or an Earth date and wants the other, or asks "what Ls is it", "what Mars year / sol", "when is Ls X in MY Y", "convert this UTC to Mars time", "what sol of the mission/year", "Mars season for this date", etc. Triggers on "Ls", "solar longitude", "Mars year", "MY##", "sol", "areocentric", "Mars season", "Mars date", "UTC to Mars".
---

# Mars ↔ Earth time converter

A pure-Python (stdlib-only) converter implementing the **Allison & McEwen
(2000) / NASA "Mars24"** areocentric-longitude recipe. Validated against the
documented Piqueux et al. (2015) Ls=0 Mars-Year start dates (worst-case
residual < 0.4°, all attributable to date-only anchors) and the Curiosity
landing (computed Ls 150.70° vs documented 150.8°).

Resolve `<skill-dir>` as the directory containing this `SKILL.md`. The converter
is `<skill-dir>/mars_time.py`; substitute its literal absolute path in commands.
This keeps the same skill portable across Claude Code and Codex installations.

Run it directly — no arguments to parse by hand; just pick the sub-command and
report the printed table back to the user.

## Commands

Current moment:
```bash
python "<skill-dir>/mars_time.py" now
```

Earth UTC → Mars (Ls, Mars Year, sol-of-year, MSD, season). Accepts
`YYYY-MM-DD` (→ 00:00 UTC) or `YYYY-MM-DDTHH:MM:SS`:
```bash
python "<skill-dir>/mars_time.py" from-utc 2026-08-25T14:30:00
```

Mars Year + Ls → Earth UTC:
```bash
python "<skill-dir>/mars_time.py" to-utc --my 37 --ls 251.4
```

Mars Year + sol-of-year → Earth UTC:
```bash
python "<skill-dir>/mars_time.py" to-utc --my 37 --sol 300
```

## Conventions & notes

- **Ls** (solar longitude): 0–360°. Ls 0 = northern spring (vernal) equinox,
  90 = N. summer solstice, 180 = N. autumnal equinox, 270 = N. winter solstice.
- **Mars Year** numbering (Clancy/Piqueux): **MY1 begins at the Ls=0 crossing
  on 1955-04-11.** Each Mars year ≈ 668.6 sols ≈ 686.97 Earth days.
- **sol-of-year** counts sols since that MY's Ls=0 crossing (1-based, runs to
  ≈668.6). This is *not* a mission sol — mission sols count from a landing.
- **MSD** (Mars Sol Date) is the absolute sol count from the Mars24 epoch
  (1873-12-29), useful as a continuous Mars timeline.
- Time scale: UTC→TT via a leap-second table (TT−UTC = 69.184 s since 2017).
- Accuracy: Ls good to ~0.1°; valid roughly 1955–2050. It does **not** model
  local-solar-time / longitude-on-Mars or spacecraft mission clocks.

## Extending

To validate after any edit:
```bash
python "<skill-dir>/_validate.py"
```
It asserts the documented MY-start residuals, exact-year boundary round-trips,
ordinary Ls/sol round-trips, and the Curiosity landing reference.
