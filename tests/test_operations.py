# SPDX-License-Identifier: GPL-3.0-or-later
"""Regressioni del coordinatore; nessun accesso a Bluetooth, audio o display."""
import ast
import time
import json
from pathlib import Path
import re
import sys
import threading
import unittest
from types import SimpleNamespace

SOURCE = Path(__file__).resolve().parents[1] / 'src/obyn.py'
if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1].endswith('.py'):
    SOURCE = Path(sys.argv.pop(1))


class Widget:
    def __init__(self, **kwargs):
        self.rows = []
        self.sensitive = True
        self.text = ''
    def set_sensitive(self, value): self.sensitive = value
    def set_text(self, value): self.text = value
    def get_row_at_index(self, index): return self.rows[index] if index < len(self.rows) else None
    def get_first_child(self): return self.rows[0] if self.rows else None
    def get_child_at_index(self, index): return self.get_row_at_index(index)
    def remove(self, row): self.rows.remove(row)
    def append(self, row): self.rows.append(row)
    def __getattr__(self, name): return lambda *a, **kw: None


class OperationsTest(unittest.TestCase):
    def setUp(self):
        self.callbacks = []
        self.workers = []
        self.calls = []
        self.connected = False
        self.failure = False
        self.removed_timers = []
        owner = self
        class Thread:
            def __init__(self, target, daemon=True): self.target = target
            def start(self): owner.workers.append(self.target)
        tree = ast.parse(SOURCE.read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ObynApplication')
        ns = dict(time=time, json=json,
            Pango=SimpleNamespace(EllipsizeMode=SimpleNamespace(END=3)),
            Gtk=SimpleNamespace(Application=Widget, ListBoxRow=Widget, Box=Widget, Overlay=Widget, GestureClick=Widget, EventControllerKey=Widget, MenuButton=Widget, Popover=Widget, Expander=Widget, Switch=Widget, ToggleButton=Widget, AccessibleProperty=SimpleNamespace(LABEL=1), Align=SimpleNamespace(END=1, START=0, CENTER=2),
                                Label=Widget, Button=Widget, Orientation=SimpleNamespace(VERTICAL=1)),
            GLib=SimpleNamespace(idle_add=lambda fn, *a: self.callbacks.append((fn, a)),
                                 source_remove=self.removed_timers.append),
            Path=Path, re=re, threading=SimpleNamespace(Thread=Thread, Event=threading.Event),
            prepara_bluetooth=lambda: 'ok', comando_bt=self.bt,
        )
        backend = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'AudioPipewire')
        exec(compile(ast.Module(body=[backend, cls], type_ignores=[]), str(SOURCE), 'exec'), ns)
        class Discovery:
            def __init__(self, controller): self.visti = set()
            def esegui(self, ferma, aggiorna, **kwargs): self.visti.add(kwargs['obiettivo'].upper())
        ns['RicercaBluez'] = Discovery
        self.namespace = ns
        App = ns['ObynApplication']
        App.carica_config = lambda app: {}
        App.salva_config = lambda app: None
        App._icona = staticmethod(lambda name: Widget())
        App._bottone_icona = lambda *args: Widget()
        self.app = App()
        self.app.lista = Widget()
        self.app.stato = Widget()
        self.app.audio_info = Widget()
        self.app.controlli_operazioni = [self.app.lista, Widget()]

    def test_volume_does_not_disable_parent_and_queues_one_worker(self):
        app = self.app
        app._avvia_operazione('volume', lambda: None)
        self.assertTrue(all(w.sensitive for w in app.controlli_operazioni))
        app._applica_volume(91)
        app._applica_volume(99)
        self.assertEqual(len(self.workers), 1)
        self.assertEqual(app.volume_pendente, 99)
        values = []
        app._volume_worker = values.append
        self.drain()
        self.assertEqual(values, [99])
        self.assertIsNone(app.volume_pendente)
        self.assertIsNone(app.operazione)

    def bt(self, *args):
        self.calls.append(args)
        if args[0] == 'show': return 'Controller 11:22:33:44:55:66 (public)'
        if args[0] == 'devices': return 'Device A4:6B:40:3F:78:72 M50'
        if args[0] == 'info':
            return 'Paired: yes\nTrusted: yes\nBlocked: no\nConnected: ' + ('yes' if self.connected else 'no')
        if self.failure: return 'Errore Bluetooth: failed test'
        if args[0] == 'connect': self.connected = True
        if args[0] == 'disconnect': self.connected = False
        return 'Success'

    def drain(self):
        for _ in range(30):
            if self.callbacks:
                fn, args = self.callbacks.pop(0)
                fn(*args)
            elif self.workers:
                self.workers.pop(0)()
            else:
                return
        self.fail('Il coordinatore non termina')

    def test_refresh_requests_coalesce_and_stale_result_is_ignored(self):
        app = self.app
        app.aggiorna_elenco()
        for _ in range(5): app.aggiorna_elenco()
        self.assertEqual(len(self.workers), 1)
        self.workers.pop(0)()
        fn, args = self.callbacks.pop(0)
        fn(*args)
        self.assertEqual(app.lista.rows, [])  # prima lettura invalidata
        self.drain()
        self.assertEqual(len(app.lista.rows), 1)
        self.assertEqual(sum(a[0] == 'devices' for a in self.calls), 2)

    def test_refresh_replaces_existing_rows(self):
        self.app.aggiorna_elenco(); self.drain()
        self.app.aggiorna_elenco(); self.drain()
        self.assertEqual(len(self.app.lista.rows), 1)

    def test_auto_connect_runs_only_once_and_disconnect_is_respected(self):
        app = self.app
        app.config['auto_connect'] = 'A4:6B:40:3F:78:72'
        app.aggiorna_elenco(); self.drain()
        self.assertTrue(self.connected)
        app.esegui_azione('disconnect', app.config['auto_connect']); self.drain()
        app.aggiorna_elenco(); self.drain()
        self.assertFalse(self.connected)
        self.assertEqual(sum(a[0] == 'connect' for a in self.calls), 1)

    def test_failed_startup_connect_is_not_retried_on_refresh(self):
        self.failure = True
        self.app.config['auto_connect'] = 'A4:6B:40:3F:78:72'
        self.app.aggiorna_elenco(); self.drain()
        self.assertIn('failed test', '\n'.join(self.app.diagnostica.values()))
        self.app.aggiorna_elenco(); self.drain()
        self.assertEqual(sum(a[0] == 'connect' for a in self.calls), 1)

    def test_double_click_audio_scan_and_selection_are_blocked(self):
        app = self.app
        app.esegui_azione('connect', 'A4:6B:40:3F:78:72')
        app.esegui_azione('disconnect', 'A4:6B:40:3F:78:72')
        app.avvia_scansione()
        app.azione_audio('hfp')
        app.seleziona_audio('other', 'Other')
        app._applica_volume(90)
        self.assertIsNone(app.dispositivo_audio)
        self.assertEqual(len(self.workers), 1)
        self.assertTrue(all(not w.sensitive for w in app.controlli_operazioni))
        self.drain()
        self.assertTrue(self.connected)
        self.assertTrue(all(w.sensitive for w in app.controlli_operazioni))

    def test_exception_releases_controls_and_pending_refresh(self):
        def fail(): raise RuntimeError('worker failed')
        self.app._avvia_operazione('test', fail)
        self.app.aggiorna_elenco()
        self.drain()
        self.assertIsNone(self.app.operazione)
        self.assertEqual(len(self.app.lista.rows), 1)
        self.assertTrue(all(w.sensitive for w in self.app.controlli_operazioni))

    def test_failed_action_refreshes_state_without_losing_error(self):
        self.failure = True
        self.app.esegui_azione('connect', 'A4:6B:40:3F:78:72')
        self.drain()
        self.assertTrue(any(a[0] == 'info' for a in self.calls))
        self.assertIn('failed test', '\n'.join(self.app.diagnostica.values()))
        self.assertIsNone(self.app.operazione)

    def test_pending_volume_is_cancelled_before_another_operation(self):
        self.app.volume_timeout = 42
        self.app.esegui_azione('connect', 'A4:6B:40:3F:78:72')
        self.assertEqual(self.removed_timers, [42])
        self.assertIsNone(self.app.volume_timeout)
        self.drain()

    def test_scan_and_audio_each_exclude_bluetooth_actions(self):
        app = self.app
        app._scansiona = lambda: None
        app.avvia_scansione()
        app.esegui_azione('connect', 'device')
        self.assertEqual(len(self.workers), 1)
        self.drain()
        self.assertFalse(app.scansione)
        app.dispositivo_audio = 'device'
        app._azione_audio = lambda action, mac: None
        app.azione_audio('hfp')
        app.esegui_azione('disconnect', 'device')
        self.assertEqual(len(self.workers), 1)
        self.drain()
        self.assertEqual(self.calls, [])

    def test_failed_enumeration_preserves_previous_list(self):
        self.app.aggiorna_elenco(); self.drain()
        old_row = self.app.lista.rows[0]
        self.namespace['comando_bt'] = lambda *args: 'Errore Bluetooth: devices failed'
        self.app.aggiorna_elenco(); self.drain()
        self.assertIs(self.app.lista.rows[0], old_row)
        self.assertIn('devices failed', self.app.diagnostica['Bluetooth'])

    def test_failed_info_is_not_reported_as_disconnected(self):
        self.app.aggiorna_elenco(); self.drain()
        old_row = self.app.lista.rows[0]
        self.namespace['comando_bt'] = lambda *args: ('Errore Bluetooth: info failed'
            if args[0] == 'info' else self.bt(*args))
        self.app.aggiorna_elenco(); self.drain()
        self.assertIs(self.app.lista.rows[0], old_row)
        self.assertIn('info failed', '\n'.join(self.app.diagnostica.values()))

    def test_scan_progress_and_finish_preserve_observed_count(self):
        self.app.scansione = True
        devices = [('MAC', 'Headset', {'connected': False, 'paired': True, 'trusted': True})]
        self.app._ricevi_scansione(devices, {'MAC'}, False, '')
        self.assertIn('Ricerca attiva', self.app.stato.text)
        self.assertIn('1 dispositivo', self.app.stato.text)
        self.app._ricevi_scansione(None, None, True, '')
        self.assertFalse(self.app.scansione)
        self.assertIn('Ricerca conclusa: 1', self.app.stato.text)
        self.assertEqual(len(self.app.lista.rows), 1)

    def test_scan_error_is_not_reported_as_zero_results(self):
        self.app._ricevi_scansione(None, None, True, 'org.bluez.Error.NotReady')
        self.assertIn('non è pronto', self.app.stato.text)
        self.assertNotIn('Ricerca conclusa', self.app.stato.text)

    def test_stop_remains_available_while_other_controls_are_locked(self):
        self.app.pulsante_ferma = Widget()
        self.app._scansiona = lambda: None
        self.app.avvia_scansione()
        self.assertTrue(self.app.pulsante_ferma.sensitive)
        self.assertFalse(self.app.lista.sensitive)
        self.app.ferma_scansione()
        self.assertTrue(self.app.ferma_scansione_evento.is_set())
        self.assertFalse(self.app.pulsante_ferma.sensitive)
        self.drain()
        self.assertTrue(self.app.lista.sensitive)
        self.assertFalse(self.app.pulsante_ferma.sensitive)

    def test_real_info_output_is_not_an_error(self):
        for connected in ('yes', 'no'):
            with self.subTest(connected=connected):
                output = ('Device A4:6B:40:3F:78:72 (public)\n'
                          '  Name: M50\n  Alias: M50\n  Class: 0x00200404 (2098180)\n'
                          '  Icon: audio-headset\n  Paired: yes\n  Bonded: yes\n'
                          '  Trusted: yes\n  Blocked: no\n  Connected: ' + connected + '\n'
                          '  UUID: Audio Sink (0000110b-0000-1000-8000-00805f9b34fb)')
                self.assertFalse(self.app._errore_comando_bt(output))
                self.assertEqual(self.app._stato_info(output)['connected'], connected == 'yes')

    def test_property_values_and_device_names_are_not_command_errors(self):
        for output in ('Blocked: yes', 'Name: Failed headset',
                       'Device AA:BB:CC:DD:EE:FF Error blocked not found',
                       'Alias: org.bluez.Error.Failed'):
            with self.subTest(output=output):
                self.assertFalse(self.app._errore_comando_bt(output))

    def test_actual_command_failures_remain_errors(self):
        for output in ('Errore Bluetooth: timeout',
                       'Attempting to connect to A4:6B:40:3F:78:72\n'
                       'Failed to connect: org.bluez.Error.Failed br-connection-page-timeout',
                       'Failed to set power on: org.bluez.Error.Blocked',
                       'Device A4:6B:40:3F:78:72 not available',
                       'No default controller available',
                       'org.bluez.Error.NotReady'):
            with self.subTest(output=output):
                self.assertTrue(self.app._errore_comando_bt(output))

    def test_refresh_accepts_connected_info_with_blocked_no(self):
        self.connected = True
        self.app.aggiorna_elenco(); self.drain()
        self.assertEqual(len(self.app.lista.rows), 1)
        self.assertNotIn('non riuscita', self.app.stato.text)

    def test_live_connection_updates_without_audio_selection(self):
        self.app.aggiorna_elenco(); self.drain()
        mac = 'A4:6B:40:3F:78:72'
        objects = {'/org/bluez/hci0/dev': {'org.bluez.Device1': {
            'Address': mac, 'Alias': 'M50', 'Connected': True, 'Paired': True, 'Trusted': True}}}
        self.app._ricevi_stato_bt(self.app.audio_generazione, objects, '')
        self.assertIsNone(self.app.dispositivo_audio)
        self.assertTrue(self.app.dispositivi_visualizzati[0][2]['connected'])
        self.assertIn('1 connesso', self.app.stato.text)
        objects['/org/bluez/hci0/dev']['org.bluez.Device1']['Connected'] = False
        self.app._ricevi_stato_bt(self.app.audio_generazione, objects, '')
        self.assertFalse(self.app.dispositivi_visualizzati[0][2]['connected'])

    def test_live_read_before_mutation_is_discarded(self):
        self.app.audio_generazione = 2
        self.app._ricevi_stato_bt(1, {}, '')
        self.assertEqual(self.app.dispositivi_visualizzati, [])

    def test_live_read_failure_preserves_known_rows(self):
        self.app.aggiorna_elenco(); self.drain()
        self.app._ricevi_stato_bt(self.app.audio_generazione, None, 'bus unavailable')
        self.assertEqual(len(self.app.dispositivi_visualizzati), 1)
        self.assertIn('non aggiornato', self.app.stato.text)

    def test_targeted_search_finishes_before_connect(self):
        calls = self.calls
        class Discovery:
            def __init__(self, controller): self.visti = set()
            def esegui(self, ferma, aggiorna, **kwargs):
                calls.append(('scan_start', kwargs['obiettivo']))
                self.visti.add(kwargs['obiettivo'].upper())
                calls.append(('scan_stop',))
        self.namespace['RicercaBluez'] = Discovery
        self.app.esegui_azione('connect', 'A4:6B:40:3F:78:72'); self.drain()
        names = [a[0] for a in calls]
        self.assertLess(names.index('scan_stop'), names.index('connect'))
        self.assertTrue(self.connected)

    def test_other_observed_device_does_not_trigger_connection(self):
        original = self.namespace['comando_bt']
        self.namespace['comando_bt'] = lambda *a: original(*a).replace('Paired: yes', 'Paired: no')
        class Discovery:
            def __init__(self, controller): self.visti = {'00:11:22:33:44:55'}
            def esegui(self, *a, **kw): pass
        self.namespace['RicercaBluez'] = Discovery
        self.app.esegui_azione('connect', 'A4:6B:40:3F:78:72'); self.drain()
        self.assertFalse(any(a[0] == 'connect' for a in self.calls))
        self.assertIn('non rilevato', self.app.stato.text)

    def test_paired_unseen_device_gets_direct_connection_without_fake_detection(self):
        class Discovery:
            def __init__(self, controller): self.visti = set()
            def esegui(self, *a, **kw): pass
        self.namespace['RicercaBluez'] = Discovery
        mac = 'A4:6B:40:3F:78:72'
        self.app.esegui_azione('connect', mac); self.drain()
        self.assertTrue(self.connected)
        self.assertEqual(sum(a[0] == 'connect' for a in self.calls), 1)
        self.assertNotIn(mac, self.app.visti_scansione)

    def test_unpair_during_search_prevents_direct_fallback(self):
        owner = self
        original = self.namespace['comando_bt']
        class Discovery:
            def __init__(self, controller): self.visti = set()
            def esegui(self, *a, **kw):
                owner.namespace['comando_bt'] = lambda *a: original(*a).replace('Paired: yes', 'Paired: no')
        self.namespace['RicercaBluez'] = Discovery
        self.app.esegui_azione('connect', 'A4:6B:40:3F:78:72'); self.drain()
        self.assertFalse(any(a[0] == 'connect' for a in self.calls))

    def test_cancel_unseen_paired_search_prevents_direct_fallback(self):
        class Discovery:
            def __init__(self, controller): self.visti = set()
            def esegui(self, ferma, *a, **kw): ferma.set()
        self.namespace['RicercaBluez'] = Discovery
        self.app.esegui_azione('connect', 'A4:6B:40:3F:78:72'); self.drain()
        self.assertFalse(any(a[0] == 'connect' for a in self.calls))

    def test_cancel_after_observation_prevents_connect(self):
        class Discovery:
            def __init__(self, controller): self.visti = set()
            def esegui(self, ferma, aggiorna, **kw):
                self.visti.add(kw['obiettivo'].upper())
                ferma.set()
        self.namespace['RicercaBluez'] = Discovery
        self.app.esegui_azione('connect', 'A4:6B:40:3F:78:72'); self.drain()
        self.assertFalse(any(a[0] == 'connect' for a in self.calls))
        self.assertIn('annullata', self.app.stato.text)

    def test_stop_button_cancels_targeted_search(self):
        self.app.esegui_azione('connect', 'A4:6B:40:3F:78:72')
        self.app.ferma_scansione(); self.drain()
        self.assertFalse(any(a[0] == 'connect' for a in self.calls))

    def test_already_connected_skips_search_and_reconnect(self):
        self.connected = True
        self.app.esegui_azione('connect', 'A4:6B:40:3F:78:72'); self.drain()
        self.assertFalse(any(a[0] in {'connect', 'show'} for a in self.calls))

    def test_failed_targeted_search_does_not_connect(self):
        class Discovery:
            def __init__(self, controller): pass
            def esegui(self, *a, **kw): raise RuntimeError('Discovery failed')
        self.namespace['RicercaBluez'] = Discovery
        self.app.esegui_azione('connect', 'A4:6B:40:3F:78:72'); self.drain()
        self.assertFalse(any(a[0] == 'connect' for a in self.calls))
        self.assertIn('Discovery failed', '\n'.join(self.app.diagnostica.values()))

    def test_busy_button_stops_after_worker_failure(self):
        events = []
        self.app.pulsante_origine = SimpleNamespace(attesa=events.append)
        def fail(): raise RuntimeError('errore simulato')
        self.app._avvia_operazione('audio', fail)
        self.drain()
        self.assertEqual(events, [True, False])
        self.assertIsNone(self.app.pulsante_in_attesa)

    def test_connect_timeout_checks_state_without_reconnecting(self):
        calls = []
        def bt(*args, **kwargs):
            calls.append((args, kwargs))
            return 'Errore Bluetooth: timed out after 20 seconds' if args[0] == 'connect' else 'Connected: yes'
        self.namespace['comando_bt'] = bt
        results = []
        self.app._azione_completata = results.append
        self.app._azione('connect', 'AA:BB:CC:DD:EE:FF')
        self.drain()
        self.assertEqual(results, [''])
        self.assertEqual([c[0][0] for c in calls], ['connect', 'info'])
        self.assertEqual(calls[1][1], {'limite': 2})
        self.assertIn('timed out', self.app.diagnostica['Bluetooth'])

    def test_connect_timeout_exhausts_bounded_state_checks(self):
        calls = []
        def bt(*args, **kwargs):
            calls.append(args[0])
            return 'Errore Bluetooth: timed out' if args[0] == 'connect' else 'Connected: no'
        self.namespace['comando_bt'] = bt
        self.namespace['time'] = SimpleNamespace(sleep=lambda _: None, strftime=time.strftime)
        results = []
        self.app._azione_completata = results.append
        self.app._azione('connect', 'AA:BB:CC:DD:EE:FF')
        self.drain()
        self.assertEqual(calls, ['connect'] + ['info']*5)
        self.assertIn('timed out', results[0])

    def test_log_keeps_changed_states_and_clear_does_not_republish_old_state(self):
        app = self.app
        app._log_stato('telefono', 'disconnesso')
        app._log_stato('telefono', 'disconnesso')
        app._log_stato('telefono', 'connesso')
        self.assertEqual(len(app.log_eventi), 2)
        app._conserva_dettaglio('Bluetooth', 'Errore completo\nseconda riga')
        self.assertIn('seconda riga', app.log_eventi[-1])
        app._cancella_log()
        self.assertEqual(app.log_eventi, [])
        self.assertEqual(app.diagnostica, {})
        app._log_stato('telefono', 'connesso')
        self.assertEqual(app.log_eventi, [])
        app._log_stato('telefono', 'disconnesso')
        self.assertEqual(len(app.log_eventi), 1)

    def test_log_close_preserves_history(self):
        self.app._log('Sessione', 'messaggio da conservare')
        self.app._chiudi_log()
        self.assertIn('messaggio da conservare', self.app.log_eventi[-1])

    def test_hidden_log_batches_text_without_losing_events(self):
        from unittest.mock import Mock
        app = self.app
        app.log_pannello = Mock()
        app.log_pannello.get_visible.return_value = False
        app.log_buffer = Mock()
        app._log('Test', 'primo')
        app._log('Test', 'secondo')
        app.log_buffer.insert.assert_not_called()
        app._aggiorna_log_testo()
        self.assertEqual(app.log_buffer.insert.call_count, 1)
        self.assertIn('primo', app.log_buffer.insert.call_args.args[1])
        self.assertIn('secondo', app.log_buffer.insert.call_args.args[1])
        app._aggiorna_log_testo()
        self.assertEqual(app.log_buffer.insert.call_count, 1)
        app._cancella_log()
        app._log('Test', 'terzo')
        app._aggiorna_log_testo()
        self.assertNotIn('primo', app.log_buffer.insert.call_args.args[1])

    def test_log_close_removes_position_timer(self):
        app = self.app
        app.log_tick = 321
        app._chiudi_log()
        self.assertIn(321, self.removed_timers)
        self.assertIsNone(app.log_tick)

    def test_routing_thread_failure_allows_next_poll(self):
        app = self.app
        class BrokenThread:
            def __init__(self, **kwargs): pass
            def start(self): raise RuntimeError('simulated thread failure')
        self.namespace['threading'] = SimpleNamespace(Thread=BrokenThread)
        app._controlla_audio()
        self.assertFalse(app.lettura_instradamento)
        self.assertIn('simulated thread failure', app.diagnostica['Audio'])

    def test_audio_poll_is_throttled_in_tray_but_immediate_when_visible(self):
        from unittest.mock import Mock
        app = self.app
        app.finestra = Mock()
        app.finestra.get_visible.return_value = False
        app.lettura_instradamento = True
        app.dispositivo_audio = 'telefono'
        app.aggiorna_info_audio = Mock()
        clock = [100]
        self.namespace['time'] = SimpleNamespace(monotonic=lambda: clock[0])
        for now in (100, 103, 106, 109, 112, 115):
            clock[0] = now
            app._controlla_audio()
        self.assertEqual(app.aggiorna_info_audio.call_count, 2)
        app.finestra.get_visible.return_value = True
        clock[0] = 116
        app._controlla_audio()
        self.assertEqual(app.aggiorna_info_audio.call_count, 3)

    def test_log_delta_preserves_initial_state_and_resets_after_clear(self):
        app = self.app
        app._log_stato('audio', '{"volume": 50, "profiles": ["a2dp", "hfp"]}')
        app._log_stato('audio', '{"volume": 60, "profiles": ["a2dp", "hfp"]}')
        self.assertIn('profiles', app.log_eventi[0])
        self.assertNotIn('profiles', app.log_eventi[1])
        self.assertIn('60', app.log_eventi[1])
        app._cancella_log()
        app._log_stato('audio', '{"volume": 70, "profiles": ["a2dp", "hfp"]}')
        self.assertIn('profiles', app.log_eventi[0])


if __name__ == '__main__':
    unittest.main()
