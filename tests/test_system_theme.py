# SPDX-License-Identifier: GPL-3.0-or-later
import unittest
from unittest.mock import Mock, patch
from test_audio import m


class SystemThemeTest(unittest.TestCase):
    def setUp(self):
        self.start = patch.object(m.Gio.DBusProxy, 'new_for_bus')
        self.start.start()
        self.addCleanup(self.start.stop)
        self.settings = Mock()
        self.theme = m.TemaSistema(self.settings)

    def signal(self, value, namespace='org.freedesktop.appearance'):
        self.theme._segnale(None, None, 'SettingChanged',
            m.GLib.Variant('(ssv)', (namespace, 'color-scheme', m.GLib.Variant('u', value))))

    def test_switch_both_directions_without_restart(self):
        self.signal(1)
        self.settings.set_property.assert_called_with('gtk-application-prefer-dark-theme', True)
        self.signal(2)
        self.settings.set_property.assert_called_with('gtk-application-prefer-dark-theme', False)

    def test_no_preference_restores_user_settings(self):
        for value in (0, 42):
            self.signal(value)
            self.settings.reset_property.assert_called_with('gtk-application-prefer-dark-theme')

    def test_unrelated_signal_does_not_change_theme(self):
        self.signal(1, 'other.namespace')
        self.settings.set_property.assert_not_called()

    def test_initial_read_cannot_override_newer_signal(self):
        proxy = Mock()
        proxy.call_finish.return_value = m.GLib.Variant('(a{sa{sv}})', (
            {'org.freedesktop.appearance': {'color-scheme': m.GLib.Variant('u', 2)}},))
        self.signal(1)
        self.theme._letto(proxy, None, 0)
        self.settings.set_property.assert_called_once_with('gtk-application-prefer-dark-theme', True)

    def test_close_cancels_and_ignores_late_signals(self):
        self.theme.proxy = Mock()
        self.theme.handler = 7
        self.theme.close()
        self.assertTrue(self.theme.cancel.is_cancelled())
        self.theme.proxy.disconnect.assert_called_once_with(7)
        self.signal(1)
        self.settings.set_property.assert_not_called()

    def test_initial_read_applies_preference(self):
        proxy = Mock()
        proxy.call_finish.return_value = m.GLib.Variant('(a{sa{sv}})', (
            {'org.freedesktop.appearance': {'color-scheme': m.GLib.Variant('u', 1)}},))
        self.theme._letto(proxy, None, 0)
        self.settings.set_property.assert_called_once_with('gtk-application-prefer-dark-theme', True)
