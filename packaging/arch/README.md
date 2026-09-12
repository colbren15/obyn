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

Il pacchetto compilato si trova in `dist/` nel progetto; il tar sorgenti e
PKGBUILD restano in questa cartella. `makepkg` esegue i test e valida il launcher.
`VERIFY.txt` riporta le verifiche effettivamente completate e i loro limiti.

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

```bash
bash packaging/arch/check-installation.sh
```

- Il pacchetto installa `/usr/bin/obyn` e `/usr/bin/obyn-tray`; il launcher
  pacchettizzato usa esplicitamente `/usr/bin/obyn`.
- La copia in `~/.local/bin` non viene rimossa. Può avere precedenza nel PATH.
- Il launcher utente con lo stesso desktop ID ha precedenza su quello globale;
  finché esiste può continuare ad aprire la copia locale dal menu applicazioni.
- App e tray individuano l’eseguibile affiancato: non mischiano il notifier
  locale con quello pacchettizzato. Il desktop ID condiviso rende l’app
  a istanza unica: uscire completamente dal tray prima di cambiare copia.
- Entrambe le copie leggono la stessa configurazione utente. Per migrare,
  disabilitare il watcher locale con `disable-auto-update.sh`, quindi spostare
  in backup i due eseguibili e il launcher utente prima di usare la copia globale.
  Valutare anche le icone utente, che hanno precedenza su quelle globali.
  La procedura non viene eseguita automaticamente dal pacchetto.

## Test isolato delle transazioni

```bash
bash packaging/arch/test-package.sh /percorso/obyn-0.1.1-5-x86_64.pkg.tar.zst
```

Crea una radice e un database pacman temporanei tramite fakeroot: installa,
reinstalla come aggiornamento e rimuove, controllando i file e preservando una
configurazione utente fittizia. Il controllo dipendenze e gli scriptlet sono disabilitati, la radice
non contiene gli hook di sistema: non è una VM, un chroot completo né una verifica dell’avvio grafico
su una nuova installazione. Il database del sistema resta intatto.

Prima della distribuzione ampia restano build in clean chroot Arch, avvio GUI
su una sessione dedicata e verifica con secondo dispositivo affidabile.

Con fakeroot alcune versioni di pacman/libarchive possono segnalare che non
possono assegnare proprietario root ai file: è un limite della simulazione
non privilegiata. I proprietari registrati nel pacchetto sono controllati
separatamente; il test non dimostra una vera installazione eseguita da root.

## Verifica successiva in Arch pulito

Completata in container rootless da immagine ufficiale Arch base-devel:127 test,
installazione con dipendenze e import del backend, reinstallazione e rimozione.
Risultati in `dist/clean-arch/VERIFY.txt`; procedura in [clean/README.md](clean/README.md).
Il precedente test fakeroot rimane distinto. Non è una verifica grafica o hardware.

## Release 0.1.1

Rapporto corrente: [VERIFY-0.1.1.txt](VERIFY-0.1.1.txt).
La verifica storica 0.1.0 resta in VERIFY.txt e dist/clean-arch.
Checklist sessione grafica: [PROVA_KDE_0.1.1.md](../../docs/PROVA_KDE_0.1.1.md).
