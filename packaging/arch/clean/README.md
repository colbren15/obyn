# Verifica Arch pulita con Podman rootless

Usa l'immagine ufficiale Arch base-devel e un database pacman separato.
Lo script `build-inside.sh` rifiuta l'esecuzione fuori da un container.
Immagine verificata il 12 settembre 2026:

`docker.io/library/archlinux@sha256:5b987b0196907ea97dd10e7b48e7d403c35c0389986da015aa86cf8d0b058084`

Origine: https://hub.docker.com/_/archlinux/

## Ripetizione

Richiede Podman rootless funzionante (subuid/subgid configurati), rete e spazio
per alcuni GB di immagine e dipendenze. Preparare prima il tar con `python3 packaging/arch/prepare-source.py` e
aggiornare `.SRCINFO` con `makepkg --printsrcinfo` dalla cartella della ricetta.
Poi, dalla radice del progetto:

```bash
work=$(mktemp -d /tmp/obyn-clean-arch.XXXXXX)
mkdir -p "$work/storage" "$work/run"
podman --root "$work/storage" --runroot "$work/run" --storage-driver vfs \
  run --name obyn-clean-build --hostname obyn-clean \
  --volume "$PWD/packaging/arch:/input:ro" \
  docker.io/library/archlinux@sha256:5b987b0196907ea97dd10e7b48e7d403c35c0389986da015aa86cf8d0b058084 \
  bash /input/clean/build-inside.sh > "$work/build.log" 2>&1
mkdir -p "$work/results"
podman --root "$work/storage" --runroot "$work/run" --storage-driver vfs \
  cp obyn-clean-build:/results/. "$work/results/"
```

Lo script inizializza le chiavi Arch, aggiorna il container e installa solo le
dipendenze dichiarate, oltre a quelle già incluse in base-devel. Compila da
utente builder non privilegiato, esegue i test della versione corrente e installa/reinstalla/rimuove
con pacman senza -dd o soppressione degli hook. Verifica import GTK, versione,
launcher, file e librerie del notifier. Non avvia la finestra o i backend reali.

Non monta home, dispositivi Bluetooth, socket audio o display dell'host.
Il repository è montato in sola lettura. Nessuna modifica a pacman dell'host.
Le dipendenze Arch rolling vengono aggiornate con -Syu: il digest blocca
l'immagine iniziale, non le successive versioni dei repository. La lista
`packages-before-build.txt` registra esattamente l'ambiente effettivo.

## Stato e pulizia

I risultati sono nella cartella temporanea scelta da `mktemp`; salvarli prima
del riavvio, perché `/tmp` può essere svuotata.
Per liberare i dati temporanei dopo aver recuperato risultati e log:

```bash
podman --root "$work/storage" --runroot "$work/run" --storage-driver vfs \
  rm obyn-clean-build
podman --root "$work/storage" --runroot "$work/run" --storage-driver vfs \
  rmi docker.io/library/archlinux@sha256:5b987b0196907ea97dd10e7b48e7d403c35c0389986da015aa86cf8d0b058084
```

Usare il valore work della propria sessione. Non usare reset globali di Podman.

È un container pulito, non il clean chroot di devtools o una VM con KDE.
Condivide il kernel dell'host. Questa verifica non copre un login grafico,
Bluetooth reale, audio reale o un secondo adattatore. Il pacchetto non è firmato né pubblicato in un repository.


## Aggiornamento da una versione precedente

Per includere la verifica di upgrade, aggiungere al comando run:
`--volume "$PWD/dist/obyn-0.1.1-5-x86_64.pkg.tar.zst:/previous/old.pkg.tar.zst:ro`.
Usare un nome container libero. Lo script legge la versione da .SRCINFO,
installa il vecchio pacchetto, crea una configurazione sintetica e verifica
identità del file e lettura delle preferenze nella nuova versione. La configurazione
è verificata anche dopo reinstallazione/rimozione. Non monta la home utente.
La verifica 0.1.1-5 → 0.1.2-1 è passata il 13 settembre 2026.
Verificati anche i cataloghi italiano/inglese installati.
