# Solar Charger Case

A two-piece enclosure for a small solar charger with an exposed solar panel, cylindrical LED/lens nose, removable snap lid, and switch access. Revision **v0.3**. Units: **millimetres**. Intended for dry use.

**Fit-review prototype; not released as a validated print-ready design.**

| Feature | Dimension |
| --- | ---: |
| Overall envelope | 115.95 × 50.0 × 38.4 mm |
| Solar panel | 80.0 × 45.0 × 3.2 mm |
| Rear section height | 17.4 mm |
| Lens front / flange diameters | 31.3 / 35.0 mm |
| Lens flange thickness / groove width | 1.3 / 1.4 mm |
| Switch access slot | 13.8 × 5.8 mm; R0.8 corners |
| External end fillets | R0.6 mm |

The panel, battery, switch, and wiring retain their relative positions. The lens flange is captured by a groove split at the seam. Four experimental catches retain the lid. The switch-side front catch is offset to clear the access slot.

## Editable source

The principal file is [SmallSolarCase.py](source/SmallSolarCase/SmallSolarCase.py). Keep its manifest, `model_spec.py`, and [prototype-settings.json](source/SmallSolarCase/prototype-settings.json) together. [design-inputs.json](design-inputs.json) supplies measured dimensions.

Edit the JSON and regenerate for global layout changes. Some native feature dimensions are expression-linked; other sketch coordinates remain fixed. See [Fusion build instructions](docs/fusion-build.md).

## Exports and status

- [Assembly STEP](exports/v0.3/small-solar-case-v0.3.step): geometry is declared in centimetres; preserve those units on import.
- [Case body STL](exports/v0.3/case-body-v0.3-PROTOTYPE.stl) and [snap lid STL](exports/v0.3/snap-lid-v0.3-PROTOTYPE.stl): millimetres, in assembly coordinates.

The original Fusion build passed solid and timeline checks. Earlier STEP and mesh reviews verified the main envelope, slot, end fillets, groove, and closed consistently oriented meshes. The public exports preserve that geometry. The portable source has not yet been re-run in Fusion.

## Limitations

Physical fit, body/lid interference, lens/PCB clearance, wire reach, inactive panel border, switch operation, and repeated snap use remain unverified. The panel retention lip assumes at least 0.5 mm of inactive border. PLA with a 0.4 mm nozzle is the proposed process, not a validated print profile. Review supports and orientation; no support-free print claim is made. Test lens-seat and latch samples before a full enclosure.
