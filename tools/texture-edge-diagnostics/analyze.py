#!/usr/bin/env python3
"""Decode bounded TextureEdgeDiag v1 captures. Python 3.8+, standard library only."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

LIMIT = 128 * 1024 * 1024
STAGES = ('decoded', 'clamped', 'upload')


def png(path, width, height, rgba):
    if len(rgba) != width * height * 4:
        raise ValueError('invalid PNG dimensions')
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
    scan = b''.join(b'\0' + rgba[y*width*4:(y+1)*width*4] for y in range(height))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' +
                     chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)) +
                     chunk(b'IDAT', zlib.compress(scan)) + chunk(b'IEND', b''))


def read_capture(path):
    if path.stat().st_size > 16384:
        raise ValueError('oversized metadata')
    meta = dict(line.split('=', 1) for line in path.read_text().splitlines() if line)
    for key in ('version', 'id', 'width', 'height', 'texture_width', 'texture_height',
                'pitch', 'rows', 'bytes', 'right_bad_pixels', 'bottom_bad_rows', 'orientation'):
        meta[key] = int(meta[key])
    w, h, tw, th, pitch = (meta[k] for k in ('width', 'height', 'texture_width', 'texture_height', 'pitch'))
    if (meta['version'] != 1 or not 1 <= meta['id'] <= 20 or meta['stage'] not in STAGES or
        meta['encoding'] not in ('BGRA', 'RGBA') or not 0 < w <= tw or not 0 < h <= th or
        pitch != tw*4 or meta['rows'] != th or meta['bytes'] != pitch*th or
        not 0 < meta['bytes'] <= LIMIT):
        raise ValueError('invalid metadata geometry, version, format or ID')
    if path.stem != '{}-{}'.format(meta['id'], meta['stage']):
        raise ValueError('filename/metadata mismatch')
    raw_path = path.with_suffix('.raw')
    if raw_path.stat().st_size != meta['bytes']:
        raise ValueError('raw file size mismatch (partial capture?)')
    raw = raw_path.read_bytes()
    rgba = bytearray(raw)
    if meta['encoding'] == 'BGRA':
        rgba[0::4], rgba[2::4] = raw[2::4], raw[0::4]
    rgba = bytes(rgba)
    image = b''.join(rgba[y*pitch:y*pitch+w*4] for y in range(h))
    right_bad = sum(rgba[y*pitch+x*4:y*pitch+x*4+4] != rgba[y*pitch+(w-1)*4:y*pitch+w*4]
                    for y in range(h) for x in range(w, tw))
    bottom_bad = sum(rgba[y*pitch:(y+1)*pitch] != rgba[(h-1)*pitch:h*pitch] for y in range(h, th))
    meta.update(image_sha256=hashlib.sha256(image).hexdigest(),
                texture_rgba_sha256=hashlib.sha256(rgba).hexdigest(),
                raw_sha256=hashlib.sha256(raw).hexdigest(),
                checked_right_bad_pixels=right_bad, checked_bottom_bad_rows=bottom_bad,
                padding_counts_match=(right_bad == meta['right_bad_pixels'] and bottom_bad == meta['bottom_bad_rows']))
    return meta, rgba, image


def export_images(out, stem, meta, rgba, image):
    w, h, tw, th, pitch = (meta[k] for k in ('width', 'height', 'texture_width', 'texture_height', 'pitch'))
    png(out / (stem+'-image.png'), w, h, image)
    png(out / (stem+'-texture.png'), tw, th, rgba)
    # Include the real edge and up to 8 pixels of right padding, magnified 4x.
    left, right = max(0, w-8), min(tw, w+8)
    edge_rows = []
    for y in range(h):
        row = b''.join(rgba[y*pitch+x*4:y*pitch+x*4+4]*4 for x in range(left, right))
        edge_rows.extend([row]*4)
    png(out / (stem+'-edge.png'), (right-left)*4, h*4, b''.join(edge_rows))
    alpha = b''.join(bytes((a, a, a, 255)) for a in image[3::4])
    png(out / (stem+'-alpha.png'), w, h, alpha)


def comparison(records, first, second):
    if (first['width'], first['height'], first['orientation']) != (second['width'], second['height'], second['orientation']):
        return 'different_geometry_or_orientation'
    return 'same_image_pixels' if first['image_sha256'] == second['image_sha256'] else 'different_image_pixels'


def analyze(session, output, good=None, bad=None):
    output.mkdir(parents=True, exist_ok=False)
    records, errors, comparisons = {}, [], []
    paths = sorted(session.glob('*.meta'))
    if len(paths) > 60:
        raise ValueError('more than 60 captures; select one session directory')
    if not paths:
        errors.append('No captures: check config path, Kodi restart, matching load and events.tsv.')
    total = 0
    for path in paths:
        try:
            # Limit aggregate input before allocating a capture.
            total += path.with_suffix('.raw').stat().st_size
            if total > LIMIT:
                raise ValueError('session exceeds 128 MiB input limit')
            meta, rgba, pixels = read_capture(path)
            records[path.stem] = meta
            if not meta['padding_counts_match']:
                errors.append('{}: recomputed padding counts disagree with capture metadata'.format(path.name))
            export_images(output, path.stem, meta, rgba, pixels)
        except (ValueError, OSError, KeyError) as exc:
            errors.append('{}: {}'.format(path.name, exc))
    ids = sorted({r['id'] for r in records.values()})
    for ident in ids:
        for stage in STAGES:
            if '{}-{}'.format(ident, stage) not in records:
                errors.append('load {}: missing {} capture; no complete CPU/upload comparison'.format(ident, stage))
        for a, b in zip(STAGES, STAGES[1:]):
            first, second = records.get('{}-{}'.format(ident, a)), records.get('{}-{}'.format(ident, b))
            if first and second:
                comparisons.append(dict(first='{}-{}'.format(ident,a), second='{}-{}'.format(ident,b),
                                        result=comparison(records, first, second)))
    if good is not None and bad is not None:
        a, b = records.get('{}-upload'.format(good)), records.get('{}-upload'.format(bad))
        if a and b:
            comparisons.append(dict(first='{}-upload (observed good)'.format(good),
                                    second='{}-upload (observed bad)'.format(bad), result=comparison(records, a, b)))
        else:
            errors.append('Requested good/bad upload capture is missing.')
    report = dict(captures=records, comparisons=comparisons, errors=errors,
                  note='Equality is not proof of visual correctness. Compare with screenshots and source. No automatic driver diagnosis.')
    (output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    lines = ['# Texture edge diagnostics', '',
             'PNG files preserve alpha; *-alpha.png displays it as opaque grayscale.',
             'Orientation is not applied. *-texture.png includes padding; *-edge.png shows the last 8 image columns and up to 8 padding columns at 4x.', '',
             '| Capture | Size | Right padding mismatches | Bottom mismatching rows |',
             '|---|---|---:|---:|']
    for key, r in records.items():
        lines.append('| {} | {}x{} / {}x{} | {} | {} |'.format(key,r['width'],r['height'],r['texture_width'],r['texture_height'],r['checked_right_bad_pixels'],r['checked_bottom_bad_rows']))
    lines += ['', 'Before clamp, padding mismatches are expected. After clamp/upload, nonzero values warrant investigation.', '']
    for c in comparisons:
        lines.append('- {} -> {}: {}'.format(c['first'], c['second'], c['result']))
    lines += ['', 'Equal upload images that are visually correct, paired with good/bad Kodi screenshots, point downstream of the CPU buffer (upload/draw/driver), not specifically to a driver bug.',
              'Different image pixels across loads of the same unchanged file suggest a CPU-side issue only after ruling out intentional dimension/orientation differences.',
              'A changed padding hash before clamping alone is normal and does not diagnose the fault.', '']
    lines += ['- WARNING: '+e for e in errors]
    (output/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session', type=Path)
    parser.add_argument('--out', required=True, type=Path, help='new output directory')
    parser.add_argument('--good', type=int, help='load ID observed good on screen')
    parser.add_argument('--bad', type=int, help='load ID observed bad on screen')
    args = parser.parse_args()
    if (args.good is None) != (args.bad is None):
        parser.error('--good and --bad must be supplied together')
    if not args.session.is_dir():
        parser.error('session must be an existing directory')
    try:
        result = analyze(args.session, args.out, args.good, args.bad)
    except (ValueError, OSError) as exc:
        parser.exit(2, str(exc)+'\n')
    print('{} captures; {} warnings. {}'.format(len(result['captures']), len(result['errors']), args.out/'report.md'))
    return 1 if result['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
