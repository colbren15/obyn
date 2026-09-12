# SPDX-License-Identifier: GPL-3.0-or-later
import json
import unittest
from unittest.mock import patch
from test_audio import m, MAC, SINK, SOURCE, snapshot

class RoutingTest(unittest.TestCase):
    def setUp(self):
        self.app = m.ObynApplication()
        self.old = {'name': 'alsa_output.previous', 'index': 2}
        self.target = {'name': SINK, 'index': 3}
        self.data = {'default': self.old['name'], 'nodes': [self.old, self.target]}
        self.read = patch.object(m.AudioPipewire, 'leggi', return_value=snapshot()).start()
        self.route = patch.object(m.AudioPipewire, 'instradamento', side_effect=lambda: {'sink': self.data, 'source': self.data}).start()
        self.move = patch.object(m.AudioPipewire, 'sposta_predefinito').start()
        self.mute = patch.object(m.AudioPipewire, 'imposta_muto').start()
        self.addCleanup(patch.stopall)

    def test_output_returns_to_previous(self):
        self.app._commuta_instradamento(MAC, 'sink')
        self.move.assert_called_with('sink', SINK, self.old['name'])
        self.data['default'] = SINK
        self.app._commuta_instradamento(MAC, 'sink')
        self.move.assert_called_with('sink', self.old['name'], SINK)
        self.assertNotIn((MAC, 'sink'), self.app.precedenti_audio)

    def test_absent_previous_does_not_change_route(self):
        self.app.precedenti_audio[(MAC, 'sink')] = self.old
        self.data.update(default=SINK, nodes=[self.target])
        self.app._commuta_instradamento(MAC, 'sink')
        self.mute.assert_called_once_with('sink', SINK, True)
        self.move.assert_not_called()

    def test_initial_default_without_history_is_not_arbitrarily_replaced(self):
        self.data['default'] = SINK
        self.app._commuta_instradamento(MAC, 'sink')
        self.mute.assert_called_once_with('sink', SINK, True)
        self.move.assert_not_called()

    def test_microphone_saves_previous_before_hfp_changes_default(self):
        self.old['name'] = 'alsa_input.previous'
        self.data['default'] = self.old['name']
        with patch.object(m.AudioPipewire, 'cambia_profilo', return_value=snapshot(True)) as profile:
            self.app._commuta_instradamento(MAC, 'source')
        profile.assert_called_once_with(MAC, 'hfp')
        self.move.assert_called_with('source', SOURCE, 'alsa_input.previous')
        self.assertEqual(self.app.precedenti_audio[(MAC, 'source')]['name'], 'alsa_input.previous')
        self.assertNotIn((MAC, 'sink'), self.app.precedenti_audio)

    def test_failed_switch_keeps_return_target(self):
        self.move.side_effect = RuntimeError('server error')
        with self.assertRaises(RuntimeError):
            self.app._commuta_instradamento(MAC, 'sink')
        self.assertEqual(self.app.precedenti_audio[(MAC, 'sink')], self.old)

    def test_muted_default_is_reactivated_without_overwriting_history(self):
        self.data['default'] = SINK
        self.target['mute'] = True
        self.app.precedenti_audio[(MAC, 'sink')] = self.old
        self.app._commuta_instradamento(MAC, 'sink')
        self.mute.assert_called_once_with('sink', SINK, False)
        self.assertEqual(self.app.precedenti_audio[(MAC, 'sink')], self.old)

    def test_microphone_without_previous_is_muted(self):
        self.target['name'] = SOURCE
        self.data['default'] = SOURCE
        self.app._commuta_instradamento(MAC, 'source')
        self.mute.assert_called_once_with('source', SOURCE, True)
        self.move.assert_not_called()

    def test_disconnected_does_not_route(self):
        self.read.return_value = {'connected': False}
        with self.assertRaisesRegex(RuntimeError, 'disconnesso'):
            self.app._commuta_instradamento(MAC, 'sink')
        self.move.assert_not_called()

class ServerRoutingTest(unittest.TestCase):
    def test_existing_streams_move_only_from_previous_default(self):
        calls = []
        def command(args):
            calls.append(args)
            if args[-1] == 'sinks': return json.dumps([{'name': 'old', 'index': 2}])
            if args[-1] == 'sink-inputs': return json.dumps([{'index': 10, 'sink': 2}, {'index': 11, 'sink': 9}])
            if args[-1] == 'info': return json.dumps({'default_sink_name': 'new'})
            return ''
        with patch.object(m.AudioPipewire, 'comando', side_effect=command):
            m.AudioPipewire.sposta_predefinito('sink', 'new', 'old')
        self.assertIn(['pactl', 'move-sink-input', '10', 'new'], calls)
        self.assertNotIn(['pactl', 'move-sink-input', '11', 'new'], calls)

    def test_wrong_server_default_is_an_error(self):
        def command(args):
            if args[-1] == 'sinks': return '[]'
            if args[-1] == 'info': return json.dumps({'default_sink_name': 'old'})
            return ''
        with patch.object(m.AudioPipewire, 'comando', side_effect=command):
            with self.assertRaisesRegex(RuntimeError, 'non ha confermato'):
                m.AudioPipewire.sposta_predefinito('sink', 'new', 'old')

class MuteVerificationTest(unittest.TestCase):
    def test_mute_is_verified_for_both_channels(self):
        for tipo in ('sink', 'source'):
            with self.subTest(tipo=tipo), patch.object(m.AudioPipewire, 'comando', side_effect=['', json.dumps([{'name': 'node', 'mute': True}])]) as command:
                m.AudioPipewire.imposta_muto(tipo, 'node', True)
                self.assertEqual(command.call_args_list[0].args[0], ['pactl', 'set-' + tipo + '-mute', 'node', '1'])

    def test_failed_mute_confirmation_is_not_accepted(self):
        with patch.object(m.AudioPipewire, 'comando', side_effect=['', json.dumps([{'name': 'node', 'mute': False}])]):
            with self.assertRaisesRegex(RuntimeError, 'non confermato'):
                m.AudioPipewire.imposta_muto('source', 'node', True)
