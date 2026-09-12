# SPDX-License-Identifier: GPL-3.0-or-later
import unittest
from pathlib import Path
from unittest.mock import patch
import wave
from test_audio import m, snapshot, MAC
from test_operations import Widget

class Process:
    def __init__(self, args, **kwargs):
        self.args = args
        self.returncode = 0
        if args[0] == 'pw-record':
            with wave.open(args[-1], 'wb') as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
                wav.writeframes(b'\0\0' * 4000)
    def poll(self): return self.returncode
    def wait(self, timeout=None): return self.returncode
    def kill(self): self.returncode = -9
    def terminate(self): self.returncode = -15

class MessageTest(unittest.TestCase):
    def setUp(self):
        self.prova = m.MessaggioAudio()
        self.addCleanup(self.prova.chiudi)

    def test_record_limited_and_no_automatic_playback(self):
        with patch.object(m.subprocess, 'Popen', side_effect=Process) as popen:
            self.prova.registra('source', lambda: None)
        self.assertTrue(self.prova.pronto)
        self.assertTrue(Path(self.prova.percorso).exists())
        self.assertEqual(popen.call_count, 1)
        args = popen.call_args.args[0]
        self.assertEqual(args[args.index('--sample-count')+1], '160000')

    def test_playback_reuses_recorded_file(self):
        with patch.object(m.subprocess, 'Popen', side_effect=Process) as popen:
            self.prova.registra('source', lambda: None)
            self.prova.riproduci('sink')
        self.assertEqual(popen.call_args.args[0], ['paplay', '--device=sink', self.prova.percorso])
        self.assertTrue(Path(self.prova.percorso).exists())

    def test_close_removes_file_and_prevents_late_start(self):
        with patch.object(m.subprocess, 'Popen', side_effect=Process):
            self.prova.registra('source', lambda: None)
        self.prova.chiudi()
        self.assertFalse(Path(self.prova.percorso).exists())
        with patch.object(m.subprocess, 'Popen') as popen:
            with self.assertRaises(RuntimeError): self.prova.registra('source', lambda: None)
        popen.assert_not_called()

    def test_close_while_recording_kills_and_deletes(self):
        def recording(args, **kw):
            proc = Process(args, **kw); proc.returncode = None
            return proc
        with patch.object(m.subprocess, 'Popen', side_effect=recording):
            with self.assertRaises(RuntimeError):
                self.prova.registra('source', self.prova.chiudi)
        self.assertFalse(Path(self.prova.percorso).exists())
        self.assertFalse(self.prova.pronto)

    def test_manual_stop_preserves_message(self):
        def recording(args, **kw):
            proc = Process(args, **kw); proc.returncode = None
            return proc
        with patch.object(m.subprocess, 'Popen', side_effect=recording):
            self.prova.registra('source', self.prova.stop.set)
        self.assertTrue(self.prova.pronto)

    def test_pipewire_168_sample_limit_exit_one_keeps_complete_wav(self):
        def recording(args, **kw):
            proc = Process(args, **kw); proc.returncode = 1
            kw['stderr'].write(args[-1] + '\n'); kw['stderr'].flush()
            with wave.open(args[-1], 'wb') as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
                wav.writeframes(b'\0\0' * 160000)
            return proc
        with patch.object(m.subprocess, 'Popen', side_effect=recording):
            self.prova.registra('source', lambda: None)
        self.assertTrue(self.prova.pronto)
        self.assertEqual(self.prova.durata, 10)

    def test_pipewire_168_manual_stop_exit_one_keeps_wav(self):
        def recording(args, **kw):
            proc = Process(args, **kw); proc.returncode = None
            proc.terminate = lambda: setattr(proc, 'returncode', 1)
            return proc
        with patch.object(m.subprocess, 'Popen', side_effect=recording):
            self.prova.registra('source', self.prova.stop.set)
        self.assertTrue(self.prova.pronto)

    def test_exit_one_with_real_error_rejects_even_valid_wav(self):
        def recording(args, **kw):
            proc = Process(args, **kw); proc.returncode = 1
            kw['stderr'].write('error: connection lost'); kw['stderr'].flush()
            return proc
        with patch.object(m.subprocess, 'Popen', side_effect=recording):
            with self.assertRaisesRegex(RuntimeError, 'connection lost'):
                self.prova.registra('source', lambda: None)
        self.assertFalse(self.prova.pronto)

    def test_exit_one_early_without_stop_rejects_partial_wav(self):
        def recording(args, **kw):
            proc = Process(args, **kw); proc.returncode = 1
            return proc
        with patch.object(m.subprocess, 'Popen', side_effect=recording):
            with self.assertRaisesRegex(RuntimeError, 'prima del limite'):
                self.prova.registra('source', lambda: None)
        self.assertFalse(self.prova.pronto)

    def test_export_survives_temporary_message_cleanup(self):
        import tempfile
        from types import SimpleNamespace
        app = self.app()
        with patch.object(m.subprocess, 'Popen', side_effect=Process):
            self.prova.registra('source', lambda: None)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'saved.wav'
            dialog = SimpleNamespace(get_file=lambda: m.Gio.File.new_for_path(str(path)),
                                     destroy=lambda: None)
            app.dialogo_salvataggio = dialog
            with patch.object(app, '_ricevi_audio'):
                app._messaggio_destinazione(dialog, m.Gtk.ResponseType.ACCEPT, self.prova)
            original = Path(self.prova.percorso).read_bytes()
            app._cancella_messaggio()
            self.assertEqual(path.read_bytes(), original)
            self.assertIsNone(app.dialogo_salvataggio)

    def test_export_rejects_replaced_session(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        app = self.app()
        destination = Mock()
        dialog = SimpleNamespace(get_file=lambda: destination, destroy=lambda: None)
        app.prova_sessione = None
        app._messaggio_destinazione(dialog, m.Gtk.ResponseType.ACCEPT, self.prova)
        destination.replace_contents.assert_not_called()
        self.assertIn('non è più disponibile', app.messaggio_audio)

    def test_automatic_deadline_marks_stalled_capture_as_incomplete(self):
        def recording(args, **kw):
            proc = Process(args, **kw); proc.returncode = None
            return proc
        with patch.object(m.subprocess, 'Popen', side_effect=recording), \
             patch.object(m.time, 'monotonic', side_effect=[0, 10.01]):
            self.prova.registra('source', lambda: None)
        self.assertTrue(self.prova.pronto)
        self.assertTrue(self.prova.incompleta)
        app = self.app()
        app._ricevi_audio(MAC, snapshot(), None)
        self.assertIn('Registrazione incompleta', app.audio_info.text)
        self.assertNotIn('Messaggio disponibile', app.audio_info.text)

    def test_short_manual_stop_is_not_marked_as_transport_failure(self):
        def recording(args, **kw):
            proc = Process(args, **kw); proc.returncode = None
            return proc
        with patch.object(m.subprocess, 'Popen', side_effect=recording):
            self.prova.registra('source', self.prova.stop.set)
        self.assertFalse(self.prova.incompleta)
        self.assertTrue(self.prova.pronto)

    def test_playback_timeout_explains_audio_flow_and_preserves_details(self):
        raw = "Command ['paplay', '--device=bluez_output.test', 'messaggio.wav'] timed out after 15 seconds"
        app = self.app()
        app._ricevi_audio(MAC, snapshot(), 'Operazione audio non riuscita: ' + raw)
        self.assertIn('flusso audio', app.audio_info.text)
        self.assertIn(raw, app.diagnostica['Audio'])

    def test_rec_automatically_prepares_hfp_and_restores_exact_a2dp(self):
        app = self.app()
        with patch.object(m.AudioPipewire, 'leggi', return_value=snapshot()), \
             patch.object(m.AudioPipewire, 'cambia_profilo', side_effect=[snapshot(True), snapshot()]) as change, \
             patch.object(self.prova, 'registra') as record:
            app._registra_preparando_microfono(MAC, self.prova)
        self.assertEqual(change.call_args_list[0].args, (MAC, 'hfp'))
        self.assertEqual(change.call_args_list[1].kwargs, {'profilo_esatto': 'a2dp-sink'})
        record.assert_called_once()

    def test_rec_keeps_original_hfp_mode(self):
        app = self.app()
        with patch.object(m.AudioPipewire, 'leggi', return_value=snapshot(True)), \
             patch.object(m.AudioPipewire, 'cambia_profilo', return_value=snapshot(True)) as change, \
             patch.object(self.prova, 'registra'):
            app._registra_preparando_microfono(MAC, self.prova)
        self.assertEqual(change.call_args.args, (MAC, 'hfp'))
        self.assertEqual(change.call_args.kwargs, {'profilo_esatto': 'headset-head-unit'})

    def test_failed_capture_still_restores_profile(self):
        app = self.app()
        with patch.object(m.AudioPipewire, 'leggi', return_value=snapshot()), \
             patch.object(m.AudioPipewire, 'cambia_profilo', side_effect=[snapshot(True), snapshot()]) as change, \
             patch.object(self.prova, 'registra', side_effect=RuntimeError('capture error')):
            with self.assertRaisesRegex(RuntimeError, 'capture error'):
                app._registra_preparando_microfono(MAC, self.prova)
        self.assertEqual(change.call_count, 2)

    def test_restore_failure_keeps_recording_and_reports_problem(self):
        app = self.app()
        self.prova.pronto = True
        with patch.object(m.AudioPipewire, 'leggi', return_value=snapshot()), \
             patch.object(m.AudioPipewire, 'cambia_profilo', side_effect=[snapshot(True), RuntimeError('profile gone')]), \
             patch.object(self.prova, 'registra'):
            with self.assertRaisesRegex(RuntimeError, 'Ripristino'):
                app._registra_preparando_microfono(MAC, self.prova)
        self.assertTrue(self.prova.pronto)

    def app(self):
        with patch.object(m.ObynApplication, 'carica_config', return_value={}): app = m.ObynApplication()
        app.audio_info = Widget();app.finestra = Widget()
        app.prova_sessione = self.prova
        app.dispositivo_audio = MAC
        return app

    def test_hiding_window_clears_session_even_without_quit(self):
        app = self.app()
        with patch.object(m.subprocess, 'Popen', side_effect=Process): self.prova.registra('source', lambda: None)
        app._nascondi_finestra()
        self.assertIsNone(app.prova_sessione)
        self.assertFalse(Path(self.prova.percorso).exists())
        app._ricevi_esito_messaggio(self.prova, MAC, snapshot(), 'Messaggio registrato')
        self.assertNotIn('Messaggio registrato', app.audio_info.text)

    def test_new_recording_discards_previous(self):
        app = self.app()
        with patch.object(m.subprocess, 'Popen', side_effect=Process): self.prova.registra('source', lambda: None)
        with patch.object(app, '_avvia_operazione'):
            app.azione_audio('test_microfono')
        self.addCleanup(app.prova_sessione.chiudi)
        self.assertIsNot(app.prova_sessione, self.prova)
        self.assertFalse(Path(self.prova.percorso).exists())

    def test_audio_action_uses_message_instead_of_default_sound(self):
        app = self.app();self.prova.pronto = True
        with patch.object(self.prova, 'riproduci') as play, \
             patch.object(m.AudioPipewire, 'leggi', return_value=snapshot()), \
             patch.object(m.AudioPipewire, 'comando') as command, \
             patch.object(m.GLib, 'idle_add', side_effect=lambda fn,*a: fn(*a)):
            app._azione_audio('test_audio', MAC)
        play.assert_called_once()
        command.assert_not_called()

    def test_last_extra_block_is_trimmed_not_discarded(self):
        with wave.open(self.prova.percorso, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
            wav.writeframes(b'\1\0' * 160256)
        self.prova._convalida_messaggio()
        with wave.open(self.prova.percorso, 'rb') as wav:
            self.assertEqual(wav.getnframes(), 160000)
        self.assertEqual(self.prova.durata, 10)

    def test_empty_recording_reports_failure(self):
        with wave.open(self.prova.percorso, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
        with self.assertRaisesRegex(RuntimeError, 'non contiene audio'):
            self.prova._convalida_messaggio()

    def test_failed_recording_never_falls_back_to_front_center(self):
        app = self.app(); self.prova.errore = 'Registratore interrotto'
        with patch.object(m.AudioPipewire, 'leggi', return_value=snapshot()), \
             patch.object(m.AudioPipewire, 'comando') as command, \
             patch.object(m.GLib, 'idle_add', side_effect=lambda fn,*a: fn(*a)):
            app._azione_audio('test_audio', MAC)
        command.assert_not_called()
        self.assertIn('Registratore interrotto', app.audio_info.text)
        self.assertNotIn('Operazione completata', app.audio_info.text)

    def test_a2dp_refresh_preserves_message_and_status(self):
        app = self.app()
        with patch.object(m.subprocess, 'Popen', side_effect=Process):
            self.prova.registra('source', lambda: None)
        app._ricevi_audio(MAC, snapshot(), None)
        self.assertTrue(self.prova.pronto)
        self.assertTrue(Path(self.prova.percorso).exists())
        self.assertIn('Registrazione pronta', app.audio_info.text)

    def test_deadline_stops_cleanly_and_keeps_valid_samples(self):
        def recording(args, **kw):
            proc = Process(args, **kw); proc.returncode = None
            return proc
        with patch.object(m.subprocess, 'Popen', side_effect=recording), \
             patch.object(m.time, 'monotonic', side_effect=[0, 10.01]):
            self.prova.registra('source', lambda: None)
        self.assertTrue(self.prova.pronto)
        self.assertTrue(Path(self.prova.percorso).exists())

if __name__ == '__main__': unittest.main()
