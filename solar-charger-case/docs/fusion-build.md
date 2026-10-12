# Build Solar Charger Case

1. Keep the entire `solar-charger-case` folder together.
2. In Fusion's Scripts and Add-Ins dialog, add `source/SmallSolarCase` and run **SmallSolarCase**.
3. Inspect the new body and lid. The script creates a fresh `exports/<revision>-<timestamp>/` folder for native F3D, STEP, millimetre STLs, reports, and an optional viewport image.
4. Read the completion or failure dialog and the reports. Partial exports do not establish a completed design.

The generator creates a new document and requests no cloud save. Fusion's own settings, caches, and background services are outside the script's control.

Coordinates use X rearward from the lens face, Y across the panel, and Z upward. Inspect negative-Y switch access, the relocated nearby catch, both R0.6 end fillets, the split 1.4 mm lens groove, and panel border overlap. The nominal envelope is 115.95 × 50.0 × 38.4 mm.

Edit `design-inputs.json` and `source/SmallSolarCase/prototype-settings.json` and regenerate for global changes. New outputs, logs, native archives, and screenshots remain ignored pending review. They can contain personal paths or native metadata.

For a source-only dimensional check from the repository root:

```sh
python3 -I -B solar-charger-case/source/SmallSolarCase/model_spec.py
```

The dimensional check uses the standard library and does not execute Fusion. Validate fit, switch operation, lens/PCB clearance, wire reach, panel border, snap force, and print orientation independently. Source validation and prior exports do not prove a new native run or a usable physical assembly.
