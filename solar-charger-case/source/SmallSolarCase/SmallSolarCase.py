"""Fusion entry point: native editable BRep enclosure, two printed bodies.

Authoring source is parameterized by model_spec.py and prototype-settings.json.
Generated sketches and operations remain in Fusion's timeline. Rebuild in a new
document for global layout changes; only named circle dimensions and feature
offsets/extents are expression-linked in this initial generator.

No network calls, subprocesses, cloud saves, application preference changes,
package installation, or modification of an existing Fusion design.
All deliberate file IO stays inside the CAD project. Fusion's own runtime and
application caches are outside this script's control.
"""
import sys
sys.dont_write_bytecode = True
import json
import importlib
import math
import re
import traceback
from datetime import datetime
from pathlib import Path

import adsk.core
import adsk.fusion

from . import model_spec

# Fusion can keep helper modules cached between runs in the same session.
# Reload the local helper so a new revision uses its matching layout rules.
load_spec = importlib.reload(model_spec).load_spec


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
NEW = adsk.fusion.FeatureOperations.NewBodyFeatureOperation
JOIN = adsk.fusion.FeatureOperations.JoinFeatureOperation
CUT = adsk.fusion.FeatureOperations.CutFeatureOperation


def within_root(path):
    path = Path(path)
    if not path.resolve().is_relative_to(ROOT):
        raise ValueError('Refusing file access outside the project: ' + str(path))
    return path


def point(x, y, z):
    # Fusion's internal length unit is cm. Source dimensions are always mm.
    return adsk.core.Point3D.create(x / 10.0, y / 10.0, z / 10.0)


def mm(value):
    return adsk.core.ValueInput.createByString(f'{value:.12g} mm')


def values(items):
    collection = adsk.core.ObjectCollection.create()
    for item in items:
        collection.add(item)
    return collection


def native_parameter_name(name):
    # Keep project keys clear of Fusion expression functions and unit names.
    return 'sc_' + name


def native_expression(expression, parameter_names):
    return re.sub(r'\b[A-Za-z_][A-Za-z_0-9]*\b',
                  lambda match: native_parameter_name(match.group(0))
                  if match.group(0) in parameter_names else match.group(0),
                  expression)


class Builder:
    def __init__(self, design, params, out, revision):
        self.design = design
        self.root = design.rootComponent
        self.p = params
        self.out = out
        self.revision = revision
        self.log = []
        self.warnings = []

    def record(self, text):
        self.log.append(text)
        with within_root(self.out / 'build-log.txt').open('a', encoding='utf-8') as stream:
            stream.write(text + '\n')
        adsk.doEvents()

    def parameters(self, confirmed):
        linked = {
            'pocket_width': 'panel_width + panel_total_xy_clearance',
            'pocket_length': 'panel_length + panel_total_xy_clearance',
            'outer_width': 'pocket_width + 2 * side_wall',
            'aperture_diameter': 'lens_front_dia + lens_total_diameter_clearance',
            'groove_diameter': 'lens_ledge_dia + lens_total_diameter_clearance',
            'nose_diameter': 'groove_diameter + 2 * nose_wall',
            'panel_top_z': 'floor + solar_component_thickness',
            'rear_height': 'panel_top_z + rim_rise_above_panel',
            'seam_z': 'rear_height / 2',
            'groove_start': 'lens_front_to_ledge_offset - (groove_width - lens_ledge_thickness) / 2',
            'groove_end': 'groove_start + groove_width',
            'switch_center_x': 'panel_actual_x + switch_center_from_panel_front',
            'switch_center_z': 'panel_top_z - switch_center_depth_below_panel_face',
        }
        # Add every value before assigning expressions, so dependency order is safe.
        for name, value in self.p.items():
            if isinstance(value, (int, float)) and value is not None:
                label = 'USER MEASURED' if name in confirmed else 'PROTOTYPE / DERIVED'
                comment = label + '. Global layout changes: edit source JSON and regenerate.'
                native_name = native_parameter_name(name)
                try:
                    self.design.userParameters.add(native_name, mm(value), 'mm', comment)
                except Exception as err:
                    raise RuntimeError(f'Could not create parameter {native_name!r} '
                                       f'from source key {name!r}: {err}') from err
        for name, expression in linked.items():
            self.design.userParameters.itemByName(native_parameter_name(name)).expression = native_expression(expression, self.p)
        self.record('Namespaced sc_ user parameters and dependency expressions created.')

    def plane(self, axis, coordinate, name, expression=None):
        base = {'x': self.root.yZConstructionPlane,
                'y': self.root.xZConstructionPlane,
                'z': self.root.xYConstructionPlane}[axis]
        # xZ's normal can point toward -Y. Obtain the signed offset explicitly.
        normal = base.geometry.normal
        component = {'x': normal.x, 'y': normal.y, 'z': normal.z}[axis]
        sign = 1 if component > 0 else -1
        definition = self.root.constructionPlanes.createInput()
        expression = native_expression(expression, self.p) if expression else None
        offset = adsk.core.ValueInput.createByString(
            expression if sign == 1 else f'-({expression})') if expression else mm(sign * coordinate)
        definition.setByOffset(base, offset)
        plane = self.root.constructionPlanes.add(definition)
        plane.name = name
        plane.isLightBulbOn = False
        return plane

    def sketch(self, axis, coordinate, name, expression=None):
        sk = self.root.sketches.add(self.plane(axis, coordinate, name + ' plane', expression))
        sk.name = name
        return sk

    def polygon(self, axis, coordinate, vertices, name):
        sk = self.sketch(axis, coordinate, name)
        local = [sk.modelToSketchSpace(point(*v)) for v in vertices]
        for a, b in zip(local, local[1:] + local[:1]):
            line = sk.sketchCurves.sketchLines.addByTwoPoints(a, b)
            line.isFixed = True
        if sk.profiles.count != 1:
            raise RuntimeError(name + ': expected one closed profile')
        return sk, sk.profiles.item(0)

    def rectangle(self, axis, coordinate, a, b, name):
        if axis == 'x':
            y0, z0 = a; y1, z1 = b
            vertices = [(coordinate, y0, z0), (coordinate, y1, z0),
                        (coordinate, y1, z1), (coordinate, y0, z1)]
        elif axis == 'y':
            x0, z0 = a; x1, z1 = b
            vertices = [(x0, coordinate, z0), (x1, coordinate, z0),
                        (x1, coordinate, z1), (x0, coordinate, z1)]
        else:
            x0, y0 = a; x1, y1 = b
            vertices = [(x0, y0, coordinate), (x1, y0, coordinate),
                        (x1, y1, coordinate), (x0, y1, coordinate)]
        return self.polygon(axis, coordinate, vertices, name)

    def circle(self, axis, coordinate, center_world, diameter, name, diameter_parameter=None):
        sk = self.sketch(axis, coordinate, name)
        center = sk.modelToSketchSpace(point(*center_world))
        circle = sk.sketchCurves.sketchCircles.addByCenterRadius(center, diameter / 20.0)
        circle.centerSketchPoint.isFixed = True
        label = adsk.core.Point3D.create(center.x + diameter / 14.0,
                                       center.y + diameter / 14.0, 0)
        dim = sk.sketchDimensions.addDiameterDimension(circle, label)
        dim.parameter.expression = (native_parameter_name(diameter_parameter)
                                    if diameter_parameter else f'{diameter:.12g} mm')
        return sk, sk.profiles.item(0)

    def rounded_section(self, x, width, height, bottom, radius, name):
        sk = self.sketch('x', x, name)
        w = width / 2; z0 = bottom; z1 = bottom + height; r = radius
        k = r / math.sqrt(2)
        def v(y, z):
            return sk.modelToSketchSpace(point(x, y, z))
        lines = [((-w+r,z0), (w-r,z0)), ((w,z0+r),(w,z1-r)),
                 ((w-r,z1),(-w+r,z1)), ((-w,z1-r),(-w,z0+r))]
        arcs = [((w-r,z0),(w-r+k,z0+r-k),(w,z0+r)),
                ((w,z1-r),(w-r+k,z1-r+k),(w-r,z1)),
                ((-w+r,z1),(-w+r-k,z1-r+k),(-w,z1-r)),
                ((-w,z0+r),(-w+r-k,z0+r-k),(-w+r,z0))]
        for a, b in lines:
            sk.sketchCurves.sketchLines.addByTwoPoints(v(*a), v(*b)).isFixed = True
        for a, mid, b in arcs:
            sk.sketchCurves.sketchArcs.addByThreePoints(v(*a), v(*mid), v(*b)).isFixed = True
        if sk.profiles.count != 1:
            raise RuntimeError(name + ': rounded rectangle is not a single profile')
        return sk, sk.profiles.item(0)

    def extrude(self, sk, profile, axis, length, name, expression=None):
        normal_origin = sk.sketchToModelSpace(adsk.core.Point3D.create(0, 0, 0))
        normal_tip = sk.sketchToModelSpace(adsk.core.Point3D.create(0, 0, 1))
        normal = normal_origin.vectorTo(normal_tip)
        direction_component = {'x': normal.x, 'y': normal.y, 'z': normal.z}[axis]
        direction = (adsk.fusion.ExtentDirections.PositiveExtentDirection if direction_component > 0
                     else adsk.fusion.ExtentDirections.NegativeExtentDirection)
        ei = self.root.features.extrudeFeatures.createInput(profile, NEW)
        distance = adsk.core.ValueInput.createByString(native_expression(expression, self.p)) if expression else mm(length)
        ei.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(distance), direction)
        feature = self.root.features.extrudeFeatures.add(ei)
        feature.name = name
        sk.isVisible = False
        return feature.bodies.item(0)

    def switch_access_tool(self, start, end, name):
        p=self.p
        sk=self.sketch('y',start,name+' sketch')
        x0,x1=p['switch_cut_x_min'],p['switch_cut_x_max']
        z0,z1=p['switch_cut_z_min'],p['switch_cut_z_max']
        r=p['switch_access_corner_radius']; k=r/math.sqrt(2)
        def v(x,z):
            return sk.modelToSketchSpace(point(x,start,z))
        lines=[((x0+r,z0),(x1-r,z0)),((x1,z0+r),(x1,z1-r)),
               ((x1-r,z1),(x0+r,z1)),((x0,z1-r),(x0,z0+r))]
        arcs=[((x1-r,z0),(x1-r+k,z0+r-k),(x1,z0+r)),
              ((x1,z1-r),(x1-r+k,z1-r+k),(x1-r,z1)),
              ((x0+r,z1),(x0+r-k,z1-r+k),(x0,z1-r)),
              ((x0,z0+r),(x0+r-k,z0+r-k),(x0+r,z0))]
        for a,b in lines:
            sk.sketchCurves.sketchLines.addByTwoPoints(v(*a),v(*b)).isFixed=True
        for a,mid,b in arcs:
            sk.sketchCurves.sketchArcs.addByThreePoints(v(*a),v(*mid),v(*b)).isFixed=True
        if sk.profiles.count != 1:
            raise RuntimeError(name+': expected one rounded access profile')
        return self.extrude(sk,sk.profiles.item(0),'y',end-start,name)

    def loft(self, sections, name):
        li = self.root.features.loftFeatures.createInput(NEW)
        for sk, profile in sections:
            li.loftSections.add(profile)
        li.isSolid = True
        li.isClosed = False
        li.isTangentEdgesMerged = True
        feature = self.root.features.loftFeatures.add(li)
        feature.name = name
        for sk, _ in sections:
            sk.isVisible = False
        return feature.bodies.item(0)

    def combine(self, target, tool, operation, name):
        ci = self.root.features.combineFeatures.createInput(target, values([tool]))
        ci.operation = operation
        ci.isKeepToolBodies = False
        feature = self.root.features.combineFeatures.add(ci)
        feature.name = name
        if feature.bodies.count != 1:
            raise RuntimeError(name + ': operation did not yield one connected solid')
        return feature.bodies.item(0)

    def box(self, x0, x1, y0, y1, z0, z1, name):
        sk, profile = self.rectangle('z', z0, (x0,y0), (x1,y1), name + ' sketch')
        return self.extrude(sk, profile, 'z', z1-z0, name)

    def cut_box(self, target, x0, x1, y0, y1, z0, z1, name):
        tool = self.box(x0,x1,y0,y1,z0,z1,name + ' tool')
        return self.combine(target, tool, CUT, name)

    def cut_cylinder(self, target, axis, start, end, center, diameter, name, param=None):
        sk, profile = self.circle(axis,start,center,diameter,name + ' sketch',param)
        tool = self.extrude(sk,profile,axis,end-start,name + ' tool')
        return self.combine(target,tool,CUT,name)

    def end_fillet(self, solid, x, expected_edges, label):
        # Called on the solid outer blank, before internal openings and the seam.
        # Bound the entire edge, not just its endpoints, to the end plane.
        coordinate = x / 10.0
        tolerance_cm = 1e-5
        edges = [edge for edge in solid.edges
                 if abs(edge.boundingBox.minPoint.x-coordinate) <= tolerance_cm
                 and abs(edge.boundingBox.maxPoint.x-coordinate) <= tolerance_cm]
        if len(edges) != expected_edges:
            raise RuntimeError(f'{label}: expected {expected_edges} end-perimeter edges, found {len(edges)}')
        definition = self.root.features.filletFeatures.createInput()
        definition.edgeSetInputs.addConstantRadiusEdgeSet(
            values(edges), adsk.core.ValueInput.createByString('sc_end_fillet_radius'), False)
        feature = self.root.features.filletFeatures.add(definition)
        feature.name = label + ' outer perimeter R' + str(self.p['end_fillet_radius']) + ' mm'
        if feature.bodies.count != 1 or not feature.bodies.item(0).isSolid:
            raise RuntimeError(label + ': fillet did not preserve a single solid')
        self.record(feature.name + ' created.')
        return feature.bodies.item(0)

    def housing(self):
        p = self.p; z = p['seam_z']; n = p['nose_straight_length']; bx = p['panel_pocket_x']
        front = -p['front_bezel_projection']
        sk, profile = self.circle('x',front,(front,0,z),p['nose_diameter'],
                                  'Nose outside section','nose_diameter')
        shell = self.extrude(sk,profile,'x',n-front,'Straight nose')
        sections = [self.circle('x',n,(n,0,z),p['nose_diameter'],'Outer transition circle','nose_diameter'),
                    self.rounded_section(bx,p['outer_width'],p['rear_height'],0,
                                         p['rear_section_corner_radius'],'Outer rear section')]
        shell = self.combine(shell,self.loft(sections,'Circle to rounded box loft'),JOIN,'Join nose and transition')
        rear_sk, rear_profile = self.rounded_section(bx,p['outer_width'],p['rear_height'],0,
                                                     p['rear_section_corner_radius'],'Rear extrusion section')
        rear = self.extrude(rear_sk,rear_profile,'x',p['rear_x']-bx,'Rear enclosure blank')
        shell = self.combine(shell,rear,JOIN,'Join rear enclosure')
        self.record('Outer housing built: cylindrical nose, loft, rounded rear box.')
        shell = self.end_fillet(shell,front,1,'Lens end fillet')
        shell = self.end_fillet(shell,p['rear_x'],8,'Rear end fillet')

        shell = self.cut_cylinder(shell,'x',front-.5,p['groove_start'],
                                  (front-.5,0,z),p['aperture_diameter'],'Front optical opening','aperture_diameter')
        shell = self.cut_cylinder(shell,'x',p['groove_start'],p['groove_end'],
                                  (p['groove_start'],0,z),p['groove_diameter'],'Confirmed 1.40 mm flange groove','groove_diameter')
        shell = self.cut_cylinder(shell,'x',p['groove_end'],n+.05,
                                  (p['groove_end'],0,z),p['rear_lens_bore_diameter'],
                                  'Lens and LED bore','rear_lens_bore_diameter')
        inside = [self.circle('x',n,(n,0,z),p['rear_lens_bore_diameter'],'Inside nose transition','rear_lens_bore_diameter'),
                  self.rounded_section(bx,p['pocket_width'],p['rear_height']-2*p['floor'],
                                       p['floor'],1.0,'Inside rear transition')]
        shell = self.combine(shell,self.loft(inside,'Interior transition tool'),CUT,'Hollow transition')
        shell = self.cut_box(shell,bx-.05,p['panel_pocket_end_x'],
                             -p['pocket_width']/2,p['pocket_width']/2,p['floor'],p['panel_cavity_top_z'],
                             'Fixed solar module pocket')
        shell = self.cut_box(shell,p['window_x'],p['window_x']+p['window_length'],
                             -p['window_width']/2,p['window_width']/2,p['panel_cavity_top_z']-.05,
                             p['nose_top_z']+2,'Panel light opening - border overlap PROVISIONAL')
        self.record('Interior and split-flange seat built. Axial groove width 1.40 mm.')
        split_plane = self.plane('z',z,'Lid seam through optical axis','seam_z')
        si = self.root.features.splitBodyFeatures.createInput(shell,split_plane,True)
        feature = self.root.features.splitBodyFeatures.add(si)
        feature.name = 'Separate body and lid through lens axis'
        bodies = list(self.root.bRepBodies)
        if len(bodies) != 2:
            raise RuntimeError('Parting operation must create exactly two solid bodies.')
        body = min(bodies,key=lambda b:b.boundingBox.minPoint.z)
        lid = next(b for b in bodies if b != body)
        body.name = '01 Case body — prototype'
        lid.name = '02 Snap lid — prototype'
        return body,lid

    def catches(self, body, lid):
        p = self.p; w = p['outer_width']/2; bw = p['snap_beam_width']; gap = p['snap_slot_clearance']
        tip = p['snap_tip_z']; rootz = p['snap_root_z']; top = p['snap_hook_top_z']; seam = p['seam_z']
        inner = p['snap_inner_y']; contact = inner-gap
        hook_tip = contact-p['snap_hook_engagement']
        for side in (-1,1):
            def span(a,b):
                return (a,b) if side == 1 else (-b,-a)
            side_key='negative_y' if side < 0 else 'positive_y'
            for index,x in enumerate(p['snap_positions_by_side'][side_key]):
                label = ('Left' if side < 0 else 'Right') + (' front' if index == 0 else ' rear')
                x0=x-bw/2; x1=x+bw/2
                y0,y1=span(contact,w+.5)
                body=self.cut_box(body,x0-gap,x1+gap,y0,y1,tip-.8,seam+.05,label+' catch landing')
                y0,y1=span(hook_tip-.1,w+.5)
                body=self.cut_box(body,x0-gap,x1+gap,y0,y1,tip+.15,top+.1,label+' hook receiver')
                # Beam extends below the seam; it bends outward into free space.
                y0,y1=span(inner,w)
                beam=self.box(x0,x1,y0,y1,tip,rootz+.1,label+' lid beam')
                lid=self.combine(lid,beam,JOIN,label+' attach beam')
                y0,y1=span(inner-p['snap_air_gap'],inner)
                lid=self.cut_box(lid,x0-gap,x1+gap,y0,y1,seam-.05,rootz,label+' flex air gap')
                y0,y1=span(inner-p['snap_air_gap'],w+.5)
                for a,b,suffix in ((x0-gap,x0,'A'),(x1,x1+gap,'B')):
                    lid=self.cut_box(lid,a,b,y0,y1,seam-.05,rootz,label+' flex slot '+suffix)
                # A shallow wedge provides an insertion ramp and upper retaining shoulder.
                yz=[(inner,tip),(hook_tip,top-.35),(hook_tip,top),(inner+.08,top),(inner+.08,tip)]
                vertices=[(x0,side*y,z) for y,z in yz]
                sk,profile=self.polygon('x',x0,vertices,label+' hook section')
                hook=self.extrude(sk,profile,'x',bw,label+' hook wedge')
                lid=self.combine(lid,hook,JOIN,label+' join hook')
                self.record(label+' outward-flexing catch built; fit and fatigue unverified.')
        # Short vertical registers prevent lateral slip. They do not intrude into the module envelope.
        x=(p['panel_pocket_x']+p['panel_pocket_end_x'])/2
        center=p['pocket_width']/2+.9
        for side in (-1,1):
            a=side*center-p['alignment_width']/2; b=side*center+p['alignment_width']/2
            tongue=self.box(x-6,x+6,a,b,seam-.05,seam+p['alignment_height'],'Seam locating tongue')
            body=self.combine(body,tongue,JOIN,'Join seam register')
            lid=self.cut_box(lid,x-6.05,x+6.05,a-.05,b+.05,seam-.05,
                              seam+p['alignment_height']+.1,'Matching seam register pocket')
        body.name='01 Case body — prototype'
        lid.name='02 Snap lid — prototype'
        return body,lid

    def switch(self, body, lid, settings):
        p=self.p
        if not settings['switch_opening']['enabled']:
            self.warnings.append('Switch cut disabled: edge, center and operating envelope require measurement.')
            return body,lid
        side=1 if settings['switch_opening']['side']=='positive_y' else -1
        start=-p['outer_width']/2-1 if side<0 else p['pocket_width']/2-.1
        end=-p['pocket_width']/2+.1 if side<0 else p['outer_width']/2+1
        for label,part in (('body',body),('lid',lid)):
            # Full-width straight sides at the seam admit the glued switch.
            tool=self.switch_access_tool(start,end,'Switch access '+label+' tool')
            result=self.combine(part,tool,CUT,'Switch access '+label)
            if label=='body': body=result
            else: lid=result
        self.record(f"Switch access {p['switch_access_width']:.2f} x {p['switch_access_height']:.2f} mm "
                    f"at X={p['switch_center_x']:.2f}, Z={p['switch_center_z']:.2f}; "
                    'full-width entry at seam, switch-side front catch relocated.')
        self.warnings.append('Switch access uses a conservative swept envelope; physical lever operation and finger access require fit review.')
        return body,lid

    def inspect(self, body, lid):
        if self.root.bRepBodies.count != 2:
            raise RuntimeError('Final document must contain exactly two printed solid bodies.')
        report=[]
        for name,solid in (('body',body),('lid',lid)):
            if not solid.isSolid:
                raise RuntimeError(name+' is not a closed solid.')
            prop=solid.physicalProperties
            if prop.volume <= 0:
                raise RuntimeError(name+' has zero/negative volume.')
            b=solid.boundingBox
            report.append({'part':name,'volume_mm3':prop.volume*1000,
                           'bounding_box_mm':{'min':[10*b.minPoint.x,10*b.minPoint.y,10*b.minPoint.z],
                                              'max':[10*b.maxPoint.x,10*b.maxPoint.y,10*b.maxPoint.z]}})
        for i in range(self.design.timeline.count):
            obj=self.design.timeline.item(i).entity
            if hasattr(obj,'healthState'):
                if obj.healthState==adsk.fusion.FeatureHealthStates.ErrorFeatureHealthState:
                    raise RuntimeError('Failed feature: '+obj.name+' '+obj.errorOrWarningMessage)
                if obj.healthState==adsk.fusion.FeatureHealthStates.WarningFeatureHealthState:
                    self.warnings.append(obj.name+': '+obj.errorOrWarningMessage)
        # Exact common-volume check without changing the design or its timeline.
        try:
            manager=adsk.fusion.TemporaryBRepManager.get()
            test_a=manager.copy(body); test_b=manager.copy(lid)
            ok=manager.booleanOperation(test_a,test_b,adsk.fusion.BooleanTypes.IntersectionBooleanType)
            overlap=test_a.volume*1000 if ok and test_a.isSolid else None
            if not ok:
                self.warnings.append('Intersection operation returned no result; common-volume check is unverified.')
            if overlap is not None and overlap > 0.001:
                raise RuntimeError(f'Body/lid overlap {overlap:.6f} mm^3 in closed position.')
        except RuntimeError:
            raise
        except Exception as err:
            overlap=None
            self.warnings.append('Automatic common-volume check unavailable: '+str(err))
        return {'parts':report,'body_lid_overlap_mm3':overlap}

    def export(self, body, lid):
        manager=self.design.exportManager
        outputs=[]
        stem='small-solar-case-'+self.revision
        for filename,options in (
            (stem+'.f3d',manager.createFusionArchiveExportOptions(str(self.out/(stem+'.f3d')))),
            (stem+'.step',manager.createSTEPExportOptions(str(self.out/(stem+'.step')),self.root))):
            if not manager.execute(options):
                raise RuntimeError('Export failed: '+filename)
            outputs.append(filename)
        for name,solid in (('case-body',body),('snap-lid',lid)):
            filename=name+'-'+self.revision+'-PROTOTYPE.stl'
            options=manager.createSTLExportOptions(solid,str(self.out/filename))
            options.meshRefinement=adsk.fusion.MeshRefinementSettings.MeshRefinementHigh
            options.isBinaryFormat=True
            # The installed getter raises on its default document-units value.
            # Assign mm directly; hasattr(options, 'unitType') calls that getter.
            options.unitType=adsk.fusion.DistanceUnits.MillimeterDistanceUnits
            if not manager.execute(options):
                raise RuntimeError('Export failed: '+filename)
            outputs.append(filename)
        return outputs


def run(context):
    app=adsk.core.Application.get()
    ui=app.userInterface
    builder=None
    out=None
    try:
        p,settings,data,project=load_spec(HERE)
        revision=settings['revision']
        if not re.fullmatch(r'v\d+(?:\.\d+)+',revision):
            raise ValueError('Revision must have a safe numeric version format such as v0.2')
        stamp=datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        out=within_root(project/'exports'/(revision+'-'+stamp))
        out.mkdir(parents=True,exist_ok=False)
        doc=app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        doc.name='Small Solar Charger Case '+revision+' — FIT REVIEW'
        design=adsk.fusion.Design.cast(app.activeProduct)
        design.designType=adsk.fusion.DesignTypes.ParametricDesignType
        design.unitsManager.distanceDisplayUnits=adsk.fusion.DistanceUnits.MillimeterDistanceUnits
        builder=Builder(design,p,out,revision)
        builder.record('New unsaved document created; existing documents untouched.')
        builder.parameters(data['user_provided_dimensions_mm'])
        body,lid=builder.housing()
        body,lid=builder.catches(body,lid)
        body,lid=builder.switch(body,lid,settings)
        body.name='01 Case body — prototype'
        lid.name='02 Snap lid — prototype'
        design.computeAll()
        report=builder.inspect(body,lid)
        builder.record('Solid and timeline checks passed.')
        within_root(out/'inspection-report.json').write_text(
            json.dumps(dict(report, warnings=builder.warnings, print_ready=False), indent=2)+'\n',
            encoding='utf-8')
        outputs=builder.export(body,lid)
        app.activeViewport.fit()
        try:
            saved=app.activeViewport.saveAsImageFile(str(out/'fusion-view.png'),1600,1000)
            if saved and (out/'fusion-view.png').is_file():
                outputs.append('fusion-view.png')
            else:
                builder.warnings.append('Viewport image was not saved.')
        except Exception as err:
            builder.warnings.append('Viewport image unavailable: '+str(err))
        report.update({'revision':settings['revision'],'status':settings['status'],
                       'print_ready':False,'outputs':outputs,'assumptions':settings['assumptions'],
                       'switch_access':settings['switch_opening'],
                       'warnings':builder.warnings,'dimensions_mm':p,
                       'native_parameter_editing':'Source JSON regenerates global layout. Native circle diameters and selected features are expression-linked; generated section sketches retain fixed coordinates.'})
        within_root(out/'build-report.json').write_text(json.dumps(report,indent=2)+'\n', encoding='utf-8')
        builder.record('Export complete. No cloud save was requested. Prototype remains NOT released for printing.')
        ui.messageBox('Two-part prototype created.\n\nLocal exports:\n'+str(out)+
                      '\n\nFIT REVIEW ONLY: switch operation, panel border, wire reach, lens/PCB clearance and PLA snaps remain unverified.',
                      'Small Solar Charger Case '+revision)
    except Exception:
        error=traceback.format_exc()
        if out:
            within_root(out/'build-error.txt').write_text(error, encoding='utf-8')
        if builder:
            builder.record('BUILD FAILED — inspect build-error.txt; do not use partial geometry.')
        ui.messageBox('The prototype build stopped. No successful model is claimed.\n\n'+error,
                      'Small Solar Charger Case — build needs repair')
