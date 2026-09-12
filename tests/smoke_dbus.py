# SPDX-License-Identifier: GPL-3.0-or-later
"""Test di integrazione su un bus privato; non usa Bluetooth reale."""
import importlib.util
from pathlib import Path
import threading
import time
from unittest.mock import patch
from gi.repository import Gio, GLib
spec=importlib.util.spec_from_file_location('obyn',Path(__file__).resolve().parents[1] / 'src/obyn.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
bus=Gio.TestDBus.new(Gio.TestDBusFlags.NONE);bus.up()
address=bus.get_bus_address()
flags=Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION
server=Gio.DBusConnection.new_for_address_sync(address,flags,None,None)
server.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','RequestName',GLib.Variant('(su)',('org.bluez',0)),None,Gio.DBusCallFlags.NONE,1000,None)
xml='''<node>
<interface name="org.freedesktop.DBus.ObjectManager"><method name="GetManagedObjects"><arg type="a{oa{sa{sv}}}" direction="out"/></method><signal name="InterfacesAdded"><arg type="o"/><arg type="a{sa{sv}}"/></signal></interface>
<interface name="org.bluez.Adapter1"><method name="SetDiscoveryFilter"><arg type="a{sv}" direction="in"/></method><method name="StartDiscovery"/><method name="StopDiscovery"/></interface>
<interface name="org.freedesktop.DBus.Properties"><method name="Get"><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/></method></interface>
</node>'''
info=Gio.DBusNodeInfo.new_for_xml(xml)
methods=[]
adapter='/org/bluez/hci0'
mac='AA:BB:CC:DD:EE:FF'
def emit():
 server.emit_signal(None,'/','org.freedesktop.DBus.ObjectManager','InterfacesAdded',GLib.Variant('(oa{sa{sv}})',(adapter+'/dev_AA_BB_CC_DD_EE_FF',{'org.bluez.Device1':{'Address':GLib.Variant('s',mac),'Adapter':GLib.Variant('o',adapter),'Name':GLib.Variant('s','Test headset')}})))
 return False
def call(conn,sender,path,iface,method,params,inv):
 methods.append(method)
 if method=='GetManagedObjects':
  inv.return_value(GLib.Variant('(a{oa{sa{sv}}})',({adapter:{'org.bluez.Adapter1':{'Address':GLib.Variant('s','11:22:33:44:55:66'),'Powered':GLib.Variant('b',True)}}},)))
 elif method=='Get': inv.return_value(GLib.Variant('(v)',(GLib.Variant('b',True),)))
 else:
  inv.return_value(GLib.Variant('()',()))
  if method=='StartDiscovery': GLib.timeout_add(100,emit)
ids=[]
for iface in info.interfaces:
 ids.append(server.register_object('/' if iface.name.endswith('ObjectManager') else adapter,iface,call,None,None))
stop=threading.Event();done=threading.Event();snapshots=[];errors=[]
def worker():
 try:
  def progress(devices,seen):
   snapshots.append((devices,seen))
   if mac in seen: stop.set()
  with patch.object(m.Gio,'dbus_address_get_for_bus_sync',return_value=address):
   m.RicercaBluez('11:22:33:44:55:66').esegui(stop,progress,durata=2)
 except Exception as exc: errors.append(str(exc))
 finally: done.set()
thread=threading.Thread(target=worker);thread.start()
ctx=GLib.MainContext.default();deadline=time.monotonic()+5
while not done.is_set() and time.monotonic()<deadline:
 while ctx.pending(): ctx.iteration(False)
 time.sleep(.005)
stop.set()
while not done.is_set() and time.monotonic()<deadline+10:
 while ctx.pending():ctx.iteration(False)
 time.sleep(.005)
thread.join(timeout=1)
for ident in ids:server.unregister_object(ident)
server.close_sync(None)
bus.stop()
assert not errors,errors
assert done.is_set()
assert snapshots and mac in snapshots[-1][1],snapshots
assert methods.count('StartDiscovery')==1 and methods.count('StopDiscovery')==1,methods
print('D-Bus reale isolato: avvio, ricezione dispositivo, stop e cleanup OK')
