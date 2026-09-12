# SPDX-License-Identifier: GPL-3.0-or-later
"""Scansione BlueZ: cache, eventi radio, stop ed errori senza hardware."""
import importlib.util
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from gi.repository import GLib

spec = importlib.util.spec_from_file_location('obyn_discovery_test', Path(__file__).resolve().parents[1] / 'src/obyn.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
ADAPTER = '/org/bluez/hci0'
DEVICE = ADAPTER + '/dev_AA_BB_CC_DD_EE_FF'
MAC = 'AA:BB:CC:DD:EE:FF'
CONTROLLER = '11:22:33:44:55:66'


def objects():
    return {ADAPTER: {'org.bluez.Adapter1': {'Address': CONTROLLER, 'Powered': True}},
            DEVICE: {'org.bluez.Device1': {'Address': MAC, 'Adapter': ADAPTER,
                                          'Alias': 'Cached headset', 'Paired': True, 'RSSI': -50}}}


class DiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.scan = module.RicercaBluez(CONTROLLER)
        self.scan.adattatore = ADAPTER
        self.scan.oggetti = objects()

    def test_discovery_preserves_service_metadata(self):
        props = self.scan.oggetti[DEVICE]['org.bluez.Device1']
        props['AddressType'] = 'random'
        props['UUIDs'] = ['0000fe2c-0000-1000-8000-00805f9b34fb']
        state = self.scan.dispositivi()[0][2]
        self.assertEqual(state['address_type'], 'random')
        self.assertEqual(state['uuids'], props['UUIDs'])

    def signal(self, name, variant, path=DEVICE):
        self.scan._segnale(None, 'org.bluez', path, '', name, variant)

    def test_cached_rssi_does_not_count_as_observation(self):
        self.assertEqual(self.scan.visti, set())
        self.assertEqual(self.scan.dispositivi()[0][0], MAC)

    def test_live_rssi_counts_but_connection_change_does_not(self):
        self.signal('PropertiesChanged', GLib.Variant('(sa{sv}as)',
                    (self.scan.DEVICE, {'Connected': GLib.Variant('b', True)}, [])))
        self.assertEqual(self.scan.visti, set())
        self.signal('PropertiesChanged', GLib.Variant('(sa{sv}as)',
                    (self.scan.DEVICE, {'RSSI': GLib.Variant('n', -40)}, [])))
        self.assertEqual(self.scan.visti, {MAC})
        self.assertTrue(self.scan.dispositivi()[0][2]['connected'])

    def test_new_device_without_name_is_visible(self):
        self.scan.oggetti.pop(DEVICE)
        self.signal('InterfacesAdded', GLib.Variant('(oa{sa{sv}})', (DEVICE, {
            self.scan.DEVICE: {'Address': GLib.Variant('s', MAC), 'Adapter': GLib.Variant('o', ADAPTER)}
        })))
        self.assertEqual(self.scan.visti, {MAC})
        self.assertEqual(self.scan.dispositivi()[0][1], MAC)

    def test_other_controller_is_excluded(self):
        self.scan.oggetti[DEVICE][self.scan.DEVICE]['Adapter'] = '/org/bluez/hci1'
        self.scan._segna_visto(DEVICE)
        self.assertEqual(self.scan.visti, set())
        self.assertEqual(self.scan.dispositivi(), [])

    def test_device_removal_removes_row(self):
        self.signal('InterfacesRemoved', GLib.Variant('(oas)', (DEVICE, [self.scan.DEVICE])))
        self.assertEqual(self.scan.dispositivi(), [])

    def test_adapter_removal_reports_error(self):
        self.signal('InterfacesRemoved', GLib.Variant('(oas)', (ADAPTER, [self.scan.ADAPTER])))
        self.assertIn('rimosso', self.scan.errore_evento)

    def test_power_loss_reports_error(self):
        self.signal('PropertiesChanged', GLib.Variant('(sa{sv}as)',
                    (self.scan.ADAPTER, {'Powered': GLib.Variant('b', False)}, [])), ADAPTER)
        self.assertTrue(self.scan.errore_evento)

    def run_session(self, *, fail_start=False, discovering=True, cancel=False, fail_stop=False):
        owner = self
        self.methods = []
        self.snapshots = []
        self.closed = False
        self.unsubscribed = []
        class Reply:
            def __init__(self, value): self.value = value
            def unpack(self): return self.value
        class Connection:
            def set_exit_on_close(self, value): pass
            def signal_subscribe(self, *args): return 10 + len(owner.methods)
            def signal_unsubscribe(self, ident): owner.unsubscribed.append(ident)
            def close_sync(self, cancellable): owner.closed = True
            def call_sync(self, bus, path, iface, method, parameters, *args):
                owner.methods.append(method)
                if method == 'GetManagedObjects': return Reply((objects(),))
                if method == 'StartDiscovery' and fail_start: raise RuntimeError('org.bluez.Error.NotReady')
                if method == 'StopDiscovery' and fail_stop: raise RuntimeError('stop failed')
                if method == 'Get': return Reply((discovering,))
                return Reply(())
        event = threading.Event()
        if cancel: event.set()
        with patch.object(module.Gio, 'dbus_address_get_for_bus_sync', return_value='test'), \
             patch.object(module.Gio.DBusConnection, 'new_for_address_sync', return_value=Connection()):
            self.scan.esegui(event, lambda devices, seen: self.snapshots.append((devices, seen)), durata=0)

    def test_success_is_confirmed_and_session_released(self):
        self.run_session()
        self.assertIn('Get', self.methods)
        self.assertEqual(len(self.snapshots), 2)
        self.assertEqual(self.snapshots[0][1], set())
        self.assertIn('StopDiscovery', self.methods)
        self.assertTrue(self.closed)

    def test_start_failure_is_not_empty_success(self):
        with self.assertRaisesRegex(RuntimeError, 'NotReady'): self.run_session(fail_start=True)
        self.assertEqual(self.snapshots, [])
        self.assertNotIn('StopDiscovery', self.methods)
        self.assertTrue(self.closed)

    def test_missing_start_confirmation_releases_session(self):
        with self.assertRaisesRegex(RuntimeError, 'confermato'): self.run_session(discovering=False)
        self.assertEqual(self.snapshots, [])
        self.assertIn('StopDiscovery', self.methods)
        self.assertTrue(self.closed)

    def test_cancel_before_start_does_not_start_session(self):
        self.run_session(cancel=True)
        self.assertNotIn('StartDiscovery', self.methods)
        self.assertTrue(self.closed)

    def test_stop_failure_still_closes_private_connection(self):
        with self.assertRaisesRegex(RuntimeError, 'stop failed'): self.run_session(fail_stop=True)
        self.assertTrue(self.closed)
        self.assertTrue(self.unsubscribed)


if __name__ == '__main__':
    unittest.main()
