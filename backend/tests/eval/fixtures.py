"""Shared simulation / viewer fixtures for chatbot eval cases."""

from __future__ import annotations

WATER_PIPE_INPUT_FIELDS: list[dict] = [
    {
        "key": "system/controlDict::startTime",
        "label": "Start Time",
        "type": "number",
        "default": "0",
        "min": "0",
        "max": "1000",
    },
    {
        "key": "system/controlDict::endTime",
        "label": "End Time",
        "type": "number",
        "default": "1",
        "min": "0.001",
        "max": "1000",
    },
    {
        "key": "system/controlDict::deltaT",
        "label": "deltaT",
        "type": "number",
        "default": "0.01",
        "min": "1e-6",
        "max": "1",
    },
    {
        "key": "system/controlDict::writeInterval",
        "label": "Write Interval",
        "type": "number",
        "default": "0.1",
        "min": "0.001",
        "max": "100",
    },
    {
        "key": "system/controlDict::timePrecision",
        "label": "Time Precision",
        "type": "number",
        "default": "6",
        "min": "0",
        "max": "12",
    },
]

JOB_VIEWER_STATE: dict = {
    "times": ["0", "0.05", "0.1", "0.15", "0.2"],
    "current_time": "0.1",
    "scalars": ["U", "p", "alpha.water"],
    "files": ["internal.vtk", "walls.vtk"],
    "regions": ["fluid", "walls"],
    "playing": False,
    "scalar": "p",
    "file": "internal.vtk",
    "region": "fluid",
    "show_streamlines": False,
}

FIELD_PROFILES: dict[str, list[dict]] = {
    "water_pipe": WATER_PIPE_INPUT_FIELDS,
}

VIEWER_PROFILES: dict[str, dict] = {
    "job_vtk": JOB_VIEWER_STATE,
}


def resolve_fields(profile: str | None) -> list[dict] | None:
    if not profile:
        return None
    return FIELD_PROFILES.get(profile)


def resolve_viewer(profile: str | None) -> dict | None:
    if not profile:
        return None
    return VIEWER_PROFILES.get(profile)
