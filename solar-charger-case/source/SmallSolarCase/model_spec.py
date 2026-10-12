"""Pure-Python dimensions shared by the Fusion builder and review drawings.

All public numeric dimensions are millimeters. This module uses no CAD kernel,
network, third-party package, or outside project file.
"""
import json
import math
from pathlib import Path


def switch_layout(p, settings):
    """Place access from measured panel datums and preserve the insertion path."""
    p['switch_center_x'] = p['panel_actual_x'] + p['switch_center_from_panel_front']
    p['switch_center_z'] = p['panel_top_z'] - p['switch_center_depth_below_panel_face']
    p['switch_tip_projection_past_case'] = (
        p['switch_overhang_beyond_panel_edge_approx'] - (p['outer_width']-p['panel_width'])/2)
    p['snap_positions_by_side'] = {side:list(p['snap_positions_x'])
                                  for side in ('negative_y','positive_y')}
    config = settings['switch_opening']
    if not config['enabled']:
        return []
    errors = []
    side = config['side']
    axis = config.get('travel_axis')
    if side not in p['snap_positions_by_side']:
        errors.append('Switch side must be explicitly configured as positive_y or negative_y.')
    if axis not in ('x','z'):
        errors.append('Confirm lever travel direction before building: x along panel length, or z toward/away from panel face.')
    for name in ('switch_barrel_diameter','switch_lever_tip_total_travel',
                 'switch_total_diameter_clearance','switch_access_corner_radius',
                 'switch_min_latch_web','switch_min_end_web','switch_min_top_web'):
        if not math.isfinite(p[name]) or p[name] <= 0:
            errors.append('Switch dimension must be finite and positive: '+name)
    if errors:
        return errors
    # Full tip travel swept by the barrel diameter is a conservative access
    # envelope, not a measurement of the moving lever's diameter at the wall.
    minor = p['switch_barrel_diameter'] + p['switch_total_diameter_clearance']
    major = minor + p['switch_lever_tip_total_travel']
    p['switch_access_width'] = major if axis == 'x' else minor
    p['switch_access_height'] = minor if axis == 'x' else major
    cx,cz = p['switch_center_x'],p['switch_center_z']
    hw,hh = p['switch_access_width']/2,p['switch_access_height']/2
    p['switch_cut_x_min'],p['switch_cut_x_max'] = cx-hw,cx+hw
    p['switch_cut_z_min'],p['switch_cut_z_max'] = cz-hh,cz+hh
    radius = p['switch_access_corner_radius']
    # The straight vertical sides include the seam. Neither half narrows at
    # its entry, unlike a circular opening merely intersecting the split.
    if not 0 < radius < min(hw,hh):
        errors.append('Switch opening corner radius must fit within its width and height.')
    if abs(p['seam_z']-cz) > hh-radius:
        errors.append('Switch access requires a wider throat to the seam for vertical assembly.')
    eps = 1e-8
    if cx-hw < p['panel_pocket_x']+p['switch_min_end_web']-eps:
        errors.append('Switch opening leaves insufficient material at the box/loft transition.')
    if cx+hw > p['panel_pocket_end_x']-p['switch_min_end_web']+eps:
        errors.append('Switch opening is too close to the rear wall.')
    if cz-hh < p['floor']+p['switch_floor_clearance']-eps:
        errors.append('Switch opening would cut into the floor clearance zone.')
    if cz+hh > p['panel_cavity_top_z']-p['switch_min_top_web']+eps:
        errors.append('Switch opening leaves insufficient material below the panel retention lip.')
    p['snap_positions_by_side'][side][0] = (
        p['panel_pocket_x']+p['switch_side_front_snap_offset_from_panel'])
    half = p['snap_beam_width']/2+p['snap_slot_clearance']
    for center in p['snap_positions_by_side'][side]:
        separation = max(center-half-(cx+hw), (cx-hw)-(center+half))
        if separation < p['switch_min_latch_web']-eps:
            errors.append('Switch opening is too close to a snap catch or its release slots.')
    register_center=(p['panel_pocket_x']+p['panel_pocket_end_x'])/2
    register_half=6.05
    if max(register_center-register_half-(cx+hw),
           (cx-hw)-(register_center+register_half)) < p['switch_min_latch_web']-eps:
        errors.append('Switch opening is too close to a seam locating register.')
    for centers in p['snap_positions_by_side'].values():
        for center in centers:
            if not p['panel_pocket_x'] < center-half < center+half < p['panel_pocket_end_x']:
                errors.append('Relocated snap catch falls outside the straight side wall.')
            if abs(center-register_center) <= half+register_half:
                errors.append('Relocated snap catch overlaps a seam locating register.')
        if centers[1]-centers[0] <= 2*half:
            errors.append('Front and rear snap catches overlap.')
    return errors


def load_spec(script_directory=None):
    folder = Path(script_directory or Path(__file__).parent)
    project = folder.parent.parent
    allowed_root = Path(__file__).resolve().parents[2]
    for path in (folder, project, project / 'design-inputs.json', folder / 'prototype-settings.json'):
        if not path.resolve().is_relative_to(allowed_root):
            raise ValueError('Input outside the project: ' + str(path))
    data = json.loads((project / 'design-inputs.json').read_text())
    settings = json.loads((folder / 'prototype-settings.json').read_text())
    d = dict(data['user_provided_dimensions_mm'])
    p = dict(settings['assumptions_mm'])
    p.update(d)
    p['groove_width'] = data['sliding_clearance']['confirmed_lens_groove_axial_width_mm']
    p['groove_start'] = p['lens_front_to_ledge_offset'] - (p['groove_width'] - p['lens_ledge_thickness']) / 2
    p['groove_end'] = p['groove_start'] + p['groove_width']
    p['aperture_diameter'] = p['lens_front_dia'] + p['lens_total_diameter_clearance']
    p['groove_diameter'] = p['lens_ledge_dia'] + p['lens_total_diameter_clearance']
    p['nose_diameter'] = p['groove_diameter'] + 2 * p['nose_wall']
    p['pocket_width'] = p['panel_width'] + p['panel_total_xy_clearance']
    p['pocket_length'] = p['panel_length'] + p['panel_total_xy_clearance']
    p['outer_width'] = p['pocket_width'] + 2 * p['side_wall']
    p['panel_top_z'] = p['floor'] + p['solar_component_thickness']
    p['panel_bottom_z'] = p['panel_top_z'] - p['panel_thickness']
    p['rear_height'] = p['panel_top_z'] + p['rim_rise_above_panel']
    p['seam_z'] = p['rear_height'] / 2
    p['nose_bottom_z'] = p['seam_z'] - p['nose_diameter'] / 2
    p['nose_top_z'] = p['seam_z'] + p['nose_diameter'] / 2
    p['panel_pocket_x'] = p['nose_straight_length'] + p['transition_length']
    p['panel_actual_x'] = p['panel_pocket_x'] + p['panel_total_xy_clearance'] / 2
    p['panel_pocket_end_x'] = p['panel_pocket_x'] + p['pocket_length']
    p['rear_x'] = p['panel_pocket_end_x'] + p['rear_wall']
    p['outer_length'] = p['rear_x'] + p['front_bezel_projection']
    p['window_length'] = p['panel_length'] - 2 * p['panel_lip_overlap']
    p['window_width'] = p['panel_width'] - 2 * p['panel_lip_overlap']
    p['window_x'] = p['panel_actual_x'] + p['panel_lip_overlap']
    p['panel_cavity_top_z'] = p['panel_top_z'] + p['panel_lip_vertical_clearance']
    p['lip_thickness'] = p['rear_height'] - p['panel_cavity_top_z']
    p['snap_positions_x'] = [p['panel_pocket_x'] + p['snap_front_offset_from_panel'],
                             p['panel_pocket_end_x'] - p['snap_rear_offset_from_panel_end']]
    p['snap_inner_y'] = p['outer_width'] / 2 - p['snap_beam_thickness']
    errors = []
    radius = p['end_fillet_radius']
    if not 0 < radius < p['groove_start'] + p['front_bezel_projection']:
        errors.append('Front end fillet must finish before the lens groove begins.')
    if radius >= min(p['rear_wall'], p['rear_section_corner_radius']):
        errors.append('Rear end fillet must stay within rear wall and section-corner limits.')
    if (p['nose_diameter'] - p['aperture_diameter']) / 2 <= radius:
        errors.append('Front end fillet would consume the optical opening shoulder.')
    if abs(p['groove_width'] - p['lens_ledge_thickness'] - 0.1) > 1e-8:
        errors.append('Confirmed groove must provide 0.10 mm TOTAL axial clearance.')
    if not p['aperture_diameter'] < p['lens_ledge_dia'] < p['groove_diameter']:
        errors.append('Front shoulder does not capture the flange.')
    if not p['rear_lens_bore_diameter'] < p['lens_ledge_dia']:
        errors.append('Rear shoulder does not capture the flange.')
    if p['nose_straight_length'] < p['frontlens_to_backofLED'] + 0.5:
        errors.append('Nose tapers before the supplied LED depth.')
    if p['side_wall'] - p['snap_beam_thickness'] - p['snap_air_gap'] < 1.0:
        errors.append('Insufficient inner liner behind outward-flexing catch.')
    if p['lip_thickness'] < 0.4:
        errors.append('Panel lip is thinner than the prototype minimum.')
    if not p['snap_tip_z'] < p['snap_hook_top_z'] < p['seam_z'] < p['snap_root_z'] < p['rear_height']:
        errors.append('Catch layout does not cross the parting seam correctly.')
    errors.extend(switch_layout(p, settings))
    if errors:
        raise ValueError('\n'.join(errors))
    return p, settings, data, project


if __name__ == '__main__':
    p, settings, _, _ = load_spec()
    print(json.dumps({'revision': settings['revision'], 'outer_length_mm': p['outer_length'],
                      'outer_width_mm': p['outer_width'], 'nose_diameter_mm': p['nose_diameter'],
                      'rear_height_mm': p['rear_height'], 'groove_width_mm': p['groove_width'],
                      'switch_cut_enabled': settings['switch_opening']['enabled']}, indent=2))
