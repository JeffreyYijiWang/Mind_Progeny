from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, validate_default=True)
    name: str = "unmeasured-duet2"
    synthetic: bool = False
    needle_gauge: int = Field(default=23, gt=0)
    needle_length_mm: float = Field(default=12.7, gt=0)
    needle_gauge_confirmed: bool = True
    needle_length_confirmed: bool = True
    needle_inner_diameter_mm: float | None = None
    needle_outer_diameter_mm: float | None = None
    syringe_barrel_inner_diameter_mm: float | None = None
    plunger_stroke_mm: float | None = None
    mm3_per_e_unit: float | None = None
    plunger_mm_per_e_unit: float | None = None
    positive_extrusion_direction: Literal[-1, 1] = 1
    capacity_mm3: float | None = None
    bead_width_mm: float | None = None
    deposition_height_mm: float = Field(default=0.5, gt=0)
    first_deposition_tip_height_mm: float | None = None
    substrate_z_mm: float | None = None
    needle_standoff_mm: float | None = None
    # User-specified 4 in X by 5 in Y per quadrant, tiled 2 x 2 around XY zero.
    x_min: float = -101.6
    x_max: float = 101.6
    y_min: float = -127
    y_max: float = 127
    z_min: float | None = None
    z_max: float | None = None
    holder_radius_mm: float | None = None
    holder_bottom_above_tip_mm: float | None = None
    travel_clearance_mm: float | None = None
    edge_margin_mm: float | None = None
    centerline_margin_mm: float | None = None
    xy_speed_mm_s: float | None = None
    z_speed_mm_s: float | None = None
    e_speed_units_s: float | None = None
    xy_accel_mm_s2: float | None = None
    z_accel_mm_s2: float | None = None
    e_accel_units_s2: float | None = None
    deposition_speed_mm_s: float | None = None
    grid_mm: float = Field(default=0.5, gt=0)
    sample_mm: float = Field(default=0.5, gt=0)
    spread_factor: float = Field(default=1.0, gt=0)
    slicer_filament_diameter_mm: float = Field(default=1.75, gt=0)
    slicer_e_mode: Literal["filament_mm", "mm3"] = "filament_mm"
    # Tool coordinates already include firmware offsets; no second offset is applied.
    firmware_version: str | None = None
    firmware_tool_number: int | None = Field(default=None, ge=0)
    cold_extrusion_reviewed: bool = False
    machine_setup_reviewed: bool = False
    confirmed_fields: list[str] = Field(default_factory=list)
    duet_url: str = "http://hans.local"

    @model_validator(mode="after")
    def sane(self):
        if self.x_min >= self.x_max or self.y_min >= self.y_max:
            raise ValueError("Invalid travel bounds")
        for key in REQUIRED:
            value = getattr(self, key)
            if value is not None and key not in SIGNED and value <= 0:
                raise ValueError(f"{key} must be positive")
        if self.needle_standoff_mm is not None and self.needle_standoff_mm < 0:
            raise ValueError("Negative standoff")
        if self.z_min is not None and self.z_max is not None and self.z_min >= self.z_max:
            raise ValueError("Invalid Z range")
        if self.bead_width_mm and self.grid_mm > self.bead_width_mm / 2:
            raise ValueError("grid_mm must be <= half bead width")
        if self.bead_width_mm and self.grid_mm > self.bead_width_mm * self.spread_factor / 2:
            raise ValueError("grid_mm must resolve the modeled spread footprint")
        if self.sample_mm > self.grid_mm:
            raise ValueError("sample_mm must be <= grid_mm")
        if self.needle_inner_diameter_mm and self.needle_outer_diameter_mm:
            if self.needle_inner_diameter_mm >= self.needle_outer_diameter_mm:
                raise ValueError("Needle bore must be smaller than outer diameter")
        return self

    def missing(self, production=False):
        missing = [k for k in REQUIRED if getattr(self, k) is None]
        if production:
            for field in ('needle_gauge_confirmed', 'needle_length_confirmed'):
                if not getattr(self, field):
                    missing.append(field)
            missing += [f"confirm:{k}" for k in REQUIRED if k not in self.confirmed_fields]
            missing += [f"confirm:{k}" for k in ("positive_extrusion_direction", "spread_factor") if k not in self.confirmed_fields]
            if self.synthetic:
                missing.append("synthetic profile cannot authorize production")
            if not self.firmware_version:
                missing.append("firmware_version")
            if self.firmware_tool_number is None:
                missing.append("firmware_tool_number")
            for k in ("cold_extrusion_reviewed", "machine_setup_reviewed"):
                if not getattr(self, k):
                    missing.append(k)
        return missing

    def require(self, production=False):
        missing = self.missing(production)
        if missing:
            raise ValueError("Unresolved profile: " + ", ".join(missing))
        area = math.pi * (self.syringe_barrel_inner_diameter_mm / 2) ** 2
        if self.capacity_mm3 > area * self.plunger_stroke_mm + 1e-8:
            raise ValueError("Capacity exceeds barrel area × usable stroke")
        if self.first_deposition_tip_height_mm < self.deposition_height_mm:
            raise ValueError("First tip height must clear nominal new material surface")

    def digest(self):
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True).encode()).hexdigest()

    def needle_summary(self):
        return {'gauge': self.needle_gauge, 'length_mm': self.needle_length_mm,
                'length_inches': self.needle_length_mm / 25.4,
                'gauge_confirmed': self.needle_gauge_confirmed,
                'length_confirmed': self.needle_length_confirmed,
                'inner_diameter_mm': self.needle_inner_diameter_mm,
                'outer_diameter_mm': self.needle_outer_diameter_mm,
                'dimensions_are_synthetic': self.synthetic,
                'diameter_source': 'invented simulation values' if self.synthetic else 'separate measurements required; never inferred from gauge or length'}


SIGNED = {"substrate_z_mm", "z_min", "needle_standoff_mm"}
REQUIRED = [
    "needle_inner_diameter_mm", "needle_outer_diameter_mm", "syringe_barrel_inner_diameter_mm",
    "plunger_stroke_mm", "mm3_per_e_unit", "plunger_mm_per_e_unit", "capacity_mm3", "bead_width_mm",
    "first_deposition_tip_height_mm", "substrate_z_mm", "needle_standoff_mm", "z_min", "z_max",
    "holder_radius_mm", "holder_bottom_above_tip_mm", "travel_clearance_mm", "edge_margin_mm",
    "centerline_margin_mm", "xy_speed_mm_s", "z_speed_mm_s", "e_speed_units_s", "xy_accel_mm_s2",
    "z_accel_mm_s2", "e_accel_units_s2", "deposition_speed_mm_s",
]


def load_profile(path):
    return Profile.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def demo_profile():
    return Profile(name="SYNTHETIC-only", synthetic=True, needle_inner_diameter_mm=0.3,
        needle_outer_diameter_mm=0.6, syringe_barrel_inner_diameter_mm=20,
        plunger_stroke_mm=80, mm3_per_e_unit=100, plunger_mm_per_e_unit=100/(math.pi*100),
        capacity_mm3=20000, bead_width_mm=1, first_deposition_tip_height_mm=0.5,
        substrate_z_mm=0, needle_standoff_mm=0.1, z_min=0, z_max=100,
        holder_radius_mm=2, holder_bottom_above_tip_mm=12.7, travel_clearance_mm=2,
        edge_margin_mm=4, centerline_margin_mm=4, xy_speed_mm_s=30, z_speed_mm_s=8,
        e_speed_units_s=5, xy_accel_mm_s2=100, z_accel_mm_s2=40, e_accel_units_s2=20,
        deposition_speed_mm_s=8)
