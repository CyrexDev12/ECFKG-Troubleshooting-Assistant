"""Operator-side logical simulator. Never passed to the agent or tool router."""
from __future__ import annotations

import json
from pathlib import Path

from ecfkg.graph import ROOT
from ecfkg.schema import Observation, StrictModel


class Preset(StrictModel):
    id: str
    label: str
    state: dict[str, str]


class SymptomRule(StrictModel):
    field: str
    equals: str
    text: str


class SimulatorSpec(StrictModel):
    version: str
    presets: list[Preset]
    check_fields: dict[str, str]
    symptom_rules: list[SymptomRule]
    nominal_symptom: str


class Simulator:
    def __init__(self, preset_id: str = "SUPPLY", path: Path | None = None):
        self.__spec = SimulatorSpec.model_validate_json(
            (path or ROOT / "data/simulator/station.json").read_bytes())
        presets = {p.id: p for p in self.__spec.presets}
        if len(presets) != len(self.__spec.presets) or preset_id not in presets:
            raise ValueError("Invalid simulator preset")
        self.__state = dict(presets[preset_id].state)
        if not set(self.__spec.check_fields.values()) <= self.__state.keys():
            raise ValueError("Incomplete simulator state")

    @staticmethod
    def presets():
        spec = SimulatorSpec.model_validate_json((ROOT / "data/simulator/station.json").read_bytes())
        return {p.id: p.label for p in spec.presets}

    def symptom(self) -> str:
        for rule in self.__spec.symptom_rules:
            if self.__state[rule.field] == rule.equals:
                return rule.text
        return self.__spec.nominal_symptom

    def check(self, check_id: str) -> Observation:
        if check_id not in self.__spec.check_fields:
            raise ValueError("Unknown simulated check")
        return Observation(check_id=check_id, outcome=self.__state[self.__spec.check_fields[check_id]], origin="simulator")

    def available_checks(self):
        return set(self.__spec.check_fields)

