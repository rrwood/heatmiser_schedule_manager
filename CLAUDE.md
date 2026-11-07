# Heatmiser Schedule Manager - Development Notes

## Project Overview

**Heatmiser Schedule Manager** is a Home Assistant custom integration (HACS) that adds schedule management services for Heatmiser Neo thermostats. It works alongside the existing [Heatmiser Neo](https://github.com/MindrustUK/Heatmiser-for-home-assistant) integration (domain `heatmiserneo`) and reuses its hub connection.

- **Repository**: https://github.com/rrwood/heatmiser_schedule_manager
- **Integration domain**: `heatmiser_schedule_manager`
- **Dependency**: `heatmiserneo` integration (must be installed and configured first)
- **NeoHub**: 192.168.111.111 (TCP 4242, null-terminated JSON API)

## Architecture

```
Home Assistant
    │
    ├── heatmiserneo integration (MindrustUK)
    │   ├── neohubapi library (NeoHub TCP/JSON client)
    │   │   └── GET_PROFILES → parses to SimpleNamespace objects
    │   ├── coordinator (polls hub, caches devices + all_live_data)
    │   │   └── all_live_data[ATTR_PROFILES] = profiles dict
    │   └── runtime_data: {hub, coordinator}
    │
    └── heatmiser_schedule_manager (this integration)
        ├── Borrows hub + coordinator from heatmiserneo runtime_data
        ├── Reads profiles from all_live_data[ATTR_PROFILES]
        ├── Writes STORE_PROFILE commands via hub._send()
        └── Exposes services: set_day_schedule, set_week_schedule, get_schedule, reload_profiles
```

## NeoHub Firmware Compatibility Fix (v1.0.2)

**Problem**: Around 2026-11-05, a NeoHub firmware update changed the `GET_PROFILES` response format:
- **Old format**: profiles dict keyed by profile ID (int or string), values = profile objects with `profiles` list
- **New format**: profiles dict keyed by **profile NAME** (e.g., `"HSM_En Suite Bathroom"`), values = `SimpleNamespace` with `info` attribute (per-day dict)
- The base integration also broke with `AttributeError: 'types.SimpleNamespace' object has no attribute 'profiles'` in helpers.py line 111

**Verified findings from the hub**:
```json
GET_PROFILES returns: {
  "HSM_En Suite Bathroom": {
    "PROFILE_ID": 6,
    "P_TYPE": 0,
    "group": null,
    "name": "HSM_En Suite Bathroom",
    "info": {
      "monday": {"wake": ["05:15", 27.0, 5.0, false], ...},
      ...
    }
  }
}
```
Only one profile returned. Unused slots = `["24:00", 5.0, 127.50, true]`.

**Solution in this integration**:
- Added helper functions: `_get_field()`, `_items()`, `_unwrap_profile()`, `_get_info()` — handle dict and SimpleNamespace uniformly
- `_lookup_profile()` falls back to scanning all profile values by their `PROFILE_ID` attribute when direct key lookup fails
- `_find_profile_by_name()` returns the profile's own `PROFILE_ID` attribute
- All direct attribute accesses (`.name`, `.info`, `.profiles[0]`) replaced with helper calls
- `get_schedule` and logging functions handle both dict and namespace day data

## Key Files

| File | Purpose |
|------|---------|
| `custom_components/heatmiser_schedule_manager/__init__.py` | Main integration code (services, profile lookup, schedule building) |
| `custom_components/heatmiser_schedule_manager/const.py` | Constants (profiles, day mappings, format slots) |
| `custom_components/heatmiser_schedule_manager/config_flow.py` | Config flow (selects heatmiserneo entry) |
| `custom_components/heatmiser_schedule_manager/manifest.json` | Integration metadata (version, dependencies) |
| `custom_components/heatmiser_schedule_manager/generate_icons.py` | Icon generation script |
| `icon.svg` / `logo.svg` | Source icons for HACS |

## Services

### `heatmiser_schedule_manager.set_day_schedule`
Update one day's schedule on one thermostat.
```yaml
device_name: "En Suite Bathroom"  # required, exact HA name
day: "friday"                      # required, monday..sunday
profile: "workday"                 # one of: named profile from YAML
# OR
schedule:                          # one of: custom setpoints
  - time: "05:15"
    temp: 27.0
```

### `heatmiser_schedule_manager.set_week_schedule`
Apply same profile to every day slot.

### `heatmiser_schedule_manager.get_schedule`
Read and return current hub schedule for a device (supports response).

### `heatmiser_schedule_manager.reload_profiles`
Reload YAML profiles file without restart.

## Profile Configuration

File: `heatmiser_schedule_profiles.yaml` (created on first load)
```yaml
default:
  workday:
    - time: "05:15"
      temp: 27.0
    - time: "08:00"
      temp: 16.0
  weekend: [...]
# Per-room overrides
Bathroom:
  workday: [...]
```

Built-in profiles: `workday`, `weekend`, `wfh`, `holiday`, `all_day_comfort`, `eco`, `nonworkday`

## Schedule Formats (hub-wide)

| Format | Slots | Behavior |
|--------|-------|----------|
| 7-day | Mon/Tue/Wed/Thu/Fri/Sat/Sun | Updates exact day |
| 2-day | Weekday + Weekend | Mon-Fri share, Sat/Sun share |
| 1-day | Single slot | All days share |

Auto-detected via `system.FORMAT`.

## Debug Logging

```yaml
logger:
  logs:
    custom_components.heatmiser_schedule_manager: debug
```

## Limitations

- Timer/switch devices not supported (only heating thermostats)
- Profiles are shared on hub — updating affects ALL thermostats using that profile
- Requires heatmiserneo integration configured with at least one named profile

## Development Commands

```bash
# Run git manager
./git-manager.sh status
./git-manager.sh push "message"
./git-manager.sh tag v1.0.3 "Release message"
./git-manager.sh release v1.0.3 "Title" "Notes"

# Generate icons
cd custom_components/heatmiser_schedule_manager
python generate_icons.py
```

## Related Repositories

- This integration: https://github.com/rrwood/heatmiser_schedule_manager
- Base integration: https://github.com/MindrustUK/Heatmiser-for-home-assistant
- neohubapi: https://github.com/MindrustUK/neohubapi

## Git History

- `fb44e35` - First fix attempt for profile issue after NeoHub firmware update
- `c445e56` - Robust fix: profiles keyed by name, SimpleNamespace info attribute
- `c957c0c` - README changelog
- `3671641` - CLAUDE.md created