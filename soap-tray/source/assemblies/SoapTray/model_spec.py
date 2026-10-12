"""Millimetre source specification. Standard library only; no CAD invocation.

The JSON files are the authority for regeneration. Local path checks reject
symlink traversal before opening files, including existing parent directories.
"""
import json
import math
import os
from pathlib import Path

# Resolve resources relative to this checkout, on any computer.
PROJECT = Path(__file__).resolve().parents[3]
ROOT = PROJECT


def scoped_path(path):
    p = Path(os.path.abspath(str(path)))
    if p != ROOT and ROOT not in p.parents:
        raise ValueError('Path is outside the project root: ' + str(p))
    if ROOT.is_symlink():
        raise ValueError('The authorized root must not be a symlink')
    cursor = ROOT
    for segment in p.relative_to(ROOT).parts:
        cursor = cursor / segment
        if cursor.is_symlink():
            raise ValueError('Refusing a symlink in project path: ' + str(cursor))
    return p


def read_json(path):
    return json.loads(scoped_path(path).read_text(encoding='utf-8'))


def rounded_area(length, width, radius):
    return length * width - (4 - math.pi) * radius * radius


def capsule_area(width, length):
    return width * (length - width) + math.pi * (width / 2) ** 2


def inside_rounded_rect(x, y, length, width, radius):
    if abs(x) > length / 2 + 1e-8 or abs(y) > width / 2 + 1e-8:
        return False
    dx = max(0.0, abs(x) - (length / 2 - radius))
    dy = max(0.0, abs(y) - (width / 2 - radius))
    return dx * dx + dy * dy <= radius * radius + 1e-8


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_spec():
    data = read_json(PROJECT / 'design-inputs.json')
    b = read_json(PROJECT / 'source/parts/catch-tray.json')
    f = read_json(PROJECT / 'source/parts/filter-insert.json')
    soap = data['user_dimensions']
    for group in (b, f, soap):
        for key, value in group.items():
            require(isinstance(value, (int, float)) and not isinstance(value, bool)
                    and math.isfinite(value) and value > 0,
                    'Expected positive finite numeric value: ' + key)
    require(isinstance(f['slot_columns'], int), 'slot_columns must be an integer')
    require(data['units'] == 'mm', 'Only millimetre input is supported')
    d = {}
    for dimension in ('length', 'width'):
        d['recess_' + dimension] = b['outer_' + dimension] - 2 * b['wall_thickness']
        d['reservoir_' + dimension] = d['recess_' + dimension] - 2 * b['ledge_width']
        d['insert_' + dimension] = d['recess_' + dimension] - 2 * f['fit_clearance_per_side']
        d['pocket_' + dimension] = d['insert_' + dimension] - 2 * f['rim_thickness']
        d['soap_clearance_' + dimension] = (d['pocket_' + dimension] - soap['soap_' + dimension]) / 2
    d['recess_radius'] = b['outer_corner_radius'] - b['wall_thickness']
    d['reservoir_radius'] = d['recess_radius'] - b['ledge_width']
    d['insert_radius'] = d['recess_radius'] - f['fit_clearance_per_side']
    d['pocket_radius'] = d['insert_radius'] - f['rim_thickness']
    d['deck_top'] = b['seat_height'] + f['deck_thickness']
    d['rib_top'] = d['deck_top'] + f['rib_height']
    d['rim_top'] = d['deck_top'] + f['rim_height_above_deck']
    d['soap_top'] = d['rib_top'] + soap['soap_height']
    d['drainage_gap'] = b['seat_height'] - b['floor_thickness']
    d['ledge_overlap'] = b['ledge_width'] - f['fit_clearance_per_side']
    d['notch_bottom'] = b['height'] - b['finger_recess_depth']
    d['slot_half_length'] = (f['slot_field_length_y'] - f['central_bridge_width']) / 2
    d['slot_y_center'] = (f['slot_field_length_y'] + f['central_bridge_width']) / 4
    d['slot_x_centers'] = [(i - (f['slot_columns'] - 1) / 2) * f['slot_pitch']
                           for i in range(f['slot_columns'])]
    d['rib_x_centers'] = [(a + c) / 2 for a, c in zip(d['slot_x_centers'], d['slot_x_centers'][1:])]
    d['total_slots'] = 2 * f['slot_columns']
    d['slot_area'] = d['total_slots'] * capsule_area(f['slot_width'], d['slot_half_length'])

    require(0 < b['floor_thickness'] < b['seat_height'] < b['height'], 'Invalid base heights')
    require(d['ledge_overlap'] >= 1.5, 'Insert needs at least 1.5 mm of ledge engagement')
    require(d['notch_bottom'] > b['seat_height'], 'Finger recess must preserve the support ledge')
    require(d['rim_top'] > b['height'], 'Insert rim must remain accessible above the base')
    require(f['rim_height_above_deck'] > f['rib_height'], 'Retaining rim must rise above ribs')
    require(d['slot_half_length'] >= f['slot_width'], 'Slot capsules are too short')
    require(f['slot_pitch'] - f['slot_width'] >= f['rib_width'] + 1,
            'Need solid deck margin beside each rib')
    require(2 <= f['slot_columns'] <= 40, 'Unsupported slot count')
    for prefix, length, width, radius in (
        ('base', b['outer_length'], b['outer_width'], b['outer_corner_radius']),
        ('recess', d['recess_length'], d['recess_width'], d['recess_radius']),
        ('reservoir', d['reservoir_length'], d['reservoir_width'], d['reservoir_radius']),
        ('insert', d['insert_length'], d['insert_width'], d['insert_radius']),
        ('pocket', d['pocket_length'], d['pocket_width'], d['pocket_radius']),
    ):
        require(0 < radius < min(length, width) / 2, prefix + ' has an invalid radius')
    require(inside_rounded_rect(soap['soap_length']/2, soap['soap_width']/2,
                               d['pocket_length'], d['pocket_width'], d['pocket_radius']),
            'The rectangular soap envelope intersects a rounded pocket corner')
    require(min(d['soap_clearance_length'], d['soap_clearance_width']) >= 2,
            'Soap envelope needs at least 2 mm side clearance')
    for x in d['slot_x_centers']:
        # Test bounding corners, conservatively stronger than testing capsule ends.
        for prefix in ('pocket', 'reservoir'):
            require(inside_rounded_rect(abs(x) + f['slot_width']/2,
                                       f['slot_field_length_y']/2,
                                       d[prefix+'_length'] - 2,
                                       d[prefix+'_width'] - 2, d[prefix+'_radius']),
                    'A slot is too near the rim or is obstructed by the ledge')
    require(f['rib_length'] >= f['rib_width'], 'Invalid rib capsule')
    for x in d['rib_x_centers']:
        require(inside_rounded_rect(abs(x)+f['rib_width']/2, f['rib_length']/2,
                                   d['pocket_length'], d['pocket_width'], d['pocket_radius']),
                'A rib intersects the retaining rim')
    require(b['finger_recess_width'] < b['outer_width'] - 2 * b['outer_corner_radius'],
            'Finger recess must stay on the straight section of the end wall')

    a_outer = rounded_area(b['outer_length'], b['outer_width'], b['outer_corner_radius'])
    a_lower = rounded_area(d['reservoir_length'], d['reservoir_width'], d['reservoir_radius'])
    a_upper = rounded_area(d['recess_length'], d['recess_width'], d['recess_radius'])
    a_insert = rounded_area(d['insert_length'], d['insert_width'], d['insert_radius'])
    a_pocket = rounded_area(d['pocket_length'], d['pocket_width'], d['pocket_radius'])
    d['expected_base_volume_mm3'] = (a_outer*b['height'] - a_lower*d['drainage_gap']
        - a_upper*(b['height']-b['seat_height'])
        - 2*b['wall_thickness']*b['finger_recess_width']*b['finger_recess_depth'])
    d['expected_insert_volume_mm3'] = ((a_insert-d['slot_area'])*f['deck_thickness']
        + (a_insert-a_pocket)*f['rim_height_above_deck']
        + len(d['rib_x_centers'])*capsule_area(f['rib_width'], f['rib_length'])*f['rib_height'])
    d['reservoir_volume_below_deck_ml'] = a_lower * d['drainage_gap'] / 1000
    d['slot_fraction_of_pocket'] = d['slot_area'] / a_pocket
    return {'input': data, 'base': b, 'filter': f, 'derived': d}


if __name__ == '__main__':
    spec = load_spec()
    print(json.dumps({'status': 'source-dimensions-pass', 'native_fusion_build': 'pending',
                      'derived_mm_unless_named_otherwise': spec['derived']}, indent=2))
