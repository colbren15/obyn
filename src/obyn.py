#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Daniele Frasca
# SPDX-FileCopyrightText: 2026 OBYN contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""OBYN — Only Bluetooth You Need, gestore grafico BlueZ/PipeWire."""

import json
import colorsys
import math
import os
import re
import subprocess
import sys
import threading
import time
import tempfile
import wave
from pathlib import Path

__version__ = '0.1.2'

import gettext

class LanguageManager:
    """Explicit language or system locale; unsupported locales fall back to English.

    Italian source messages need no catalog. Supply ordered catalog directories.
    Persistence and UI refresh belong to the host application. A failed catalog
    load falls back to source messages and is exposed via ``catalog_loaded``.
    """
    supported = ('it', 'en')

    def __init__(self, domain, locale_dirs, *, preference='auto', environ=None):
        self.domain = domain
        self.locale_dirs = tuple(Path(p) for p in locale_dirs)
        self.environ = os.environ if environ is None else environ
        self.configure(preference)

    @classmethod
    def resolve(cls, preference='auto', environ=None):
        if preference in cls.supported:
            return preference
        env = os.environ if environ is None else environ
        # Locale precedence; LANGUAGE is ignored for the untranslated C locale.
        locale = env.get('LC_ALL') or env.get('LC_MESSAGES') or env.get('LANG') or 'C'
        if locale.upper() in ('C', 'POSIX', 'C.UTF-8', 'C.UTF8'):
            return 'en'
        candidates = (env.get('LANGUAGE') or locale).split(':')
        for candidate in candidates:
            language = candidate.split('.')[0].split('@')[0].replace('-', '_').split('_')[0].lower()
            if language in cls.supported:
                return language
        return 'en'

    def configure(self, preference='auto'):
        self.preference = preference if preference in ('auto', *self.supported) else 'auto'
        self.language = self.resolve(self.preference, self.environ)
        self.translation = gettext.NullTranslations()
        self.catalog_loaded = self.language == 'it'
        if self.language != 'it':
            for directory in self.locale_dirs:
                try:
                    self.translation = gettext.translation(self.domain, directory, languages=[self.language])
                    self.catalog_loaded = True
                    break
                except (OSError, EOFError, ValueError, UnicodeError):
                    continue
        return self.language

    def gettext(self, message):
        return self.translation.gettext(message)

    def ngettext(self, singular, plural, number):
        return self.translation.ngettext(singular, plural, number)


# Source checkout first; installed copies use their XDG or system data directory.
_lingue = LanguageManager('obyn', [
    Path(__file__).resolve().parent.parent / 'locale',
    (Path('/usr/share/locale') if Path(__file__).resolve().parent == Path('/usr/bin')
     else Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'obyn/locale'),
    Path('/usr/share/locale'),
], preference='it')
tr = _lingue.gettext
ngettext = _lingue.ngettext


if __name__ == '__main__' and sys.argv[1:] == ['--version']:
    print('OBYN ' + __version__)
    sys.exit(0)

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import GLib, Gio, Gtk, Gdk, Pango, Graphene, Gsk


TONALITA_PETROLIO = colorsys.rgb_to_hls(16/255, 61/255, 59/255)[0] * 360
COLORI_TEMA = ('#103d3b', '#eefbf6', '#63dfbb', '#d9f1ed', '#283d3c',
               '#203331', '#568e83', '#2b4541', '#36574f', '#5794ba')


def tonalita_valida(valore):
    try:
        numero = float(valore)
        return max(0.0, min(360.0, numero)) if math.isfinite(numero) else TONALITA_PETROLIO
    except (TypeError, ValueError):
        return TONALITA_PETROLIO


def ruota_tonalita(colore, tonalita):
    rgb = tuple(int(colore[i:i+2], 16)/255 for i in (1, 3, 5))
    h, l, s = colorsys.rgb_to_hls(*rgb)
    rgb = colorsys.hls_to_rgb((h + (tonalita - TONALITA_PETROLIO)/360) % 1, l, s)
    return '#' + ''.join(f'{round(c*255):02x}' for c in rgb)


class ColoriKde:
    """Ricarica le definizioni colore generate da KDE; nessun polling."""
    def __init__(self, display, directory=None):
        self.display = display
        self.path = Path(directory or Path(GLib.get_user_config_dir()) / 'gtk-4.0') / 'colors.css'
        self.monitor = None
        self.timer = None
        self.provider = None
        self.ultimo_css = None
        self.chiuso = False
        # KDE crea questa directory quando configura GTK. Negli altri desktop
        # non creiamo file o preferenze e resta la normale gestione del tema.
        try:
            self.monitor = Gio.File.new_for_path(str(self.path.parent)).monitor_directory(
                Gio.FileMonitorFlags.NONE, None)
            self.monitor.connect('changed', self._cambiato)
        except GLib.Error:
            return
        self._ricarica()

    def _cambiato(self, monitor, file, other, event):
        if self.chiuso or not any(f and f.get_basename() == 'colors.css' for f in (file, other)):
            return
        if self.timer is not None:
            GLib.source_remove(self.timer)
        # Le scritture KDE possono sostituire il file con una rename atomica.
        self.timer = GLib.timeout_add(150, self._ricarica)

    def _ricarica(self):
        self.timer = None
        if self.chiuso:
            return False
        try:
            css = self.path.read_text()
        except (OSError, UnicodeError):
            return False
        if css == self.ultimo_css:
            return False
        nuovo = Gtk.CssProvider()
        errori = []
        nuovo.connect('parsing-error', lambda *args: errori.append(args[-1]))
        nuovo.load_from_data(css.encode())
        if errori:
            return False  # Mantiene l'ultimo stile valido durante scritture parziali.
        Gtk.StyleContext.add_provider_for_display(
            self.display, nuovo, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
        if self.provider is not None:
            Gtk.StyleContext.remove_provider_for_display(self.display, self.provider)
        self.provider = nuovo
        self.ultimo_css = css
        return False

    def close(self):
        self.chiuso = True
        if self.monitor is not None:
            self.monitor.cancel()
        if self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None
        if self.provider is not None:
            Gtk.StyleContext.remove_provider_for_display(self.display, self.provider)
            self.provider = None


class TemaSistema:
    """Segue il portale desktop senza polling né modifiche alla configurazione."""
    def __init__(self, settings):
        self.settings = settings
        self.cancel = Gio.Cancellable()
        self.proxy = None
        self.handler = None
        self.revisione = 0
        self.chiuso = False
        Gio.DBusProxy.new_for_bus(
            Gio.BusType.SESSION, Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES,
            None, 'org.freedesktop.portal.Desktop', '/org/freedesktop/portal/desktop',
            'org.freedesktop.portal.Settings', self.cancel, self._pronto)

    def _pronto(self, source, result):
        try:
            proxy = Gio.DBusProxy.new_for_bus_finish(result)
        except GLib.Error:
            return  # Senza portale resta il tema GTK dell'utente.
        if self.chiuso:
            return
        self.proxy = proxy
        self.handler = proxy.connect('g-signal', self._segnale)
        revisione = self.revisione
        proxy.call('ReadAll', GLib.Variant('(as)', (['org.freedesktop.appearance'],)),
                   Gio.DBusCallFlags.NONE, 3000, self.cancel, self._letto, revisione)

    def _letto(self, proxy, result, revisione):
        try:
            dati = proxy.call_finish(result).unpack()[0]
        except GLib.Error:
            return
        if not self.chiuso and revisione == self.revisione:
            self._applica(dati.get('org.freedesktop.appearance', {}).get('color-scheme', 0))

    def _segnale(self, proxy, sender, name, parameters):
        if self.chiuso or name != 'SettingChanged':
            return
        namespace, key, value = parameters.unpack()
        if namespace == 'org.freedesktop.appearance' and key == 'color-scheme':
            self.revisione += 1
            self._applica(value)

    def _applica(self, value):
        # Il portale usa 1=scuro, 2=chiaro; 0 e valori futuri non impongono nulla.
        prop = 'gtk-application-prefer-dark-theme'
        if value in (1, 2):
            # Questo seleziona anche la variante del tema GTK di base, non soltanto
            # le media query del provider CSS personalizzato.
            self.settings.set_property(prop, value == 1)
        else:
            self.settings.reset_property(prop)

    def close(self):
        self.chiuso = True
        self.cancel.cancel()
        if self.proxy is not None and self.handler is not None:
            self.proxy.disconnect(self.handler)
            self.handler = None


class BordoAttesa:
    """Indicatore disegnato sopra il bottone: nessuna modifica al layout."""
    def attesa(self, attiva):
        tick = getattr(self, '_attesa_tick', None)
        if attiva and tick is None:
            self._attesa_fase = 0.0
            self._attesa_tick = self.add_tick_callback(self._anima_attesa)
        elif not attiva and tick is not None:
            self.remove_tick_callback(tick)
            self._attesa_tick = None
        self.queue_draw()

    def _anima_attesa(self, widget, clock):
        self._attesa_fase = (clock.get_frame_time() / 2400000) % 1
        self.queue_draw()
        return True

    def _disegna_attesa(self, snapshot):
        if getattr(self, '_attesa_tick', None) is None:
            return
        w, h = self.get_width() - 6, self.get_height() - 6
        if min(w, h) <= 0:
            return
        r = min(9, w / 2, h / 2)
        # Percorso in senso orario, a velocità uniforme anche sui lati corti.
        linee = [w-2*r, h-2*r, w-2*r, h-2*r]
        arco = math.pi*r/2
        perimetro = sum(linee) + 4*arco
        for i in range(4):
            d = ((self._attesa_fase - i*0.035) % 1)*perimetro
            for lato, lunghezza in enumerate(linee):
                if d <= lunghezza:
                    x, y = [(r+d, 0), (w, r+d), (w-r-d, h), (0, h-r-d)][lato]
                    break
                d -= lunghezza
                if d <= arco:
                    cx, cy = [(w-r, r), (w-r, h-r), (r, h-r), (r, r)][lato]
                    angolo = -math.pi/2 + lato*math.pi/2 + d/r
                    x, y = cx+r*math.cos(angolo), cy+r*math.sin(angolo)
                    break
                d -= arco
            rect = Graphene.Rect().init(x+1, y+1, 4, 4)
            clip = Gsk.RoundedRect()
            clip.init_from_rect(rect, 2)
            colore = Gdk.RGBA()
            trovato, accento = self.get_style_context().lookup_color('obyn_accent')
            colore.parse(accento.to_string() if trovato else '#63dfbb')
            colore.alpha = 1-i*0.18
            snapshot.push_rounded_clip(clip)
            snapshot.append_color(colore, rect)
            snapshot.pop()


class PulsanteAttesa(BordoAttesa, Gtk.Button):
    def do_snapshot(self, snapshot):
        Gtk.Button.do_snapshot(self, snapshot)
        self._disegna_attesa(snapshot)


class InterruttoreAttesa(BordoAttesa, Gtk.ToggleButton):
    def do_snapshot(self, snapshot):
        Gtk.ToggleButton.do_snapshot(self, snapshot)
        self._disegna_attesa(snapshot)


def comando_bt(*argomenti, limite=20):
    try:
        risultato = subprocess.run(
            ['bluetoothctl', *argomenti], text=True, capture_output=True,
            timeout=limite, check=False, env={**os.environ, 'LC_ALL': 'C', 'TERM': 'dumb'},
        )
        testo = '\n'.join(parte for parte in (risultato.stdout, risultato.stderr) if parte).strip()
        testo = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', testo)
        if risultato.returncode:
            return tr('Errore Bluetooth: {v0}').format(v0=testo or tr('comando non riuscito'))
        return testo
    except (OSError, subprocess.SubprocessError) as exc:
        return tr('Errore Bluetooth: {v0}').format(v0=exc)


def prepara_bluetooth():
    """Rimuove un eventuale blocco software e accende il controller BlueZ.

    rfkill unblock non richiede privilegi aggiuntivi per il blocco software
    dell'utente e non può rimuovere un blocco hardware: in quel caso l'errore
    di BlueZ rimane visibile invece di essere mascherato.
    """
    try:
        subprocess.run(
            ['rfkill', 'unblock', 'bluetooth'], text=True, capture_output=True,
            timeout=8, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        # Su sistemi senza rfkill lasciamo comunque tentare a BlueZ l'accensione.
        pass
    return comando_bt('power', 'on')


class RicercaBluez:
    """Sessione privata D-Bus; tutti i suoi eventi vivono nel worker.

    La cache iniziale non prova la presenza radio. Soltanto oggetti nuovi o
    aggiornamenti radio ricevuti durante la sessione contano come rilevamenti.
    """
    ADAPTER = 'org.bluez.Adapter1'
    DEVICE = 'org.bluez.Device1'
    PROPERTIES = 'org.freedesktop.DBus.Properties'
    OBJECTS = 'org.freedesktop.DBus.ObjectManager'
    RADIO = {'RSSI', 'TxPower', 'ManufacturerData', 'ServiceData'}

    def __init__(self, controller):
        self.controller = controller.upper()
        self.connessione = None
        self.oggetti = {}
        self.adattatore = None
        self.visti = set()
        self.modificato = False
        self.errore_evento = ''

    def _chiama(self, percorso, interfaccia, metodo, parametri=None):
        return self.connessione.call_sync(
            'org.bluez', percorso, interfaccia, metodo, parametri, None,
            Gio.DBusCallFlags.NONE, 8000, None,
        ).unpack()

    def _segnale(self, connessione, mittente, percorso, interfaccia,
                 segnale, parametri, *extra):
        dati = parametri.unpack()
        if segnale == 'InterfacesAdded':
            percorso, interfacce = dati
            nuovo = self.DEVICE not in self.oggetti.get(percorso, {})
            self.oggetti.setdefault(percorso, {}).update(interfacce)
            if nuovo and self.DEVICE in interfacce:
                self._segna_visto(percorso)
        elif segnale == 'InterfacesRemoved':
            percorso, interfacce = dati
            for nome in interfacce:
                self.oggetti.get(percorso, {}).pop(nome, None)
            if percorso == self.adattatore and self.ADAPTER in interfacce:
                self.errore_evento = tr('Il controller Bluetooth è stato rimosso.')
        elif segnale == 'PropertiesChanged':
            nome, modifiche, invalidate = dati
            proprieta = self.oggetti.setdefault(percorso, {}).setdefault(nome, {})
            proprieta.update(modifiche)
            for chiave in invalidate:
                proprieta.pop(chiave, None)
            if nome == self.DEVICE and self.RADIO.intersection(modifiche):
                self._segna_visto(percorso)
            if percorso == self.adattatore and nome == self.ADAPTER:
                if modifiche.get('Powered') is False or modifiche.get('Discovering') is False:
                    self.errore_evento = tr('La ricerca Bluetooth si è interrotta sul controller.')
        self.modificato = True

    def _segna_visto(self, percorso):
        proprieta = self.oggetti.get(percorso, {}).get(self.DEVICE, {})
        if proprieta.get('Adapter') == self.adattatore and proprieta.get('Address'):
            self.visti.add(proprieta['Address'].upper())

    def dispositivi(self):
        risultato = {}
        for interfacce in self.oggetti.values():
            p = interfacce.get(self.DEVICE, {})
            if p.get('Adapter') != self.adattatore or not p.get('Address'):
                continue
            mac = p['Address'].upper()
            risultato[mac] = (mac, p.get('Alias') or p.get('Name') or mac, {
                'connected': bool(p.get('Connected', False)),
                'paired': bool(p.get('Paired', False)),
                'trusted': bool(p.get('Trusted', False)),
                **{k: p[v] for k, v in [('address_type', 'AddressType'), ('uuids', 'UUIDs'), ('icon', 'Icon')] if v in p},
            })
        return sorted(risultato.values(), key=lambda d: (d[0] not in self.visti, d[1].casefold()))

    def esegui(self, ferma, aggiorna, durata=30, obiettivo=None):
        contesto = GLib.MainContext.new()
        contesto.push_thread_default()
        iscrizioni = []
        avviata = False
        try:
            indirizzo = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SYSTEM, None)
            self.connessione = Gio.DBusConnection.new_for_address_sync(
                indirizzo, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT |
                Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None,
            )
            self.connessione.set_exit_on_close(False)
            self.oggetti = self._chiama('/', self.OBJECTS, 'GetManagedObjects')[0]
            self.adattatore = next((
                path for path, interfaces in self.oggetti.items()
                if interfaces.get(self.ADAPTER, {}).get('Address', '').upper() == self.controller
            ), None)
            if self.adattatore is None:
                raise RuntimeError(tr('Il controller Bluetooth selezionato non è disponibile.'))
            if ferma.is_set():
                return
            for interfaccia, segnale in [
                (self.OBJECTS, 'InterfacesAdded'), (self.OBJECTS, 'InterfacesRemoved'),
                (self.PROPERTIES, 'PropertiesChanged'),
            ]:
                iscrizioni.append(self.connessione.signal_subscribe(
                    'org.bluez', interfaccia, segnale, None, None,
                    Gio.DBusSignalFlags.NONE, self._segnale,
                ))
            self._chiama(self.adattatore, self.ADAPTER, 'SetDiscoveryFilter',
                         GLib.Variant('(a{sv})', ({'Transport': GLib.Variant('s', 'auto'),
                                                  'DuplicateData': GLib.Variant('b', True)},)))
            self._chiama(self.adattatore, self.ADAPTER, 'StartDiscovery')
            avviata = True
            attiva = self._chiama(self.adattatore, self.PROPERTIES, 'Get',
                                  GLib.Variant('(ss)', (self.ADAPTER, 'Discovering')))[0]
            if not attiva:
                raise RuntimeError(tr('BlueZ non ha confermato l’avvio della ricerca.'))
            aggiorna(self.dispositivi(), set(self.visti))
            inizio = ultimo_invio = ultima_verifica = time.monotonic()
            while not ferma.is_set() and time.monotonic() - inizio < durata:
                # Il limite impedisce che molti annunci BLE ritardino “Ferma”.
                for _ in range(100):
                    if not contesto.pending():
                        break
                    contesto.iteration(False)
                if self.errore_evento:
                    raise RuntimeError(self.errore_evento)
                if obiettivo and obiettivo.upper() in self.visti:
                    break
                ora = time.monotonic()
                if self.modificato and ora - ultimo_invio >= 0.3:
                    aggiorna(self.dispositivi(), set(self.visti))
                    self.modificato = False
                    ultimo_invio = ora
                if ora - ultima_verifica >= 2:
                    # Rileva anche riavvio BlueZ, perdita del bus o stop esterno.
                    attiva = self._chiama(self.adattatore, self.PROPERTIES, 'Get',
                                          GLib.Variant('(ss)', (self.ADAPTER, 'Discovering')))[0]
                    if not attiva:
                        raise RuntimeError(tr('La ricerca Bluetooth non è più attiva.'))
                    ultima_verifica = ora
                ferma.wait(0.05)
            aggiorna(self.dispositivi(), set(self.visti))
        finally:
            try:
                if self.connessione:
                    try:
                        if avviata:
                            self._chiama(self.adattatore, self.ADAPTER, 'StopDiscovery')
                    finally:
                        for iscrizione in iscrizioni:
                            self.connessione.signal_unsubscribe(iscrizione)
                        # Chiudere la connessione privata libera solo la nostra
                        # sessione, anche se Start/StopDiscovery hanno un timeout.
                        self.connessione.close_sync(None)
            finally:
                contesto.pop_thread_default()


class AudioPipewire:
    """Snapshot verificati BlueZ e pactl JSON, senza accessi GTK."""
    @staticmethod
    def comando(argomenti, limite=None):
        timeout = 5 if limite is None else min(5, limite - time.monotonic())
        if timeout < 0.1:
            raise TimeoutError(tr('Tempo scaduto in attesa dello stato audio.'))
        try:
            risultato = subprocess.run(argomenti, text=True, capture_output=True,
                                       timeout=timeout, check=False,
                                       env={**os.environ, 'LC_ALL': 'C.UTF-8', 'TERM': 'dumb'})
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(tr('Il sistema audio/Bluetooth non ha risposto entro il tempo disponibile.')) from exc
        if risultato.returncode:
            raise RuntimeError((risultato.stderr or risultato.stdout).strip() or tr('Comando audio fallito.'))
        return risultato.stdout

    @classmethod
    def leggi(cls, mac, limite=None):
        info_bt = cls.comando(['bluetoothctl', 'info', mac], limite)
        match = re.search(r'^\s*Connected:\s*(yes|no)\s*$', info_bt, re.M)
        if not match:
            raise RuntimeError(tr('Stato Bluetooth non verificabile: ') + info_bt.strip())
        stato = {'connected': match.group(1) == 'yes', 'card': None, 'active': None,
                 'profiles': {}, 'sink': None, 'source': None, 'volume': None,
                 'default_sink': None, 'default_source': None}
        if not stato['connected']:
            return stato
        def dati(*args):
            return json.loads(cls.comando(['pactl', '--format=json', *args], limite))
        carte = dati('list', 'cards')
        carta = next((c for c in carte if c.get('name', '').lower() ==
                      f'bluez_card.{mac.replace(":", "_")}'.lower()), None)
        if carta is None:
            return stato
        stato['card'] = carta['name']
        stato['active'] = carta.get('active_profile')
        stato['profiles'] = {nome: p for nome, p in carta.get('profiles', {}).items()
                             if p.get('available') is True}
        def nodo(tipo, prefisso):
            candidati = [n for n in dati('list', tipo)
                         if cls.appartiene(n, carta, mac) and
                         n.get('name', '').startswith(prefisso) and
                         not n['name'].endswith('.monitor') and
                         n.get('properties', {}).get('device.class') != 'monitor']
            return next(iter(sorted(candidati, key=lambda n:
                str(n.get('properties', {}).get('bluez5.loopback', 'false')).lower() == 'true')), None)
        sink = nodo('sinks', 'bluez_output.')
        # WirePlumber può esporre un ingresso loopback anche in A2DP:
        # la sua presenza da sola non conferma un microfono HFP attivo.
        source = nodo('sources', 'bluez_input.') if cls.tipo_profilo(stato['active']) == 'hfp' else None
        stato['sink'] = sink['name'] if sink else None
        stato['source'] = source['name'] if source else None
        if sink:
            valori = [v['value'] / 65536 * 100 for v in sink.get('volume', {}).values()
                      if isinstance(v, dict) and isinstance(v.get('value'), (int, float))]
            if valori:
                stato['volume'] = round(sum(valori) / len(valori))
        server = dati('info')
        stato['default_sink'] = server.get('default_sink_name')
        stato['default_source'] = server.get('default_source_name')
        return stato

    @classmethod
    def instradamento(cls):
        server = json.loads(cls.comando(['pactl', '--format=json', 'info']))
        return {tipo: {'default': server.get('default_' + tipo + '_name'),
                       'nodes': json.loads(cls.comando(['pactl', '--format=json', 'list', tipo + 's']))}
                for tipo in ('sink', 'source')}

    @staticmethod
    def mac_nodo(nodo):
        proprieta = nodo.get('properties', {})
        valore = proprieta.get('api.bluez5.address', '') or nodo.get('name', '')
        match = re.search(r'([0-9a-f]{2}(?:[_:][0-9a-f]{2}){5})', valore, re.I)
        return match.group(1).replace('_', ':').upper() if match else None

    @classmethod
    def sposta_predefinito(cls, tipo, destinazione, precedente):
        cls.comando(['pactl', 'set-default-' + tipo, destinazione])
        # Sposta anche i flussi già aperti sull'endpoint precedente.
        flusso = 'sink-input' if tipo == 'sink' else 'source-output'
        nodi = json.loads(cls.comando(['pactl', '--format=json', 'list', tipo + 's']))
        vecchio = next((n for n in nodi if n['name'] == precedente), None)
        if vecchio is not None:
            for stream in json.loads(cls.comando(['pactl', '--format=json', 'list', flusso + 's'])):
                if str(stream.get(tipo)) == str(vecchio['index']):
                    cls.comando(['pactl', 'move-' + flusso, str(stream['index']), destinazione])
        server = json.loads(cls.comando(['pactl', '--format=json', 'info']))
        if server.get('default_' + tipo + '_name') != destinazione:
            raise RuntimeError(tr('Il sistema non ha confermato il dispositivo audio predefinito.'))

    @classmethod
    def imposta_muto(cls, tipo, nome, muto):
        cls.comando(['pactl', 'set-' + tipo + '-mute', nome, '1' if muto else '0'])
        nodi = json.loads(cls.comando(['pactl', '--format=json', 'list', tipo + 's']))
        nodo = next((n for n in nodi if n['name'] == nome), None)
        if nodo is None or nodo.get('mute') is not muto:
            raise RuntimeError(tr('Stato silenziato del dispositivo non confermato dal sistema.'))

    @staticmethod
    def appartiene(nodo, carta, mac):
        p = nodo.get('properties', {})
        indirizzo = p.get('api.bluez5.address')
        if indirizzo and indirizzo.upper() != mac.upper():
            return False
        if nodo.get('card') is not None:
            return str(nodo['card']) == str(carta['index'])
        if indirizzo:
            return True
        if p.get('device.name'):
            return p['device.name'] == carta['name']
        object_id = carta.get('properties', {}).get('object.id')
        return object_id is not None and str(p.get('device.id')) == str(object_id)

    @staticmethod
    def tipo_profilo(nome):
        nome = nome or ''
        if nome.startswith('a2dp'):
            return 'a2dp'
        if any(p in nome for p in ('headset', 'handsfree', 'hfp')):
            return 'hfp'
        return None

    @staticmethod
    def profili(stato, tipo):
        def compatibile(nome):
            return nome.startswith('a2dp') if tipo == 'a2dp' else any(
                p in nome for p in ('headset', 'handsfree', 'hfp'))
        return sorted((nome for nome in stato.get('profiles', {}) if compatibile(nome)),
                      key=lambda nome: (-stato['profiles'][nome].get('priority', 0), nome))

    @classmethod
    def cambia_profilo(cls, mac, tipo, profilo_esatto=None):
        limite = time.monotonic() + 15
        stato = cls.leggi(mac, limite)
        candidati = cls.profili(stato, tipo)
        if not stato['connected'] or not stato['card'] or not candidati:
            raise RuntimeError(tr('Profilo non disponibile per il dispositivo connesso.'))
        if profilo_esatto is not None and profilo_esatto not in candidati:
            raise RuntimeError(tr('Il profilo precedente non è più disponibile.'))
        profilo = profilo_esatto or (stato['active'] if stato['active'] in candidati else candidati[0])
        if stato['active'] != profilo:
            cls.comando(['pactl', 'set-card-profile', stato['card'], profilo], limite)
        while True:
            if limite - time.monotonic() < 0.1:
                raise TimeoutError(tr('Cambio profilo non confermato: profilo attivo ') + str(stato.get('active')) + tr('. Uscita o microfono richiesti non pronti.'))
            stato = cls.leggi(mac, limite)
            if not stato['connected']:
                raise RuntimeError(tr('Il dispositivo si è disconnesso durante il cambio profilo.'))
            if stato['active'] == profilo and stato['sink'] and (tipo == 'a2dp' or stato['source']):
                return stato
            if time.monotonic() >= limite:
                raise TimeoutError(tr('Il profilo o i nodi audio non sono diventati disponibili entro 15 secondi.'))
            time.sleep(min(0.25, max(0, limite - time.monotonic())))


class MessaggioAudio:
    """Un solo messaggio temporaneo, legato alla finestra e cancellabile."""
    def __init__(self):
        self.cartella = tempfile.TemporaryDirectory(prefix='obyn-messaggio-')
        self.percorso = str(Path(self.cartella.name) / 'messaggio.wav')
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.chiuso = False
        self.pronto = False
        self.errore = ''
        self.durata = 0
        self.incompleta = False
        self.processo = None

    def chiudi(self):
        with self.lock:
            self.chiuso = True
            self.pronto = False
            self.stop.set()
            if self.processo is not None and self.processo.poll() is None:
                self.processo.kill()
            # Il worker non può avviare un processo dopo questa cancellazione.
            self.cartella.cleanup()

    def _avvia(self, args, errori):
        with self.lock:
            if self.chiuso:
                raise RuntimeError(tr('Messaggio cancellato alla chiusura della finestra.'))
            self.processo = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=errori)
            return self.processo

    def registra(self, source, iniziata):
        with tempfile.TemporaryFile(mode='w+t') as errori:
            processo = self._avvia(['pw-record', '--target', source, '--rate', '16000',
                '--channels', '1', '--format', 's16', '--container', 'wav', '--sample-count', '160000', self.percorso], errori)
            iniziata()
            limite = time.monotonic() + 10
            interrotta = False
            scaduta = False
            try:
                while processo.poll() is None:
                    if self.stop.wait(0.05):
                        interrotta = True
                        if processo.poll() is None:
                            processo.terminate()
                        break
                    if time.monotonic() >= limite:
                        scaduta = True
                        interrotta = True
                        if processo.poll() is None:
                            processo.terminate()
                        break
                codice = processo.wait(timeout=3)
                errori.seek(0)
                # pw-record 1.6.8 stampa il nome file anche senza errori e
                # restituisce 1 dopo cattura completa/SIGTERM (nessun drain).
                dettaglio = '\n'.join(r for r in errori.read().splitlines()
                                      if r.strip() != self.percorso).strip()
                compatibile = codice == 1 and not dettaglio
                if codice != 0 and not (interrotta and codice == -15) and not compatibile:
                    raise RuntimeError(tr('Registrazione non riuscita (codice {v0}): ').format(v0=codice)
                                       + (dettaglio or tr('registratore terminato in modo inatteso.')))
                with self.lock:
                    if self.chiuso:
                        raise RuntimeError(tr('Registrazione cancellata.'))
                    self._convalida_messaggio()
                    if compatibile and not interrotta and self.durata < 10:
                        raise RuntimeError(tr('Registrazione interrotta prima del limite (pw-record: codice 1). Ripeti la prova.'))
                    self.incompleta = scaduta and self.durata < 8
                    self.pronto = True
            except Exception as exc:
                self.errore = str(exc) or type(exc).__name__
                self.chiudi()
                raise
            finally:
                if processo.poll() is None:
                    processo.kill()
                processo.wait(timeout=3)

    def _convalida_messaggio(self):
        # Verificare i campioni realmente presenti, non soltanto l'intestazione.
        # Un ultimo blocco del recorder può oltrepassare il limite richiesto.
        with wave.open(self.percorso, 'rb') as audio:
            canali, larghezza, frequenza = audio.getnchannels(), audio.getsampwidth(), audio.getframerate()
            if (canali, larghezza, frequenza) != (1, 2, 16000):
                raise RuntimeError(tr('Formato della registrazione inatteso.'))
            campioni = audio.readframes(frequenza * 10)
        passo = canali * larghezza
        campioni = campioni[:len(campioni) // passo * passo]
        if not campioni:
            raise RuntimeError(tr('La registrazione non contiene audio. Ripeti “Prova microfono” in HFP.'))
        with wave.open(self.percorso, 'wb') as audio:
            audio.setnchannels(canali)
            audio.setsampwidth(larghezza)
            audio.setframerate(frequenza)
            audio.writeframes(campioni)
        self.durata = len(campioni) / passo / frequenza

    def riproduci(self, sink):
        with tempfile.TemporaryFile(mode='w+t') as errori:
            processo = self._avvia(['paplay', f'--device={sink}', self.percorso], errori)
            try:
                if processo.wait(timeout=15) != 0:
                    errori.seek(0)
                    raise RuntimeError(tr('Riproduzione non riuscita: ') + errori.read().strip())
            finally:
                if processo.poll() is None:
                    processo.kill()
                processo.wait(timeout=3)


class ObynApplication(Gtk.Application):
    _icone_svg = {}
    _tema_colori = {}

    def __init__(self):
        super().__init__(application_id='io.obyn.Bluetooth')
        self.lista = None
        self.schede = {}
        self.interruttori_avvio = {}
        self.sincronizza_avvio = False
        self.pulsanti_instradamento = {}
        self.precedenti_audio = {}
        self.snapshot_instradamento = {}
        self.lettura_instradamento = False
        self.ultimo_poll_audio = 0.0
        self.scroller_dispositivi = None
        self.frecce_dispositivi = []
        self.dispositivi_visualizzati = []
        self.monitor_bt = None
        self.lettura_bt_in_corso = False
        self.timer_bt = None
        self.stato = None
        self.log_eventi = []
        self.log_visualizzati = 0
        self.log_stati = {}
        self.log_basi = set()
        self.log_buffer = None
        self.log_pannello = None
        self.log_sfondo = None
        self.log_scroll = None
        self.log_segui = True
        self.log_tick = None
        self.log_operazione = None
        self.diagnostica = {}
        self.finestra = None
        self.tema_timer = None
        self.tema_salvataggio = None
        self.tema_provider = None
        self.tema_sistema = None
        self.colori_kde = None
        self.scansione = False
        self.connessione_in_corso = False
        self.ferma_scansione_evento = threading.Event()
        self.pulsante_ferma = None
        self.visti_scansione = set()
        self.ricerca_eseguita = False
        # Stato del coordinatore: modificato soltanto dal thread GTK.
        self.operazione = None
        self.pulsante_origine = None
        self.pulsante_in_attesa = None
        self.aggiornamento_pendente = False
        self.generazione_elenco = 0
        self.auto_avvio_consumato = False
        self.errore_azione_pendente = ''
        self.controlli_operazioni = []
        self.dispositivo_audio = None
        self.nome_dispositivo_audio = ''
        self.audio_info = None
        self.audio_dettagli = None
        self.prova_sessione = None
        self.dialogo_salvataggio = None
        self.ferma_registrazione_button = None
        self.pulsanti_audio = {}
        self.stato_audio = {}
        self.audio_generazione = 0
        self.audio_lettura_in_corso = False
        self.messaggio_audio = ''
        self.volume_slider = None
        self.volume_label = None
        self.volume_timeout = None
        self.volume_in_aggiornamento = False
        self.volume_trascinamento = False
        self.volume_pendente = None
        self.volume_ultima_modifica = 0
        self.tray_process = None
        self.tray_quit_file = None
        self.tray_watch_id = None
        self.config_path = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'obyn' / 'config.json'
        self.config = self.carica_config()

    def carica_config(self):
        try:
            return json.loads(self.config_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            return {}

    def salva_config(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(self.config, indent=2), encoding='utf-8')

    @staticmethod
    def _icona(nome):
        chiave = (nome, ObynApplication._tema_colori.get('#103d3b', '#103d3b') if nome.endswith('-active') else '')
        if chiave in ObynApplication._icone_svg:
            icona = Gtk.Image.new_from_gicon(ObynApplication._icone_svg[chiave])
            icona.set_pixel_size(24)
            return icona
        attiva = nome.endswith('-active')
        nome = nome.removesuffix('-active')
        # SVG incorporati: stesso tratto e proporzioni, indipendenti dal tema icone.
        forme = {
            'palette': '<path d="M12 3a9 9 0 1 0 0 18h1a2 2 0 0 0 1-3.7 1.5 1.5 0 0 1 1-2.8h2a4 4 0 0 0 4-4A9 9 0 0 0 12 3Z"/><circle cx="7" cy="10" r=".8"/><circle cx="10" cy="6.5" r=".8"/><circle cx="15" cy="7" r=".8"/>',
            'info': '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.2"/>',
            'mic': '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8"/>',
            'left': '<path d="m15 5-7 7 7 7"/>',
            'right': '<path d="m9 5 7 7-7 7"/>',
            'connect': '<path d="M8 4v5m8-5v5M6 9h12v3a6 6 0 0 1-12 0ZM12 18v4"/>',
            'disconnect': '<path d="m4 4 16 16M8 4v3m8-3v5M9 9h9v3c0 1-.2 2-.7 2.8M6 10v2a6 6 0 0 0 8 5.7M12 18v4"/>',
            'pair': '<path d="m9 14 6-6M7 16l-1 1a4 4 0 0 1-5-5l4-4a4 4 0 0 1 5 0m4 2a4 4 0 0 0 5 0l3-3a4 4 0 0 0-5-5l-2 2" transform="translate(1 2) scale(.9)"/>',
            'forget': '<path d="M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7"/>',
            'headset': '<path d="M4 14v-3a8 8 0 0 1 16 0v3M4 12H2v7h4v-7Zm16 0h2v7h-4v-7Z"/>',
            'output': '<path d="M3 9h4l6-5v16l-6-5H3Z"/><path d="M17 8a6 6 0 0 1 0 8M20 5a10 10 0 0 1 0 14"/>',
            'speaker': '<rect x="5" y="2" width="14" height="20" rx="2"/><circle cx="12" cy="15" r="4"/><circle cx="12" cy="6" r="1"/>',
            'phone': '<rect x="6" y="2" width="12" height="20" rx="2"/><path d="M10 18h4"/>',
            'computer': '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M12 17v4m-5 0h10"/>',
            'keyboard': '<rect x="2" y="6" width="20" height="13" rx="2"/><path d="M6 10h1m3 0h1m3 0h1m3 0h1M6 14h1m3 0h1m3 0h4"/>',
            'mouse': '<rect x="6" y="2" width="12" height="20" rx="6"/><path d="M12 3v6"/>',
            'device': '<rect x="5" y="3" width="14" height="18" rx="3"/><circle cx="12" cy="16" r="1"/>',
            'check': '<circle cx="12" cy="12" r="9" fill="#23865b" stroke="#fff" stroke-width="1.5"/><path d="m7 12 3 3 7-7" stroke="#fff" stroke-width="2"/>',
            'radar': '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><path d="M12 12 19 5"/><circle cx="8" cy="15" r="1" fill="currentColor" stroke="none"/>',
            'stop': '<path d="M7 12V6a1.5 1.5 0 0 1 3 0v5-7a1.5 1.5 0 0 1 3 0v7-6a1.5 1.5 0 0 1 3 0v6-4a1.5 1.5 0 0 1 3 0v7c0 5-2 7-6 7-3 0-4-1-6-4l-3-4c-1-2 1-3 2-2l2 2"/>',
            'refresh': '<path d="M20 10a8 8 0 1 0-2 8M20 4v6h-6"/>',
            'settings': '<path d="m10 3-.5 2-2 .9-1.9-.6-2 3.4 1.5 1.4v2.8L3.6 14l2 3.4 1.9-.6 2 .9.5 2.3h4l.5-2.3 2-.9 1.9.6 2-3.4-1.5-1.1v-2.8l1.5-1.4-2-3.4-1.9.6-2-.9L14 3Z"/><circle cx="12" cy="11.5" r="3"/>',
            'rec': '<circle cx="12" cy="12" r="6" fill="#ef5350" stroke="none"/>',
            'play': '<path d="m9 5 10 7-10 7Z"/>',
            'save': '<path d="M12 3v12m-4-4 4 4 4-4M4 15v5h16v-5"/>',
        }
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
               'viewBox="0 0 24 24" fill="none" stroke="#8996a5" color="#8996a5" '
               'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
               + forme[nome] + '</svg>')
        if attiva:
            svg = svg.replace('#8996a5', ObynApplication._tema_colori.get('#103d3b', '#103d3b'))
        dati = Gio.BytesIcon.new(GLib.Bytes.new(svg.encode()))
        ObynApplication._icone_svg[chiave] = dati
        icona = Gtk.Image.new_from_gicon(dati)
        icona.set_pixel_size(24)
        return icona

    def _memorizza_pulsante(self, pulsante):
        self.pulsante_origine = pulsante
        def dimentica():
            if getattr(self, 'pulsante_origine', None) is pulsante:
                self.pulsante_origine = None
            return False
        GLib.idle_add(dimentica)

    def _bottone_icona(self, nome, testo, solo_icona=False, interruttore=False):
        pulsante = InterruttoreAttesa() if interruttore else PulsanteAttesa()
        pulsante.connect('clicked', self._memorizza_pulsante)
        pulsante.set_tooltip_text(testo)
        pulsante.update_property([Gtk.AccessibleProperty.LABEL], [testo])
        if solo_icona:
            pulsante.set_child(self._icona(nome))
            pulsante.add_css_class('obyn-tool')
        else:
            contenuto = Gtk.Box(spacing=7)
            contenuto.set_halign(Gtk.Align.CENTER)
            contenuto.append(self._icona(nome))
            contenuto.append(Gtk.Label(label=testo))
            pulsante.set_child(contenuto)
        return pulsante

    def _crea_tema(self, barra):
        self.menu_tema = Gtk.MenuButton()
        self.menu_tema.add_css_class('obyn-settings')
        self.menu_tema.set_child(self._icona('palette'))
        self.menu_tema.set_tooltip_text(tr('Tonalità del tema'))
        self.menu_tema.update_property([Gtk.AccessibleProperty.LABEL], [tr('Tonalità del tema')])
        popover = Gtk.Popover()
        popover.add_css_class('obyn-info')
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for lato in ('top', 'bottom', 'start', 'end'):
            getattr(box, 'set_margin_' + lato)(12)
        titolo = Gtk.Label(label=tr('Tonalità del tema'), xalign=0)
        titolo.add_css_class('heading')
        box.append(titolo)
        self.tema_slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 360, 1)
        self.tema_slider.set_size_request(230, -1)
        self.tema_slider.set_draw_value(False)
        self.tema_slider.set_has_origin(False)
        self.tema_slider.add_css_class('hue-spectrum')
        self.tema_slider.update_property([Gtk.AccessibleProperty.LABEL], [tr('Tonalità del tema')])
        self.tema_slider.set_value(self.tema_tonalita)
        self.tema_slider.connect('value-changed', self._cambia_tema)
        box.append(self.tema_slider)
        reset = Gtk.Button(label=tr('Ripristina petrolio'))
        reset.connect('clicked', lambda *_: self.tema_slider.set_value(TONALITA_PETROLIO))
        box.append(reset)
        popover.set_child(box)
        self.menu_tema.set_popover(popover)
        barra.append(self.menu_tema)

    def _cambia_tema(self, slider):
        self.tema_tonalita = tonalita_valida(slider.get_value())
        if self.tema_timer is None:
            self.tema_timer = GLib.timeout_add(33, self._applica_tema)
        if self.tema_salvataggio is not None:
            GLib.source_remove(self.tema_salvataggio)
        self.tema_salvataggio = GLib.timeout_add(400, self._salva_tema)

    def _applica_tema(self):
        self.tema_timer = None
        mappa = {c: ruota_tonalita(c, self.tema_tonalita) for c in COLORI_TEMA}
        ObynApplication._tema_colori = mappa
        css = re.sub(r'#[0-9a-fA-F]{6}', lambda m: mappa.get(m[0], m[0]), self.css_base.decode())
        css += '\n@define-color obyn_accent ' + mappa['#63dfbb'] + ';\n'
        css += '.obyn scale.volume-wide:not(:disabled) highlight { background: @obyn_accent; border-color: @obyn_accent; }'
        css += '.obyn scale.volume-wide:not(:disabled) slider { border-color: @obyn_accent; }'
        # Lo spettro non ruota con la palette: è il riferimento del selettore.
        css += 'popover.obyn-info scale.hue-spectrum trough { min-height: 10px; background: linear-gradient(to right, #df6363, #dfdf63, #63df63, #63dfdf, #6363df, #df63df, #df6363); }'
        self.tema_provider.load_from_data(css.encode())
        # KDE's user stylesheet has higher priority than application CSS.
        # Override only our popover links, not the desktop or other controls.
        link_css = ('popover.obyn-info button.link { color: ' + mappa['#eefbf6'] + '; }'
                    'popover.obyn-info button.link label { color: inherit; }'
                    'popover.obyn-info button.link:focus-visible { outline: 2px solid ' +
                    mappa['#63dfbb'] + '; outline-offset: 2px; }')
        self.tema_link_provider.load_from_data(link_css.encode())
        # Conserva solo le varianti attive correnti; i widget possiedono il loro GIcon.
        ObynApplication._icone_svg = {k: v for k, v in ObynApplication._icone_svg.items() if not k[0].endswith('-active')}
        for (_, azione), pulsante in self.pulsanti_instradamento.items():
            if pulsante.has_css_class('route-active'):
                pulsante.set_child(self._icona(('output' if azione == 'uscita' else 'mic') + '-active'))
        return False

    def _salva_tema(self):
        self.tema_salvataggio = None
        precedente = self.config.get('theme_hue')
        self.config['theme_hue'] = self.tema_tonalita
        try:
            self.salva_config()
        except OSError as exc:
            if precedente is None:
                self.config.pop('theme_hue', None)
            else:
                self.config['theme_hue'] = precedente
            self._conserva_dettaglio(tr('Tema'), tr('Preferenza non salvata: ') + str(exc))
        else:
            self._log(tr('Tema'), tr('Tonalità {v0:.1f}°').format(v0=self.tema_tonalita))
        return False

    def do_activate(self):
        if self.finestra is None:
            _lingue.configure(self.config.get('language', 'auto'))
        if self.finestra:
            self._log(tr('Sessione'), tr('Finestra riaperta dal tray'))
            self.finestra.present()
            self._controlla_audio()
            return
        self.tema_sistema = TemaSistema(Gtk.Settings.get_default())
        self.finestra = Gtk.ApplicationWindow(application=self)
        self.colori_kde = ColoriKde(self.finestra.get_display())
        self.finestra.set_title('OBYN · Only Bluetooth You Need')
        self.finestra.set_icon_name('io.obyn.Bluetooth')
        self.finestra.set_default_size(1000, 680)
        self.finestra.set_size_request(388, -1)  # una card da 300 px e margini per le frecce
        self.finestra.add_css_class('obyn')
        css = Gtk.CssProvider()
        self.tema_provider = css
        self.tema_link_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(self.finestra.get_display(),
            self.tema_link_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 2)
        self.css_base = b'''
            .obyn label:not(.title-2):not(.device-state):not(.obyn-section):not(.heading),
            popover.obyn-info label:not(.heading) { font-family: "Adwaita Sans", "Noto Sans", sans-serif; }
            /* Il titolo del popup usava gia Adwaita Sans in grassetto. */
            popover.obyn-info label.heading { font-family: "Adwaita Sans", "Noto Sans", sans-serif; }
            .obyn button { border-radius: 10px; padding: 9px 13px; }
            .obyn button.obyn-tool, .obyn .obyn-settings > button { min-width: 48px; min-height: 48px; padding: 0; }
            .obyn .obyn-panel { border-radius: 14px; padding: 0; }
            .obyn scale.volume-wide { padding: 6px 0; margin: 0; }
            .obyn .device-card { border-radius: 14px; background: alpha(#8996a5, .08); padding: 12px; }
            .obyn .device-card.selected { background: #103d3b; color: #eefbf6; box-shadow: inset 0 0 0 1px #63dfbb; }
            .obyn .device-card:focus { outline: 2px solid #63dfbb; }
            .obyn .device-state { font-size: 1.12em; font-weight: bold; }
            .obyn .edge-left { background: linear-gradient(to right, alpha(#d9f1ed, .22), transparent); }
            .obyn .edge-right { background: linear-gradient(to left, alpha(#d9f1ed, .22), transparent); }
            .obyn .edge-button { padding: 0; min-width: 30px; min-height: 50px; background: transparent; border: none; }
            .obyn .device-actions button, .obyn button.compact-tool { min-width: 36px; min-height: 36px; padding: 0; border-radius: 9px; }
            .obyn button.route-active { background: #63dfbb; color: #103d3b; border-color: #63dfbb; }
            .obyn button.startup-toggle { min-width: 22px; min-height: 42px; padding: 3px; border-radius: 16px; background: #283d3c; }
            .obyn button.startup-toggle:checked { background: #63dfbb; border-color: #63dfbb; }
            .obyn .startup-dot { min-width: 16px; min-height: 16px; border-radius: 50%; background: #103d3b; border: 1px solid #63dfbb; }
            popover.obyn-info > contents { background: #203331; color: #eefbf6; border: 1px solid #568e83; border-radius: 14px; padding: 4px; }
            popover.obyn-info button { background: #2b4541; color: #eefbf6; border: 1px solid #568e83; border-radius: 10px; padding: 9px 13px; }
            popover.obyn-info button:hover, .obyn .session-log button:hover { background: #36574f; }
            .obyn .session-log button:focus-visible { outline: 2px solid #63dfbb; outline-offset: 2px; }
            popover.obyn-info .language-choices button { padding: 7px 5px; }
            popover.obyn-info .language-choices button:checked { background: #63dfbb; color: #103d3b; border-color: #63dfbb; }
            .obyn .session-log { background: #203331; color: #eefbf6; border: 1px solid #568e83; border-radius: 14px; }
            .obyn .session-log textview, .obyn .session-log textview text { background: transparent; color: #eefbf6; font-family: "Adwaita Sans", "Noto Sans", sans-serif; }
            .obyn .session-log button { background: #2b4541; color: #eefbf6; border: 1px solid #568e83; border-radius: 9px; }
            .obyn .device-address { font-size: 0.85em; opacity: .7; }
            .obyn .obyn-section { font-weight: bold; margin-top: 8px; }
            .obyn .obyn-mode { border-color: #5794ba; background: alpha(#5794ba, 0.18); }
            .obyn button.obyn-mode:disabled { color: @theme_fg_color; opacity: 1; }
        '''
        self.tema_tonalita = tonalita_valida(self.config.get('theme_hue', TONALITA_PETROLIO))
        self._applica_tema()
        Gtk.StyleContext.add_provider_for_display(self.finestra.get_display(), css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.set_margin_top(16); root.set_margin_bottom(16)
        root.set_margin_start(44); root.set_margin_end(44)
        # Il layout determina l’altezza minima: nessuno scroll verticale
        # della pagina e nessun controllo fuori dalla finestra.
        overlay = Gtk.Overlay()
        self.overlay_principale = overlay
        overlay.set_child(root)
        self.finestra.set_child(overlay)
        # Il pulsante di chiusura nasconde la finestra: OBYN rimane visibile
        # nel vassoio KDE e può continuare a gestire una scansione in corso.
        self.finestra.connect('close-request', self._nascondi_finestra)

        titolo = Gtk.Label(label=tr('Dispositivi Bluetooth'))
        titolo.set_xalign(0)
        titolo.add_css_class('title-2')
        titolo.set_wrap(True)
        root.append(titolo)
        self.stato = Gtk.Label(label=tr('Premi “Cerca dispositivi” per iniziare.'))
        self.stato.set_xalign(0)
        self.stato.set_wrap(True)
        self.stato.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.stato.set_selectable(True)
        self.stato.set_focusable(False)
        root.append(self.stato)

        barra = Gtk.Box(spacing=8)
        root.append(barra)
        cerca = self._bottone_icona('radar', tr('Cerca dispositivi'), True)
        cerca.connect('clicked', self.avvia_scansione)
        barra.append(cerca)
        self.pulsante_ferma = self._bottone_icona('stop', tr('Ferma ricerca'), True)
        self.pulsante_ferma.set_sensitive(False)
        self.pulsante_ferma.connect('clicked', self.ferma_scansione)
        barra.append(self.pulsante_ferma)
        aggiorna = self._bottone_icona('refresh', tr('Aggiorna elenco'), True)
        aggiorna.connect('clicked', lambda *_: self.aggiorna_elenco())
        barra.append(aggiorna)
        self.controlli_operazioni.extend([cerca, aggiorna])
        self.menu_impostazioni = Gtk.MenuButton()
        self.menu_impostazioni.set_child(self._icona('settings'))
        self.menu_impostazioni.add_css_class('obyn-settings')
        self.menu_impostazioni.set_tooltip_text(tr('Informazioni e opzioni del dispositivo selezionato'))
        self.menu_impostazioni.update_property([Gtk.AccessibleProperty.LABEL], [tr('Opzioni del dispositivo selezionato')])
        self.menu_impostazioni.set_create_popup_func(self._crea_opzioni_popup)
        barra.append(self.menu_impostazioni)
        self.controlli_operazioni.append(self.menu_impostazioni)
        self._crea_tema(barra)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.NEVER)
        scroller.set_min_content_width(300)
        scroller.set_min_content_height(192)
        self.scroller_dispositivi = scroller
        self.lista = Gtk.Box(spacing=12)
        self.lista.set_valign(Gtk.Align.START)
        self.controlli_operazioni.append(self.lista)
        scroller.set_child(self.lista)
        root.append(scroller)
        aggiustamento = scroller.get_hadjustment()
        for direzione, allineamento, classe in [(-1, Gtk.Align.START, 'edge-left'), (1, Gtk.Align.END, 'edge-right')]:
            fascia = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            fascia.set_size_request(36, -1)
            fascia.set_halign(allineamento)
            fascia.add_css_class(classe)
            spazio_sopra = Gtk.Box(vexpand=True)
            spazio_sopra.set_can_target(False)
            fascia.append(spazio_sopra)
            freccia = self._bottone_icona('left' if direzione < 0 else 'right',
                                        tr('Dispositivi precedenti') if direzione < 0 else tr('Dispositivi successivi'))
            # Nelle fasce laterali resta la sola freccia, con nome accessibile.
            freccia.set_child(self._icona('left' if direzione < 0 else 'right'))
            freccia.add_css_class('edge-button')
            freccia.connect('clicked', lambda _, d=direzione: self._scorri_dispositivi(d))
            fascia.append(freccia)
            spazio_sotto = Gtk.Box(vexpand=True)
            spazio_sotto.set_can_target(False)
            fascia.append(spazio_sotto)
            overlay.add_overlay(fascia)
            self.frecce_dispositivi.append((fascia, freccia, direzione))
        aggiustamento.connect('changed', self._aggiorna_frecce)
        aggiustamento.connect('value-changed', self._aggiorna_frecce)
        self._aggiorna_frecce(aggiustamento)
        self.crea_controlli_audio(root)
        self._crea_log(overlay)
        self._log(tr('Sessione'), tr('Finestra aperta · OBYN ') + __version__)
        self.finestra.present()
        self._avvia_tray()
        self.aggiorna_elenco()
        GLib.timeout_add_seconds(3, self._controlla_audio)
        self._avvia_monitor_bt()
        GLib.timeout_add_seconds(3, self._aggiorna_stato_bt)

    def _aggiorna_frecce(self, aggiustamento):
        limite = max(0, aggiustamento.get_upper() - aggiustamento.get_page_size())
        valore = aggiustamento.get_value()
        for fascia, freccia, direzione in self.frecce_dispositivi:
            disponibile = limite > 1 and (valore > 1 if direzione < 0 else valore < limite - 1)
            fascia.set_visible(disponibile)
            freccia.set_sensitive(disponibile)

    def _scorri_dispositivi(self, direzione):
        aggiustamento = self.scroller_dispositivi.get_hadjustment()
        passo = 312  # larghezza scheda più spazio: nessuna variazione al resize
        limite = max(0, aggiustamento.get_upper() - aggiustamento.get_page_size())
        aggiustamento.set_value(max(0, min(limite, aggiustamento.get_value() + direzione * passo)))

    def _avvia_monitor_bt(self):
        def pronto(sorgente, risultato):
            try:
                self.monitor_bt = Gio.bus_get_finish(risultato)
                for interfaccia, segnale in [
                    ('org.freedesktop.DBus.Properties', 'PropertiesChanged'),
                    ('org.freedesktop.DBus.ObjectManager', 'InterfacesAdded'),
                    ('org.freedesktop.DBus.ObjectManager', 'InterfacesRemoved'),
                ]:
                    self.monitor_bt.signal_subscribe('org.bluez', interfaccia, segnale,
                        None, None, Gio.DBusSignalFlags.NONE, self._evento_bt)
                self._aggiorna_stato_bt()
            except GLib.Error as exc:
                self._mostra_errore_bt(tr('Aggiornamento automatico non disponibile: ') + str(exc))
        Gio.bus_get(Gio.BusType.SYSTEM, None, pronto)

    def _evento_bt(self, connessione, mittente, percorso, interfaccia, segnale, parametri):
        if segnale == 'PropertiesChanged':
            nome, modifiche, invalidate = parametri.unpack()
            if nome != 'org.bluez.Device1' or not ({'Connected', 'Paired', 'Trusted', 'Alias', 'Name', 'UUIDs', 'AddressType', 'Icon'} & (set(modifiche) | set(invalidate))):
                return
        if self.timer_bt is None:
            self.timer_bt = GLib.timeout_add(150, self._evento_bt_differito)

    def _evento_bt_differito(self):
        self.timer_bt = None
        self._aggiorna_stato_bt()
        return False

    def _aggiorna_stato_bt(self):
        if self.monitor_bt is None or self.operazione is not None or self.lettura_bt_in_corso:
            return True
        self.lettura_bt_in_corso = True
        generazione = self.audio_generazione
        def leggi():
            try:
                oggetti = self.monitor_bt.call_sync('org.bluez', '/',
                    'org.freedesktop.DBus.ObjectManager', 'GetManagedObjects', None,
                    None, Gio.DBusCallFlags.NONE, 5000, None).unpack()[0]
                GLib.idle_add(self._ricevi_stato_bt, generazione, oggetti, '')
            except Exception as exc:
                GLib.idle_add(self._ricevi_stato_bt, generazione, None, str(exc))
        try:
            threading.Thread(target=leggi, daemon=True).start()
        except Exception as exc:
            self._ricevi_stato_bt(generazione, None, str(exc))
        return True

    def _ricevi_stato_bt(self, generazione, oggetti, errore):
        self.lettura_bt_in_corso = False
        if generazione != self.audio_generazione or self.operazione is not None:
            return False
        if errore:
            self._mostra_errore_bt(tr('Stato Bluetooth non aggiornato: ') + errore)
            return False
        # Non iniziare scansioni o riconnessioni: osservare gli oggetti BlueZ.
        dispositivi = []
        nascosti = set(self.config.get('hidden_devices', []))
        for interfacce in oggetti.values():
            p = interfacce.get('org.bluez.Device1', {})
            mac = p.get('Address', '').upper()
            if not mac or mac in nascosti:
                continue
            dispositivi.append((mac, p.get('Alias') or p.get('Name') or mac, {
                'connected': bool(p.get('Connected')), 'paired': bool(p.get('Paired')),
                'trusted': bool(p.get('Trusted')),
                **{k: p[v] for k, v in [('address_type', 'AddressType'), ('uuids', 'UUIDs'), ('icon', 'Icon')] if v in p},
            }))
        dispositivi.sort(key=lambda d: d[0])
        if dispositivi != sorted(self.dispositivi_visualizzati, key=lambda d: d[0]):
            self.generazione_elenco += 1
            self.audio_generazione += 1
            self.errore_azione_pendente = ''
            self._mostra_dispositivi(dispositivi)
            self.aggiorna_info_audio()
        return False

    def _nascondi_finestra(self, *_):
        self._chiudi_log()
        self._log(tr('Sessione'), tr('Finestra chiusa nel tray; registrazione temporanea cancellata'))
        self._cancella_messaggio()
        self.finestra.hide()
        return True

    def _avvia_tray(self):
        """Avvia il piccolo StatusNotifier KDE, se incluso nell'installazione."""
        if self.tray_process and self.tray_process.poll() is None:
            return
        eseguibile = Path(__file__).with_name('obyn-tray')
        if not eseguibile.is_file() or not os.access(eseguibile, os.X_OK):
            return
        self.tray_quit_file = Path('/tmp') / f'obyn-quit-{os.getpid()}'
        self.tray_quit_file.unlink(missing_ok=True)
        try:
            self.tray_process = subprocess.Popen([
                str(eseguibile), '--obyn-exec', str(Path(sys.argv[0]).resolve()),
                '--quit-file', str(self.tray_quit_file),
                '--open-label', tr('Apri OBYN'), '--quit-label', tr('Esci da OBYN'),
                '--status-label', tr('Gestione Bluetooth attiva'),
            ])
        except OSError:
            self.tray_process = None
            return
        if self.tray_watch_id is None:
            self.tray_watch_id = GLib.timeout_add(500, self._controlla_richiesta_uscita)

    def _controlla_richiesta_uscita(self):
        if self.tray_quit_file and self.tray_quit_file.exists():
            self.tray_quit_file.unlink(missing_ok=True)
            self.quit()
            return False
        return True

    def do_shutdown(self):
        if self.colori_kde is not None:
            self.colori_kde.close()
        if self.tema_sistema is not None:
            self.tema_sistema.close()
        if self.tema_timer is not None:
            GLib.source_remove(self.tema_timer)
            self.tema_timer = None
        if self.tema_salvataggio is not None:
            GLib.source_remove(self.tema_salvataggio)
            self._salva_tema()
        self._cancella_messaggio()
        self.ferma_scansione_evento.set()
        if self.tray_process and self.tray_process.poll() is None:
            self.tray_process.terminate()
        if self.tray_quit_file:
            self.tray_quit_file.unlink(missing_ok=True)
        Gtk.Application.do_shutdown(self)

    def crea_controlli_audio(self, root):
        riquadro = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        riquadro.append(Gtk.Label(label=tr('Audio Bluetooth'), xalign=0))
        riquadro.add_css_class('obyn-panel')
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        box.set_margin_top(8); box.set_margin_bottom(8)
        riquadro.append(box)
        root.append(riquadro)
        self.ferma_registrazione_button = self._bottone_icona('stop', tr('Ferma registrazione'))
        self.ferma_registrazione_button.set_visible(False)
        self.ferma_registrazione_button.connect('clicked', self._ferma_registrazione)
        root.append(self.ferma_registrazione_button)
        self.audio_info = Gtk.Label(label=tr('Seleziona un dispositivo per i controlli audio.'))
        self.audio_info.set_xalign(0)
        self.audio_info.set_wrap(True)
        self.audio_info.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.audio_info.set_selectable(True)
        self.audio_info.set_focusable(False)
        box.append(self.audio_info)
        riga = Gtk.Box(spacing=8)
        box.append(riga)
        for icona, testo, azione in [('rec', tr('Registra fino a 10 secondi: il microfono viene preparato automaticamente'), 'test_microfono'),
                                     ('play', tr('Riproduci la registrazione o il suono di prova'), 'test_audio'),
                                     ('save', tr('Salva una copia della registrazione'), 'salva_messaggio')]:
            pulsante = self._bottone_icona(icona, testo, True)
            pulsante.add_css_class('compact-tool')
            pulsante.connect('clicked', lambda _, a=azione: self.azione_audio(a))
            riga.append(pulsante)
            self.pulsanti_audio[azione] = pulsante
            pulsante.set_sensitive(False)

        self.pulsante_log = self._bottone_icona('info', tr('Log della sessione'), True)
        self.pulsante_log.add_css_class('compact-tool')
        self.pulsante_log.connect('clicked', self._apri_log)
        riga.append(self.pulsante_log)

        volume_riga = Gtk.Box(spacing=10)
        volume_riga.set_margin_top(4)
        box.append(volume_riga)
        etichetta_volume = Gtk.Label(label=tr('Volume'))
        etichetta_volume.set_xalign(0)
        etichetta_volume.set_hexpand(True)
        volume_riga.append(etichetta_volume)
        self.volume_slider = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, 150, 1,
        )
        self.volume_slider.add_css_class('volume-wide')
        self.volume_slider.set_hexpand(True)
        self.volume_slider.set_draw_value(False)
        self.volume_slider.set_value(100)
        self.volume_slider.set_sensitive(False)
        self.volume_slider.set_tooltip_text(
            tr('Volume dell’uscita Bluetooth selezionata. In HFP può compensare in parte l’attenuazione tipica delle chiamate.')
        )
        self.volume_slider.connect('value-changed', self._volume_modificato)
        eventi_volume = Gtk.EventControllerLegacy()
        eventi_volume.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        eventi_volume.connect('event', self._evento_volume)
        self.volume_slider.add_controller(eventi_volume)
        box.append(self.volume_slider)
        self.volume_label = Gtk.Label(label='')
        self.volume_label.set_width_chars(5)
        self.volume_label.set_xalign(1)
        volume_riga.append(self.volume_label)

    def _avvia_operazione(self, nome, funzione, *argomenti):
        """Una sola operazione alla volta sul controller e sull'audio.

        La prenotazione avviene nel thread GTK prima di avviare il worker:
        anche due clic consecutivi non possono lanciare comandi concorrenti.
        """
        if self.operazione is not None:
            return False
        self.operazione = nome
        origine = getattr(self, 'pulsante_origine', None)
        self.pulsante_origine = None
        if nome != 'volume' and origine is not None:
            self.pulsante_in_attesa = origine
            origine.attesa(True)
        self.log_operazione = None
        if nome != 'elenco' or origine is not None:
            dettagli = ' · '.join(str(a) for a in argomenti if isinstance(a, (str, int, float)))
            self.log_operazione = nome + (' · ' + dettagli if dettagli else '')
            self._log(tr('Avvio'), self.log_operazione)
        self.audio_generazione += 1
        if self.volume_timeout:
            GLib.source_remove(self.volume_timeout)
            self.volume_timeout = None
        # Un comando volume non deve revocare il grab di Gtk.Scale.
        if nome != 'volume':
            for pulsante in self.pulsanti_audio.values():
                pulsante.set_sensitive(False)
            if self.volume_slider is not None:
                self.volume_slider.set_sensitive(False)
            for controllo in self.controlli_operazioni:
                controllo.set_sensitive(False)

        def lavoro():
            try:
                funzione(*argomenti)
            except Exception as exc:
                GLib.idle_add(self._mostra_errore_bt, str(exc))
            finally:
                GLib.idle_add(self._termina_operazione)

        try:
            threading.Thread(target=lavoro, daemon=True).start()
        except Exception as exc:
            self._mostra_errore_bt(str(exc))
            self._termina_operazione()
        return True

    def _termina_operazione(self):
        attivo = getattr(self, 'pulsante_in_attesa', None)
        if attivo is not None:
            attivo.attesa(False)
            self.pulsante_in_attesa = None
        if self.log_operazione is not None:
            self._log(tr('Fine operazione'), self.log_operazione)
            self.log_operazione = None
        precedente = self.operazione
        self.operazione = None
        self.scansione = False
        if self.pulsante_ferma is not None:
            self.pulsante_ferma.set_sensitive(False)
        for controllo in self.controlli_operazioni:
            controllo.set_sensitive(True)
        if self.aggiornamento_pendente:
            self.pulsante_origine = attivo
            self.aggiornamento_pendente = False
            self.aggiorna_elenco()
        elif precedente in {'elenco', 'bluetooth', 'scansione'} and self.dispositivo_audio:
            self.aggiorna_info_audio()
        self._abilita_audio()
        if precedente == 'volume' and self.volume_pendente is not None:
            valore, self.volume_pendente = self.volume_pendente, None
            if self.operazione is None:
                self._applica_volume(valore)
        return False

    def aggiorna_elenco(self):
        if self.lista is None:
            return
        self.generazione_elenco += 1
        if self.operazione is not None:
            # Accorpa le richieste e invalida una lettura ormai superata.
            self.aggiornamento_pendente = True
            return
        auto_mac = None
        if not self.auto_avvio_consumato:
            self.auto_avvio_consumato = True
            auto_mac = self.config.get('auto_connect')
        self._avvia_operazione(
            'elenco', self._leggi_dispositivi, self.generazione_elenco, auto_mac,
        )

    def _leggi_dispositivi(self, generazione, auto_mac):
        accensione = prepara_bluetooth()
        if self._errore_comando_bt(accensione):
            GLib.idle_add(self._ricevi_elenco, generazione, None, accensione)
            return
        testo = comando_bt('devices')
        if self._errore_comando_bt(testo):
            GLib.idle_add(self._ricevi_elenco, generazione, None, testo)
            return
        dispositivi = []
        errore = ''
        nascosti = set(self.config.get('hidden_devices', []))
        for riga in testo.splitlines():
            match = re.match(r'Device\s+([0-9A-F:]{17})\s+(.+)', riga.strip(), re.I)
            if not match:
                continue
            mac, nome = match.groups()
            if mac.upper() in nascosti:
                continue
            info = comando_bt('info', mac)
            if self._errore_comando_bt(info):
                GLib.idle_add(self._ricevi_elenco, generazione, None, info)
                return
            stato = self._stato_info(info)
            if auto_mac and auto_mac.upper() == mac.upper() and not stato['connected']:
                esito = comando_bt('connect', mac)
                if self._errore_comando_bt(esito):
                    errore = esito
                conferma = comando_bt('info', mac)
                if self._errore_comando_bt(conferma):
                    GLib.idle_add(self._ricevi_elenco, generazione, None, esito if errore else conferma)
                    return
                stato = self._stato_info(conferma)
            dispositivi.append((mac, nome, stato))
        GLib.idle_add(self._ricevi_elenco, generazione, dispositivi, errore)

    def _ricevi_elenco(self, generazione, dispositivi, errore):
        if generazione != self.generazione_elenco:
            return False
        if dispositivi is not None:
            self._mostra_dispositivi(dispositivi)
        errore = self.errore_azione_pendente or errore
        self.errore_azione_pendente = ''
        if errore:
            self._mostra_errore_bt(errore)
        return False

    @staticmethod
    def _errore_comando_bt(esito):
        # Riconoscere messaggi di fallimento, non parole nelle proprietà o
        # nei nomi: “Blocked: no” è un normale campo di bluetoothctl info.
        return bool(re.search(
            r'^\s*(?:Errore Bluetooth:|Bluetooth error:|Failed\b|Failure\b|Error\b|'
            r'org\.bluez\.Error\.|No default controller\b|No agent\b|'
            r'Device\s+[0-9A-F:]{17}\s+(?:not available|not found)\b)',
            esito, re.I | re.M,
        ))

    @staticmethod
    def _stato_info(info):
        def valore(chiave):
            m = re.search(rf'^\s*{chiave}:\s*(\w+)', info, re.M | re.I)
            return m.group(1).lower() if m else 'no'
        stato = {
            'connected': valore('Connected') == 'yes',
            'paired': valore('Paired') == 'yes',
            'trusted': valore('Trusted') == 'yes',
        }

        indirizzo = re.search(r'^Device\s+[0-9A-F:]{17}\s+\((public|random)\)', info, re.M | re.I)
        if indirizzo:
            stato['address_type'] = indirizzo.group(1).lower()
        uuids = re.findall(r'^\s*UUID:.*?([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', info, re.M | re.I)
        icona = re.search(r'^\s*Icon:\s*(\S+)', info, re.M)
        if icona:
            stato['icon'] = icona.group(1)
        if uuids:
            stato['uuids'] = [uuid.lower() for uuid in uuids]
        return stato

    @staticmethod
    def _dicitura_dispositivo(stato):
        uuids = {str(u).lower() for u in stato.get('uuids', [])}
        fast_pair = '0000fe2c-0000-1000-8000-00805f9b34fb' in uuids
        audio = any('0000' + servizio + '-0000-1000-8000-00805f9b34fb' in uuids
                    for servizio in ('1108', '110a', '110b', '1112', '111e', '111f'))
        parti = []
        if fast_pair:
            parti.append('Google Fast Pair')
        if audio:
            parti.append(tr('Servizi audio dichiarati'))
        elif not uuids:
            parti.append(tr('Servizi non ancora identificati'))
        elif not fast_pair:
            parti.append(tr('Altri servizi dichiarati'))
        tipo = {'public': tr('indirizzo pubblico'), 'random': tr('indirizzo casuale')}.get(stato.get('address_type'))
        if tipo:
            parti.append(tipo)
        return ' · '.join(parti)

    @staticmethod
    def _tipo_icona(stato):
        return {'audio-headset': 'headset', 'audio-headphones': 'headset',
                'audio-card': 'speaker', 'audio-speakers': 'speaker',
                'phone': 'phone', 'computer': 'computer',
                'input-keyboard': 'keyboard', 'input-mouse': 'mouse'}.get(stato.get('icon'), 'device')

    def _mostra_dispositivi(self, dispositivi):
        for mac, nome, stato in dispositivi:
            self._log_stato('Bluetooth · ' + nome + ' · ' + mac, json.dumps(stato, ensure_ascii=False, sort_keys=True))
        presenti = {mac for mac, _, _ in dispositivi}
        for mac, nome, _ in self.dispositivi_visualizzati:
            if mac not in presenti:
                self._log_stato('Bluetooth · ' + nome + ' · ' + mac, tr('Non più presente nell’elenco'))
        self.dispositivi_visualizzati = [(mac, nome, dict(stato)) for mac, nome, stato in dispositivi]
        self.schede = {}
        self.interruttori_avvio = {}
        self.pulsanti_instradamento = {}
        while (riga := self.lista.get_first_child()) is not None:
            self.lista.remove(riga)
        connessi = sum(bool(stato['connected']) for _, _, stato in dispositivi)
        self.stato.set_text(ngettext('{count} dispositivo nell’elenco Bluetooth', '{count} dispositivi nell’elenco Bluetooth', len(dispositivi)).format(count=len(dispositivi)) + '; ' + ngettext('{count} connesso.', '{count} connessi.', connessi).format(count=connessi)
                            if dispositivi else tr('Nessun dispositivo nell’elenco salvato. Premi “Cerca dispositivi”.'))
        for mac, nome, stato in dispositivi:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            box.add_css_class('device-card')
            box.set_size_request(300, 180)
            self.schede[mac] = box
            if mac == self.dispositivo_audio:
                box.add_css_class('selected')
            box.set_focusable(True)
            clic = Gtk.GestureClick()
            clic.connect('released', lambda _, n, x, y, m=mac, nom=nome: self.seleziona_audio(m, nom))
            box.add_controller(clic)
            tastiera = Gtk.EventControllerKey()
            tastiera.connect('key-pressed', self._tasto_scheda, mac, nome)
            box.add_controller(tastiera)
            box.set_hexpand(False)
            box.set_vexpand(False)
            box.set_valign(Gtk.Align.START)
            testata = Gtk.Box(spacing=10)
            simbolo = Gtk.Overlay()
            simbolo.set_valign(Gtk.Align.START)
            icona = self._icona(self._tipo_icona(stato))
            icona.set_pixel_size(40)
            simbolo.set_child(icona)
            if stato['paired'] and stato['trusted']:
                spunta = self._icona('check')
                spunta.set_pixel_size(18)
                spunta.set_halign(Gtk.Align.END)
                spunta.set_valign(Gtk.Align.END)
                spunta.set_tooltip_text(tr('Associato e autorizzato; la connessione è indicata separatamente.'))
                simbolo.add_overlay(spunta)
            simbolo.set_tooltip_text(tr('Associato e autorizzato') if stato['paired'] and stato['trusted'] else
                                    tr('Associato; da autorizzare') if stato['paired'] else
                                    tr('Autorizzato; da associare') if stato['trusted'] else tr('Da associare'))
            testata.append(simbolo)
            titoli = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            titoli.set_hexpand(True)
            stato_label = Gtk.Label(label=tr('Connesso') if stato['connected'] else tr('Disconnesso') if stato['paired'] else tr('Da associare'), xalign=0)
            stato_label.add_css_class('device-state')
            titoli.append(stato_label)
            nome_label = Gtk.Label(label=nome, xalign=0)
            nome_label.set_max_width_chars(19)
            nome_label.set_ellipsize(Pango.EllipsizeMode.END)
            nome_label.set_tooltip_text(nome)
            titoli.append(nome_label)
            testata.append(titoli)
            interruttore = Gtk.ToggleButton()
            interruttore.add_css_class('startup-toggle')
            interruttore.set_valign(Gtk.Align.START)
            pista = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            punto = Gtk.Box()
            punto.add_css_class('startup-dot')
            punto.set_vexpand(True)
            punto.set_halign(Gtk.Align.CENTER)
            punto.set_valign(Gtk.Align.START if self.config.get('auto_connect') == mac else Gtk.Align.END)
            pista.append(punto)
            interruttore.set_child(pista)
            interruttore.set_active(self.config.get('auto_connect') == mac)
            interruttore.set_tooltip_text(tr('Connetti all’apertura di OBYN: un solo dispositivo alla volta.'))
            interruttore.update_property([Gtk.AccessibleProperty.LABEL], [tr('Connetti {name} all’apertura di OBYN').format(name=nome)])
            interruttore.connect('toggled', lambda b, m=mac: self._imposta_avvio(b, b.get_active(), m))
            self.interruttori_avvio[mac] = interruttore
            testata.append(interruttore)
            box.append(testata)
            if mac.upper() in self.visti_scansione:
                presenza = tr('Rilevato ora') if self.scansione else tr('Rilevato nell’ultima ricerca')
            else:
                presenza = tr('Presenza non verificata dalla ricerca')
            indirizzo = Gtk.Label(label=mac, xalign=0, selectable=True)
            indirizzo.set_focusable(False)
            self.log_ancora = indirizzo
            indirizzo.add_css_class('device-address')
            indirizzo.set_tooltip_text(presenza)
            box.append(indirizzo)
            azioni = Gtk.Box(spacing=6)
            azioni.add_css_class('device-actions')
            box.append(azioni)
            self._pulsante(azioni, tr('Disconnetti') if stato['connected'] else tr('Connetti'),
                           'disconnect' if stato['connected'] else 'connect', mac)
            if not (stato['paired'] and stato['trusted']):
                self._pulsante(azioni, tr('Completa autorizzazione') if stato['paired'] else tr('Associa e autorizza'), 'pair_trust', mac)
            for icona, testo, azione in [('output', tr('Usa come uscita audio'), 'uscita'), ('mic', tr('Usa come microfono'), 'microfono')]:
                pulsante = self._bottone_icona(icona, testo, True, True)
                pulsante.set_sensitive(bool(stato['connected']))
                pulsante.connect('clicked', lambda _, a=azione, m=mac, n=nome: self._commuta_scheda(a, m, n))
                self.pulsanti_instradamento[(mac, azione)] = pulsante
                azioni.append(pulsante)
            self._pulsante(azioni, tr('Dimentica'), 'remove', mac)
            dettagli = self._dicitura_dispositivo(stato) + '\n' + presenza + '\n' + mac
            indirizzo.set_tooltip_text(dettagli)
            self.lista.append(box)
        self._mostra_instradamento()
        return False

    def _tasto_scheda(self, controller, tasto, codice, modificatori, mac, nome):
        if tasto in (Gdk.KEY_Return, Gdk.KEY_space):
            self.seleziona_audio(mac, nome)
            return True
        return False

    def _commuta_scheda(self, azione, mac, nome):
        # Il click non anticipa il verde: attendi la conferma del server.
        self._mostra_instradamento()
        self._azione_scheda(azione, mac, nome)

    def _azione_scheda(self, azione, mac, nome):
        if self.operazione is not None:
            return
        self.seleziona_audio(mac, nome)
        self.azione_audio(azione)

    def _imposta_avvio(self, interruttore, attivo, mac):
        if self.sincronizza_avvio or self.operazione is not None:
            return True
        precedente = self.config.get('auto_connect')
        if attivo:
            self.config['auto_connect'] = mac
        elif precedente == mac:
            self.config.pop('auto_connect', None)
        try:
            self.salva_config()
        except OSError as exc:
            if precedente is None:
                self.config.pop('auto_connect', None)
            else:
                self.config['auto_connect'] = precedente
            self._mostra_errore_bt(str(exc))
        self.sincronizza_avvio = True
        try:
            for indirizzo, controllo in self.interruttori_avvio.items():
                controllo.set_active(self.config.get('auto_connect') == indirizzo)
                controllo.get_child().get_first_child().set_valign(
                    Gtk.Align.START if self.config.get('auto_connect') == indirizzo else Gtk.Align.END)
        finally:
            self.sincronizza_avvio = False
        return True

    def _pulsante(self, contenitore, testo, azione, mac):
        icona = {'connect': 'connect', 'disconnect': 'disconnect',
                 'pair_trust': 'pair', 'remove': 'forget'}[azione]
        pulsante = self._bottone_icona(icona, testo, True)
        pulsante.connect('clicked', lambda *_: self.esegui_azione(azione, mac))
        contenitore.append(pulsante)

    def esegui_azione(self, azione, mac):
        if self.operazione is not None:
            return
        if azione == 'connect':
            self.ferma_scansione_evento.clear()
            self.connessione_in_corso = False
            if self.pulsante_ferma is not None:
                self.pulsante_ferma.set_sensitive(True)
            self.stato.set_text(tr('Cerco {v0} prima di connetterlo (massimo 30 secondi)…').format(v0=mac))
            self._avvia_operazione('ricerca_connessione', self._cerca_e_connetti, mac)
        elif self._avvia_operazione('bluetooth', self._azione, azione, mac):
            descrizione = {'pair_trust': tr('Associazione e autorizzazione'), 'remove': 'Rimozione', 'disconnect': tr('Disconnessione')}.get(azione, azione)
            self.stato.set_text(f'{descrizione}…')

    def _cerca_e_connetti(self, mac):
        try:
            info = comando_bt('info', mac)
            if not self._errore_comando_bt(info) and self._stato_info(info)['connected']:
                GLib.idle_add(self._azione_completata, '')
                return
            preparazione = prepara_bluetooth()
            if self._errore_comando_bt(preparazione):
                raise RuntimeError(preparazione)
            if self.ferma_scansione_evento.is_set():
                raise RuntimeError(tr('Ricerca annullata: connessione non tentata.'))
            controller = comando_bt('show')
            match = re.search(r'^Controller\s+([0-9A-F:]{17})', controller, re.M | re.I)
            if not match:
                raise RuntimeError(tr('Controller Bluetooth non disponibile. ') + controller)
            ricerca = RicercaBluez(match.group(1))
            ricerca.esegui(self.ferma_scansione_evento, lambda *_: None, obiettivo=mac)
            # esegui rilascia la propria sessione prima del comando connect.
            if self.ferma_scansione_evento.is_set():
                raise RuntimeError(tr('Ricerca annullata: connessione non tentata.'))
            rilevato = mac.upper() in ricerca.visti
            if not rilevato:
                # La discovery non è una prova di raggiungibilità dei dispositivi
                # associati. Verifica nuovamente lo stato dopo la ricerca.
                info = comando_bt('info', mac)
                if self._errore_comando_bt(info):
                    raise RuntimeError(info)
                stato = self._stato_info(info)
                if stato['connected']:
                    GLib.idle_add(self._azione_completata, '')
                    return
                if not stato['paired']:
                    raise RuntimeError(tr('Dispositivo non rilevato e non associato: connessione non tentata. Attiva la modalità di associazione e ripeti la ricerca.'))
            if self.ferma_scansione_evento.is_set():
                raise RuntimeError(tr('Ricerca annullata: connessione non tentata.'))
            self.connessione_in_corso = True
            GLib.idle_add(self._dispositivo_trovato, mac, rilevato)
            self._azione('connect', mac)
        except Exception as exc:
            GLib.idle_add(self._azione_completata, str(exc))

    def _dispositivo_trovato(self, mac, rilevato=True):
        if rilevato:
            self.visti_scansione.add(mac.upper())
        if self.pulsante_ferma is not None:
            self.pulsante_ferma.set_sensitive(False)
        self.stato.set_text(tr('Dispositivo rilevato. Connessione a {v0} in corso…').format(v0=mac) if rilevato else
                            tr('Dispositivo associato non rilevato: tentativo di connessione diretta a {v0}…').format(v0=mac))
        return False

    def _azione(self, azione, mac):
        if azione == 'pair_trust':
            self._associa_autorizza(mac)
            return
        esito = comando_bt(azione, mac)
        if azione == 'connect' and 'timed out' in esito.lower():
            GLib.idle_add(self._conserva_dettaglio, 'Bluetooth', esito)
            GLib.idle_add(self.stato.set_text, tr('Connessione in attesa: verifico lo stato del dispositivo…'))
            for _ in range(5):
                info = comando_bt('info', mac, limite=2)
                if not self._errore_comando_bt(info) and self._stato_info(info)['connected']:
                    esito = ''
                    break
                time.sleep(1)
        if self._errore_comando_bt(esito):
            GLib.idle_add(self._azione_completata, esito or tr('Operazione {v0} non riuscita.').format(v0=azione))
            return
        if azione == 'remove' and self.config.get('auto_connect') == mac:
            self.config.pop('auto_connect', None)
            self.salva_config()
        if azione == 'remove':
            nascosti = set(self.config.get('hidden_devices', []))
            nascosti.add(mac.upper())
            self.config['hidden_devices'] = sorted(nascosti)
            self.salva_config()
        GLib.idle_add(self._azione_completata, '')

    def _associa_autorizza(self, mac):
        try:
            def stato_attuale():
                info = comando_bt('info', mac)
                if self._errore_comando_bt(info):
                    raise RuntimeError(info)
                return self._stato_info(info)
            stato = stato_attuale()
            for comando, campo in [('pair', 'paired'), ('trust', 'trusted')]:
                if stato[campo]:
                    continue
                esito = comando_bt(comando, mac)
                if self._errore_comando_bt(esito):
                    raise RuntimeError(esito)
                stato = stato_attuale()
                if not stato[campo]:
                    raise RuntimeError(tr('Associazione non confermata.') if campo == 'paired' else tr('Autorizzazione non confermata.'))
            if not (stato['paired'] and stato['trusted']):
                raise RuntimeError(tr('Associazione e autorizzazione non entrambe confermate.'))
            errore = ''
        except Exception as exc:
            errore = str(exc)
        GLib.idle_add(self._azione_completata, errore)

    def _azione_completata(self, errore):
        # Anche un tentativo fallito può avere cambiato lo stato BlueZ.
        self.errore_azione_pendente = errore
        self.aggiorna_elenco()
        return False

    @staticmethod
    def _errore_leggibile(messaggio):
        testo = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', str(messaggio)).strip()
        basso = testo.lower()
        if 'paplay' in basso and 'timed out' in basso:
            return tr('La riproduzione non è terminata entro 15 secondi. Il dispositivo può risultare connesso anche se il flusso audio è bloccato. Prova a disconnetterlo e riconnetterlo.')
        for segnali, spiegazione in [
            (('br-connection-page-timeout',), tr('Il dispositivo non ha risposto alla connessione. Verifica che sia acceso e vicino al PC, poi riprova.')),
            (('authenticationfailed', 'authenticationrejected', 'authenticationcanceled'), tr('Associazione non completata. Attiva la modalità di associazione sul dispositivo e riprova.')),
            (('notready', 'rfkill'), tr('Il Bluetooth non è pronto. Verifica che sia acceso e che la modalità aereo sia disattivata.')),
            (('notauthorized', 'accessdenied', 'permission denied'), tr('Il sistema non ha autorizzato questa operazione.')),
            (('serviceunknown', 'namehasnoowner', 'connection refused'), tr('Il servizio Bluetooth o audio non è raggiungibile.')),
            (('inprogress',), tr('È già in corso un’operazione sul dispositivo. Attendi e riprova.')),
            (('timed out', 'timeout', 'tempo scaduto'), tr('Il sistema non ha confermato l’operazione in tempo. Lo stato attuale viene verificato separatamente.')),
        ]:
            if any(segnale in basso for segnale in segnali):
                return spiegazione
        if any(segnale in basso for segnale in ('org.bluez', 'traceback', '/tmp/', 'command [', 'failed')):
            return tr('Consulta il log della sessione per la diagnosi.')
        for prefisso in (tr('Operazione audio non riuscita: '), tr('Operazione Bluetooth non riuscita: '), tr('Errore Bluetooth: ')):
            testo = testo.removeprefix(prefisso)
        return testo

    def _conserva_dettaglio(self, ambito, messaggio):
        self.diagnostica[ambito] = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', str(messaggio))
        self._log(ambito + tr(' · errore'), self.diagnostica[ambito])

    def _copia_dettagli(self, pulsante):
        self.finestra.get_clipboard().set('\n'.join(self.log_eventi))
        pulsante.set_tooltip_text(tr('Log copiato negli appunti'))

    def _cancella_log(self, *_):
        self.log_eventi.clear()
        self.log_basi.clear()
        self.log_visualizzati = 0
        self.diagnostica.clear()
        # Conservare l'ultima fotografia evita di ripubblicare stati invariati.
        if self.log_buffer is not None:
            self.log_buffer.set_text('')
        self.log_segui = True

    def _log(self, ambito, messaggio):
        # Chiamato sul thread GTK: i worker consegnano gli eventi con idle_add.
        testo = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', str(messaggio))
        riga = f'[{time.strftime("%H:%M:%S")}] {ambito}: {testo}'
        self.log_eventi.append(riga)
        if self.log_pannello is not None and self.log_pannello.get_visible():
            self._aggiorna_log_testo()
        return False

    def _aggiorna_log_testo(self):
        nuovi = self.log_eventi[self.log_visualizzati:]
        if nuovi and self.log_buffer is not None:
            self.log_buffer.insert(self.log_buffer.get_end_iter(), '\n'.join(nuovi) + '\n')
            self.log_visualizzati = len(self.log_eventi)

    def _log_stato(self, chiave, valore):
        precedente = self.log_stati.get(chiave)
        if precedente == valore:
            return
        self.log_stati[chiave] = valore
        # Prima fotografia completa, poi solo campi cambiati: ricostruibile
        # senza ripetere liste UUID e profili ad ogni variazione di volume.
        dettaglio = valore
        try:
            prima, dopo = json.loads(precedente if chiave in self.log_basi else None), json.loads(valore)
            if isinstance(prima, dict) and isinstance(dopo, dict):
                delta = {k: v for k, v in dopo.items() if k not in prima or prima[k] != v}
                rimossi = [k for k in prima if k not in dopo]
                dettaglio = tr('Modifiche: ') + json.dumps(delta, ensure_ascii=False, sort_keys=True)
                if rimossi:
                    dettaglio += tr(' · Campi rimossi: ') + ', '.join(sorted(rimossi))
        except (TypeError, ValueError):
            pass
        self.log_basi.add(chiave)
        self._log(chiave, dettaglio)

    def _crea_log(self, overlay):
        # Transparent dismissal layer: an outside click closes the log without
        # activating a device or audio control underneath it.
        sfondo = Gtk.DrawingArea(hexpand=True, vexpand=True)
        sfondo.set_halign(Gtk.Align.FILL)
        sfondo.set_valign(Gtk.Align.FILL)
        sfondo.set_size_request(1, 1)
        sfondo.set_visible(False)
        clic_fuori = Gtk.GestureClick()
        clic_fuori.set_button(0)
        clic_fuori.connect('pressed', self._clic_fuori_log)
        sfondo.add_controller(clic_fuori)
        overlay.add_overlay(sfondo)
        self.log_sfondo = sfondo
        self.finestra.connect('notify::is-active', self._log_finestra_attiva)
        pannello = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        pannello.add_css_class('session-log')
        pannello.set_size_request(300, -1)
        pannello.set_halign(Gtk.Align.START)
        pannello.set_valign(Gtk.Align.FILL)
        pannello.set_margin_start(44)
        pannello.set_margin_bottom(12)
        interno = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for lato in ('top', 'bottom', 'start', 'end'):
            getattr(interno, 'set_margin_' + lato)(12)
        pannello.append(interno)
        interno.set_vexpand(True)
        barra = Gtk.Box(spacing=6)
        titolo = Gtk.Label(label=tr('Log della sessione'), xalign=0, hexpand=True)
        titolo.add_css_class('heading')
        barra.append(titolo)
        chiudi = Gtk.Button(label='×')
        chiudi.set_tooltip_text(tr('Chiudi log'))
        chiudi.connect('clicked', lambda *_: self._chiudi_log())
        barra.append(chiudi)
        interno.append(barra)
        copia = Gtk.Button(label=tr('Copia tutto'))
        copia.connect('clicked', self._copia_dettagli)
        azioni = Gtk.Box(spacing=6)
        copia.set_hexpand(True)
        azioni.append(copia)
        cancella = Gtk.Button(label=tr('Cancella'))
        cancella.set_tooltip_text(tr('Cancella storico della sessione'))
        cancella.connect('clicked', self._cancella_log)
        cancella.set_hexpand(True)
        azioni.append(cancella)
        interno.append(azioni)
        self.log_scroll = Gtk.ScrolledWindow(vexpand=True)
        self.log_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        vista = Gtk.TextView(editable=False, cursor_visible=False)
        vista.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.log_buffer = vista.get_buffer()
        self.log_visualizzati = 0
        self._aggiorna_log_testo()
        self.log_scroll.set_child(vista)
        interno.append(self.log_scroll)
        adj = self.log_scroll.get_vadjustment()
        adj.connect('value-changed', self._log_scorrimento)
        adj.connect('changed', self._log_dimensioni)
        pannello.set_visible(False)
        overlay.add_overlay(pannello)
        self.log_pannello = pannello
        escape = Gtk.EventControllerKey()
        escape.connect('key-pressed', lambda _, key, *args: self._chiudi_log() if key == Gdk.KEY_Escape else False)
        pannello.add_controller(escape)

    def _log_scorrimento(self, adj):
        if self.log_pannello is None or not self.log_pannello.get_visible():
            return
        self.log_segui = adj.get_value() >= adj.get_upper() - adj.get_page_size() - 3

    def _log_dimensioni(self, adj):
        if self.log_segui:
            adj.set_value(max(0, adj.get_upper() - adj.get_page_size()))

    def _posiziona_log(self, *_):
        top = 240
        ancora = getattr(self, 'log_ancora', None)
        if ancora is not None:
            valido, bounds = ancora.compute_bounds(self.overlay_principale)
            if valido:
                top = round(bounds.get_y())
        top = max(0, min(top, self.overlay_principale.get_height() - 170))
        if self.log_pannello.get_margin_top() != top:
            self.log_pannello.set_margin_top(top)
        return True

    def _apri_log(self, *_):
        if self.log_pannello.get_visible():
            self._chiudi_log()
            return
        segui = self.log_segui
        self._aggiorna_log_testo()
        self._posiziona_log()
        self.log_sfondo.set_visible(True)
        self.log_pannello.set_visible(True)
        self.log_tick = GLib.timeout_add(150, self._posiziona_log)
        GLib.timeout_add(60, self._log_aperto, segui)

    def _log_aperto(self, segui):
        # Il TextView aggiorna i limiti dello scroll dopo la prima allocazione.
        if segui and self.log_pannello.get_visible():
            self.log_segui = True
            self._log_dimensioni(self.log_scroll.get_vadjustment())
        return False

    def _clic_fuori_log(self, gesture, *_):
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self._chiudi_log()

    def _log_finestra_attiva(self, window, *_):
        if not window.is_active():
            self._chiudi_log()

    def _chiudi_log(self):
        if self.log_tick is not None:
            GLib.source_remove(self.log_tick)
            self.log_tick = None
        if self.log_pannello is not None:
            self.log_pannello.set_visible(False)
        if self.log_sfondo is not None:
            self.log_sfondo.set_visible(False)
        return True

    def _mostra_errore_bt(self, messaggio):
        self._conserva_dettaglio('Bluetooth', messaggio)
        if self.stato:
            self.stato.set_text(tr('Ultimo tentativo Bluetooth non riuscito: ') + self._errore_leggibile(messaggio))
        return False

    def seleziona_audio(self, mac, nome):
        if self.operazione is not None:
            return
        if self.volume_timeout:
            GLib.source_remove(self.volume_timeout)
            self.volume_timeout = None
        self.audio_generazione += 1
        self._log(tr('Selezione'), nome + ' · ' + mac)
        self.dispositivo_audio = mac
        self.nome_dispositivo_audio = nome
        for indirizzo, scheda in self.schede.items():
            if indirizzo == mac:
                scheda.add_css_class('selected')
            else:
                scheda.remove_css_class('selected')
        self.stato_audio = {}
        self.messaggio_audio = ''
        self.aggiorna_info_audio()

    def _controlla_audio(self):
        # Nel tray osserviamo ancora l'audio, con meno processi di lettura.
        adesso = time.monotonic()
        if (self.finestra is not None and not self.finestra.get_visible()
                and adesso - self.ultimo_poll_audio < 15):
            return True
        self.ultimo_poll_audio = adesso
        if self.operazione is None and not self.lettura_instradamento:
            self.lettura_instradamento = True
            try:
                threading.Thread(target=self._leggi_instradamento, args=(self.audio_generazione,), daemon=True).start()
            except Exception as exc:
                self.lettura_instradamento = False
                self._conserva_dettaglio('Audio', tr('Lettura instradamento non avviata: ') + str(exc))
        if self.dispositivo_audio and self.operazione is None and self.volume_timeout is None:
            self.aggiorna_info_audio()
        return True

    def _leggi_instradamento(self, generazione):
        try:
            stato = AudioPipewire.instradamento()
        except Exception:
            stato = {}
        GLib.idle_add(self._ricevi_instradamento, generazione, stato)

    def _ricevi_instradamento(self, generazione, stato):
        self.lettura_instradamento = False
        if generazione == self.audio_generazione and self.operazione is None:
            self.snapshot_instradamento = stato
            self._mostra_instradamento()
        return False

    def _instradamento_confermato(self, stato):
        self.snapshot_instradamento = stato
        self._mostra_instradamento()
        return False

    def _mostra_instradamento(self):
        for (mac, azione), pulsante in self.pulsanti_instradamento.items():
            tipo = 'sink' if azione == 'uscita' else 'source'
            dati = self.snapshot_instradamento.get(tipo, {})
            nodo = next((n for n in dati.get('nodes', []) if n['name'] == dati.get('default')), {})
            attivo = AudioPipewire.mac_nodo(nodo) == mac.upper() and not nodo.get('mute', False)
            if pulsante.has_css_class('route-active') != attivo:
                icona = 'output' if tipo == 'sink' else 'mic'
                pulsante.set_child(self._icona(icona + ('-active' if attivo else '')))
            if attivo:
                pulsante.add_css_class('route-active')
            else:
                pulsante.remove_css_class('route-active')
            testo = (tr('Disattiva: torna al precedente, oppure silenzia') if attivo else
                     tr('Usa come uscita audio') if tipo == 'sink' else tr('Usa come microfono'))
            pulsante.set_tooltip_text(testo)
            pulsante.set_active(attivo)

    def _commuta_instradamento(self, mac, tipo):
        stato = AudioPipewire.leggi(mac)
        if not stato['connected']:
            raise RuntimeError(tr('Il dispositivo è disconnesso.'))
        prima = AudioPipewire.instradamento()[tipo]
        corrente = next((n for n in prima['nodes'] if n['name'] == prima['default']), None)
        chiave = (mac, tipo)
        spegni = corrente is not None and AudioPipewire.mac_nodo(corrente) == mac.upper() and not corrente.get('mute', False)
        if spegni:
            precedente = self.precedenti_audio.get(chiave)
            candidati = [n for n in prima['nodes'] if precedente and n['name'] == precedente['name']]
            if not candidati and precedente and AudioPipewire.mac_nodo(precedente):
                candidati = [n for n in prima['nodes'] if AudioPipewire.mac_nodo(n) == AudioPipewire.mac_nodo(precedente)
                             and not n['name'].endswith('.monitor')]
            if len(candidati) != 1 or candidati[0]['name'] == corrente['name']:
                # Nessuna destinazione da ripristinare: spegni davvero il nodo,
                # senza cambiare profilo o disconnettere l'altro canale audio.
                AudioPipewire.imposta_muto(tipo, corrente['name'], True)
                return AudioPipewire.leggi(mac)
            destinazione = candidati[0]['name']
        else:
            # Conserva il precedente prima che HFP possa cambiare i default.
            if corrente is not None and AudioPipewire.mac_nodo(corrente) != mac.upper():
                self.precedenti_audio[chiave] = corrente
            if tipo == 'source' and not stato['source']:
                stato = AudioPipewire.cambia_profilo(mac, 'hfp')
            destinazione = stato[tipo]
            if not destinazione:
                raise RuntimeError(tr('Uscita o microfono non disponibile sul dispositivo.'))
        AudioPipewire.sposta_predefinito(tipo, destinazione, prima['default'])
        if not spegni:
            AudioPipewire.imposta_muto(tipo, destinazione, False)
        if spegni:
            self.precedenti_audio.pop(chiave, None)
        return AudioPipewire.leggi(mac)

    def aggiorna_info_audio(self):
        if not self.dispositivo_audio or self.operazione is not None or self.audio_lettura_in_corso:
            return
        self.audio_lettura_in_corso = True
        mac, generazione = self.dispositivo_audio, self.audio_generazione
        try:
            threading.Thread(target=self._leggi_audio_worker, args=(mac, generazione), daemon=True).start()
        except Exception as exc:
            self._ricevi_lettura_audio(mac, generazione, {}, tr('Stato audio non disponibile: {v0}').format(v0=exc))

    def _leggi_audio_worker(self, mac, generazione):
        try:
            stato = AudioPipewire.leggi(mac)
            messaggio = None
        except Exception as exc:
            stato, messaggio = {}, tr('Stato audio non disponibile: {v0}').format(v0=exc)
        GLib.idle_add(self._ricevi_lettura_audio, mac, generazione, stato, messaggio)

    def _ricevi_lettura_audio(self, mac, generazione, stato, messaggio):
        self.audio_lettura_in_corso = False
        # Le letture non bloccano i pulsanti; una mutazione o nuova selezione
        # invalida la risposta iniziata prima, evitando stati audio superati.
        if (generazione != self.audio_generazione or self.operazione is not None or
                self.volume_timeout is not None):
            return False
        return self._ricevi_audio(mac, stato, messaggio)

    def _ricevi_audio(self, mac, stato, messaggio):
        if mac != self.dispositivo_audio:
            return False
        self._log_stato(tr('Audio · ') + mac, json.dumps(stato, ensure_ascii=False, sort_keys=True))
        if messaggio:
            self._log(tr('Esito audio · ') + mac, messaggio)
        self.stato_audio = stato
        if self.operazione == 'volume' and stato.get('connected'):
            # Conserva l'esito, senza ricostruire testi/controlli ad ogni passo.
            if messaggio is not None:
                self.messaggio_audio = messaggio
            return False
        if 'connected' in stato and self.lista is not None:
            for indirizzo, _, precedente in self.dispositivi_visualizzati:
                if indirizzo.upper() == mac.upper() and precedente['connected'] != stato['connected']:
                    precedente['connected'] = stato['connected']
                    self._mostra_dispositivi(self.dispositivi_visualizzati)
                    break
        if messaggio is not None:
            self.messaggio_audio = messaggio
        elif self.messaggio_audio.startswith(tr('Stato audio non disponibile:')):
            self.messaggio_audio = ''
        dettagli = ''
        if not stato:
            descrizione = tr('Stato audio non verificato.')
        elif not stato['connected']:
            descrizione = tr('Dispositivo disconnesso.')
        elif not stato['card']:
            descrizione = tr('Preparazione audio in corso…')
        else:
            tipo = AudioPipewire.tipo_profilo(stato['active'])
            descrizione = {'a2dp': tr('Ascolto (A2DP)'), 'hfp': tr('Voce e microfono (HFP)')}.get(tipo, tr('Modalità non verificata'))
            if not stato['sink']:
                descrizione += tr('\nUscita audio non ancora disponibile.')
            if tipo == 'hfp' and not stato['source']:
                descrizione += tr('\nMicrofono non ancora disponibile.')
            uscita = tr('predefinita') if stato['sink'] and stato['sink'] == stato['default_sink'] else tr('disponibile') if stato['sink'] else tr('non disponibile')
            microfono = tr('predefinito') if stato['source'] and stato['source'] == stato['default_source'] else tr('disponibile') if stato['source'] else tr('non attivo')
            dettagli = tr('Uscita {v0} · Microfono {v1}').format(v0=uscita, v1=microfono)
        if self.audio_dettagli is not None and self.audio_dettagli.get_text() != dettagli:
            self.audio_dettagli.set_text(dettagli)
        registrazione = ''
        if self.prova_sessione is not None:
            if self.prova_sessione.pronto:
                if self.prova_sessione.incompleta:
                    registrazione = (tr('\nRegistrazione incompleta: ricevuti {v0:.1f} s di audio in 10 s. Puoi salvarla o ripetere REC.').format(v0=self.prova_sessione.durata))
                else:
                    registrazione = tr('\nRegistrazione pronta · {v0:.1f} secondi').format(v0=self.prova_sessione.durata)
            elif self.operazione is None or self.prova_sessione.chiuso:
                registrazione = tr('\nNessuna registrazione disponibile. Ripeti REC in modalità HFP.')
        esito_audio = self.messaggio_audio
        if any(t in esito_audio.lower() for t in ('non riuscit', 'non disponibile', 'nessun messaggio', 'interrott', 'scadut', 'failed', 'unavailable', 'no valid recording', 'stopped before', 'timed out')):
            if messaggio is not None:
                self._conserva_dettaglio('Audio', esito_audio)
            esito_audio = tr('Operazione non riuscita: ') + self._errore_leggibile(esito_audio)
        elif esito_audio in (tr('Operazione completata.'), tr('Messaggio registrato. Premi “Test audio” per ascoltarlo.'),
                             tr('Messaggio registrato riprodotto.')):
            esito_audio = ''
        esito = registrazione + (f'\n{esito_audio}' if esito_audio else '')
        testo = f'{self.nome_dispositivo_audio} · {descrizione}{esito}'
        if self.audio_info.get_text() != testo:
            self.audio_info.set_text(testo)
        if (self.volume_slider is not None and not self.volume_trascinamento
                and self.operazione != 'volume' and self.volume_timeout is None
                and time.monotonic() - self.volume_ultima_modifica > 1):
            volume = stato.get('volume')
            self.volume_in_aggiornamento = True
            if volume is not None:
                self.volume_slider.set_value(min(150, max(0, volume)))
            self.volume_in_aggiornamento = False
            self.volume_label.set_text(f'{volume}%' if volume is not None else '')
        self._abilita_audio()
        return False

    def _abilita_audio(self):
        stato = self.stato_audio
        pronto = bool(stato.get('connected')) and self.operazione is None
        sink, source = stato.get('sink'), stato.get('source')
        permessi = {
            'uscita': pronto and sink and sink != stato.get('default_sink'),
            'microfono': pronto and source and source != stato.get('default_source'),
            'a2dp': pronto and bool(AudioPipewire.profili(stato, 'a2dp')) and
                    stato.get('active') not in AudioPipewire.profili(stato, 'a2dp'),
            'hfp': pronto and bool(AudioPipewire.profili(stato, 'hfp')) and
                   stato.get('active') not in AudioPipewire.profili(stato, 'hfp'),
            'salva_messaggio': self.operazione is None and self.prova_sessione is not None
                               and self.prova_sessione.pronto,
            'test_audio': pronto and sink,
            'test_microfono': pronto and bool(AudioPipewire.profili(stato, 'hfp')),
            'auto_connect': self.dispositivo_audio is not None and self.operazione is None,
        }
        for azione, pulsante in self.pulsanti_audio.items():
            pulsante.set_sensitive(bool(permessi[azione]))
            if azione in ('a2dp', 'hfp'):
                attivo = bool(stato.get('connected')) and AudioPipewire.tipo_profilo(stato.get('active')) == azione
                if attivo:
                    pulsante.add_css_class('obyn-mode')
                else:
                    pulsante.remove_css_class('obyn-mode')
            if azione == 'auto_connect':
                attiva = self.dispositivo_audio is not None and self.config.get('auto_connect') == self.dispositivo_audio
                testo = tr('Tentativo all’avvio: ') + (tr('attiva') if attiva else tr('spenta'))
                if pulsante.get_label() != testo:
                    pulsante.set_label(testo)
        if self.volume_slider is not None:
            self.volume_slider.set_sensitive(bool(stato.get('connected') and self.operazione in (None, 'volume')
                                                  and sink and stato.get('volume') is not None))

    def _evento_volume(self, controller, evento):
        tipo = evento.get_event_type()
        if tipo in (Gdk.EventType.BUTTON_PRESS, Gdk.EventType.TOUCH_BEGIN):
            self._inizia_volume()
        elif tipo in (Gdk.EventType.BUTTON_RELEASE, Gdk.EventType.TOUCH_END):
            # Il valore finale viene letto dopo che Gtk.Scale ha gestito il rilascio.
            GLib.idle_add(self._finisci_volume)
        elif tipo == Gdk.EventType.TOUCH_CANCEL:
            self.volume_trascinamento = False
        return False  # Lascia a Gtk.Scale il controllo del gesto e del grab.

    def _inizia_volume(self):
        self.volume_trascinamento = True
        if self.volume_timeout:
            GLib.source_remove(self.volume_timeout)
            self.volume_timeout = None

    def _finisci_volume(self):
        if self.volume_trascinamento:
            self.volume_trascinamento = False
            self._volume_modificato(self.volume_slider)
        return False

    def _volume_modificato(self, slider):
        percentuale = round(slider.get_value())
        if self.volume_label:
            self.volume_label.set_text(f'{percentuale}%')
        if not self.volume_in_aggiornamento:
            self.volume_ultima_modifica = time.monotonic()
        if self.volume_in_aggiornamento or self.volume_trascinamento or not self.dispositivo_audio or self.operazione not in (None, 'volume'):
            return
        if self.operazione == 'volume':
            self.volume_pendente = percentuale
            return
        if self.volume_timeout:
            GLib.source_remove(self.volume_timeout)
        self.volume_timeout = GLib.timeout_add(180, self._applica_volume, percentuale)

    def _applica_volume(self, percentuale):
        self.volume_timeout = None
        if self.operazione == 'volume':
            self.volume_pendente = percentuale
            return False
        self._avvia_operazione('volume', self._volume_worker, percentuale)
        return False

    def _volume_worker(self, percentuale):
        self._azione_audio('volume', self.dispositivo_audio, percentuale)

    def _salva_messaggio(self):
        prova = self.prova_sessione
        if prova is None or not prova.pronto or self.dialogo_salvataggio is not None:
            return
        dialogo = Gtk.FileChooserNative.new(tr('Salva una copia della registrazione'),
            self.finestra, Gtk.FileChooserAction.SAVE, 'Salva', 'Annulla')
        dialogo.set_modal(True)
        dialogo.set_current_name('messaggio-microfono.wav')
        filtro = Gtk.FileFilter()
        filtro.set_name(tr('Audio WAV'))
        filtro.add_pattern('*.wav')
        dialogo.add_filter(filtro)
        dialogo.connect('response', self._messaggio_destinazione, prova)
        self.dialogo_salvataggio = dialogo
        dialogo.show()

    def _messaggio_destinazione(self, dialogo, risposta, prova):
        try:
            if risposta != Gtk.ResponseType.ACCEPT:
                return
            destinazione = dialogo.get_file()
            if destinazione is None:
                return
            with prova.lock:
                if prova is not self.prova_sessione or prova.chiuso or not prova.pronto:
                    raise RuntimeError(tr('Il messaggio temporaneo non è più disponibile.'))
                dati = Path(prova.percorso).read_bytes()
                destinazione.replace_contents(dati, None, False, Gio.FileCreateFlags.NONE, None)
            self.messaggio_audio = tr('Copia salvata: ') + destinazione.get_parse_name()
            self._log(tr('Salvataggio'), self.messaggio_audio)
        except (OSError, GLib.Error, RuntimeError) as exc:
            self.messaggio_audio = tr('Salvataggio non riuscito: ') + str(exc)
            self._conserva_dettaglio(tr('Salvataggio'), self.messaggio_audio)
        finally:
            dialogo.destroy()
            if self.dialogo_salvataggio is dialogo:
                self.dialogo_salvataggio = None
            if self.prova_sessione is prova:
                self._ricevi_audio(self.dispositivo_audio, self.stato_audio, None)

    def azione_audio(self, azione):
        if self.operazione is not None:
            return
        if azione == 'salva_messaggio':
            self._salva_messaggio()
            return
        if not self.dispositivo_audio:
            self.audio_info.set_text(tr('Prima seleziona il dispositivo desiderato.'))
            return
        self.audio_info.set_text(tr('Operazione audio in corso…'))
        if azione == 'test_microfono':
            self._cancella_messaggio()
            self.prova_sessione = MessaggioAudio()
            self.audio_info.set_text(tr('Preparazione della registrazione…'))
            self._avvia_operazione('audio', self._azione_audio, azione, self.dispositivo_audio, None, self.prova_sessione)
        else:
            self._avvia_operazione('audio', self._azione_audio, azione, self.dispositivo_audio)


    def _registra_preparando_microfono(self, mac, prova):
        if prova is None or prova.chiuso:
            raise RuntimeError(tr('Sessione di registrazione non disponibile.'))
        iniziale = AudioPipewire.leggi(mac)
        precedente = iniziale.get('active')
        tipo = AudioPipewire.tipo_profilo(precedente)
        if not iniziale.get('connected') or not tipo:
            raise RuntimeError(tr('Dispositivo disconnesso o modalità audio non verificata.'))
        errore = None
        try:
            stato = AudioPipewire.cambia_profilo(mac, 'hfp')
            if prova.chiuso:
                raise RuntimeError(tr('Registrazione cancellata alla chiusura della finestra.'))
            prova.registra(stato['source'], lambda: GLib.idle_add(self._registrazione_iniziata, prova))
        except Exception as exc:
            errore = str(exc)
        try:
            # Anche WirePlumber può cambiare profilo alla fine della cattura.
            stato = AudioPipewire.cambia_profilo(mac, tipo, profilo_esatto=precedente)
        except Exception as exc:
            ripristino = tr('Ripristino della modalità precedente non riuscito: ') + str(exc)
            errore = (errore + '\n' if errore else '') + ripristino
        if errore:
            raise RuntimeError(errore)
        return stato

    def _azione_audio(self, azione, mac, volume=None, prova=None):
        stato = {}
        messaggio = tr('Operazione completata.')
        try:
            if azione == 'auto_connect':
                if self.config.get('auto_connect') == mac:
                    self.config.pop('auto_connect')
                    messaggio = tr('Riconnessione all’avvio disattivata.')
                else:
                    self.config['auto_connect'] = mac
                    messaggio = tr('Riconnessione all’avvio attivata.')
                self.salva_config()
            elif azione == 'test_microfono':
                stato = self._registra_preparando_microfono(mac, prova)
                messaggio = (tr('Il flusso del microfono non ha fornito la durata attesa.') if prova.incompleta
                             else tr('Messaggio registrato. Premi “Test audio” per ascoltarlo.'))
            else:
                # Rileggere prima di agire: il dispositivo può essersi spento
                # dopo l'ultimo aggiornamento della finestra.
                stato = AudioPipewire.leggi(mac)
                if not stato['connected']:
                    raise RuntimeError(tr('Il dispositivo è disconnesso.'))
                sink, source = stato['sink'], stato['source']
                if azione in {'a2dp', 'hfp'}:
                    stato = AudioPipewire.cambia_profilo(mac, azione)
                elif azione in {'uscita', 'microfono'}:
                    stato = self._commuta_instradamento(mac, 'sink' if azione == 'uscita' else 'source')
                elif azione == 'volume' and sink:
                    AudioPipewire.comando(['pactl', 'set-sink-volume', sink, f'{volume}%'])
                elif azione == 'test_audio' and sink:
                    prova = self.prova_sessione
                    if prova is not None:
                        if not prova.pronto:
                            raise RuntimeError(tr('Nessun messaggio valido. ') + (prova.errore or tr('Ripeti “Prova microfono”.')))
                        prova.riproduci(sink)
                        messaggio = tr('Messaggio registrato riprodotto.')
                    else:
                        AudioPipewire.comando(['paplay', f'--device={sink}', '/usr/share/sounds/alsa/Front_Center.wav'])
                else:
                    raise RuntimeError(tr('Funzione non disponibile nello stato audio corrente.'))
            if azione not in {'a2dp', 'hfp', 'test_microfono'}:
                stato = AudioPipewire.leggi(mac)
        except Exception as exc:
            messaggio = tr('Operazione audio non riuscita: {v0}').format(v0=exc)
            # Un cambio parzialmente riuscito può avere alterato profili e nodi.
            try:
                stato = AudioPipewire.leggi(mac, time.monotonic() + 3)
            except Exception:
                stato = {}
        if azione in {'uscita', 'microfono'}:
            if messaggio.startswith(tr('Operazione audio non riuscita:')):
                GLib.idle_add(self._conserva_dettaglio, 'Audio', messaggio)
            messaggio = ''
            try:
                GLib.idle_add(self._instradamento_confermato, AudioPipewire.instradamento())
            except Exception:
                GLib.idle_add(self._instradamento_confermato, {})
        if azione == 'test_microfono':
            if prova is not None and not prova.pronto and not prova.errore:
                prova.errore = messaggio
            GLib.idle_add(self._registrazione_finita, prova)
        if prova is not None:
            GLib.idle_add(self._ricevi_esito_messaggio, prova, mac, stato, messaggio)
        else:
            GLib.idle_add(self._ricevi_audio, mac, stato, messaggio)

    def _ricevi_esito_messaggio(self, prova, mac, stato, messaggio):
        if prova is self.prova_sessione:
            return self._ricevi_audio(mac, stato, messaggio)
        return False

    def _registrazione_iniziata(self, prova):
        if prova is self.prova_sessione and not prova.chiuso:
            self._log(tr('Registrazione'), tr('Cattura iniziata'))
            self.audio_info.set_text(tr('Registrazione in corso: parla ora (massimo 10 secondi). Nessun riascolto automatico.'))
            if self.ferma_registrazione_button is not None:
                self.ferma_registrazione_button.set_visible(True)
                self.ferma_registrazione_button.set_sensitive(True)
        return False

    def _registrazione_finita(self, prova):
        if prova is self.prova_sessione and self.ferma_registrazione_button is not None:
            self.ferma_registrazione_button.set_visible(False)
        return False

    def _ferma_registrazione(self, *_):
        self._log(tr('Registrazione'), tr('Arresto richiesto'))
        if self.prova_sessione is not None:
            self.prova_sessione.stop.set()
        if self.ferma_registrazione_button is not None:
            self.ferma_registrazione_button.set_sensitive(False)

    def _cancella_messaggio(self):
        self.volume_trascinamento = False
        if self.dialogo_salvataggio is not None:
            self.dialogo_salvataggio.destroy()
            self.dialogo_salvataggio = None
        prova, self.prova_sessione = self.prova_sessione, None
        if prova is not None:
            prova.chiudi()
        self.messaggio_audio = ''
        if self.ferma_registrazione_button is not None:
            self.ferma_registrazione_button.set_visible(False)
        if self.audio_info is not None:
            self.audio_info.set_text(tr('Messaggio temporaneo cancellato. Seleziona un dispositivo per i controlli.'))

    def avvia_scansione(self, *_):
        if self.operazione is not None:
            return
        if self.config.pop('hidden_devices', None) is not None:
            self.salva_config()
        self.scansione = True
        self.ricerca_eseguita = False
        self.visti_scansione.clear()
        self.ferma_scansione_evento.clear()
        self.stato.set_text(tr('Avvio della ricerca Bluetooth…'))
        if self.pulsante_ferma is not None:
            self.pulsante_ferma.set_sensitive(True)
        self._avvia_operazione('scansione', self._scansiona)

    def ferma_scansione(self, *_):
        self._log(tr('Ricerca'), tr('Arresto richiesto'))
        if self.operazione == 'scansione' or (self.operazione == 'ricerca_connessione' and not self.connessione_in_corso):
            self.ferma_scansione_evento.set()
            self.stato.set_text(tr('Arresto della ricerca…'))
            if self.pulsante_ferma is not None:
                self.pulsante_ferma.set_sensitive(False)

    def _scansiona(self):
        errore = ''
        try:
            accensione = prepara_bluetooth()
            if self._errore_comando_bt(accensione):
                raise RuntimeError(accensione)
            if not self.ferma_scansione_evento.is_set():
                controller = comando_bt('show')
                match = re.search(r'^Controller\s+([0-9A-F:]{17})', controller, re.M | re.I)
                if not match:
                    raise RuntimeError(tr('Controller Bluetooth non disponibile. ') + controller)
                ricerca = RicercaBluez(match.group(1))
                ricerca.esegui(self.ferma_scansione_evento, lambda dispositivi, visti:
                    GLib.idle_add(self._ricevi_scansione, dispositivi, visti, False, ''))
        except Exception as exc:
            errore = str(exc)
        GLib.idle_add(self._ricevi_scansione, None, None, True, errore)

    def _ricevi_scansione(self, dispositivi, visti, conclusa, errore):
        if dispositivi is not None:
            self.ricerca_eseguita = True
            self.visti_scansione = visti
            self.ultimi_dispositivi_scansione = dispositivi
        if conclusa:
            self._log(tr('Ricerca'), tr('Terminata · {v0} dispositivi osservati · annullata={v1}').format(v0=len(self.visti_scansione), v1=self.ferma_scansione_evento.is_set()))
            self.scansione = False
        if self.ricerca_eseguita:
            self._mostra_dispositivi(self.ultimi_dispositivi_scansione)
        quanti = len(self.visti_scansione)
        if errore:
            errore = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', errore)
            if 'NotReady' in errore:
                motivo = tr('Il controller Bluetooth non è pronto. Verifica che sia acceso e non bloccato.')
            elif 'NotAuthorized' in errore or 'AccessDenied' in errore:
                motivo = tr('Il sistema non ha autorizzato la ricerca Bluetooth.')
            elif 'ServiceUnknown' in errore or 'NameHasNoOwner' in errore:
                motivo = tr('Il servizio Bluetooth non è disponibile.')
            else:
                motivo = tr('Ricerca Bluetooth non riuscita o interrotta.')
            self._conserva_dettaglio('Bluetooth', errore)
            self.stato.set_text(motivo + ' ' + self._errore_leggibile(errore))
        elif conclusa:
            fine = tr('Ricerca fermata') if self.ferma_scansione_evento.is_set() else tr('Ricerca conclusa')
            if self.ricerca_eseguita:
                self.stato.set_text(fine + ': ' + ngettext('{count} dispositivo osservato.', '{count} dispositivi osservati.', quanti).format(count=quanti) + ' ' + tr('La presenza dei dispositivi salvati non osservati non è verificata.'))
            else:
                self.stato.set_text(tr('Ricerca annullata prima dell’avvio.'))
        elif self.ferma_scansione_evento.is_set():
            self.stato.set_text(tr('Arresto della ricerca…'))
        else:
            self.stato.set_text(tr('Ricerca attiva (massimo 30 secondi): ') + ngettext('{count} dispositivo osservato.', '{count} dispositivi osservati.', quanti).format(count=quanti) + ' ' + tr('Per un nuovo dispositivo, attiva la sua modalità di associazione.'))
        return False

    def _scegli_lingua(self, lingua, avviso):
        precedente = self.config.get('language', 'auto')
        self.config['language'] = lingua
        try:
            self.salva_config()
        except OSError as exc:
            self.config['language'] = precedente
            avviso.set_text(tr('Preferenza non salvata: ') + str(exc))
            return
        avviso.set_text(tr('La lingua cambierà alla prossima apertura di OBYN. Esci dal tray e riapri l’app.'))

    def _crea_opzioni_popup(self, menu, *_args):
        popover = Gtk.Popover()
        popover.add_css_class('obyn-info')
        popover.set_autohide(True)
        self._prepara_opzioni_dispositivo(popover)
        menu.set_popover(popover)
        # Rebuild for the next selected device, after GTK has released its grab.
        popover.connect('closed', lambda popup:
            GLib.idle_add(self._rilascia_opzioni_popup, menu, popup))

    @staticmethod
    def _rilascia_opzioni_popup(menu, popover):
        if menu.get_popover() is popover and not popover.get_visible():
            menu.set_popover(None)
        return False

    def _prepara_opzioni_dispositivo(self, popover):
        opzioni = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        opzioni.set_margin_top(10); opzioni.set_margin_bottom(10)
        opzioni.set_margin_start(10); opzioni.set_margin_end(10)
        popover.set_child(opzioni)
        versione = Gtk.Label(label=f'OBYN {__version__} · Daniele Frasca', xalign=0, wrap=True)
        versione.add_css_class('dim-label')
        opzioni.append(versione)
        contatto = Gtk.LinkButton.new_with_label(
            'mailto:balthasar2222@gmail.com?subject=OBYN%20-%20Personalizzazione',
            tr('Richiedi una personalizzazione'))
        contatto.set_tooltip_text(tr('Scrivi a balthasar2222@gmail.com'))
        opzioni.append(contatto)
        sostegno = Gtk.LinkButton.new_with_label(
            'https://paypal.me/colbren15df', tr('Sostieni OBYN'))
        sostegno.set_tooltip_text(tr('Contributo volontario tramite PayPal'))
        opzioni.append(sostegno)
        opzioni.append(Gtk.Label(label=tr('Lingua'), xalign=0))
        # Inline choices avoid a nested popup and its competing input grab.
        scelte_lingua = Gtk.Box(spacing=4, homogeneous=True)
        scelte_lingua.add_css_class('language-choices')
        opzioni.append(scelte_lingua)
        avviso_lingua = Gtk.Label(label='', wrap=True, xalign=0, max_width_chars=30)
        opzioni.append(avviso_lingua)
        preferita = self.config.get('language', 'auto')
        if preferita not in ('it', 'en'):
            preferita = 'auto'
        gruppo = None
        for codice, etichetta in (('auto', 'Auto'), ('it', 'Italiano'), ('en', 'English')):
            scelta = Gtk.ToggleButton(label=etichetta)
            if gruppo is None:
                gruppo = scelta
            else:
                scelta.set_group(gruppo)
            scelta.set_active(codice == preferita)
            if codice == 'auto':
                scelta.set_tooltip_text(tr('Automatica (sistema)'))
            scelta.connect('toggled', lambda widget, lingua=codice:
                self._scegli_lingua(lingua, avviso_lingua) if widget.get_active() else None)
            scelte_lingua.append(scelta)

        dispositivo = next((d for d in self.dispositivi_visualizzati if d[0] == self.dispositivo_audio), None)
        if dispositivo is None:
            opzioni.append(Gtk.Label(label=tr('Seleziona una scheda per vedere informazioni e opzioni.'), wrap=True, max_width_chars=32))
            return
        mac, nome, stato = dispositivo
        titolo = Gtk.Label(label=nome, xalign=0)
        titolo.set_wrap(True)
        titolo.set_max_width_chars(36)
        titolo.add_css_class('heading')
        opzioni.append(titolo)
        presenza = (tr('Rilevato ora') if self.scansione else tr('Rilevato nell’ultima ricerca')) if mac.upper() in self.visti_scansione else tr('Presenza non verificata dalla ricerca')
        dettagli = self._dicitura_dispositivo(stato) + '\n' + presenza + '\n' + mac
        testo_info = Gtk.Label(label=dettagli, xalign=0, wrap=True, selectable=True)
        testo_info.set_focusable(False)
        testo_info.set_max_width_chars(36)
        opzioni.append(testo_info)
        avanzate = Gtk.Expander(label=tr('Avanzate · modalità audio'))
        profili = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        profili.set_margin_top(8)
        for testo, azione in [(tr('Ascolto · A2DP'), 'a2dp'), (tr('Voce e microfono · HFP'), 'hfp')]:
            profilo = PulsanteAttesa(label=testo)
            profilo.connect('clicked', self._memorizza_pulsante)
            profilo.set_sensitive(bool(stato['connected']))
            profilo.connect('clicked', lambda _, a=azione: self._opzione_dispositivo(popover, a, mac, nome))
            profili.append(profilo)
        avanzate.set_child(profili)
        opzioni.append(avanzate)

    def _opzione_dispositivo(self, popover, azione, mac, nome):
        self._azione_scheda(azione, mac, nome)


if __name__ == '__main__':
    ObynApplication().run(None)
