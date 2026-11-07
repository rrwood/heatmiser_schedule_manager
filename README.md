# Heatmiser Schedule Manager

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/rrwood/heatmiser_schedule_manager)](https://github.com/rrwood/heatmiser_schedule_manager/releases)

A Home Assistant custom integration that adds schedule management services for Heatmiser Neo thermostats. Set any day's heating schedule using named profiles or custom time/temperature setpoints — driven entirely from HA automations and scripts.

Works alongside the existing [Heatmiser Neo](https://github.com/MindrustUK/Heatmiser-for-home-assistant) integration. Does **not** modify or replace it.

---

## How it works

Heatmiser Neo thermostats use shared named profiles (stored on the hub) to define their heating schedules. This integration updates a profile's schedule for one day at a time by:

1. Connecting to the NeoHub via the existing Heatmiser Neo integration (no extra credentials needed)
2. Reading the thermostat's currently assigned profile
3. Replacing the target day's setpoints with the new schedule
4. Writing the full updated profile back to the hub

The change takes effect immediately on all thermostats using that profile.

---

## Installation

### Via HACS (recommended)

1. Open HACS → **Integrations** → click the three-dot menu → **Custom repositories**.
2. Add `https://github.com/rrwood/heatmiser_schedule_manager` as an **Integration**.
3. Search for **Heatmiser Schedule Manager** and click **Download**.
4. Restart Home Assistant.
5. Go to **Settings → Devices & Services → Add Integration**.
6. Search for **Heatmiser Schedule Manager** and follow the setup steps.

### Manual installation

1. Copy the `custom_components/heatmiser_schedule_manager/` folder to your HA `custom_components/` directory.
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration → Heatmiser Schedule Manager**.

---

## Prerequisites

- The [Heatmiser Neo](https://github.com/MindrustUK/Heatmiser-for-home-assistant) integration must already be installed and configured.
- At least one thermostat must be assigned a **named profile** (not profile 0) in the Heatmiser app.
- The hub must be in programmable mode (not `FORMAT=ZERO`).

---

## Profile configuration

On first load, the integration creates `heatmiser_schedule_profiles.yaml` in your HA config directory. Edit this file to customise schedules per room:

```yaml
default:
  workday:
    - time: "05:15"
      temp: 27.0
    - time: "08:00"
      temp: 16.0
    - time: "19:00"
      temp: 25.0
    - time: "21:00"
      temp: 16.0
  weekend:
    - time: "08:00"
      temp: 26.0
    - time: "18:00"
      temp: 23.5
    - time: "22:30"
      temp: 16.0
  holiday:
    - time: "00:00"
      temp: 15.0
  # ... other profiles

# Per-room overrides (optional — uses 'default' if section absent)
Bathroom:
  workday:
    - time: "06:00"
      temp: 24.0
    - time: "08:30"
      temp: 16.0
    - time: "18:00"
      temp: 24.0
    - time: "22:00"
      temp: 16.0
```

After editing, call `heatmiser_schedule_manager.reload_profiles` to apply without restarting HA.

### Built-in profiles

| Profile | Description |
|---------|-------------|
| `workday` | Standard working day — warm morning/evening, cooler midday |
| `weekend` | Later start, longer comfort period |
| `wfh` | Work from home — comfort hours through the day |
| `nonworkday` | Bank holiday or day off |
| `holiday` | Frost protection (15 °C) |
| `all_day_comfort` | 20 °C all day |
| `eco` | 16 °C all day |

---

## Services

### `heatmiser_schedule_manager.set_day_schedule`

Update the schedule for a specific day on one thermostat.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `device_name` | yes | Thermostat name exactly as shown in HA |
| `day` | yes | `monday` … `sunday` |
| `profile` | one of | Named profile from `heatmiser_schedule_profiles.yaml` |
| `schedule` | one of | Custom list of `{time, temp}` setpoints |

`profile` and `schedule` are mutually exclusive.

### `heatmiser_schedule_manager.set_week_schedule`

Apply the same profile to **every** day slot in one call. Useful for initialising a device or applying a week-long override.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `device_name` | yes | Thermostat name |
| `profile` | one of | Named profile |
| `schedule` | one of | Custom setpoints |

### `heatmiser_schedule_manager.get_schedule`

Read and return the current hub schedule for a thermostat. Returns data for use in scripts/automations and logs each day to `home-assistant.log`.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `device_name` | yes | Thermostat name |

### `heatmiser_schedule_manager.reload_profiles`

Reload `heatmiser_schedule_profiles.yaml` without restarting HA. Call this after editing the file.

---

## Example automations

See the [`examples/`](examples/) directory for ready-to-use YAML files:

| File | Description |
|------|-------------|
| `automation_calendar_schedule.yaml` | Set tomorrow's profile on all thermostats from a calendar |
| `automation_holiday_mode.yaml` | Activate/deactivate full holiday mode via a toggle helper |
| `script_set_all_thermostats.yaml` | Reusable script to apply any profile to all thermostats |

### Calendar-based daily scheduling

The most useful pattern: each evening at 21:30 this automation checks your HA calendar for tomorrow's events and picks the right heating profile automatically.

```yaml
- id: set_tomorrow_heatmiser_heating_profile
  alias: Set Tomorrow's Heatmiser Heating Profile
  triggers:
    - trigger: time
      at: "21:30:00"
  actions:
    - action: calendar.get_events
      target:
        entity_id: calendar.homeautomation
      data:
        start_date_time: >
          {{ (today_at('00:00') + timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S') }}
        duration:
          hours: 24
      response_variable: tomorrow_events

    - variables:
        tomorrow_day: "{{ (now() + timedelta(days=1)).weekday() }}"
        tomorrow_day_name: "{{ (now() + timedelta(days=1)).strftime('%A').lower() }}"
        events: "{{ tomorrow_events['calendar.homeautomation'].events }}"
        has_holiday: >
          {{ events | selectattr('summary', 'search', 'holiday', ignorecase=True)
             | list | length > 0 }}
        has_nonworkday: >
          {{ events | selectattr('summary', 'search', 'nonworkday', ignorecase=True)
             | list | length > 0 }}

    - variables:
        chosen_profile: >
          {% if has_holiday %}holiday
          {% elif has_nonworkday %}nonworkday
          {% elif tomorrow_day in [0, 1, 2, 3] %}workday
          {% elif tomorrow_day == 4 %}nonworkday
          {% else %}weekend{% endif %}

    - action: heatmiser_schedule_manager.set_day_schedule
      data:
        device_name: Kitchen and Hall
        day: "{{ tomorrow_day_name }}"
        profile: "{{ chosen_profile | trim }}"

    # Repeat for each thermostat...
```

See [`examples/automation_calendar_schedule.yaml`](examples/automation_calendar_schedule.yaml) for the full version covering all thermostats.

### Holiday mode

```yaml
- action: heatmiser_schedule_manager.set_week_schedule
  data:
    device_name: Bathroom
    profile: holiday
```

---

## Schedule format notes

NeoHub supports three schedule formats, configured hub-wide:

| Format | Slots | Effect on this service |
|--------|-------|------------------------|
| 7-day | Mon/Tue/Wed/Thu/Fri/Sat/Sun | Updates exactly the day specified |
| 2-day | Weekday + Weekend | Mon–Fri share one slot; Sat/Sun share another |
| 1-day | Single slot | All days share one slot |

The integration detects the hub's format automatically.

---

## Debug logging

Add to `configuration.yaml` to see detailed logs:

```yaml
logger:
  logs:
    custom_components.heatmiser_schedule_manager: debug
```

---

## Limitations

- Timer/switch devices are not supported — only heating thermostats.
- Because profiles are shared on the hub, updating a profile affects **all thermostats** using that profile. Assign each thermostat its own profile if you need independent schedules.

---

## Changelog

### v1.0.2 (2026-11-07)
- **Fix**: NeoHub firmware compatibility — the GET_PROFILES response format changed to key profiles by name instead of ID, and profile objects are now SimpleNamespace with an `info` attribute. The integration now handles both old and new formats.

### v1.0.1 (2026-04-20)
- Initial fix attempt for profile lookup after NeoHub firmware update.

### v1.0.0 (2026-04-02)
- Initial release.

---

## License

MIT
