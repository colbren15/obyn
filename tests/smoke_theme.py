# SPDX-License-Identifier: GPL-3.0-or-later
"""Run with dbus-run-session; uses Broadway and temporary GTK configuration only."""
import os
import tempfile
import subprocess
import time
import importlib.util
from pathlib import Path
from unittest.mock import Mock

with tempfile.TemporaryDirectory(prefix='obyn-theme-smoke-') as temp:
    config = Path(temp) / 'gtk-4.0'
    config.mkdir()
    colors = config / 'colors.css'
    light = '@define-color theme_bg_color #fafafa;\n'
    dark = '@define-color theme_bg_color #202020;\n'
    colors.write_text(light)
    (config / 'gtk.css').write_text("@import 'colors.css';\n")
    os.environ['XDG_CONFIG_HOME'] = temp
    os.environ['GDK_BACKEND'] = 'broadway'
    os.environ['BROADWAY_DISPLAY'] = ':89'
    server = subprocess.Popen(['gtk4-broadwayd', '--port=18089', ':89'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        time.sleep(.3)
        assert server.poll() is None, 'Broadway failed to start'
        spec = importlib.util.spec_from_file_location('obyn', os.environ.get('OBYN_TEST_SOURCE',
                    str(Path(__file__).resolve().parents[1] / 'src/obyn.py')))
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        assert m.Gtk.init_check()
        ctx = m.GLib.MainContext.default()
        def drain(seconds=.3):
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                while ctx.pending(): ctx.iteration(False)
                time.sleep(.005)
        w = m.Gtk.Window()
        def color():
            ok, value = w.get_style_context().lookup_color('theme_bg_color')
            assert ok
            return value.to_string()
        before = color()
        colors.write_text(dark); drain()
        assert color() == before, 'Expected cached GTK user stylesheet'
        watcher = m.ColoriKde(w.get_display(), config)
        drain()
        assert color() != before, 'Reload must replace cached color definitions'
        after = color()
        replacement = config / 'new.css'; replacement.write_text(light); replacement.replace(colors)
        drain()
        assert color() == before, 'Atomic replacement must be observed'
        colors.write_text(dark); drain()
        assert color() == after, 'Repeated dark switch must work'
        colors.write_text('invalid {'); drain()
        assert color() == after, 'Invalid partial write must retain valid colors'
        watcher.close()
        assert watcher.timer is None and watcher.provider is None
        # Real D-Bus transport on private session bus, not direct callback calls.
        bus = m.Gio.bus_get_sync(m.Gio.BusType.SESSION, None)
        bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus',
            'RequestName',m.GLib.Variant('(su)',('org.freedesktop.portal.Desktop',0)),
            None,m.Gio.DBusCallFlags.NONE,1000,None)
        xml = '''<node><interface name="org.freedesktop.portal.Settings">
        <method name="ReadAll"><arg type="as" direction="in"/><arg type="a{sa{sv}}" direction="out"/></method>
        <signal name="SettingChanged"><arg type="s"/><arg type="s"/><arg type="v"/></signal>
        </interface></node>'''
        info = m.Gio.DBusNodeInfo.new_for_xml(xml)
        def call(conn, sender, path, iface, method, params, invocation):
            invocation.return_value(m.GLib.Variant('(a{sa{sv}})',(
                {'org.freedesktop.appearance':{'color-scheme':m.GLib.Variant('u',2)}},)))
        ident = bus.register_object('/org/freedesktop/portal/desktop',info.interfaces[0],call,None,None)
        settings = Mock()
        theme = m.TemaSistema(settings); drain(.5)
        settings.set_property.assert_called_with('gtk-application-prefer-dark-theme',False)
        for value in (1,2):
            bus.emit_signal(None,'/org/freedesktop/portal/desktop','org.freedesktop.portal.Settings',
                'SettingChanged',m.GLib.Variant('(ssv)',('org.freedesktop.appearance','color-scheme',m.GLib.Variant('u',value))))
            drain()
            settings.set_property.assert_called_with('gtk-application-prefer-dark-theme',value==1)
        theme.close(); bus.unregister_object(ident); w.destroy()
        print('PASS: stale CSS reproduced; reload, atomic rename, invalid write, cleanup, private D-Bus ReadAll and live signals')
    finally:
        server.terminate(); server.wait(timeout=5)
