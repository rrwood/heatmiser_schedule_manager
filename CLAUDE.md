# Heatmiser Schedule Manager - Development Notes

## NeoHub Firmware Compatibility Fix (v1.0.2)

**Problem**: Around 2026-11-05, a NeoHub firmware update changed the `GET_PROFILES` response format:
- Profiles dict is now keyed by **profile NAME** (e.g., `"HSM_En Suite Bathroom"`) instead of profile ID
- Profile objects are `SimpleNamespace` with an `info` attribute (per-day dict) instead of a `profiles` list
- The base integration (MindrustUK/Heatmiser-for-home-assistant) also broke with `AttributeError: 'types.SimpleNamespace' object has no attribute 'profiles'` in helpers.py line 111

**Solution**: Made the integration robust to both old and new formats:
- Added helper functions: `_get_field()`, `_items()`, `_unwrap_profile()`, `_get_info()` — handle dict and SimpleNamespace uniformly
- `_lookup_profile()` now falls back to scanning all profile values by their `PROFILE_ID` attribute when direct key lookup fails
- `_find_profile_by_name()` returns the profile's own `PROFILE_ID` attribute
- All direct attribute accesses (`.name`, `.info`, `.profiles[0]`) replaced with helper calls
- `get_schedule` and logging functions handle both dict and namespace day data

## Key Files

- `custom_components/heatmiser_schedule_manager/__init__.py` — Main integration code
- `custom_components/heatmiser_schedule_manager/const.py` — Constants (profiles, day mappings, format slots)
- `custom_components/heatmiser_schedule_manager/config_flow.py` — Config flow (depends on heatmiserneo)
- `custom_components/heatmiser_schedule_manager/manifest.json` — Integration metadata (version, dependencies)

## Dependencies

- Requires `heatmiserneo` integration (MindrustUK/Heatmiser-for-home-assistant)
- Uses `neohubapi` library (installed as dependency of heatmiserneo)

## Testing

No automated tests. Manual testing requires:
1. Home Assistant instance with heatmiserneo configured
2. NeoHub at 192.168.111.111 (port 4242)
3. At least one thermostat with named profile assigned

## Service: `heatmiser_schedule_manager.set_day_schedule`

Parameters:
- `device_name` (required): Thermostat name as shown in HA
- `day` (required): monday..sunday
- `profile` OR `schedule` (one required): Named profile from YAML or custom setpoints

## Debug Logging

```yaml
logger:
  logs:
    custom_components.heatmiser_schedule_manager: debug
```

## Related Repositories

- This integration: https://github.com/rrwood/heatmiser_schedule_manager
- Base integration: https://github.com/MindrustUK/Heatmiser-for-home-assistant
- neohubapi: https://github.com/MindrustUK/neohubapi