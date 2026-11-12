"""Validate attributed, self-contained static GLB aircraft supplied locally."""
from pathlib import Path
import hashlib
import json
import math
import re
import struct

MAX_GLB_BYTES = 128 * 1024 * 1024
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_ACCESSORS = 256
MAX_ACCESSOR_ELEMENTS = 6_000_000
MAX_TOTAL_ELEMENTS = 12_000_000
MAX_VERTICES = 2_000_000
MAX_TRIANGLES = 2_000_000
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 4096 * 4096
MAX_TOTAL_IMAGE_PIXELS = 64 * 1024 * 1024
SUPPORTED_EXTENSIONS = frozenset({
    'KHR_lights_punctual', 'KHR_texture_transform', 'KHR_materials_unlit',
    'KHR_materials_clearcoat', 'KHR_materials_transmission', 'KHR_materials_volume',
    'KHR_materials_ior', 'KHR_materials_specular', 'KHR_materials_sheen',
    'KHR_materials_emissive_strength', 'KHR_materials_iridescence', 'KHR_materials_anisotropy',
})
AXES = ('+X', '-X', '+Y', '-Y', '+Z', '-Z')
METADATA_KEYS = {'length_m', 'wingspan_m', 'nose_axis', 'up_axis', 'source'}
RECORD_KEYS = {'path', 'bytes', 'sha256'}


def _integer(value, label, maximum, minimum=0):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'Aircraft GLB {label} must be an integer in [{minimum}, {maximum}]')
    return value


def _objects(document, name, maximum):
    values = document.get(name, [])
    if not isinstance(values, list) or len(values) > maximum or not all(isinstance(v, dict) for v in values):
        raise ValueError(f'Aircraft GLB supports at most {maximum} {name} objects')
    return values


def _reference(values, index, label):
    return values[_integer(index, label, len(values)-1)]


def _image_pixels(raw, mime):
    """Read PNG/JPEG dimensions without decoding an image or loading a codec."""
    width = height = 0
    if mime == 'image/png' and raw[:8] == b'\x89PNG\r\n\x1a\n' and raw[8:16] == b'\0\0\0\rIHDR' and len(raw) >= 33:
        width, height = struct.unpack('>II', raw[16:24])
    elif mime == 'image/jpeg' and raw[:2] == b'\xff\xd8':
        offset = 2
        while offset < len(raw):
            if raw[offset] != 255:
                break
            while offset < len(raw) and raw[offset] == 255:
                offset += 1
            if offset >= len(raw):
                break
            marker = raw[offset]; offset += 1
            if marker in (0xd9, 0xda) or offset+2 > len(raw):
                break
            length = int.from_bytes(raw[offset:offset+2], 'big')
            if length < 2 or offset+length > len(raw):
                break
            if marker in (0xc0, 0xc1, 0xc2):
                if length < 8:
                    break
                height, width = struct.unpack('>HH', raw[offset+3:offset+7])
                break
            offset += length
        if width == 0:
            raise ValueError('Aircraft GLB JPEG must have a bounded baseline/progressive size header')
    else:
        raise ValueError('Aircraft GLB textures must be embedded PNG or JPEG images')
    if not 0 < width <= 4096 or not 0 < height <= 4096 or width*height > MAX_IMAGE_PIXELS:
        raise ValueError('Aircraft GLB texture exceeds 4096 pixels per side or 16 megapixels')
    return width*height


def _validate_storage(document, path, binary_offset, binary_bytes):
    """Bound the static mesh subset before Blender allocates geometry/textures."""
    views = _objects(document, 'bufferViews', 512)
    accessors = _objects(document, 'accessors', MAX_ACCESSORS)
    layouts = []
    for view in views:
        if view.get('buffer') != 0 or isinstance(view.get('buffer'), bool):
            raise ValueError('Aircraft GLB bufferViews must reference its embedded buffer')
        offset = _integer(view.get('byteOffset', 0), 'bufferView offset', binary_bytes)
        length = _integer(view.get('byteLength'), 'bufferView length', binary_bytes, 1)
        if offset+length > binary_bytes:
            raise ValueError('Aircraft GLB bufferView extends beyond the embedded buffer')
        if 'byteStride' in view:
            stride = _integer(view['byteStride'], 'bufferView stride', 252, 4)
            if stride % 4:
                raise ValueError('Aircraft GLB bufferView stride must be a multiple of four')
    elements = decoded = 0
    component_sizes = {5120:1, 5121:1, 5122:2, 5123:2, 5125:4, 5126:4}
    widths = {'SCALAR':1, 'VEC2':2, 'VEC3':3, 'VEC4':4}
    for accessor in accessors:
        if 'sparse' in accessor or 'bufferView' not in accessor:
            raise ValueError('Aircraft GLB requires dense accessors backed by an embedded bufferView')
        view = _reference(views, accessor['bufferView'], 'accessor bufferView index')
        component = component_sizes.get(accessor.get('componentType'))
        width = widths.get(accessor.get('type'))
        if component is None or width is None:
            raise ValueError('Aircraft GLB requires scalar or vector mesh accessors with standard component types')
        count = _integer(accessor.get('count'), 'accessor count', MAX_ACCESSOR_ELEMENTS, 1)
        offset = _integer(accessor.get('byteOffset', 0), 'accessor offset', view['byteLength'])
        packed = component*width
        stride = view.get('byteStride', packed)
        extent = (count-1)*stride+packed
        if stride < packed or offset+extent > view['byteLength'] or (view.get('byteOffset', 0)+offset) % component:
            raise ValueError('Aircraft GLB accessor range/stride/alignment exceeds its bufferView')
        # Blender may expand normalized integer attributes to float32.
        elements += count; decoded += count*width*max(component, 4)
        if elements > MAX_TOTAL_ELEMENTS or decoded > MAX_GLB_BYTES:
            raise ValueError('Aircraft GLB accessor allocation exceeds the static model budget')
        layouts.append((view.get('byteOffset', 0)+offset, extent, stride))
    meshes = _objects(document, 'meshes', 128)
    nodes = _objects(document, 'nodes', 512)
    _objects(document, 'materials', 128)
    images = _objects(document, 'images', 64)
    if not meshes:
        raise ValueError('Aircraft GLB requires at least one mesh')
    vertices = triangles = primitive_count = 0
    with Path(path).open('rb') as handle:
        for mesh in meshes:
            primitives = mesh.get('primitives', [])
            if not isinstance(primitives, list) or not primitives:
                raise ValueError('Aircraft GLB meshes require triangle primitives')
            for primitive in primitives:
                primitive_count += 1
                if primitive_count > 256 or primitive.get('mode', 4) != 4 or primitive.get('targets'):
                    raise ValueError('Aircraft GLB supports at most 256 static triangle primitives; bake morph targets')
                attributes = primitive.get('attributes', {})
                position = _reference(accessors, attributes.get('POSITION'), 'POSITION accessor index')
                if position['type'] != 'VEC3' or position['componentType'] != 5126:
                    raise ValueError('Aircraft GLB POSITION must be an uncompressed float32 VEC3 accessor')
                for index in attributes.values():
                    if _reference(accessors, index, 'attribute accessor index')['count'] != position['count']:
                        raise ValueError('Aircraft GLB vertex attribute counts must agree')
                count = position['count']
                if 'indices' in primitive:
                    index = primitive['indices']
                    accessor = _reference(accessors, index, 'triangle indices accessor')
                    if accessor['type'] != 'SCALAR' or accessor['componentType'] not in (5121,5123,5125):
                        raise ValueError('Aircraft GLB triangle indices require unsigned scalar accessors')
                    offset, extent, stride = layouts[index]
                    handle.seek(binary_offset+offset); raw = handle.read(extent)
                    code = {5121:'<B',5123:'<H',5125:'<I'}[accessor['componentType']]
                    if max(struct.unpack_from(code, raw, i*stride)[0] for i in range(accessor['count'])) >= count:
                        raise ValueError('Aircraft GLB triangle index is outside its POSITION accessor')
                    count = accessor['count']
                if count % 3:
                    raise ValueError('Aircraft GLB triangle primitive element count must be divisible by three')
                vertices += position['count']; triangles += count//3
                if vertices > MAX_VERTICES or triangles > MAX_TRIANGLES:
                    raise ValueError('Aircraft GLB geometry exceeds two million vertices or triangles')
        pixels = 0
        for image in images:
            if 'uri' in image:
                raise ValueError('Aircraft GLB textures must use embedded bufferViews, not data or external URIs')
            view = _reference(views, image.get('bufferView'), 'image bufferView index')
            if view['byteLength'] > MAX_IMAGE_BYTES or 'byteStride' in view:
                raise ValueError('Aircraft GLB embedded image exceeds 8 MiB or has an invalid stride')
            handle.seek(binary_offset+view.get('byteOffset',0))
            pixels += _image_pixels(handle.read(view['byteLength']), image.get('mimeType'))
            if pixels > MAX_TOTAL_IMAGE_PIXELS:
                raise ValueError('Aircraft GLB textures exceed the 64 megapixel aggregate budget')
    # A compact tree bound also prevents repeated/cyclic node expansion.
    parents = set()
    for node in nodes:
        if 'mesh' in node:
            _reference(meshes, node['mesh'], 'node mesh index')
        for child in node.get('children', []):
            _reference(nodes, child, 'child node index')
            if child in parents:
                raise ValueError('Aircraft GLB nodes must have only one parent')
            parents.add(child)
    def visit(index, chain):
        if index in chain or len(chain) >= 64:
            raise ValueError('Aircraft GLB node hierarchy is cyclic or exceeds 64 levels')
        for child in nodes[index].get('children', []):
            visit(child, chain | {index})
    for index in range(len(nodes)):
        visit(index, set())


def validate_model_metadata(metadata):
    """Return normalized model metadata; accept a full bundle file record too."""
    if not isinstance(metadata, dict):
        raise ValueError('Aircraft model metadata must be an object')
    unknown = set(metadata) - METADATA_KEYS - RECORD_KEYS
    if unknown:
        raise ValueError('Unknown aircraft model metadata: ' + ', '.join(sorted(unknown)))
    result = {}
    for key in ('length_m', 'wingspan_m'):
        value = metadata.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 500:
            raise ValueError(f'Aircraft {key} must be finite and between 0 and 500 metres')
        result[key] = float(value)
    for key in ('nose_axis', 'up_axis'):
        if metadata.get(key) not in AXES:
            raise ValueError(f'Aircraft {key} must name a signed glTF axis: ' + ', '.join(AXES))
        result[key] = metadata[key]
    if result['nose_axis'][1] == result['up_axis'][1]:
        raise ValueError('Aircraft nose_axis and up_axis must be perpendicular')
    source = metadata.get('source')
    keys = {'url', 'credit', 'license_url', 'notes'}
    if not isinstance(source, dict) or set(source) != keys or not all(isinstance(source[k], str) and source[k].strip() for k in keys):
        raise ValueError('Aircraft source requires nonempty url, credit, license_url and notes strings')
    result['source'] = dict(source)
    if 'sha256' in metadata and (not isinstance(metadata['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', metadata['sha256'])):
        raise ValueError('Aircraft sha256 must be a lowercase SHA256 digest')
    return result


def _glb_document(path):
    path = Path(path)
    size = path.stat().st_size
    if path.suffix.lower() != '.glb' or not 20 <= size <= MAX_GLB_BYTES:
        raise ValueError('Aircraft asset must be a self-contained GLB of at most 128 MiB')
    with path.open('rb') as handle:
        header = handle.read(12)
        magic, version, length = struct.unpack('<4sII', header)
        if magic != b'glTF' or version != 2 or length != size:
            raise ValueError('Aircraft asset must have a valid glTF 2 GLB header and complete contents')
        chunks = []
        document = None
        binary_bytes = 0
        binary_offset = 0
        while handle.tell() < size:
            raw = handle.read(8)
            if len(raw) != 8:
                raise ValueError('Aircraft GLB has an incomplete chunk header')
            count, kind = struct.unpack('<I4s', raw)
            if count % 4 or handle.tell() + count > size or kind not in (b'JSON', b'BIN\0') or kind in chunks:
                raise ValueError('Aircraft GLB has invalid or unsupported chunks')
            chunks.append(kind)
            if kind == b'JSON':
                if len(chunks) != 1 or count > MAX_JSON_BYTES:
                    raise ValueError('Aircraft GLB must start with at most 16 MiB of JSON')
                try:
                    document = json.loads(handle.read(count))
                except (UnicodeDecodeError, ValueError) as exc:
                    raise ValueError('Aircraft GLB contains invalid JSON') from exc
            else:
                binary_bytes = count
                binary_offset = handle.tell()
                handle.seek(count, 1)
    if not isinstance(document, dict) or document.get('asset', {}).get('version') != '2.0':
        raise ValueError('Aircraft GLB requires glTF asset version 2.0')
    buffers = document.get('buffers', [])
    if len(buffers) != 1 or 'uri' in buffers[0] or type(buffers[0].get('byteLength')) is not int or not 0 < buffers[0]['byteLength'] <= binary_bytes:
        raise ValueError('Aircraft GLB must embed its mesh buffer in the binary chunk')
    for name in ('extensionsRequired', 'extensionsUsed'):
        extensions = document.get(name, [])
        if not isinstance(extensions, list) or any(not isinstance(item, str) or item not in SUPPORTED_EXTENSIONS for item in extensions):
            raise ValueError('Aircraft GLB uses unsupported extensions; export uncompressed static PBR geometry and PNG/JPEG textures')
    def check_uris(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == 'uri':
                    raise ValueError('Aircraft GLB must embed textures in bufferViews; data and external URIs are not supported')
                if key == 'extensions' and (not isinstance(item, dict) or set(item)-SUPPORTED_EXTENSIONS):
                    raise ValueError('Aircraft GLB contains an unsupported extension')
                check_uris(item)
        elif isinstance(value, list):
            for item in value:
                check_uris(item)
    check_uris(document)
    if document.get('animations') or document.get('skins'):
        raise ValueError('Aircraft GLB must be static; export the desired pose without animations or skins')
    _validate_storage(document, path, binary_offset, buffers[0]['byteLength'])
    return document


def validate_aircraft_model(path, metadata):
    """Validate local content and optional expected bytes/hash before importing."""
    result = validate_model_metadata(metadata)
    path = Path(path)
    try:
        _glb_document(path)
    except (TypeError, AttributeError, KeyError, struct.error, RecursionError) as exc:
        raise ValueError('Aircraft GLB has malformed glTF structures') from exc
    if 'bytes' in metadata and metadata['bytes'] != path.stat().st_size:
        raise ValueError('Aircraft GLB byte count differs from its bundle record')
    if 'sha256' in metadata:
        digest = hashlib.sha256()
        with path.open('rb') as handle:
            for block in iter(lambda: handle.read(1024*1024), b''):
                digest.update(block)
        if digest.hexdigest() != metadata['sha256']:
            raise ValueError('Aircraft GLB hash differs from its immutable bundle record')
    return result


# Original simplified 737NG geometry, sampled from Boeing D6-58325-7 Rev C,
# section 2.2.8 (PDF page 37). Metres: x lateral, aft distance from nose, z
# above fuselage centre. Dimensions are anchors; contours are illustrative.
BOEING_737_900ER = {
    'name': 'Boeing 737-900ER', 'length_m': 42.11, 'span_m': 35.79,
    'fuselage_width_m': 3.76, 'fuselage_height_m': 4.01,
    'fuselage_length_m': 40.90, 'tailplane_span_m': 14.35,
    'engine_center_offset_m': 4.83, 'engine_lip_aft_nose_m': 14.73,
    'wingtip': 'Conventional upward blended winglets; no split-scimitar or MAX tips',
    'leg': None, 'registration': None,
    'reference': 'https://www.boeing.com/content/dam/boeing/v2/airports/acaps/737NG_REV_C.pdf',
    'reference_pages': 'D6-58325-7 Rev C, October 2025, section 2.2.8, page 2-16 (PDF page 37)',
    'detail_sources': ['https://www.aviationpartnersboeing.com/products_737_900er.php',
                       'https://www.cfmaeroengines.com/cfm56/CFM56-5B-CFM56-7B'],
    'equipment_evidence': 'User-selected 737-900ER illustration in the manufacturer-documented conventional blended-winglet configuration; not verification of a specific aircraft, registration or actual winglet retrofit.',
    'geometry_notes': 'Original 737NG three-view illustration, not Airbus-derived or engineering CAD. Overall length, winglet span, body width, stabilizer span and intake station/offset are drawing dimensions. Fuselage end, height, nose, wing sections, dorsal fin and flattened CFM56-7B family nacelle contours are approximate drawing samples. No landing gear; aircraft shown in flight configuration.',
}
BOEING_737_PLANFORM = {
    'wing': [(1.70,16.50,-.65),(4.83,18.45,-.60),(10.,21.05,-.15),
             (16.60,24.75,.50),(17.05,25.45,.58),
             (17.05,26.65,.58),(15.80,26.35,.45),
             (5.55,23.05,-.55),(1.70,23.05,-.65)],
    'winglet': [(16.60,24.75,.50),(17.05,25.05,.75),
                (17.40,25.65,1.45),(17.895,26.70,4.05),
                (17.895,27.58,4.05),(17.35,26.90,1.45),
                (17.05,26.65,.58)],
    'tailplane': [(1.05,36.30,.70),(6.55,40.85,1.25),
                  (7.175,40.85,1.30),(7.175,42.11,1.30),
                  (1.05,40.05,.70)],
    # Long dorsal fillet and swept fin, unlike an Airbus sharklet/tail silhouette.
    'fin': [(0.,31.60,1.90),(0.,35.45,3.35),(0.,39.70,9.65),
            (0.,41.25,9.65),(0.,39.70,1.35)],
}
BOEING_737_BODY = [
    # aft, half width, half height, section centre height
    (0.,.012,.015,-.36),(.35,.38,.38,-.30),(1.1,.95,.88,-.20),
    (2.4,1.53,1.45,-.05),(4.8,1.86,1.98,0.),
    (7.0,1.88,2.005,0.),(30.3,1.88,2.005,0.),
    (33.0,1.70,1.84,.10),(36.0,1.15,1.35,.30),
    (38.7,.54,.70,.65),(40.30,.20,.25,.91),(40.90,.012,.015,1.00),
]


def boeing_737_model_point(point, side=1):
    """Map dimensioned stations to the centered, 12.01-unit display envelope."""
    x, aft, z = point
    unit = BOEING_737_900ER['length_m']/12.01
    return side*x/unit, 6.005-aft/unit, z/unit


# Shared procedural-type registry for trip validation, chase scale, calibration
# and Blender CLI selection. Keep new types visible to every entry point.
AIRCRAFT_LENGTHS_M = {
    'a321neo': 44.51, '777-200er': 63.73, '787-9': 62.81,
    '757-300': 54.43, '737-900er': BOEING_737_900ER['length_m'],
}
SUPPORTED_AIRCRAFT = tuple(AIRCRAFT_LENGTHS_M)
