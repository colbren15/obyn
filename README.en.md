# OBYN — Only Bluetooth You Need

[Italiano](README.md) | **English**

**Author: Daniele Frasca. GPL-3.0-or-later.**

OBYN is a standalone Bluetooth manager for Linux, currently developed and
manually tested on Arch/KDE and an EndeavourOS KDE live session with an M50
headset. It uses BlueZ and PipeWire/WirePlumber; it does not replace them.

Version 0.1.2 is a pre-release. It includes Italian/English, improved link
contrast and consistent popup dismissal. The Arch 0.1.2-1 package was built
and checked in a clean container, including upgrade from 0.1.1-5 and
preservation of a test configuration. Hardware coverage remains limited.

## Using OBYN

Search for devices with the radar button, then pair/connect a device.
Select its card to use the recording and volume controls. The speaker and
microphone buttons select that device as the default; switching them off
restores the previous available endpoint or mutes when none is available.
The vertical switch selects one device for a single connection attempt at
startup. Connection status is verified through the system services.

REC sets up the microphone automatically and records up to ten seconds.
Play replays the recording; Save exports a copy. Recordings are temporary
until exported. The information button opens a copyable, clearable session
log. The gear opens device options and language preferences. The palette
button changes hue while preserving the palette's saturation/lightness.

Language defaults to the system setting, with English for unsupported
languages. Choose Auto (system), Italiano or English in the gear menu. Quit
OBYN from the tray and reopen it to apply the preference. This avoids
interrupting active operations. Newly generated log descriptions use the
selected language; raw external diagnostics, addresses and device names
remain unchanged. GTK's own dialogs follow the desktop language.

## Install from source (Arch/KDE)

```bash
sudo pacman -S --needed python python-gobject gtk4 bluez bluez-utils \
  pipewire pipewire-pulse wireplumber libpulse alsa-utils util-linux \
  gcc qt6-base kstatusnotifieritem gettext
bash tools/compile-translations.sh
bash install-local.sh
```

This installs to your user directories. A user installation may take
precedence over `/usr/bin/obyn` and the system desktop entry. Configuration
uses `$XDG_CONFIG_HOME/obyn/config.json` (default `~/.config/obyn/config.json`).

Run automated tests with `python3 -m unittest discover -s tests`.
GTK smoke tests require a private session bus and Broadway; they use
simulated devices. Passing tests is not a guarantee for all hardware.
For building an Arch package, see `packaging/arch/README.md`.
For translation maintenance, see `po/README.md`.

## Downloads and support

[Source repository](https://github.com/colbren15/obyn) ·
[Pre-releases](https://github.com/colbren15/obyn/releases)

The app is free, with all features available. You can provide
[voluntary support](https://paypal.me/colbren15df) or
[email a paid customization request](mailto:balthasar2222@gmail.com).
No payment or message is sent automatically. Not published on AUR yet.

Reusable components are available as `obyn-components-0.1.2.zip` in the release.
Extract the collection into `reusable/obyn-components` to run the optional
link-contrast smoke test, which also checks the reusable author header.

## REC level meter — Arch revision 0.1.2-2

During recording, the volume bar becomes a microphone level meter using the
current theme color, then returns to the volume control. It reads recorded
PCM from the WAV file on a −60..0 dBFS scale, subject to recorder buffering,
without opening another audio stream. Included in package 0.1.2-2.
The user also confirmed 0.1.2-1 installation, connections, recording/playback
and theme switching on their Manjaro KDE mini PC.

The meter animates at approximately 30 frames per second, with fast attack
and gradual release; audio reads remain limited to 10 Hz.
