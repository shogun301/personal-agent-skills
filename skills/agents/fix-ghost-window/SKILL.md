---
name: fix-ghost-window
description: Diagnose and clear a ghost or orphaned window frame on Windows by restarting Explorer or, when necessary, Desktop Window Manager. Use only after explicitly warning the user about visible disruption and obtaining approval for the exact restart action.
---

# Fix a ghost Windows frame

A stale window outline can remain after the owning process exits because the
desktop compositor did not repaint. Confirm first that the apparent owning
process is gone; do not terminate a live application merely because its frame
looks stuck.

## Consent boundary

Both remedies visibly operate the desktop. Before running either one, describe
the effect and obtain explicit approval:

- `explorer`: closes and relaunches Explorer, including taskbar, desktop, and
  open File Explorer windows.
- `dwm`: requires a native UAC prompt, briefly blanks or flickers the display,
  and forces Windows to relaunch Desktop Window Manager.

Do not infer approval from the diagnosis request alone.

## Usage

Resolve `<skill-dir>` as the directory containing this file:

```powershell
& "<skill-dir>\restart_dwm.ps1" -Target explorer -ConfirmAction
& "<skill-dir>\restart_dwm.ps1" -Target dwm -ConfirmAction
```

Pass `-ConfirmAction` only after the user approves the exact operation. Use
`explorer` first when it is likely to repaint the affected surface. Use `dwm`
only when the user approved the stronger compositor restart.

Expected result lines:

- `EXPLORER-RESTARTED`
- `DWM-RESTARTED`

The DWM path invokes the absolute Windows system `taskkill.exe` directly with
elevation. It throws if the UAC prompt is denied or the process returns a
nonzero exit code.
