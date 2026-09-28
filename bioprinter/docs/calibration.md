# Measurements before production

The supplied brief confirms **23 gauge** and **1/2 inch needle length = 12.7 mm**.
Its original phrase “23 mm gauge” is not a 23 mm diameter. The gauge designation
does not determine an exact bore. No real-machine measurements were performed here.

1. Record manufacturer/model and measure or obtain bore and outer diameter separately.
   Record syringe barrel inner diameter and usable stroke, mounting length, holder radius
   and height above the tip. Do not put needle length into a diameter field.
2. Establish the substrate Z reference, first-deposition tip height and needle standoff.
   Deposition height (default 0.5 mm), tip Z and material surface Z are distinct.
3. With an operator-controlled machine setup and appropriate collection vessel, measure
   delivered volume for known E increments. Fit `mm3_per_e_unit` from measured positive
   displacement; measure `plunger_mm_per_e_unit` separately and record direction ±1.
   Account for usable starting volume and barrel/stroke limits. G92 is not a refill.
4. Measure bead width and retained height at the intended feed/flow rate and material
   conditions. Test starts/stops, adjoining paths, repeat passes, holes and crossings.
   The geometric model unions adjoining footprints and adds height for later events;
   it does not model pressure lag, spread, cure, sagging or free-surface stability.
5. Record measured safe XYZ/E speeds and acceleration limits, travel clearance, edge
   margins, needle/holder geometry, and actual Z travel. Test a dry path above the plate
   before material deposition under operator control. No dry run is automatic here.
6. Copy `config.example.yaml`, fill values, and add each measured field to
   `confirmed_fields`. Enter actual RRF version and firmware tool number. Review tool
   offsets, volumetric-E setting, extrusion units, feed/flow factors, bed compensation,
   machine limits and cold-extrusion permissions. Set review flags only after this work.

Example: slicer filament diameter 1.75 mm and E=10 mm means
`10 × π × (1.75/2)^2 = 24.0528 mm³`. If measured calibration is 100 mm³/E unit,
that is 0.240528 syringe E units. Those example numbers are **not hardware calibration**.
Needle diameter is absent from this conversion; barrel geometry constrains capacity.

The model uses rectangular bead cross-section width × nominal height per unit path
length; end caps, junctions and conservative raster cells are not volume-exact fluid
surfaces. `spread_factor` expands footprint at a fixed nominal height, so any value
other than 1 requires its own empirical model review. Partial support is recorded as
production-blocking. No bypass is provided: change paths/order or implement and verify
a more appropriate measured deposition model before production.

Changing a profile requires recomposition. Never edit final G-code and retain its old
approval/byte mapping. Refilling or replacing a syringe requires an explicit new measured
material state and physical reconciliation; automatic queue refill/reset is unsupported.
