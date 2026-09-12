# SPDX-License-Identifier: GPL-3.0-or-later
"""Profili, nodi, verifiche e controlli audio senza hardware o display."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from test_operations import Widget

spec = importlib.util.spec_from_file_location('obyn_audio_test', Path(__file__).resolve().parents[1] / 'src/obyn.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
MAC = 'AA:BB:CC:DD:EE:FF'
CARD = 'bluez_card.AA_BB_CC_DD_EE_FF'
SINK = 'bluez_output.AA_BB_CC_DD_EE_FF.1'
SOURCE = 'bluez_input.AA:BB:CC:DD:EE:FF'


def snapshot(hfp=False):
    return {'connected': True, 'card': CARD, 'active': 'headset-head-unit' if hfp else 'a2dp-sink',
            'profiles': {'a2dp-sink': {'available': True, 'priority': 40},
                         'headset-head-unit': {'available': True, 'priority': 20}},
            'sink': SINK, 'source': SOURCE if hfp else None, 'volume': 80,
            'default_sink': 'other', 'default_source': 'other'}


class BackendTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.connected = True
        self.cards = [{'name': CARD, 'index': 5, 'active_profile': 'a2dp-sink',
                       'profiles': {'a2dp-sink': {'available': True, 'priority': 40},
                                    'headset-head-unit': {'available': False, 'priority': 20},
                                    'off': {'available': True}, 'unknown': {}}}]
        self.sinks = [{'name': SINK, 'card': 5, 'volume': {'left': {'value': 65536}, 'right': {'value': 32768}}}]
        self.sources = [{'name': SINK + '.monitor', 'card': 5},
                        {'name': 'bluez_input.other', 'card': 9}]

    def command(self, args, limite=None):
        self.calls.append(args)
        if args[0] == 'bluetoothctl':
            return 'Blocked: no\nConnected: ' + ('yes' if self.connected else 'no')
        if args[-1] == 'cards': return json.dumps(self.cards)
        if args[-1] == 'sinks': return json.dumps(self.sinks)
        if args[-1] == 'sources': return json.dumps(self.sources)
        if args[-1] == 'info': return json.dumps({'default_sink_name': SINK, 'default_source_name': 'other'})
        raise AssertionError(args)

    def read(self):
        with patch.object(m.AudioPipewire, 'comando', side_effect=self.command):
            return m.AudioPipewire.leggi(MAC)

    def test_snapshot_uses_actual_card_and_excludes_monitors_other_devices(self):
        state = self.read()
        self.assertEqual(state['sink'], SINK)
        self.assertIsNone(state['source'])
        self.assertEqual(state['volume'], 75)
        self.assertEqual(state['default_sink'], SINK)
        self.assertEqual(m.AudioPipewire.profili(state, 'hfp'), [])
        self.assertNotIn('unknown', state['profiles'])

    def test_hfp_source_is_identified_by_card_not_mac_spelling(self):
        self.cards[0]['active_profile'] = 'headset-head-unit'
        self.sources.append({'name': SOURCE, 'card': 5})
        self.assertEqual(self.read()['source'], SOURCE)

    def test_disconnected_does_not_expose_stale_pipewire_nodes(self):
        self.connected = False
        state = self.read()
        self.assertFalse(state['connected'])
        self.assertIsNone(state['sink'])
        self.assertEqual(len(self.calls), 1)

    def test_missing_card_does_not_guess_profiles(self):
        self.cards = []
        state = self.read()
        self.assertIsNone(state['card'])
        self.assertEqual(state['profiles'], {})

    def test_change_waits_for_active_profile_and_both_hfp_nodes(self):
        a2dp = snapshot()
        pending = snapshot(True); pending['source'] = None
        with patch.object(m.AudioPipewire, 'leggi', side_effect=[a2dp, a2dp, pending, snapshot(True)]) as read, \
             patch.object(m.AudioPipewire, 'comando') as command, patch.object(m.time, 'sleep'):
            result = m.AudioPipewire.cambia_profilo(MAC, 'hfp')
        self.assertEqual(read.call_count, 4)
        self.assertEqual(result['source'], SOURCE)
        self.assertEqual(command.call_args.args[0], ['pactl', 'set-card-profile', CARD, 'headset-head-unit'])

    def test_unavailable_profile_does_not_run_guessed_names(self):
        state = snapshot(); state['profiles'].pop('headset-head-unit')
        with patch.object(m.AudioPipewire, 'leggi', return_value=state), patch.object(m.AudioPipewire, 'comando') as command:
            with self.assertRaisesRegex(RuntimeError, 'non disponibile'):
                m.AudioPipewire.cambia_profilo(MAC, 'hfp')
        command.assert_not_called()

    def test_wait_times_out_without_false_success(self):
        clock = [0]
        with patch.object(m.AudioPipewire, 'leggi', return_value=snapshot()), \
             patch.object(m.AudioPipewire, 'comando'), \
             patch.object(m.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(m.time, 'sleep', side_effect=lambda value: clock.__setitem__(0, clock[0] + value)):
            with self.assertRaises(TimeoutError): m.AudioPipewire.cambia_profilo(MAC, 'hfp')
        self.assertLessEqual(clock[0], 15)

    def test_disconnect_during_switch_is_failure(self):
        state = snapshot(); state['connected'] = False
        with patch.object(m.AudioPipewire, 'leggi', side_effect=[snapshot(), state]), patch.object(m.AudioPipewire, 'comando'):
            with self.assertRaisesRegex(RuntimeError, 'disconnesso'):
                m.AudioPipewire.cambia_profilo(MAC, 'hfp')

    def test_command_failure_and_timeout_are_not_success(self):
        with patch.object(m.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'audio failed')):
            with self.assertRaisesRegex(RuntimeError, 'audio failed'):
                m.AudioPipewire.comando(['paplay', 'test.wav'])
        with patch.object(m.subprocess, 'run', side_effect=subprocess.TimeoutExpired('pactl', 5)):
            with self.assertRaises(TimeoutError): m.AudioPipewire.comando(['pactl', 'info'])

    def test_real_pipewire_node_without_card_field_is_recognized(self):
        self.sinks[0].pop('card')
        self.sinks[0]['properties'] = {'api.bluez5.address': MAC, 'device.name': CARD, 'device.id': '91'}
        self.cards[0]['properties'] = {'object.id': '91'}
        self.assertEqual(self.read()['sink'], SINK)

    def test_hfp_microphone_without_card_field_is_recognized(self):
        self.cards[0]['active_profile'] = 'headset-head-unit'
        self.sources.append({'name': SOURCE, 'properties': {'api.bluez5.address': MAC, 'device.name': CARD}})
        self.assertEqual(self.read()['source'], SOURCE)

    def test_a2dp_loopback_is_not_an_active_hfp_microphone(self):
        self.sources.append({'name': SOURCE, 'properties': {'api.bluez5.address': MAC, 'bluez5.loopback': 'true'}})
        self.assertIsNone(self.read()['source'])

    def test_conflicting_mac_cannot_match_card(self):
        self.sinks[0]['properties'] = {'api.bluez5.address': '00:11:22:33:44:55'}
        self.assertIsNone(self.read()['sink'])

    def test_pipewire_object_id_is_distinct_from_pulse_index(self):
        self.cards[0]['properties'] = {'object.id': '91'}
        self.sinks[0].pop('card')
        self.sinks[0]['properties'] = {'device.id': '91'}
        self.assertEqual(self.read()['sink'], SINK)
        self.sinks[0]['properties']['device.id'] = '5'
        self.assertIsNone(self.read()['sink'])

    def test_tiny_remaining_deadline_does_not_spawn_a_process(self):
        with patch.object(m.time, 'monotonic', return_value=10), patch.object(m.subprocess, 'run') as run:
            with self.assertRaises(TimeoutError): m.AudioPipewire.comando(['bluetoothctl', 'info', MAC], 10.001)
        run.assert_not_called()


class ControlsTest(unittest.TestCase):
    def setUp(self):
        with patch.object(m.ObynApplication, 'carica_config', return_value={}):
            self.app = m.ObynApplication()
        self.app.dispositivo_audio = MAC
        self.app.nome_dispositivo_audio = 'Headset'
        self.app.audio_info = Widget()
        self.app.pulsanti_audio = {action: Widget() for action in
            ('uscita', 'microfono', 'a2dp', 'hfp', 'test_audio', 'test_microfono', 'auto_connect')}
        self.app.volume_slider = Widget()
        self.app.volume_label = Widget()

    def test_startup_switch_replaces_previous_device(self):
        from unittest.mock import Mock
        app = self.app
        app.config = {'auto_connect': 'previous'}
        old, new = Mock(), Mock()
        app.interruttori_avvio = {'previous': old, MAC: new}
        with patch.object(app, 'salva_config'):
            app._imposta_avvio(new, True, MAC)
        self.assertEqual(app.config['auto_connect'], MAC)
        old.set_active.assert_called_with(False)
        new.set_active.assert_called_with(True)

    def test_carousel_navigation_stays_within_bounds(self):
        from unittest.mock import Mock
        app = self.app
        adj = Mock()
        adj.get_upper.return_value = 924
        adj.get_page_size.return_value = 400
        adj.get_value.return_value = 400
        app.scroller_dispositivi = Mock()
        app.scroller_dispositivi.get_hadjustment.return_value = adj
        app._scorri_dispositivi(1)
        adj.set_value.assert_called_with(524)
        adj.get_value.return_value = 100
        app._scorri_dispositivi(-1)
        adj.set_value.assert_called_with(0)

    def test_carousel_arrows_only_show_for_overflow(self):
        from unittest.mock import Mock
        app = self.app
        left, right, rail_left, rail_right = Mock(), Mock(), Mock(), Mock()
        app.frecce_dispositivi = [(rail_left, left, -1), (rail_right, right, 1)]
        adj = Mock()
        adj.get_upper.return_value = 300
        adj.get_page_size.return_value = 500
        adj.get_value.return_value = 0
        app._aggiorna_frecce(adj)
        rail_left.set_visible.assert_called_with(False)
        adj.get_upper.return_value = 924
        app._aggiorna_frecce(adj)
        rail_left.set_visible.assert_called_with(False)
        rail_right.set_visible.assert_called_with(True)
        left.set_sensitive.assert_called_with(False)
        right.set_sensitive.assert_called_with(True)
        adj.get_value.return_value = 424
        app._aggiorna_frecce(adj)
        rail_right.set_visible.assert_called_with(False)
        rail_left.set_visible.assert_called_with(True)

    def test_normal_audio_status_hides_routine_success_and_routing_details(self):
        app = self.app
        app.audio_dettagli = Widget()
        app._ricevi_audio(MAC, snapshot(True), 'Operazione completata.')
        self.assertNotIn('Operazione completata', app.audio_info.text)
        self.assertNotIn('Uscita', app.audio_info.text)
        self.assertIn('Uscita', app.audio_dettagli.text)
        self.assertIn('Voce e microfono (HFP)', app.audio_info.text)

    def test_copy_details_preserves_exact_diagnostic_text(self):
        from unittest.mock import Mock
        app = self.app
        app.finestra = Mock()
        app.dettagli_label = Mock()
        app.log_eventi = ['Bluetooth\nErrore originale', 'Audio\nSecondo errore']
        app._copia_dettagli(Mock())
        app.finestra.get_clipboard.return_value.set.assert_called_once_with(
            'Bluetooth\nErrore originale\nAudio\nSecondo errore')

    def test_combined_pairing_verifies_both_states(self):
        app = self.app
        outputs = ['Paired: no\nTrusted: no', 'Pairing successful',
                   'Paired: yes\nTrusted: no', 'trust succeeded',
                   'Paired: yes\nTrusted: yes']
        with patch.object(m, 'comando_bt', side_effect=outputs) as command, \
             patch.object(m.GLib, 'idle_add') as idle:
            app._associa_autorizza(MAC)
        self.assertEqual([c.args[0] for c in command.call_args_list],
                         ['info','pair','info','trust','info'])
        self.assertEqual(idle.call_args.args[1], '')

    def test_pair_failure_does_not_trust_device(self):
        with patch.object(m, 'comando_bt', side_effect=['Paired: no', 'Failed pairing']) as command, \
             patch.object(m.GLib, 'idle_add') as idle:
            self.app._associa_autorizza(MAC)
        self.assertEqual([c.args[0] for c in command.call_args_list], ['info','pair'])
        self.assertIn('Failed', idle.call_args.args[1])

    def test_already_paired_only_completes_trust(self):
        with patch.object(m, 'comando_bt', side_effect=['Paired: yes\nTrusted: no', 'ok',
             'Paired: yes\nTrusted: yes']) as command, patch.object(m.GLib, 'idle_add'):
            self.app._associa_autorizza(MAC)
        self.assertEqual([c.args[0] for c in command.call_args_list], ['info','trust','info'])

    def test_device_icon_uses_bluez_hint(self):
        self.assertEqual(m.ObynApplication._tipo_icona({'icon': 'audio-headset'}), 'headset')
        self.assertEqual(m.ObynApplication._tipo_icona({}), 'device')

    def test_fast_pair_label_uses_uuid_not_name_or_random_address(self):
        describe = m.ObynApplication._dicitura_dispositivo
        self.assertEqual(describe({'address_type': 'random', 'uuids':
            ['0000fe2c-0000-1000-8000-00805f9b34fb']}), 'Google Fast Pair · indirizzo casuale')
        self.assertNotIn('Fast Pair', describe({'address_type': 'random'}))
        self.assertIn('Servizi non ancora identificati', describe({'address_type': 'public'}))
        both = describe({'uuids': ['0000fe2c-0000-1000-8000-00805f9b34fb',
                                   '0000110b-0000-1000-8000-00805f9b34fb']})
        self.assertIn('Google Fast Pair', both)
        self.assertIn('Servizi audio dichiarati', both)

    def test_refresh_parses_address_type_and_uuid(self):
        state = m.ObynApplication._stato_info(
            'Device AA:BB:CC:DD:EE:FF (random)\nPaired: yes\nUUID: Vendor specific (0000fe2c-0000-1000-8000-00805f9b34fb)')
        self.assertEqual(state['address_type'], 'random')
        self.assertIn('Google Fast Pair', m.ObynApplication._dicitura_dispositivo(state))

    def test_error_summary_keeps_technical_detail_separate(self):
        app = self.app
        detail = 'Command bluetoothctl timed out after 0.1 seconds'
        app._ricevi_audio(MAC, snapshot(), 'Operazione audio non riuscita: ' + detail)
        self.assertNotIn('0.1 seconds', app.audio_info.text)
        self.assertIn('non ha confermato', app.audio_info.text)
        self.assertIn(detail, app.diagnostica['Audio'])
        app._ricevi_audio(MAC, snapshot(True), 'Operazione completata.')
        self.assertIn('Voce e microfono (HFP)', app.audio_info.text)
        self.assertIn(detail, app.diagnostica['Audio'])

    def test_bluez_timeout_is_explained_without_losing_diagnostic(self):
        app = self.app
        app.stato = Widget()
        detail = 'org.bluez.Error.Failed br-connection-page-timeout'
        app._mostra_errore_bt(detail)
        self.assertIn('non ha risposto', app.stato.text)
        self.assertNotIn('org.bluez', app.stato.text)
        self.assertEqual(app.diagnostica['Bluetooth'], detail)

    def test_recent_user_value_is_not_overwritten_by_initial_snapshot(self):
        app = self.app
        app.volume_ultima_modifica = 100
        with patch.object(m.time, 'monotonic', return_value=100.5), \
             patch.object(app.volume_slider, 'set_value') as move:
            app._ricevi_audio(MAC, snapshot(), None)
        move.assert_not_called()

    def test_volume_completion_does_not_rewrite_status_text(self):
        app = self.app
        app.operazione = 'volume'
        with patch.object(app.audio_info, 'set_text') as text:
            app._ricevi_audio(MAC, snapshot(), 'Operazione completata.')
        text.assert_not_called()
        self.assertEqual(app.messaggio_audio, 'Operazione completata.')

    def test_volume_write_keeps_slider_enabled_and_position(self):
        app = self.app
        app.operazione = 'volume'
        with patch.object(app.volume_slider, 'set_value') as move:
            app._ricevi_audio(MAC, snapshot(), None)
            move.assert_not_called()
        self.assertTrue(app.volume_slider.sensitive)
        self.assertTrue(app.pulsanti_audio['hfp'].sensitive)

    def test_changes_during_volume_write_keep_only_latest(self):
        app = self.app
        app.operazione = 'volume'
        with patch.object(app.volume_slider, 'get_value', side_effect=[91, 99]), \
             patch.object(m.GLib, 'timeout_add') as timer:
            app._volume_modificato(app.volume_slider)
            app._volume_modificato(app.volume_slider)
        self.assertEqual(app.volume_pendente, 99)
        timer.assert_not_called()
        self.assertEqual(app.volume_label.text, '99%')

    def test_drag_defers_volume_until_release(self):
        app = self.app
        app.volume_timeout = 42
        with patch.object(m.GLib, 'source_remove') as remove, \
             patch.object(m.GLib, 'timeout_add', return_value=43) as timer, \
             patch.object(app.volume_slider, 'get_value', return_value=97):
            app._inizia_volume()
            remove.assert_called_once_with(42)
            app._volume_modificato(app.volume_slider)
            timer.assert_not_called()
            self.assertEqual(app.volume_label.text, '97%')
            app._finisci_volume()
            timer.assert_called_once_with(180, app._applica_volume, 97)
            self.assertFalse(app.volume_trascinamento)

    def test_background_refresh_does_not_move_dragged_slider(self):
        app = self.app
        app._inizia_volume()
        with patch.object(app.volume_slider, 'set_value') as move:
            app._ricevi_audio(MAC, snapshot(), None)
            move.assert_not_called()
        self.assertTrue(app.volume_slider.sensitive)

    def test_a2dp_disables_microphone_and_active_profile_button(self):
        self.app._ricevi_audio(MAC, snapshot(), '')
        buttons = self.app.pulsanti_audio
        self.assertFalse(buttons['microfono'].sensitive)
        self.assertTrue(buttons['test_microfono'].sensitive)
        self.assertFalse(buttons['a2dp'].sensitive)
        self.assertTrue(buttons['hfp'].sensitive)
        self.assertTrue(buttons['test_audio'].sensitive)
        self.assertIn('Ascolto (A2DP)', self.app.audio_info.text)

    def test_hfp_enables_microphone_only_with_source(self):
        self.app._ricevi_audio(MAC, snapshot(True), '')
        self.assertTrue(self.app.pulsanti_audio['test_microfono'].sensitive)
        self.app.operazione = 'audio'
        self.app._abilita_audio()
        self.assertFalse(any(w.sensitive for w in self.app.pulsanti_audio.values()))

    def test_disconnected_disables_audio_but_preserves_auto_preference_control(self):
        state = snapshot(); state['connected'] = False
        self.app._ricevi_audio(MAC, state, '')
        self.assertFalse(self.app.volume_slider.sensitive)
        self.assertFalse(self.app.pulsanti_audio['test_audio'].sensitive)
        self.assertTrue(self.app.pulsanti_audio['auto_connect'].sensitive)

    def test_stale_selection_result_is_discarded(self):
        self.app._ricevi_audio('OTHER', snapshot(True), '')
        self.assertEqual(self.app.stato_audio, {})

    def test_disconnect_before_action_prevents_playback(self):
        state = snapshot(); state['connected'] = False
        with patch.object(m.AudioPipewire, 'leggi', return_value=state), \
             patch.object(m.AudioPipewire, 'comando') as command, \
             patch.object(m.GLib, 'idle_add', side_effect=lambda fn,*a: fn(*a)):
            self.app._azione_audio('test_audio', MAC)
        command.assert_not_called()
        self.assertIn('non riuscita', self.app.audio_info.text)

    def test_failed_playback_is_visible(self):
        with patch.object(m.AudioPipewire, 'leggi', return_value=snapshot()), \
             patch.object(m.AudioPipewire, 'comando', side_effect=RuntimeError('paplay failed')), \
             patch.object(m.GLib, 'idle_add', side_effect=lambda fn,*a: fn(*a)):
            self.app._azione_audio('test_audio', MAC)
        self.assertIn('paplay failed', '\n'.join(self.app.diagnostica.values()))
        self.assertNotIn('Operazione completata', self.app.audio_info.text)

    def test_missing_default_confirmation_is_failure(self):
        with patch.object(m.AudioPipewire, 'leggi', return_value=snapshot()), \
             patch.object(self.app, '_commuta_instradamento', side_effect=RuntimeError('Uscita non confermata')), \
             patch.object(m.GLib, 'idle_add', side_effect=lambda fn,*a: fn(*a)):
            self.app._azione_audio('uscita', MAC)
        self.assertNotIn('non confermata', self.app.audio_info.text)
        self.assertIn('non confermata', str(self.app.diagnostica))

    def test_auto_connect_can_be_disabled(self):
        self.app.config['auto_connect'] = MAC
        with patch.object(self.app, 'salva_config'), patch.object(m.AudioPipewire, 'leggi', return_value=snapshot()), \
             patch.object(m.GLib, 'idle_add', side_effect=lambda fn,*a: fn(*a)):
            self.app._azione_audio('auto_connect', MAC)
        self.assertNotIn('auto_connect', self.app.config)
        self.assertIn('disattivata', self.app.audio_info.text)

    def test_background_result_after_operation_is_discarded(self):
        self.app.audio_generazione = 2
        self.app.audio_lettura_in_corso = True
        self.app._ricevi_lettura_audio(MAC, 1, snapshot(), None)
        self.assertEqual(self.app.stato_audio, {})
        self.assertFalse(self.app.audio_lettura_in_corso)

    def test_background_result_does_not_override_pending_volume(self):
        self.app.volume_timeout = 42
        self.app._ricevi_lettura_audio(MAC, self.app.audio_generazione, snapshot(), None)
        self.assertEqual(self.app.stato_audio, {})

    def test_recovered_read_clears_connection_error(self):
        self.app._ricevi_audio(MAC, {}, 'Stato audio non disponibile: connection refused')
        self.app._ricevi_audio(MAC, snapshot(), None)
        self.assertNotIn('connection refused', self.app.audio_info.text)


if __name__ == '__main__':
    unittest.main()
