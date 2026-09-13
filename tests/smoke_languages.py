# SPDX-License-Identifier: GPL-3.0-or-later
"""Isolated bilingual UI test. No Bluetooth/audio commands or tray process."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import time
from unittest.mock import Mock

root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='obyn-languages-') as temp:
    os.environ.update(XDG_CONFIG_HOME=temp,GDK_BACKEND='broadway',BROADWAY_DISPLAY=':91')
    server=subprocess.Popen(['gtk4-broadwayd','--port=18091',':91'],stdout=subprocess.DEVNULL)
    try:
        time.sleep(.3); assert server.poll() is None
        spec=importlib.util.spec_from_file_location('obyn',os.environ.get('OBYN_SOURCE',root/'src/obyn.py'))
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        m._lingue.locale_dirs=(root/'locale',)
        def drain():
            end=time.monotonic()+.2
            while time.monotonic()<end:
                while m.GLib.MainContext.default().pending():m.GLib.MainContext.default().iteration(False)
                time.sleep(.002)
        def descendants(widget):
            yield widget
            child=widget.get_first_child()
            while child:
                yield from descendants(child)
                child=child.get_next_sibling()
        for language,title in [('it','Dispositivi Bluetooth'),('en','Bluetooth devices')]:
            app=m.ObynApplication();app.set_application_id('io.obyn.LanguageTest.'+language)
            app.config={'language':language}
            for name in ('_avvia_tray','aggiorna_elenco','_avvia_monitor_bt','_controlla_audio','_aggiorna_stato_bt'):
                setattr(app,name,Mock(return_value=False))
            app.register(None);app.activate();drain()
            app.finestra.set_default_size(388,680)
            state={'paired':True,'trusted':True,'connected':True,'uuids':[], 'address_type':'public'}
            app._mostra_dispositivi([('AA:BB:CC:DD:EE:FF','Test headset',state)])
            app.dispositivo_audio='AA:BB:CC:DD:EE:FF'
            app.menu_impostazioni.popup();drain()
            pop=app.menu_impostazioni.get_popover()
            labels=[w.get_text() for w in descendants(app.finestra) if isinstance(w,m.Gtk.Label)]
            assert title in labels, labels
            assert ('Connesso' if language=='it' else 'Connected') in labels
            assert ('Richiedi una personalizzazione' if language=='it' else 'Request a customization') in labels
            assert app.finestra.measure(m.Gtk.Orientation.HORIZONTAL,-1).minimum<=388
            assert not any(isinstance(w,m.Gtk.DropDown) for w in descendants(pop))
            assert pop.get_autohide()
            choice=next(w for w in descendants(pop) if isinstance(w,m.Gtk.ToggleButton) and w.get_label()==('Italiano' if language=='en' else 'English'))
            choice.set_active(True);drain()
            assert pop.get_visible()
            assert pop.measure(m.Gtk.Orientation.HORIZONTAL,-1).minimum <= 344
            assert app.config['language']==('it' if language=='en' else 'en')
            assert m._lingue.language==language,'Preference applies on restart, not mid-session'
            assert 'language' in app.config_path.read_text()
            app._log(m.tr('Sessione'),m.tr('Operazione completata.'))
            assert ('Operation completed.' if language=='en' else 'Operazione completata.') in app.log_eventi[-1]
            pop.popdown();drain();assert not pop.get_visible()
            assert app.menu_impostazioni.get_popover() is None
            app.menu_impostazioni.popup();drain()
            fresh=app.menu_impostazioni.get_popover()
            assert fresh is not pop and fresh.get_visible()
            fresh.popdown();drain()
            app._apri_log();drain()
            # Broadway without a browser may wait for frame acknowledgements.
            app.overlay_principale.allocate(app.overlay_principale.get_width(), app.overlay_principale.get_height(), -1, None)
            assert app.log_pannello.get_visible() and app.log_sfondo.get_visible()
            picked=app.overlay_principale.pick(2,2,m.Gtk.PickFlags.DEFAULT)
            assert picked is app.log_sfondo, 'Outside click must reach dismissal layer'
            valid,bounds=app.log_pannello.compute_bounds(app.overlay_principale)
            assert valid
            picked=app.overlay_principale.pick(bounds.get_x()+15,bounds.get_y()+15,m.Gtk.PickFlags.DEFAULT)
            assert picked is app.log_pannello or picked.is_ancestor(app.log_pannello), 'Inside click must stay in log'
            saved=list(app.log_eventi)
            gesture=Mock();app._clic_fuori_log(gesture,1,2,2)
            gesture.set_state.assert_called_once_with(m.Gtk.EventSequenceState.CLAIMED)
            assert not app.log_pannello.get_visible() and not app.log_sfondo.get_visible()
            assert app.log_tick is None and app.log_eventi==saved
            app._apri_log();drain();app._cancella_log()
            assert app.log_pannello.get_visible() and not app.log_eventi
            app._log_finestra_attiva(Mock(is_active=Mock(return_value=False)))
            assert not app.log_pannello.get_visible()
            app.finestra.destroy();app.quit()
            print('PASS:',language,'labels, device card, minimum width, preference persistence and session log')
    finally:
        server.terminate();server.wait(timeout=5)
