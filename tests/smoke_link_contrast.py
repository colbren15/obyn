# SPDX-License-Identifier: GPL-3.0-or-later
"""Isolated GTK test; run with dbus-run-session. No Bluetooth or public links opened."""
import ast
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import time
from types import SimpleNamespace

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='obyn-link-test-') as temp:
    os.environ.update(XDG_CONFIG_HOME=temp, GDK_BACKEND='broadway', BROADWAY_DISPLAY=':90')
    server = subprocess.Popen(['gtk4-broadwayd', '--port=18090', ':90'], stdout=subprocess.DEVNULL)
    try:
        time.sleep(.3)
        assert server.poll() is None
        spec = importlib.util.spec_from_file_location('obyn', os.environ.get('OBYN_SOURCE', root / 'src/obyn.py'))
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        Gtk, GLib = m.Gtk, m.GLib
        Gtk.init()
        def drain():
            end = time.monotonic() + .04
            while time.monotonic() < end:
                while GLib.MainContext.default().pending(): GLib.MainContext.default().iteration(False)
                time.sleep(.002)
        def css(text, priority):
            p = Gtk.CssProvider(); p.load_from_data(text.encode())
            Gtk.StyleContext.add_provider_for_display(w.get_display(), p, priority)
            return p
        w = Gtk.Window(); anchor = Gtk.MenuButton(label='Options'); w.set_child(anchor)
        pop = Gtk.Popover(); pop.add_css_class('obyn-info'); anchor.set_popover(pop)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); pop.set_child(box)
        link = Gtk.LinkButton.new_with_label('https://example.org', 'Sostieni OBYN'); box.append(link)
        tree = ast.parse(Path(spec.origin).read_text())
        base = next(n.value.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Attribute) and t.attr == 'css_base' for t in n.targets))
        app = SimpleNamespace(tema_timer=None, tema_tonalita=m.TONALITA_PETROLIO,
            css_base=base, tema_provider=Gtk.CssProvider(), tema_link_provider=Gtk.CssProvider(),
            pulsanti_instradamento={})
        Gtk.StyleContext.add_provider_for_display(w.get_display(), app.tema_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        Gtk.StyleContext.add_provider_for_display(w.get_display(), app.tema_link_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER+2)
        desktop = css('button.link, button.link label { color: #800080; }', Gtk.STYLE_PROVIDER_PRIORITY_USER+1)
        w.present(); pop.popup(); drain()
        assert link.get_child().get_style_context().get_color().red < .6, 'Reproduce purple label'
        worst = 21
        def luminance(c):
            v = [int(c[i:i+2],16)/255 for i in (1,3,5)]
            v = [x/12.92 if x <= .04045 else ((x+.055)/1.055)**2.4 for x in v]
            return sum(a*b for a,b in zip(v,(.2126,.7152,.0722)))
        for dark in (False, True):
            Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme', dark)
            for hue in range(0,361,30):
                app.tema_tonalita=hue; m.ObynApplication._applica_tema(app)
                expected=m.ruota_tonalita('#eefbf6',hue)
                for visited in (False, True):
                    link.set_visited(visited)
                    for flags in (Gtk.StateFlags.NORMAL, Gtk.StateFlags.PRELIGHT, Gtk.StateFlags.FOCUSED | Gtk.StateFlags.FOCUS_VISIBLE):
                        link.set_state_flags(flags, False); drain()
                        c=link.get_child().get_style_context().get_color()
                        assert all(abs(v-int(expected[i:i+2],16)/255)<.01 for v,i in zip((c.red,c.green,c.blue),(1,3,5)))
                        link.unset_state_flags(flags)
                for bg in ('#203331','#2b4541','#36574f'):
                    ratio=(luminance(expected)+.05)/(luminance(m.ruota_tonalita(bg,hue))+.05)
                    worst=min(worst,ratio); assert ratio>=4.5, (hue,bg,ratio)
        import sys
        sys.path.insert(0,str(root/'reusable/obyn-components'))
        from obyn_components.author_header import AuthorHeader
        header=AuthorHeader('Demo','1','Author',support_url='https://example.org')
        box.append(header)
        host=Gtk.CssProvider()
        header.get_style_context().add_provider(host,Gtk.STYLE_PROVIDER_PRIORITY_USER+2)
        for fg,bg in (('#eefbf6','#203331'),('#202020','#fafafa')):
            host.load_from_data(f'.author-header {{ color: {fg}; background: {bg}; }}'.encode())
            for visited in (False,True):
                header.support_button.set_visited(visited); drain()
                c=header.support_button.get_child().get_style_context().get_color()
                assert all(abs(v-int(fg[i:i+2],16)/255)<.01 for v,i in zip((c.red,c.green,c.blue),(1,3,5)))
        print(f'PASS: light/dark, 13 hues, visited/hover/focus; minimum link contrast {worst:.2f}:1; reusable header on light/dark hosts')
        w.destroy()
    finally:
        server.terminate(); server.wait(timeout=5)
