# SPDX-License-Identifier: GPL-3.0-or-later
import struct
import unittest
from pathlib import Path
from test_audio import m


class InputLevelTest(unittest.TestCase):
    def setUp(self):
        self.audio = m.MessaggioAudio()
        self.addCleanup(self.audio.chiudi)

    def write_live(self, value, extra=b''):
        # Size fields intentionally unfinished, as in an active WAV recorder.
        fmt = struct.pack('<HHIIHH', 1, 1, 16000, 32000, 2, 16)
        data = (b'RIFF' + struct.pack('<I', 0) + b'WAVEfmt ' +
                struct.pack('<I', 16) + fmt + extra + b'data' +
                struct.pack('<I', 0) + struct.pack('<h', value) * 1600)
        Path(self.audio.percorso).write_bytes(data)

    def test_live_header_and_new_samples_only(self):
        self.write_live(32767, b'JUNK' + struct.pack('<I', 3) + b'abc\0')
        original = Path(self.audio.percorso).read_bytes()
        self.assertAlmostEqual(self.audio.livello_ingresso(), 1, places=4)
        self.assertEqual(self.audio.livello_ingresso(), 0)
        self.assertEqual(Path(self.audio.percorso).read_bytes(), original)
        with open(self.audio.percorso, 'ab') as f:
            f.write(struct.pack('<h', 3277) * 1600)  # about -20 dBFS
        self.assertAlmostEqual(self.audio.livello_ingresso(), 2/3, places=3)

    def test_silence_missing_partial_and_closed(self):
        self.assertEqual(self.audio.livello_ingresso(), 0)
        Path(self.audio.percorso).write_bytes(b'RIFF')
        self.assertEqual(self.audio.livello_ingresso(), 0)
        self.write_live(0)
        self.assertEqual(self.audio.livello_ingresso(), 0)
        self.audio.chiudi()
        self.assertEqual(self.audio.livello_ingresso(), 0)


class MeterAnimationTest(unittest.TestCase):
    def test_smooth_motion_without_reading_on_every_frame(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        bar = SimpleNamespace(value=0.0)
        bar.get_fraction = lambda: bar.value
        bar.set_fraction = lambda v: setattr(bar, 'value', v)
        recording = SimpleNamespace(chiuso=False, stop=Mock(),
                                    livello_ingresso=Mock(return_value=1.0))
        recording.stop.is_set.return_value = False
        app = SimpleNamespace(prova_sessione=recording, livello_barra=bar,
                              livello_obiettivo=0.0, livello_ultimo_frame=0.0,
                              livello_prossima_lettura=0.0)
        with patch.object(m.time, 'monotonic', return_value=0.033):
            self.assertTrue(m.ObynApplication._aggiorna_livello(app, recording))
        first = bar.value
        self.assertTrue(0 < first < 1)
        with patch.object(m.time, 'monotonic', return_value=0.066):
            m.ObynApplication._aggiorna_livello(app, recording)
        self.assertTrue(first < bar.value < 1)
        recording.livello_ingresso.assert_called_once()
        recording.livello_ingresso.return_value = 0.0
        previous = bar.value
        with patch.object(m.time, 'monotonic', return_value=0.15):
            m.ObynApplication._aggiorna_livello(app, recording)
        self.assertTrue(0 < bar.value < previous)
        with patch.object(m.time, 'monotonic', return_value=2.0):
            m.ObynApplication._aggiorna_livello(app, recording)
        self.assertEqual(bar.value, 0.0)
