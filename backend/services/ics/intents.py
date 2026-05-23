"""User intent taxonomy for the Intent Classification Service (ICS)."""

from __future__ import annotations

from enum import Enum
from typing import TypedDict


class UserIntent(str, Enum):
    """Canonical intent ids returned by ICS."""

    SIMULATION_EXECUTION = "simulation_execution"
    PARAMETER_CONFIGURATION = "parameter_configuration"
    RESULTS_ANALYSIS = "results_analysis"


class IntentDefinition(TypedDict):
    intent: str
    label: str
    description: str


INTENT_DEFINITIONS: list[IntentDefinition] = [
    {
        "intent": UserIntent.SIMULATION_EXECUTION.value,
        "label": "Simulation Execution",
        "description": (
            "Starting, stopping, or re-running the simulation; executing solver "
            "commands, Allrun scripts, mesh generation, or job control actions."
        ),
    },
    {
        "intent": UserIntent.PARAMETER_CONFIGURATION.value,
        "label": "Parameter Configuration",
        "description": (
            "Changing simulation inputs, boundary conditions, material properties, "
            "controlDict settings, or template field values before or between runs."
        ),
    },
    {
        "intent": UserIntent.RESULTS_ANALYSIS.value,
        "label": "Results Analysis",
        "description": (
            "Exploring finished results: VTK visualization, time steps, scalars, "
            "streamlines, interpreting fields, or comparing output data."
        ),
    },
]

VALID_INTENT_IDS = frozenset(d["intent"] for d in INTENT_DEFINITIONS)
