# Home Assistant history cards

`hvac-energy-history-card.js` registers three configurable Lovelace custom
cards:

- `custom:hvac-energy-history-card`
- `custom:site-battery-power-history-card`
- `custom:conditional-export-energy-history-card`

Install the JavaScript file as a Home Assistant module resource. All entity IDs
belong in dashboard YAML; the source contains no deployment-specific entities.

## Conditional export example

```yaml
type: custom:conditional-export-energy-history-card
title: Export with battery headroom
entities:
  grid_export: sensor.grid_export_power
  battery_soc: sensor.battery_state_of_charge
soc_threshold: 100
peak_start: "16:00"
peak_end: "21:00"
billing_cycle_name: utility
billing_cycle_start_day: 1
```

`grid_export` must be a non-negative exported-power statistic convertible to
kW, and `battery_soc` must report percent. Configure the peak window and
billing-cycle start for the applicable tariff; the provider-neutral defaults
are examples, not a statement about any utility plan.

The card integrates the exported-power history only while SOC is below the
configured threshold and displays a second cumulative series limited to the
configured daily peak window.
