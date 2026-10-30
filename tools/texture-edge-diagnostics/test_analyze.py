"""Synthetic diagnostic captures: no Kodi build, device or extra dependencies."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

spec = importlib.util.spec_from_file_location('analyze', Path(__file__).with_name('analyze.py'))
analyze = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyze)


def fixture(folder, ident, stage, rgba, encoding='BGRA', width=2, height=2, tw=4, th=3):
    raw = bytearray(rgba)
    if encoding == 'BGRA':
        raw[0::4], raw[2::4] = rgba[2::4], rgba[0::4]
    pitch = tw*4
    right = sum(rgba[y*pitch+x*4:y*pitch+x*4+4] != rgba[y*pitch+(width-1)*4:y*pitch+width*4]
                for y in range(height) for x in range(width,tw))
    bottom = sum(rgba[y*pitch:(y+1)*pitch] != rgba[(height-1)*pitch:height*pitch] for y in range(height,th))
    stem = '{}-{}'.format(ident, stage)
    (folder/(stem+'.raw')).write_bytes(raw)
    fields = dict(version=1, id=ident, stage=stage, encoding=encoding, width=width, height=height,
                  texture_width=tw, texture_height=th, pitch=pitch, rows=th, bytes=len(raw),
                  right_bad_pixels=right, bottom_bad_rows=bottom, orientation=0)
    path = folder/(stem+'.meta')
    path.write_text(''.join('{}={}\n'.format(k,v) for k,v in fields.items()))
    return path


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        # Distinct row edges and alpha catch wrong-row padding and channel-order mistakes.
        a, b, c, d = bytes((12,34,56,255)), bytes((70,90,110,128)), bytes((3,7,11,0)), bytes((13,17,19,200))
        self.correct = a+b*3+c+d*3+c+d*3

    def tearDown(self):
        self.temp.cleanup()

    def test_bgra_rgba_and_padding(self):
        p = fixture(self.root,1,'clamped',self.correct)
        q = fixture(self.root,1,'upload',self.correct,'RGBA')
        m, rgba, _ = analyze.read_capture(p)
        n, rgba2, _ = analyze.read_capture(q)
        self.assertEqual(rgba, rgba2)
        self.assertEqual(m['image_sha256'], n['image_sha256'])
        self.assertNotEqual(m['raw_sha256'], n['raw_sha256'])
        self.assertEqual((m['checked_right_bad_pixels'],m['checked_bottom_bad_rows']),(0,0))

    def test_old_clamp_first_row_repeated(self):
        wrong = bytearray(self.correct)
        wrong[24:32] = wrong[8:16]  # second row padding copied from first row
        p = fixture(self.root,1,'clamped',bytes(wrong))
        m, _, _ = analyze.read_capture(p)
        self.assertEqual(m['checked_right_bad_pixels'], 2)
        self.assertEqual(m['checked_bottom_bad_rows'], 1)

    def test_partial_raw_rejected(self):
        p = fixture(self.root,1,'upload',self.correct)
        p.with_suffix('.raw').write_bytes(b'partial')
        with self.assertRaisesRegex(ValueError,'size mismatch'):
            analyze.read_capture(p)

    def test_bad_geometry_rejected(self):
        p = fixture(self.root,1,'upload',self.correct)
        p.write_text(p.read_text().replace('pitch=16','pitch=8'))
        with self.assertRaises(ValueError):
            analyze.read_capture(p)

    def test_report_and_png_integrity(self):
        for stage in analyze.STAGES:
            fixture(self.root,1,stage,self.correct,'RGBA' if stage == 'upload' else 'BGRA')
        out = self.root/'report'
        r = analyze.analyze(self.root,out,1,1)
        self.assertFalse(r['errors'])
        self.assertTrue(all(c['result']=='same_image_pixels' for c in r['comparisons']))
        data = (out/'1-upload-image.png').read_bytes()
        self.assertEqual(data[:8],b'\x89PNG\r\n\x1a\n')
        pos, compressed = 8, b''
        while pos < len(data):
            length = struct.unpack('>I', data[pos:pos+4])[0]
            tag, payload = data[pos+4:pos+8], data[pos+8:pos+8+length]
            crc = struct.unpack('>I',data[pos+8+length:pos+12+length])[0]
            self.assertEqual(crc,zlib.crc32(tag+payload)&0xffffffff)
            if tag == b'IDAT': compressed += payload
            pos += length+12
        decoded = zlib.decompress(compressed)
        self.assertEqual(decoded, b'\0'+self.correct[:8]+b'\0'+self.correct[16:24])
        with self.assertRaises(FileExistsError):
            analyze.analyze(self.root,out)

    def test_missing_stage_and_changed_image(self):
        fixture(self.root,1,'upload',self.correct)
        changed = bytearray(self.correct)
        changed[0] ^= 255
        fixture(self.root,2,'upload',bytes(changed))
        r = analyze.analyze(self.root,self.root/'report',1,2)
        self.assertEqual(r['comparisons'][-1]['result'],'different_image_pixels')
        self.assertTrue(any('missing decoded' in e for e in r['errors']))

    def test_padding_metadata_mismatch_is_reported_as_error(self):
        for stage in analyze.STAGES:
            p = fixture(self.root,1,stage,self.correct)
            if stage == 'clamped':
                p.write_text(p.read_text().replace('right_bad_pixels=0', 'right_bad_pixels=9'))
        r = analyze.analyze(self.root,self.root/'report')
        self.assertEqual(len(r['errors']), 1)
        self.assertIn('padding counts disagree', r['errors'][0])
        self.assertFalse(r['captures']['1-clamped']['padding_counts_match'])


if __name__ == '__main__':
    unittest.main()
