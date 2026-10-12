# Build Soap Tray

1. Keep the entire `soap-tray` folder together.
2. In Fusion's Scripts and Add-Ins dialog, add the script folder `source/assemblies/SoapTray` and run **SoapTray**.
3. Inspect the new design with **01 Catch tray** and **02 Filter insert**. A successful run creates a native F3D in `source/assemblies/generated/<run>/` and STEP, millimetre STLs, and reports in `exports/<run>/`.
4. Check the completion dialog and `build-report.json`. A partial native file alone does not confirm a successful build.

The generator creates a new design, keeps a feature timeline, and requests no cloud save. Fusion's own application services and caches are outside the script's control.

Verify the 116 × 78 × 17.4 mm assembled envelope, insert seating at Z=10.4 mm, drainage slots, raised ribs, and finger recesses. The build checks solid counts, dimensions, analytical volumes, and timeline errors. These checks do not establish physical fit, watertightness, or freedom from every possible interference.

Edit `design-inputs.json` and the two `source/parts/` JSON files, then regenerate. New output folders are ignored by Git pending a separate publication review. Logs and native archives may contain local paths or application metadata.

For a source-only dimensional check from the repository root:

```sh
python3 -I -B soap-tray/source/assemblies/SoapTray/model_spec.py
```

This check uses only Python's standard library and does not run Fusion. A successful original native build is recorded in the project README; a new run of the portable source still needs native inspection.
