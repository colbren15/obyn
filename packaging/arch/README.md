# Pacchetto locale Arch/KDE — OBYN 0.1.1-5

Target x86_64. Il pacchetto include app Python, notifier Qt6/KF6, launcher,
icone, licenza e documentazione. Non contiene configurazioni personali,
registrazioni o moduli riutilizzabili. Non viene avviato automaticamente.

## Preparazione e build

Servono gli strumenti base-devel e le dipendenze dichiarate nel PKGBUILD.
Eseguire makepkg da utente normale, non root:

```bash
python3 packaging/arch/prepare-source.py
cd packaging/arch
SOURCE_DATE_EPOCH=1789171200 makepkg --cleanbuild --force --log
```

`prepare-source.py` usa una lista esplicita di file del repository, controlla
la versione Python, produce un tar.gz deterministico e aggiorna SHA-256 nel
PKGBUILD. Dopo modifiche ai sorgenti o ai documenti inclusi, rigenerarlo.
Non usa una URL pubblica inventata né checksum SKIP. Questa distribuzione è
locale: non è ancora pubblicata in un repository Arch/AUR.

Il pacchetto compilato si trova nella cartella di build, salvo impostazioni
PKGDEST personali; il tar sorgenti e PKGBUILD restano in questa cartella. `makepkg` esegue i test e valida il launcher.


## Installazione e aggiornamento sul sistema

Questi sono comandi da eseguire quando si decide di passare al pacchetto:

```bash
sudo pacman -U obyn-0.1.1-5-x86_64.pkg.tar.zst
```

Lo stesso comando aggiorna un pacchetto già installato. Rimozione:

```bash
sudo pacman -R obyn
```

La rimozione non cancella `~/.config/obyn`, copie WAV esportate o installazioni
in `~/.local`. Non abilitiamo servizi Bluetooth né modifichiamo preferenze audio.
Le normali integrazioni icone/desktop vengono gestite dagli hook della distribuzione.

## Convivenza con l’installazione locale

Il pacchetto installa `/usr/bin/obyn` e `/usr/bin/obyn-tray`. La copia in
`~/.local/bin` e il launcher utente possono avere precedenza. Uscire da OBYN
tramite il tray prima di passare da una copia all’altra. Entrambe leggono
la stessa configurazione utente.

## Verifiche

147 test automatici passati per la revisione 5, costruita sul sistema Arch
di sviluppo. La revisione 1 è stata costruita anche in un container Arch
pulito. Queste verifiche non garantiscono ogni dispositivo o desktop.
I dettagli e i pacchetti sono nelle [release](https://github.com/colbren15/obyn/releases).
