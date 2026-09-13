# Changelog

## Revisione Arch 0.1.2-2 — 13 settembre 2026

- Indicatore REC del livello microfono, con animazione fluida e ingombro invariato.
- Letture audio limitate a 10 Hz; timer soltanto durante cattura.
- Indicatore e fluidità confermati dall’utente; release precedente verificata su Manjaro KDE.
- Modulo recording aggiornato nella raccolta riutilizzabile 0.1.3.


## 0.1.2 — 13 settembre 2026

Pre-release Arch 0.1.2-1.

- Italiano/inglese con gettext, plurali e preferenza automatica/manuale.
- Tray e nuove descrizioni del log nella lingua dell’app; diagnostica esterna invariata.
- Link del popover leggibili con accenti diversi del tema di sistema.
- README inglese, cataloghi installabili e modulo languages riutilizzabile.
- Chiusura dei pannelli con clic esterno e hover coerente nei pulsanti del log.
- Build Arch pulita: 151 test, cataloghi, aggiornamento e conservazione configurazione.


## 0.1.1 — 12 settembre 2026

- Tema regolabile in tonalità, anteprima e preferenza persistente.
- Log di sessione copiabile e cancellabile, con stati incrementali.
- Indicatori animati sulle operazioni e verifica BlueZ dopo timeout di connessione.
- Riduzione delle letture audio nel tray, cache icone e aggiornamenti log differiti.
- Versione visibile nelle opzioni; layout e font approvati conservati.

Verifiche di release riportate in packaging/arch/VERIFY-0.1.1.txt.

## 0.1.0 — 12 settembre 2026

Prima versione documentata del prototipo OBYN per Arch Linux/KDE.
Non costituisce pubblicazione di un pacchetto distributivo verificato.

- Ricerca BlueZ con presenza osservata, associazione/autorizzazione unificate
  e connessione con ricerca e fallback per dispositivi già associati.
- Aggiornamenti connessione live, tray KDE e riconnessione opzionale all’avvio.
- Schede petrolio, monogramma dedicato, layout fino a una card, opzioni
  contestuali e controlli a icona con descrizioni accessibili.
- Routing uscita/microfono reversibile, fallback silenziamento verificato.
- REC fino a 10s con preparazione HFP e ripristino profilo, riascolto e copia WAV.
- Volume al rilascio senza interruzione del trascinamento, barra full-width.
- Diagnostica copiabile, testi senza selezione automatica, font consolidati.
- `obyn --version`, documentazione corrente separata dalla cronologia.

Verifiche: 127 test simulati, compilazione Python, anteprime GTK e riscontri
utente sull’M50. Restano packaging riproducibile e secondo hardware affidabile.

### Revisione Arch 0.1.1-2

- Segue i cambiamenti chiaro/scuro del portale desktop senza riavvio o polling.
- Mantiene la tonalità scelta e le configurazioni GTK degli utenti.

### Revisione Arch 0.1.1-3

- Ricarica colors.css di KDE su notifica del filesystem: evita colori rimasti
  in cache fino al riavvio. Debounce150ms, mantiene CSS valido su scrittura
  incompleta, libera monitor e provider all'uscita.
- Test integrato con configurazione temporanea, Broadway e bus D-Bus privato.

### Revisione Arch 0.1.1-4

- Attribuzione a Daniele Frasca nei sorgenti e nel pannello informazioni.
- AUTHORS.md incluso nel pacchetto e nell'archivio sorgenti.

### Revisione Arch 0.1.1-5

- Collegamenti nelle informazioni per personalizzazioni via email e sostegno
  volontario tramite PayPal.Me, disponibili anche senza scheda selezionata.
