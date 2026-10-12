"""Run manually in Fusion: build two editable components and export locally.

No cloud save, network call, subprocess, package install or preference change.
Fusion's own autosaves, runtime and services are outside this script's control.
Global dimensions come from the project JSON: edit source and regenerate.
"""
import sys
sys.dont_write_bytecode = True
import importlib
import json
import math
import re
import traceback
from datetime import datetime

import adsk.core
import adsk.fusion
from . import model_spec

spec_module = importlib.reload(model_spec)
scoped_path = spec_module.scoped_path
PROJECT = spec_module.PROJECT
NEW = adsk.fusion.FeatureOperations.NewBodyFeatureOperation
CUT = adsk.fusion.FeatureOperations.CutFeatureOperation
JOIN = adsk.fusion.FeatureOperations.JoinFeatureOperation


def point(x, y, z):
    # All source dimensions are mm; Fusion API points use cm.
    return adsk.core.Point3D.create(x / 10, y / 10, z / 10)


def mm(value):
    return adsk.core.ValueInput.createByString(f'{value:.12g} mm')


def collection(items):
    result = adsk.core.ObjectCollection.create()
    for item in items:
        result.add(item)
    return result


def write_json(path, value):
    scoped_path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


class Builder:
    def __init__(self, design, spec):
        self.design = design
        self.root = design.rootComponent
        self.spec = spec
        self.warnings = []

    def component(self, name):
        occurrence = self.root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        occurrence.component.name = name
        return occurrence.component

    def sketch(self, component, z, name):
        definition = component.constructionPlanes.createInput()
        definition.setByOffset(component.xYConstructionPlane, mm(z))
        plane = component.constructionPlanes.add(definition)
        plane.name = name + ' plane'
        plane.isLightBulbOn = False
        sketch = component.sketches.add(plane)
        sketch.name = name
        return sketch

    def rounded_loop(self, sketch, length, width, radius, cx=0, cy=0):
        # Four quarter arcs also cover capsule shapes; omit zero-length edges.
        a, b, r = length/2, width/2, radius
        k = r / math.sqrt(2)
        def p(x, y):
            return point(cx+x, cy+y, 0)
        lines = [((-a+r,-b),(a-r,-b)), ((a,-b+r),(a,b-r)),
                 ((a-r,b),(-a+r,b)), ((-a,b-r),(-a,-b+r))]
        arcs = [((a-r,-b),(a-r+k,-b+r-k),(a,-b+r)),
                ((a,b-r),(a-r+k,b-r+k),(a-r,b)),
                ((-a+r,b),(-a+r-k,b-r+k),(-a,b-r)),
                ((-a,-b+r),(-a+r-k,-b+r-k),(-a+r,-b))]
        for start, end in lines:
            if math.dist(start, end) > 1e-8:
                sketch.sketchCurves.sketchLines.addByTwoPoints(p(*start), p(*end)).isFixed = True
        for start, middle, end in arcs:
            sketch.sketchCurves.sketchArcs.addByThreePoints(p(*start), p(*middle), p(*end)).isFixed = True

    def extrude_profiles(self, component, sketch, height, name, expected_count):
        if sketch.profiles.count != expected_count:
            raise RuntimeError(f'{name}: expected {expected_count} profiles; got {sketch.profiles.count}')
        profiles = collection([sketch.profiles.item(i) for i in range(sketch.profiles.count)])
        definition = component.features.extrudeFeatures.createInput(profiles, NEW)
        definition.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(mm(height)),
                                    adsk.fusion.ExtentDirections.PositiveExtentDirection)
        feature = component.features.extrudeFeatures.add(definition)
        feature.name = name
        sketch.isVisible = False
        if feature.bodies.count != expected_count:
            raise RuntimeError(name + ': unexpected number of extruded solids')
        return [feature.bodies.item(i) for i in range(feature.bodies.count)]

    def rounded_prism(self, component, length, width, radius, z, height, name):
        sketch = self.sketch(component, z, name + ' profile')
        self.rounded_loop(sketch, length, width, radius)
        return self.extrude_profiles(component, sketch, height, name, 1)[0]

    def box(self, component, x0, x1, y0, y1, z, height, name):
        sketch = self.sketch(component, z, name + ' profile')
        corners = [(x0,y0),(x1,y0),(x1,y1),(x0,y1)]
        for a, b in zip(corners, corners[1:]+corners[:1]):
            sketch.sketchCurves.sketchLines.addByTwoPoints(point(*a,0), point(*b,0)).isFixed = True
        return self.extrude_profiles(component, sketch, height, name, 1)[0]

    def combine(self, component, target, tools, operation, name):
        definition = component.features.combineFeatures.createInput(target, collection(tools))
        definition.operation = operation
        definition.isKeepToolBodies = False
        feature = component.features.combineFeatures.add(definition)
        feature.name = name
        if feature.bodies.count != 1:
            raise RuntimeError(name + ': operation must leave one connected solid')
        return feature.bodies.item(0)

    def build_base(self):
        b, d = self.spec['base'], self.spec['derived']
        comp = self.component('01 Catch tray')
        body = self.rounded_prism(comp, b['outer_length'], b['outer_width'],
                                  b['outer_corner_radius'], 0, b['height'], 'Outer tray')
        tool = self.rounded_prism(comp, d['reservoir_length'], d['reservoir_width'],
                                  d['reservoir_radius'], b['floor_thickness'],
                                  b['height'] - b['floor_thickness'] + .2, 'Reservoir tool')
        body = self.combine(comp, body, [tool], CUT, 'Hollow reservoir; preserve floor')
        tool = self.rounded_prism(comp, d['recess_length'], d['recess_width'], d['recess_radius'],
                                  b['seat_height'], b['height']-b['seat_height']+.2, 'Seat recess tool')
        body = self.combine(comp, body, [tool], CUT, 'Recess insert; preserve continuous ledge')
        for side in (-1, 1):
            x0, x1 = d['recess_length']/2-.2, b['outer_length']/2+.5
            if side < 0:
                x0, x1 = -x1, -x0
            tool = self.box(comp, x0, x1, -b['finger_recess_width']/2,
                            b['finger_recess_width']/2, d['notch_bottom'],
                            b['finger_recess_depth']+.2, 'End finger recess tool')
            body = self.combine(comp, body, [tool], CUT, 'Open finger recess ' + str(side))
        body.name = 'Catch tray'
        return comp, body

    def build_filter(self):
        b, f, d = self.spec['base'], self.spec['filter'], self.spec['derived']
        comp = self.component('02 Filter insert')
        body = self.rounded_prism(comp, d['insert_length'], d['insert_width'], d['insert_radius'],
                                  b['seat_height'], f['deck_thickness'], 'Filter deck')
        sketch = self.sketch(comp, b['seat_height']-.1, str(d['total_slots']) + ' drainage slots')
        for x in d['slot_x_centers']:
            for side in (-1, 1):
                self.rounded_loop(sketch, f['slot_width'], d['slot_half_length'],
                                  f['slot_width']/2, x, side*d['slot_y_center'])
        tools = self.extrude_profiles(comp, sketch, f['deck_thickness']+.2,
                                      'Drainage slot tools', d['total_slots'])
        body = self.combine(comp, body, tools, CUT, 'Through drainage slots; retain central bridge')
        rim = self.rounded_prism(comp, d['insert_length'], d['insert_width'], d['insert_radius'],
                                 d['deck_top'], f['rim_height_above_deck'], 'Retaining rim blank')
        tool = self.rounded_prism(comp, d['pocket_length'], d['pocket_width'], d['pocket_radius'],
                                  d['deck_top']-.05, f['rim_height_above_deck']+.1, 'Soap pocket tool')
        rim = self.combine(comp, rim, [tool], CUT, 'Hollow retaining rim')
        body = self.combine(comp, body, [rim], JOIN, 'Join retaining rim to deck')
        sketch = self.sketch(comp, d['deck_top'], 'Raised soap contact ribs')
        for x in d['rib_x_centers']:
            self.rounded_loop(sketch, f['rib_width'], f['rib_length'], f['rib_width']/2, x, 0)
        tools = self.extrude_profiles(comp, sketch, f['rib_height'], 'Raised rib solids',
                                      len(d['rib_x_centers']))
        body = self.combine(comp, body, tools, JOIN, 'Join raised soap contact ribs')
        body.name = 'Filter insert'
        return comp, body

    def inspect(self, parts):
        b, d = self.spec['base'], self.spec['derived']
        if self.root.occurrences.count != 2 or self.root.bRepBodies.count != 0:
            raise RuntimeError('Assembly must contain exactly two part components')
        bounds = [([-b['outer_length']/2,-b['outer_width']/2,0],
                   [b['outer_length']/2,b['outer_width']/2,b['height']]),
                  ([-d['insert_length']/2,-d['insert_width']/2,b['seat_height']],
                   [d['insert_length']/2,d['insert_width']/2,d['rim_top']])]
        expected_volumes = [d['expected_base_volume_mm3'], d['expected_insert_volume_mm3']]
        reports = []
        for (comp, body), expected, expected_volume in zip(parts, bounds, expected_volumes):
            if comp.bRepBodies.count != 1 or not body.isSolid:
                raise RuntimeError(comp.name + ': expected one closed solid')
            volume = body.physicalProperties.volume * 1000
            bbox = body.boundingBox
            actual = ([10*bbox.minPoint.x,10*bbox.minPoint.y,10*bbox.minPoint.z],
                      [10*bbox.maxPoint.x,10*bbox.maxPoint.y,10*bbox.maxPoint.z])
            if max(abs(a-e) for aa, ee in zip(actual, expected) for a,e in zip(aa,ee)) > .02:
                raise RuntimeError(comp.name + ': native envelope differs from source dimensions')
            if abs(volume-expected_volume) > max(1.0, expected_volume*.001):
                raise RuntimeError(comp.name + ': native volume differs from analytical solid volume')
            reports.append({'component':comp.name, 'closed_solid':True, 'volume_mm3':volume,
                            'expected_volume_mm3':expected_volume, 'bounds_mm':actual})
        for i in range(self.design.timeline.count):
            entity = self.design.timeline.item(i).entity
            if hasattr(entity, 'healthState'):
                if entity.healthState == adsk.fusion.FeatureHealthStates.ErrorFeatureHealthState:
                    raise RuntimeError('Failed timeline feature: ' + entity.name)
                if entity.healthState == adsk.fusion.FeatureHealthStates.WarningFeatureHealthState:
                    self.warnings.append(entity.name + ': ' + entity.errorOrWarningMessage)
        return {'parts':reports, 'timeline_errors':0, 'warnings':self.warnings,
                'assembly_clearance': 'Source dimensions checked; native common-volume test not performed',
                'physical_fit': 'Not tested'}

    def export(self, parts, output_dir, native_dir):
        manager = self.design.exportManager
        outputs = []
        revision = self.spec['input']['revision']
        native_path = scoped_path(native_dir / ('SoapTray-' + revision + '.f3d'))
        step_path = scoped_path(output_dir / ('soap-tray-assembly-' + revision + '.step'))
        for path, options in (
            (native_path, manager.createFusionArchiveExportOptions(str(native_path))),
            (step_path, manager.createSTEPExportOptions(str(step_path), self.root))):
            if not manager.execute(options):
                raise RuntimeError('Export failed: ' + str(path))
            outputs.append(str(path.relative_to(PROJECT)))
        for name, (comp, body) in zip(('catch-tray', 'filter-insert'), parts):
            path = scoped_path(output_dir / (name + '-' + revision + '-mm.stl'))
            options = manager.createSTLExportOptions(body, str(path))
            options.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementHigh
            options.isBinaryFormat = True
            options.unitType = adsk.fusion.DistanceUnits.MillimeterDistanceUnits
            if not manager.execute(options):
                raise RuntimeError('STL export failed: ' + name)
            outputs.append(str(path.relative_to(PROJECT)))
        return outputs


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    output_dir = None
    try:
        spec = spec_module.load_spec()
        revision = spec['input']['revision']
        if not re.fullmatch(r'v\d+(?:\.\d+)+', revision):
            raise ValueError('Invalid revision string')
        stamp = revision + '-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        output_dir = scoped_path(PROJECT / 'exports' / stamp)
        native_dir = scoped_path(PROJECT / 'source/assemblies/generated' / stamp)
        output_dir.mkdir(parents=True, exist_ok=False)
        native_dir.mkdir(parents=True, exist_ok=False)
        write_json(output_dir / 'source-spec.json', spec)
        doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        doc.name = 'Soap Tray ' + revision
        design = adsk.fusion.Design.cast(app.activeProduct)
        design.designType = adsk.fusion.DesignTypes.ParametricDesignType
        design.unitsManager.distanceDisplayUnits = adsk.fusion.DistanceUnits.MillimeterDistanceUnits
        builder = Builder(design, spec)
        parts = [builder.build_base(), builder.build_filter()]
        design.computeAll()
        report = builder.inspect(parts)
        write_json(output_dir / 'inspection-report.json', report)
        outputs = builder.export(parts, output_dir, native_dir)
        app.activeViewport.fit()
        report.update({'status':'native-build-and-export-complete', 'outputs':outputs,
                       'units':'mm', 'source_editing':'Edit project JSON and regenerate globally; sketch coordinates are fixed.',
                       'stl_orientation':'Separate parts; place each flat underside on the print bed in the slicer.',
                       'assumptions':spec['input']['assumptions']})
        write_json(output_dir / 'build-report.json', report)
        ui.messageBox('Soap Tray: two parts built and exported.\n\n' + str(output_dir)
                      + '\n\nNative assembly:\n' + str(native_dir)
                      + '\n\nInspect the ledge, insert clearance, drainage slots and finger access.'
                      + '\nPhysical fit and watertightness remain untested.', 'Soap Tray')
    except Exception:
        error = traceback.format_exc()
        if output_dir is not None:
            scoped_path(output_dir / 'build-error.txt').write_text(error, encoding='utf-8')
        ui.messageBox('Build stopped. Partial geometry is not a completed design.\n\n' + error,
                      'Soap Tray — build needs repair')
