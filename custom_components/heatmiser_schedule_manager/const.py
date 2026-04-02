"""Constants for Heatmiser Schedule Manager."""

DOMAIN = "heatmiser_schedule_manager"

# Service names
SERVICE_SET_DAY_SCHEDULE = "set_day_schedule"
SERVICE_SET_WEEK_SCHEDULE = "set_week_schedule"
SERVICE_GET_SCHEDULE = "get_schedule"
SERVICE_RELOAD_PROFILES = "reload_profiles"

# User-editable profiles file (relative to HA config dir)
PROFILES_FILE = "heatmiser_schedule_profiles.yaml"

DAYS_OF_WEEK = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]

# Heating level names in NeoHub profile format
HEATING_LEVELS_4 = ["wake", "leave", "return", "sleep"]
HEATING_LEVELS_6 = ["wake", "level1", "level2", "level3", "level4", "sleep"]

# Map a user-specified day to the correct profile slot per schedule format.
# NeoHub stores days as lowercase strings matching the neohubapi Weekday enum values.
DAY_TO_SLOT = {
    # ScheduleFormat.SEVEN — direct mapping
    "seven": {
        "monday": "monday",
        "tuesday": "tuesday",
        "wednesday": "wednesday",
        "thursday": "thursday",
        "friday": "friday",
        "saturday": "saturday",
        "sunday": "sunday",
    },
    # ScheduleFormat.TWO — weekdays share "monday", weekend shares "sunday"
    "two": {
        "monday": "monday",
        "tuesday": "monday",
        "wednesday": "monday",
        "thursday": "monday",
        "friday": "monday",
        "saturday": "sunday",
        "sunday": "sunday",
    },
    # ScheduleFormat.ONE — every day shares "sunday"
    "one": {day: "sunday" for day in DAYS_OF_WEEK},
}

# All slots per schedule format (keys present in a profile's info object)
FORMAT_SLOTS = {
    "seven": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
    "two": ["monday", "sunday"],
    "one": ["sunday"],
}

# Built-in schedule profiles (time/temp setpoints per day)
DEFAULT_PROFILES = {
    "workday": [
        {"time": "05:15", "temp": 27.0},
        {"time": "08:00", "temp": 16.0},
        {"time": "19:00", "temp": 25.0},
        {"time": "21:00", "temp": 16.0},
    ],
    "weekend": [
        {"time": "08:00", "temp": 26.0},
        {"time": "10:00", "temp": 16.0},
        {"time": "18:00", "temp": 23.5},
        {"time": "22:30", "temp": 16.0},
    ],
    "wfh": [
        {"time": "07:00", "temp": 26.0},
        {"time": "09:00", "temp": 16.5},
        {"time": "18:00", "temp": 23.5},
        {"time": "22:00", "temp": 16.0},
    ],
    "holiday": [
        {"time": "00:00", "temp": 15.0},
    ],
    "all_day_comfort": [
        {"time": "00:00", "temp": 20.0},
    ],
    "eco": [
        {"time": "00:00", "temp": 16.0},
    ],
    "nonworkday": [
        {"time": "07:00", "temp": 26.0},
        {"time": "09:00", "temp": 16.0},
        {"time": "18:00", "temp": 25.5},
        {"time": "22:00", "temp": 16.0},
    ],
}
