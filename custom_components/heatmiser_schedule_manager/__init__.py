"""Heatmiser Schedule Manager integration."""
from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

from neohubapi.neohub import (
    ATTR_DEVICES,
    ATTR_PROFILES,
    ATTR_PROFILES_0,
    ATTR_SYSTEM,
)
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    DAY_TO_SLOT,
    DAYS_OF_WEEK,
    DEFAULT_PROFILES,
    DOMAIN,
    FORMAT_SLOTS,
    HEATING_LEVELS_4,
    HEATING_LEVELS_6,
    PROFILES_FILE,
    SERVICE_GET_SCHEDULE,
    SERVICE_RELOAD_PROFILES,
    SERVICE_SET_DAY_SCHEDULE,
    SERVICE_SET_WEEK_SCHEDULE,
)

_LOGGER = logging.getLogger(__name__)

HEATMISERNEO_DOMAIN = "heatmiserneo"

SERVICE_SET_DAY_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required("device_name"): cv.string,
        vol.Required("day"): vol.In(DAYS_OF_WEEK),

        vol.Optional("profile"): cv.string,
        vol.Optional("schedule"): vol.All(
            cv.ensure_list,
            [
                vol.Schema(
                    {
                        vol.Required("time"): cv.string,
                        vol.Required("temp"): vol.Coerce(float),
                    }
                )
            ],
        ),
    },
    extra=vol.ALLOW_EXTRA,
)

SERVICE_SET_WEEK_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required("device_name"): cv.string,
        vol.Optional("profile"): cv.string,
        vol.Optional("schedule"): vol.All(
            cv.ensure_list,
            [
                vol.Schema(
                    {
                        vol.Required("time"): cv.string,
                        vol.Required("temp"): vol.Coerce(float),
                    }
                )
            ],
        ),
    },
    extra=vol.ALLOW_EXTRA,
)


def _schedule_format_key(schedule_format) -> str:
    """Return lowercase string key for a ScheduleFormat enum value (seven/two/one/zero)."""
    return schedule_format.name.lower()


def _build_day_info(setpoints: list[dict], heating_levels: int) -> dict:
    """Build a STORE_PROFILE day dict from a list of {time, temp} setpoints."""
    level_names = HEATING_LEVELS_4 if heating_levels <= 4 else HEATING_LEVELS_6
    sorted_setpoints = sorted(setpoints, key=lambda x: x["time"])
    result = {}
    for i, name in enumerate(level_names):
        if i < len(sorted_setpoints):
            result[name] = [sorted_setpoints[i]["time"], sorted_setpoints[i]["temp"]]
        else:
            result[name] = ["24:00", 5]
    return result


def _extract_day_info(profile, slot: str, heating_levels: int) -> dict | None:
    """Extract a day's level dict from a profile object, preserving exact hub key names.

    Returns the raw {level_name: value} dict from the hub without remapping,
    so preserved days are round-tripped with their original label assignments intact.
    """
    if hasattr(profile, "info"):
        info = profile.info
    elif hasattr(profile, "profiles") and profile.profiles:
        info = profile.profiles[0]
    else:
        return None

    day_data = getattr(info, slot, None)
    if day_data is None:
        return None

    # Hub returns 4-element arrays [time, temp, extra, flag] for existing slots,
    # but STORE_PROFILE only accepts 2-element arrays [time, temp].
    # Truncate to avoid silent write failures from malformed payloads.
    return {
        key: value[:2] if isinstance(value, (list, tuple)) and len(value) > 2 else value
        for key, value in day_data.__dict__.items()
    }


def _build_profile_info(
    source_profile,
    slots: list[str],
    target_slot: str,
    new_day_info: dict,
    heating_levels: int,
) -> dict:
    """Build the full profile info dict for STORE_PROFILE.

    Preserves all existing slots from source_profile, replacing target_slot
    with new_day_info. source_profile may be None (all slots will be empty).
    """
    level_names = HEATING_LEVELS_4 if heating_levels <= 4 else HEATING_LEVELS_6
    empty_slot = {name: ["24:00", 5] for name in level_names}

    profile_info = {}
    for slot in slots:
        if slot == target_slot:
            profile_info[slot] = new_day_info
        else:
            existing = (
                _extract_day_info(source_profile, slot, heating_levels)
                if source_profile is not None
                else None
            )
            profile_info[slot] = existing if existing is not None else empty_slot
    return profile_info


def _lookup_profile(profiles: dict, profile_id: int):
    """Look up a profile by integer ID, handling string keys and list-wrapped values.

    NeoHub firmware updates have been observed to change the profile dict format:
    - Keys may be strings ("6") instead of integers (6)
    - Values may be wrapped in a single-element list ([profile_obj]) instead of bare objects
    """
    profile = profiles.get(profile_id) or profiles.get(str(profile_id))
    if profile is None:
        _LOGGER.debug(
            "Profile id=%s not found. Available keys: %s (types: %s)",
            profile_id,
            list(profiles.keys())[:10],
            list({type(k).__name__ for k in profiles.keys()}),
        )
        return None
    if isinstance(profile, list):
        _LOGGER.debug(
            "Profile id=%s value is a list (len=%d); unwrapping first element. "
            "This suggests a NeoHub firmware format change.",
            profile_id, len(profile),
        )
        profile = profile[0] if profile else None
    return profile


def _find_profile_by_name(profiles: dict, name: str):
    """Return (profile_id, profile) for the first profile matching name, or (None, None)."""
    for pid, p in profiles.items():
        if isinstance(p, list):
            p = p[0] if p else None
        if p is not None and p.name == name:
            return pid, p
    return None, None


def _log_profile_slots(label: str, profile_info: dict) -> None:
    """Log every slot/level in a profile_info dict at DEBUG level."""
    _LOGGER.debug("--- %s ---", label)
    for slot, levels in profile_info.items():
        if isinstance(levels, dict):
            for level, value in levels.items():
                _LOGGER.debug("  slot=%-12s  level=%-8s  value=%s", slot, level, value)
        else:
            _LOGGER.debug("  slot=%-12s  raw=%s", slot, levels)


def _log_extract_debug(source_profile, slots: list[str], heating_levels: int) -> None:
    """Log what _extract_day_info reads from the existing profile for each slot."""
    _LOGGER.debug("--- Existing profile read-back before write ---")
    if source_profile is None:
        _LOGGER.debug("  source_profile is None — all unmodified slots will be set to 24:00/5")
        return
    # Log raw object type so we can see its structure
    _LOGGER.debug("  source_profile type: %s", type(source_profile))
    if hasattr(source_profile, "info"):
        _LOGGER.debug("  source_profile.info type: %s  attrs: %s",
                      type(source_profile.info),
                      [a for a in dir(source_profile.info) if not a.startswith("_")])
    elif hasattr(source_profile, "profiles"):
        _LOGGER.debug("  source_profile.profiles: %s", source_profile.profiles)
    for slot in slots:
        extracted = _extract_day_info(source_profile, slot, heating_levels)
        if extracted is None:
            _LOGGER.debug("  slot=%-12s  -> NOT FOUND (will use 24:00/5 placeholder)", slot)
        else:
            for level, value in extracted.items():
                _LOGGER.debug("  slot=%-12s  level=%-8s  read=%s", slot, level, value)


async def _log_profile_after_refresh(coordinator, profile_id: int, profile_name: str, heating_levels: int) -> None:
    """Log the full profile as reported by the hub after a coordinator refresh."""
    _LOGGER.debug("--- Hub profile state after write (profile '%s' id=%s) ---", profile_name, profile_id)
    try:
        _, all_live_data = coordinator.data
        profiles = all_live_data.get(ATTR_PROFILES, {})
        profile = _lookup_profile(profiles, profile_id)
        if profile is None:
            _LOGGER.debug("  Profile id=%s not found in post-refresh data", profile_id)
            return
        for slot in [a for a in dir(profile.info) if not a.startswith("_")]:
            slot_data = getattr(profile.info, slot, None)
            if slot_data is None:
                continue
            if hasattr(slot_data, "__dict__"):
                _LOGGER.debug("  slot=%-12s  %s", slot, slot_data.__dict__)
            else:
                _LOGGER.debug("  slot=%-12s  %s", slot, slot_data)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("  Could not read back profile: %s", exc)


def _create_profiles_file(profiles_path: Path, device_names: list[str]) -> dict:
    """Create the profiles YAML file with defaults and per-device stubs."""
    sections: dict = {"default": DEFAULT_PROFILES}
    for name in sorted(device_names):
        sections[name] = DEFAULT_PROFILES

    lines = [
        "# Heatmiser Schedule Manager — heating schedule profiles",
        "# Edit this file to customise per-room schedules, then call",
        "# heatmiser_schedule_manager.reload_profiles to apply without restarting HA.",
        "#",
        "# Structure: each top-level key is either 'default' or a thermostat name",
        "# exactly as it appears in Home Assistant. When setting a schedule,",
        "# the device's own section is used if present, otherwise 'default' is used.",
        "#",
        "# Times in HH:MM format. Temperatures in °C.",
        "# Up to 4 setpoints per day (or 6 for 6-level hubs).",
        "",
    ]
    lines.append(yaml.dump(sections, default_flow_style=False, sort_keys=False, allow_unicode=True))
    profiles_path.write_text("\n".join(lines), encoding="utf-8")
    try:
        os.chmod(profiles_path, 0o666)
    except OSError as exc:
        _LOGGER.warning("Could not set permissions on %s: %s", profiles_path, exc)
    _LOGGER.info("Created profiles file at %s with sections: %s", profiles_path, list(sections.keys()))
    return sections


def _load_or_create_profiles(profiles_path: Path, device_names: list[str] | None = None) -> dict:
    """Load profiles from YAML file, creating it with defaults if it doesn't exist."""
    if not profiles_path.exists():
        return _create_profiles_file(profiles_path, device_names or [])

    loaded = yaml.safe_load(profiles_path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        _LOGGER.error("Profiles file %s is not a valid YAML mapping; using defaults", profiles_path)
        return {"default": dict(DEFAULT_PROFILES)}
    return loaded


def _resolve_profile(profiles: dict, device_name: str, profile_name: str) -> list | None:
    """Look up a profile for a device, falling back to default then flat format.

    Supports two file layouts:
      - Sectioned: top-level keys are device names / 'default', values are dicts of profiles
      - Flat (legacy): top-level keys are profile names, values are setpoint lists
    """
    # Sectioned format: device-specific section
    device_section = profiles.get(device_name)
    if isinstance(device_section, dict) and profile_name in device_section:
        return device_section[profile_name]

    # Sectioned format: default section
    default_section = profiles.get("default")
    if isinstance(default_section, dict) and profile_name in default_section:
        return default_section[profile_name]

    # Flat (legacy) format
    value = profiles.get(profile_name)
    if isinstance(value, list):
        return value

    return None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Heatmiser Schedule Manager from a config entry."""
    profiles_path = Path(hass.config.path(PROFILES_FILE))

    # Get device names from the heatmiserneo coordinator so the generated file
    # includes a section stub for every thermostat.
    device_names: list[str] = []
    neo_entry_id = entry.data.get("heatmiserneo_entry_id")
    neo_entry = hass.config_entries.async_get_entry(neo_entry_id)
    if neo_entry is not None:
        try:
            devices, _ = neo_entry.runtime_data.coordinator.data
            device_names = [
                name for name, dev in devices.items()
                if not getattr(dev, "time_clock_mode", False)
            ]
        except Exception:  # noqa: BLE001
            pass

    profiles: dict = await hass.async_add_executor_job(
        _load_or_create_profiles, profiles_path, device_names
    )
    _LOGGER.info("Loaded profiles file with sections: %s", list(profiles.keys()))

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"profiles": profiles}

    async def async_handle_set_day_schedule(call: ServiceCall) -> None:
        """Handle the set_day_schedule service call."""
        device_name: str = call.data["device_name"]
        day: str = call.data["day"]
        profile_name: str | None = call.data.get("profile")
        custom_schedule: list | None = call.data.get("schedule")

        if not profile_name and not custom_schedule:
            raise HomeAssistantError("Either 'profile' or 'schedule' must be provided")
        if profile_name and custom_schedule:
            raise HomeAssistantError("Provide either 'profile' or 'schedule', not both")

        profiles = hass.data[DOMAIN][entry.entry_id]["profiles"]

        # Borrow the hub and coordinator from the heatmiserneo integration
        neo_entry_id = entry.data.get("heatmiserneo_entry_id")
        neo_entry = hass.config_entries.async_get_entry(neo_entry_id)
        if neo_entry is None:
            raise HomeAssistantError(
                "Could not find the heatmiserneo config entry. "
                "Ensure the Heatmiser Neo integration is configured."
            )

        hub = neo_entry.runtime_data.hub
        coordinator = neo_entry.runtime_data.coordinator

        # Use coordinator's cached data — no extra network call
        devices, all_live_data = coordinator.data

        device = devices.get(device_name)
        if device is None:
            raise HomeAssistantError(
                f"Device '{device_name}' not found. "
                f"Available devices: {sorted(devices.keys())}"
            )

        if device.time_clock_mode:
            raise HomeAssistantError(
                f"Device '{device_name}' is a timer/switch, not a thermostat. "
                "This service only supports heating thermostats."
            )

        system = all_live_data[ATTR_SYSTEM]
        format_key = _schedule_format_key(system.FORMAT)

        if format_key == "zero":
            raise HomeAssistantError(
                "NeoHub is in non-programmable mode (FORMAT=ZERO). "
                "Profiles cannot be updated."
            )

        heating_levels = getattr(system, "HEATING_LEVELS", 4)
        target_slot = DAY_TO_SLOT.get(format_key, DAY_TO_SLOT["seven"])[day]
        slots = FORMAT_SLOTS.get(format_key, FORMAT_SLOTS["seven"])

        if profile_name:
            resolved = _resolve_profile(profiles, device_name, profile_name)
            if resolved is None:
                raise HomeAssistantError(
                    f"Profile '{profile_name}' not found for device '{device_name}' "
                    f"and no default exists. Edit {PROFILES_FILE} to add it."
                )
            new_setpoints = resolved
        else:
            new_setpoints = custom_schedule
        new_day_info = _build_day_info(new_setpoints, heating_levels)

        profile_id = int(device.active_profile)
        profiles = all_live_data.get(ATTR_PROFILES, {})

        if profile_id == 0:
            await _handle_profile_zero(
                hub=hub,
                coordinator=coordinator,
                device_name=device_name,
                device=device,
                profiles=profiles,
                all_live_data=all_live_data,
                slots=slots,
                target_slot=target_slot,
                new_day_info=new_day_info,
                heating_levels=heating_levels,
                day=day,
                applied=f"profile '{profile_name}'" if profile_name else "custom schedule",
            )
            return

        # Named profile — update it directly
        profile = _lookup_profile(profiles, profile_id)
        if profile is None:
            raise HomeAssistantError(
                f"Profile {profile_id} for device '{device_name}' not found in hub data."
            )

        _log_extract_debug(profile, slots, heating_levels)
        profile_info = _build_profile_info(
            profile, slots, target_slot, new_day_info, heating_levels
        )
        _log_profile_slots(f"STORE_PROFILE payload — profile '{profile.name}' id={profile_id}", profile_info)

        msg = {
            "STORE_PROFILE": {
                "ID": profile_id,
                "info": profile_info,
                "name": profile.name,
            }
        }
        await hub._send(msg, {"result": "profile created"})  # noqa: SLF001

        applied = f"profile '{profile_name}'" if profile_name else "custom schedule"
        _LOGGER.info(
            "Updated slot '%s' (day '%s') for device '%s' using %s",
            target_slot, day, device_name, applied,
        )
        await coordinator.async_request_refresh()
        await _log_profile_after_refresh(coordinator, profile_id, profile.name, heating_levels)

    async def async_handle_set_week_schedule(call: ServiceCall) -> None:
        """Handle the set_week_schedule service call — applies one profile to every slot."""
        device_name: str = call.data["device_name"]
        profile_name: str | None = call.data.get("profile")
        custom_schedule: list | None = call.data.get("schedule")

        if not profile_name and not custom_schedule:
            raise HomeAssistantError("Either 'profile' or 'schedule' must be provided")
        if profile_name and custom_schedule:
            raise HomeAssistantError("Provide either 'profile' or 'schedule', not both")

        profiles = hass.data[DOMAIN][entry.entry_id]["profiles"]

        neo_entry_id = entry.data.get("heatmiserneo_entry_id")
        neo_entry = hass.config_entries.async_get_entry(neo_entry_id)
        if neo_entry is None:
            raise HomeAssistantError("Could not find the heatmiserneo config entry.")

        hub = neo_entry.runtime_data.hub
        coordinator = neo_entry.runtime_data.coordinator
        devices, all_live_data = coordinator.data

        device = devices.get(device_name)
        if device is None:
            raise HomeAssistantError(
                f"Device '{device_name}' not found. "
                f"Available devices: {sorted(devices.keys())}"
            )

        system = all_live_data[ATTR_SYSTEM]
        format_key = _schedule_format_key(system.FORMAT)
        if format_key == "zero":
            raise HomeAssistantError("NeoHub is in non-programmable mode (FORMAT=ZERO).")

        heating_levels = getattr(system, "HEATING_LEVELS", 4)
        slots = FORMAT_SLOTS.get(format_key, FORMAT_SLOTS["seven"])

        if profile_name:
            resolved = _resolve_profile(profiles, device_name, profile_name)
            if resolved is None:
                raise HomeAssistantError(
                    f"Profile '{profile_name}' not found for device '{device_name}' "
                    f"and no default exists. Edit {PROFILES_FILE} to add it."
                )
            new_setpoints = resolved
        else:
            new_setpoints = custom_schedule

        new_day_info = _build_day_info(new_setpoints, heating_levels)

        # Build profile_info with every slot set to the same day_info
        profile_info = {slot: new_day_info for slot in slots}

        profile_id = int(device.active_profile)
        hub_profiles = all_live_data.get(ATTR_PROFILES, {})

        if profile_id == 0:
            managed_name = f"HSM_{device_name}"
            existing_id, _ = _find_profile_by_name(hub_profiles, managed_name)

            if existing_id is not None:
                msg = {"STORE_PROFILE": {"ID": existing_id, "info": profile_info, "name": managed_name}}
                await hub._send(msg, {"result": "profile created"})  # noqa: SLF001
                if int(device.active_profile) == 0:
                    await device.set_profile_id(existing_id)
            else:
                create_msg = {"STORE_PROFILE": {"info": profile_info, "name": managed_name}}
                await hub._send(create_msg, {"result": "profile created"})  # noqa: SLF001
                await coordinator.async_request_refresh()
                _, updated_all_data = coordinator.data
                updated_profiles = updated_all_data.get(ATTR_PROFILES, {})
                new_id, _ = _find_profile_by_name(updated_profiles, managed_name)
                if new_id is None:
                    raise HomeAssistantError(f"Created profile '{managed_name}' but could not find it.")
                updated_device = coordinator.data[0].get(device_name)
                await updated_device.set_profile_id(new_id)
        else:
            profile = _lookup_profile(hub_profiles, profile_id)
            if profile is None:
                raise HomeAssistantError(f"Profile {profile_id} for '{device_name}' not found.")
            msg = {"STORE_PROFILE": {"ID": profile_id, "info": profile_info, "name": profile.name}}
            await hub._send(msg, {"result": "profile created"})  # noqa: SLF001

        applied = f"profile '{profile_name}'" if profile_name else "custom schedule"
        _LOGGER.info(
            "Set all slots %s for device '%s' using %s", slots, device_name, applied
        )
        await coordinator.async_request_refresh()

    async def async_handle_get_schedule(call: ServiceCall) -> dict:
        """Return and log the current hub schedule for a device."""
        device_name: str = call.data["device_name"]

        neo_entry_id = entry.data.get("heatmiserneo_entry_id")
        neo_entry = hass.config_entries.async_get_entry(neo_entry_id)
        if neo_entry is None:
            raise HomeAssistantError("Could not find the heatmiserneo config entry.")

        coordinator = neo_entry.runtime_data.coordinator
        devices, all_live_data = coordinator.data

        device = devices.get(device_name)
        if device is None:
            raise HomeAssistantError(
                f"Device '{device_name}' not found. "
                f"Available devices: {sorted(devices.keys())}"
            )

        system = all_live_data[ATTR_SYSTEM]
        format_key = _schedule_format_key(system.FORMAT)
        profile_id = int(device.active_profile)
        hub_profiles = all_live_data.get(ATTR_PROFILES, {})

        if profile_id == 0:
            profile_0_map = all_live_data.get(ATTR_PROFILES_0, {})
            raw_profile = profile_0_map.get(device.device_id)
            profile_name = "per-device profile 0"
        else:
            raw_profile = _lookup_profile(hub_profiles, profile_id)
            profile_name = getattr(raw_profile, "name", str(profile_id))

        _LOGGER.info(
            "=== Schedule for '%s' | profile: %s (id=%s) | format: %s ===",
            device_name, profile_name, profile_id, format_key,
        )

        schedule = {}
        if raw_profile is not None:
            if hasattr(raw_profile, "info"):
                info = raw_profile.info
            elif hasattr(raw_profile, "profiles") and raw_profile.profiles:
                info = raw_profile.profiles[0]
            else:
                info = None

            if info is not None:
                for slot in sorted(vars(info).keys()):
                    day_data = getattr(info, slot)
                    day_levels = []
                    for level_name, value in sorted(vars(day_data).items()):
                        time_val = value[0] if len(value) > 0 else "?"
                        temp_val = value[1] if len(value) > 1 else "?"
                        active = not value[3] if len(value) > 3 else True
                        if time_val != "24:00" and active:
                            day_levels.append({"level": level_name, "time": time_val, "temp": temp_val})
                    day_levels.sort(key=lambda x: x["time"])
                    schedule[slot] = day_levels
                    _LOGGER.info(
                        "  %-12s %s",
                        slot,
                        "  ".join(f"{lv['time']}={lv['temp']}°" for lv in day_levels) or "(no active setpoints)",
                    )

        return {
            "device": device_name,
            "profile_id": profile_id,
            "profile_name": profile_name,
            "format": format_key,
            "schedule": schedule,
        }

    async def async_handle_reload_profiles(call: ServiceCall) -> None:
        """Reload profiles from the YAML file without restarting HA."""
        reloaded: dict = await hass.async_add_executor_job(_load_or_create_profiles, profiles_path)
        hass.data[DOMAIN][entry.entry_id]["profiles"] = reloaded
        _LOGGER.info("Reloaded %d profiles from %s", len(reloaded), profiles_path)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_DAY_SCHEDULE,
        async_handle_set_day_schedule,
        schema=SERVICE_SET_DAY_SCHEDULE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_WEEK_SCHEDULE,
        async_handle_set_week_schedule,
        schema=SERVICE_SET_WEEK_SCHEDULE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_SCHEDULE,
        async_handle_get_schedule,
        schema=vol.Schema({vol.Required("device_name"): cv.string}, extra=vol.ALLOW_EXTRA),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RELOAD_PROFILES,
        async_handle_reload_profiles,
        schema=vol.Schema({}),
    )

    _LOGGER.info("Heatmiser Schedule Manager loaded")
    return True


async def _handle_profile_zero(
    hub,
    coordinator,
    device_name: str,
    device,
    profiles: dict,
    all_live_data: dict,
    slots: list[str],
    target_slot: str,
    new_day_info: dict,
    heating_levels: int,
    day: str,
    applied: str,
) -> None:
    """Handle set_day_schedule for a device using per-device profile 0.

    Creates (or updates) a named profile 'HSM_{device_name}', seeded from
    the device's existing profile 0 data, then assigns it to the device.
    On subsequent calls the HSM profile is updated in place.
    """
    managed_name = f"HSM_{device_name}"

    # Check whether the HSM profile already exists
    existing_id, existing_profile = _find_profile_by_name(profiles, managed_name)

    if existing_id is not None:
        # Update the existing HSM profile
        _log_extract_debug(existing_profile, slots, heating_levels)
        profile_info = _build_profile_info(
            existing_profile, slots, target_slot, new_day_info, heating_levels
        )
        _log_profile_slots(f"STORE_PROFILE payload — HSM profile '{managed_name}' id={existing_id}", profile_info)

        msg = {
            "STORE_PROFILE": {
                "ID": existing_id,
                "info": profile_info,
                "name": managed_name,
            }
        }
        await hub._send(msg, {"result": "profile created"})  # noqa: SLF001

        # Re-assign in case the device was manually switched back to profile 0
        if int(device.active_profile) == 0:
            await device.set_profile_id(existing_id)
            _LOGGER.info(
                "Re-assigned existing profile '%s' (id=%d) to device '%s'",
                managed_name, existing_id, device_name,
            )

        _LOGGER.info(
            "Updated slot '%s' (day '%s') for device '%s' using %s "
            "(HSM profile '%s' id=%d)",
            target_slot, day, device_name, applied, managed_name, existing_id,
        )
        await coordinator.async_request_refresh()
        await _log_profile_after_refresh(coordinator, existing_id, managed_name, heating_levels)
        return

    # Create a new named profile seeded from profile 0 data
    profile_0_data = all_live_data.get(ATTR_PROFILES_0, {}).get(device.device_id)
    if profile_0_data is None:
        _LOGGER.warning(
            "No profile 0 data found for device '%s' (device_id=%s); "
            "new profile will have empty slots for unmodified days",
            device_name, device.device_id,
        )

    _log_extract_debug(profile_0_data, slots, heating_levels)
    profile_info = _build_profile_info(
        profile_0_data, slots, target_slot, new_day_info, heating_levels
    )
    _log_profile_slots(f"STORE_PROFILE payload — new HSM profile '{managed_name}'", profile_info)

    create_msg = {
        "STORE_PROFILE": {
            "info": profile_info,
            "name": managed_name,
        }
    }
    await hub._send(create_msg, {"result": "profile created"})  # noqa: SLF001

    # Refresh coordinator to get the newly created profile's ID
    await coordinator.async_request_refresh()
    updated_devices, updated_all_data = coordinator.data
    updated_profiles = updated_all_data.get(ATTR_PROFILES, {})
    new_id, _ = _find_profile_by_name(updated_profiles, managed_name)

    if new_id is None:
        raise HomeAssistantError(
            f"Created profile '{managed_name}' but could not find it in hub data. "
            "The profile may still have been created — check the Heatmiser app."
        )

    # Assign using the coordinator's fresh NeoStat (which shares the coordinator's hub)
    updated_device = updated_devices.get(device_name)
    if updated_device is None:
        raise HomeAssistantError(
            f"Device '{device_name}' disappeared after profile creation."
        )

    await updated_device.set_profile_id(new_id)

    _LOGGER.info(
        "Created profile '%s' (id=%d), seeded from profile 0, "
        "assigned to device '%s'. Updated slot '%s' (day '%s') using %s",
        managed_name, new_id, device_name, target_slot, day, applied,
    )
    await coordinator.async_request_refresh()
    await _log_profile_after_refresh(coordinator, new_id, managed_name, heating_levels)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.data[DOMAIN].pop(entry.entry_id, None)
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, SERVICE_SET_DAY_SCHEDULE)
        hass.services.async_remove(DOMAIN, SERVICE_SET_WEEK_SCHEDULE)
        hass.services.async_remove(DOMAIN, SERVICE_GET_SCHEDULE)
        hass.services.async_remove(DOMAIN, SERVICE_RELOAD_PROFILES)
    return True
