# CAD

Public repository: `adam-yl/CAD`.

CAD designs, editable Fusion generators, and reviewed interchange files. Dimensions are in **millimetres** unless a file format explicitly declares otherwise.

## Project catalog

| Category | Project | Description | Status |
| --- | --- | --- | --- |
| Household | [Soap Tray](soap-tray/) | Two-piece draining insert and catch tray | v0.1; physical fit and watertightness unverified |
| Electronics | [Solar Charger Case](solar-charger-case/) | Two-piece enclosure for a small solar charger | v0.3 fit-review prototype |

Each project has its own folder with a README, editable `source/`, and versioned `exports/`. Project READMEs describe dimensions, files, units, build instructions, and limitations.

## Working with the designs

Download or clone the complete repository so the Python scripts stay beside their JSON dependencies. Run the generators manually in Autodesk Fusion using the project instructions. Standard Python can check the dimensional specifications, but cannot execute the Fusion builders without Fusion's `adsk` modules.

The public scripts locate files relative to their project folder. Generated logs, native archives, screenshots, and new exports are excluded from Git by default. Only specifically reviewed paths are allowed by `.gitignore`; review new files before adding an exception.

The supplied STEP/STL files come from prior successful builds. Publication changes remove private paths and export metadata without changing geometry. The adapted public generators have passed source checks; they have not been re-run in Fusion after these portability edits.

See [PUBLICATION.md](PUBLICATION.md) for the release contents and review limits. No redistribution license has been selected for this initial preparation.
