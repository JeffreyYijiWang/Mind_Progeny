"""Offline, data-only import of exported Prusa print/filament/printer presets.

Only reviewed path-generation options cross into PrusaSlicer. Source files are
preserved byte-for-byte; calibration and executable hooks never come from an INI.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
from zipfile import ZipFile


ROLES = {'print': 'layer_height', 'filament': 'filament_diameter', 'printer': 'nozzle_diameter'}
PATH_OPTIONS = set('''perimeters fill_density fill_pattern fill_angle top_solid_layers
bottom_solid_layers top_fill_pattern bottom_fill_pattern perimeter_generator thin_walls
gap_fill_enabled extra_perimeters external_perimeters_first infill_first infill_overlap
infill_anchor infill_anchor_max only_one_perimeter_first_layer seam_position
min_bead_width min_feature_size wall_distribution_count wall_transition_angle
wall_transition_filter_deviation wall_transition_length seam_gap_distance'''.split())
PRIVATE = re.compile(r'password|api.?key|token|print_host|printhost', re.I)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def parse_ini(data):
    if len(data) > 1_000_000:
        raise ValueError('Prusa preset exceeds 1 MB')
    result = {}
    for number, line in enumerate(data.decode('utf-8-sig').splitlines(), 1):
        line = line.strip()
        if not line or line.startswith(('#', ';')):
            continue
        if '=' not in line:
            raise ValueError(f'Expected a flat exported Prusa preset at line {number}; config bundles/sections are unsupported')
        key, value = (part.strip() for part in line.split('=', 1))
        if not re.fullmatch(r'[a-z][a-z0-9_]*', key) or key in result:
            raise ValueError(f'Invalid/duplicate Prusa key at line {number}')
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError(f'Control character in Prusa setting {key}')
        if PRIVATE.search(key) and value not in ('', '""'):
            raise ValueError(f'Remove private/host setting {key} before importing; value was not saved')
        result[key] = value
    if result.get('inherits', '') not in ('', '""'):
        raise ValueError('Export a flattened preset without inherits; no external preset lookup is allowed')
    return result


def import_zip(archive, destination):
    """Require three standalone INIs. Validate everything before creating files."""
    archive, destination = Path(archive), Path(destination)
    if destination.exists():
        raise ValueError('Use a new Prusa bundle destination; existing presets are never overwritten')
    sources = {}
    with ZipFile(archive) as zipped:
        entries = zipped.infolist()
        if len(entries) > 20 or sum(i.file_size for i in entries) > 3_000_000:
            raise ValueError('Prusa archive exceeds file count/size limits')
        for info in entries:
            name = info.orig_filename
            path = PurePosixPath(name)
            if ('\\' in name or '\x00' in name or path.is_absolute()
                    or any(p in ('.', '..') or ':' in p for p in path.parts)
                    or stat.S_ISLNK(info.external_attr >> 16)):
                raise ValueError('Unsafe Prusa archive path')
            if info.is_dir():
                continue
            if path.suffix.lower() != '.ini' or info.file_size > 1_000_000:
                raise ValueError('Prusa archive must contain only three exported INI presets')
            data = zipped.read(info)
            values = parse_ini(data)
            roles = [role for role, marker in ROLES.items() if marker in values]
            if len(roles) != 1 or roles[0] in sources:
                raise ValueError('Expected exactly one print, filament and printer preset')
            sources[roles[0]] = (name, data)
    if set(sources) != set(ROLES):
        raise ValueError('Prusa archive must supply print, filament and printer presets')
    manifest = {'schema_version': 1, 'archive_name': archive.name,
                'archive_sha256': digest(archive.read_bytes()), 'sources': []}
    destination.mkdir(parents=True, exist_ok=False)
    for role in ROLES:
        name, data = sources[role]
        filename = role + '.ini'
        (destination / filename).write_bytes(data)
        manifest['sources'].append({'role': role, 'path': filename,
                                    'archive_member': name, 'sha256': digest(data)})
    target = destination / 'bundle.json'
    target.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return target


@dataclass(frozen=True)
class Bundle:
    manifest_bytes: bytes
    sources: tuple

    def snapshot(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=False)
        for entry, data, _ in self.sources:
            (directory / entry['path']).write_bytes(data)
        (directory / 'bundle.json').write_bytes(self.manifest_bytes)
        return directory / 'bundle.json'

    def audit(self, config):
        records = []
        for entry, _, values in self.sources:
            for key, value in values.items():
                effective = config.get(key)
                if key not in config:
                    action, reason = 'ignored', 'Not in the reviewed path-generation options; never passed to PrusaSlicer'
                elif str(effective) == value:
                    action, reason = 'retained', 'Matches the effective configuration'
                else:
                    action, reason = 'overridden', 'Explicit slice option, active machine profile, or offline single-layer policy takes precedence'
                records.append({'role': entry['role'], 'key': key, 'source': value,
                                'effective': effective, 'action': action, 'reason': reason})
        return {'bundle_sha256': digest(self.manifest_bytes),
                'sources': [entry for entry, _, _ in self.sources], 'settings': records,
                'production_approved': False, 'printer_contacted': False}

    def path_options(self):
        # Printer/filament exports cannot smuggle print settings into precedence.
        values = next(values for entry, _, values in self.sources if entry['role'] == 'print')
        options = {key: value for key, value in values.items() if key in PATH_OPTIONS}
        for key, value in options.items():
            # Flat single values only: no escape sequences, templates, paths or hooks.
            if not re.fullmatch(r'[a-zA-Z0-9_.%+-]+', value):
                raise ValueError(f'Unsupported Prusa value for {key}')
        return options


def load_bundle(path):
    if isinstance(path, Bundle):
        return path
    path = Path(path)
    if path.is_dir():
        path /= 'bundle.json'
    data = path.read_bytes()
    manifest = json.loads(data)
    if manifest.get('schema_version') != 1 or len(manifest.get('sources', [])) != 3:
        raise ValueError('Expected a bioprinter Prusa bundle.json with three sources')
    sources = []
    roles = set()
    for entry in manifest['sources']:
        role = entry['role']
        if role not in ROLES or role in roles or entry['path'] != role + '.ini':
            raise ValueError('Invalid Prusa bundle role/path')
        source = (path.parent / entry['path']).resolve()
        if not source.is_relative_to(path.parent.resolve()):
            raise ValueError('Prusa source leaves bundle directory')
        raw = source.read_bytes()
        if digest(raw) != entry['sha256']:
            raise ValueError(f'Prusa source hash changed: {role}; reimport the archive')
        values = parse_ini(raw)
        if [r for r, marker in ROLES.items() if marker in values] != [role]:
            raise ValueError('Prusa source role does not match its contents')
        sources.append((entry, raw, values))
        roles.add(role)
    bundle = Bundle(data, tuple(sources))
    bundle.path_options()
    return bundle
