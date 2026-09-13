# OBYN — Only Bluetooth You Need

**Italiano** | [English](README.en.md)

**Autore: Daniele Frasca.**

**Versione di prova 0.1.2 — prototipo funzionante per Arch Linux/KDE.**

OBYN è un gestore Bluetooth grafico autonomo, indipendente da ADA. Usa BlueZ
per i collegamenti e PipeWire/PulseAudio per l’audio. Licenza GPL-3.0-or-later.
Non sostituisce i servizi Bluetooth/audio del sistema.

## Dispositivi

La barra superiore offre ricerca (radar), arresto della ricerca (palmo),
aggiornamento (freccia circolare) e opzioni del dispositivo selezionato
(ingranaggio), più il selettore della tonalità (tavolozza). Nomi e spiegazioni sono disponibili al passaggio del mouse.
La ricerca dura al massimo 30 secondi; distingue rilevamenti attuali da
informazioni salvate. Un dispositivo salvato non è necessariamente raggiungibile.

Seleziona una card con un clic, oppure Invio/Spazio quando ha il focus:
si evidenzia in petrolio e abilita i relativi controlli audio. Le card mostrano
nome, stato, MAC e icona di tipologia, quando BlueZ la fornisce. La spunta
bordata indica associazione e autorizzazione, non la connessione.

Le azioni sulla card permettono di connettere/disconnettere, associare e
autorizzare, scegliere uscita/microfono e dimenticare il dispositivo.
“Associa e autorizza” verifica entrambe le operazioni, senza ripetere
l’associazione se è già presente. “Dimentica” rimuove il dispositivo e nasconde
l’eventuale cache fino alla prossima ricerca esplicita.

“Connetti” cerca prima il dispositivo. Se non lo rileva ma BlueZ conferma
l’associazione, tenta comunque una connessione diretta. Senza associazione e
senza rilevamento non tenta; fermare la ricerca annulla anche il tentativo
successivo. Non rimuove né ripete automaticamente il pairing.

L’interruttore verticale sulla card sceglie il dispositivo da connettere
all’apertura di OBYN: un solo destinatario e un solo tentativo. Non viene
riattivato da aggiornamenti o disconnessioni manuali. Il sistema può comunque
riconnettere autonomamente un auricolare alla sua accensione.

L’ingranaggio mostra nome, servizi dichiarati, presenza osservata e indirizzo
della card selezionata. In “Avanzate” permette di scegliere A2DP/HFP; il backend
usa solo profili realmente disponibili. Senza selezione invita a scegliere
una card. Non apre il mixer esterno.

## Audio e registrazione

Uscita e microfono sono interruttori: verde chiaro significa dispositivo
predefinito e non silenziato, verificato nel server audio. Attivandoli OBYN
memorizza separatamente il precedente dispositivo di uscita e di ingresso.
Disattivandoli ripristina il precedente disponibile, spostando anche i flussi
aperti su quell’endpoint. Lo storico dura fino all’uscita dall’app.

Se manca un precedente disponibile, OBYN silenzia il canale e spegne il
pulsante senza messaggi nel riepilogo. Un nuovo clic lo riattiva. Il dispositivo
può rimanere predefinito ma silenziato. Il microfono prepara HFP se necessario.
Eventuali errori effettivi dei due interruttori rimangono nel log della sessione.

- **REC:** prepara HFP, attende il microfono e registra fino a 10 secondi.
  “Ferma registrazione” termina prima. Non c’è riascolto automatico. Al termine
  tenta di ripristinare il profilo esatto precedente, anche dopo un errore.
- **Riproduci:** ascolta il messaggio registrato sul dispositivo selezionato.
  Prima di tentare una registrazione usa il suono di prova standard. Una
  registrazione fallita non viene sostituita silenziosamente dal suono standard.
- **Salva:** esporta una copia WAV nel percorso scelto; la copia resta sul disco.

Una nuova registrazione sostituisce quella precedente. Il messaggio temporaneo
(`/tmp/obyn-messaggio-…/messaggio.wav`) viene cancellato chiudendo la finestra,
anche se OBYN resta nel tray, oppure uscendo dall’app. La chiusura interrompe
registrazione e riproduzione in corso. Una cattura valida resta salvabile
anche dopo disconnessione o errore di ripristino del profilo.

Se dopo i 10 secondi sono arrivati meno di 8 secondi di audio, OBYN segnala una
cattura incompleta, comunque esportabile. Una registrazione fermata manualmente
prima del limite non è considerata incompleta per la sola durata.

Il volume arriva al 150%. La percentuale segue il cursore; il valore viene
applicato al rilascio, senza ricostruire l’interfaccia durante il trascinamento.
Etichetta e percentuale sono sopra la barra, larga quanto la card al minimo.
Senza volume verificato il controllo è disabilitato e non mostra percentuali.

## Finestra e tray

Le card hanno dimensioni fisse di 300 × 180 pixel logici e scorrono in
orizzontale. Le frecce laterali compaiono soltanto dove è possibile avanzare.
La larghezza minima è 388 pixel: una card e i margini per le frecce. I testi
vanno a capo; l’altezza minima segue il contenuto, senza scroll verticale
della pagina. Dettagli lunghi hanno un proprio scorrimento.

Chiudere la finestra lascia l’app nel tray. “Apri OBYN” la riapre;
“Esci da OBYN” termina app e notifier. I testi copiabili non vengono selezionati
automaticamente alla riapertura. Gli errori conservano dettagli tecnici
copiabili nel log cronologico della sessione.

Il monogramma OBYN usa la palette petrolio, senza logo Bluetooth SIG.
I testi normali usano Adwaita Sans, con fallback Noto Sans/sans-serif.
I caratteri in grassetto conservano l’aspetto corrente; formato e carattere
dell’indirizzo MAC restano invariati.

## Installazione locale e verifica

Ambiente di riferimento: Arch Linux/KDE, BlueZ e PipeWire/WirePlumber attivi.
Dipendenze per app, registrazione e compilazione del notifier:

```bash
sudo pacman -S --needed python python-gobject gtk4 bluez bluez-utils \
  pipewire pipewire-pulse wireplumber libpulse alsa-utils util-linux \
  gcc qt6-base kstatusnotifieritem
bash install-local.sh
```

L’installazione è per l’utente corrente, senza ADA: `~/.local/bin/obyn`,
`~/.local/bin/obyn-tray`, launcher e icone in `~/.local/share`.
La configurazione è in `~/.config/obyn/config.json`. I percorsi rispettano
le variabili XDG usate dagli script. Il launcher usa un percorso assoluto
per funzionare anche se KDE non include `~/.local/bin` nel PATH.

```bash
obyn --version
python3 src/obyn.py
python3 -m py_compile src/obyn.py
python3 -m unittest discover -s tests -v
```

`python3 tests/smoke_dbus.py` usa un bus D-Bus privato simulato; richiede
`dbus-daemon` e socket locali. Non usa il controller reale.

`bash enable-auto-update.sh` attiva un watcher systemd utente che reinstalla
le modifiche locali a Python, C++, launcher e script d’installazione. Non
scarica aggiornamenti e non riavvia OBYN. Per disattivarlo:
`bash disable-auto-update.sh`. Le sole modifiche agli SVG richiedono una
reinstallazione esplicita.

## Stato e limiti

L’utente ha verificato sull’M50 connessione, aggiornamento dopo riaccensione,
registrazione, volume e comportamento degli interruttori; l’ultima conferma
è del 12 settembre 2026. I 151 test automatici coprono backend e coordinamento
con simulazioni, senza garantire compatibilità con ogni hardware.

I problemi dei Nothing ear (1), sospettati difettosi dall’utente, non sono stati
risolti né usati come criterio bloccante. Serve un secondo dispositivo
sicuramente funzionante prima di estendere le garanzie di compatibilità.
Il pacchetto 0.1.2-1 è stato compilato e verificato in un container Arch pulito,
inclusi installazione, aggiornamento da 0.1.1-5, cataloghi e rimozione.
La configurazione di prova è rimasta identica. M50 e cambio tema sono stati
verificati dall’utente anche in una live EndeavourOS KDE con la versione
precedente; lingue e popup sono stati confermati sul profilo di sviluppo.
Altri desktop e hardware restano da verificare. Il gestore Bluetooth completo
di sistema è un’idea rimandata, non una funzione annunciata per questa versione.

OBYN è software libero GPL-3.0-or-later. Vedi [LICENSE](LICENSE).

## Componenti salvati per il riuso

La raccolta autonoma di tredici moduli comprende backend Bluetooth/audio,
componenti grafici e gestione delle lingue, con esempi, test e licenza.
È disponibile come [obyn-components-0.1.2.zip nelle release](https://github.com/colbren15/obyn/releases).
È una copia separata: OBYN non la importa e gli aggiornamenti non si
sincronizzano automaticamente.

## Pacchetto Arch/KDE

Per compilazione, installazione e convivenza con la copia in `~/.local`,
vedi [packaging/arch/README.md](packaging/arch/README.md). Il pacchetto usa
`/usr/bin/obyn`; non rimuove installazioni o configurazioni utente. Le verifiche
locali non sostituiscono i test su una nuova installazione Arch e altro hardware.

### Operazioni in corso

I pulsanti che avviano operazioni bloccanti mostrano quattro pallini verde chiaro
che percorrono il bordo in senso orario: ricerca, aggiornamento, connessione,
disconnessione, associazione/autorizzazione, rimozione, routing, profili audio,
registrazione e riproduzione. Il volume e il dialogo Salva non usano questo
indicatore. I pallini indicano attività, non una percentuale di completamento.
Dopo un timeout di connessione OBYN verifica lo stato fino a cinque volte, con
letture limitate a due secondi, senza ripetere il comando di connessione.
Il timeout resta nello storico tecnico anche se lo stato conferma la connessione.

### Log della sessione

La i accanto a Salva apre un pannello petrolio largo quanto una card,
dall'altezza del MAC al margine inferiore della finestra. Il log resta accessibile
durante le operazioni e raccoglie orario, avvio/fine, cambiamenti Bluetooth/audio,
registrazione, volume, salvataggi ed errori completi. Le letture identiche non
vengono ripetute. Non registra i contenuti audio né salva automaticamente file.
Il testo è selezionabile; “Copia tutto” copia l'intero storico. “Cancella” svuota
il log senza toccare dispositivi o registrazioni; gli eventi successivi continuano
ad essere raccolti. Il log sopravvive alla chiusura nel tray, fino all'uscita
completa dall'app. Risalendo nel testo si sospende lo scorrimento automatico;
tornando in fondo lo si riattiva. Chiudere il pannello con × o Esc.

### Risorse e versione

Il pannello dell'ingranaggio mostra la versione di OBYN. Nel tray le letture
audio periodiche avvengono ogni 15 secondi, anziché ogni 3; riaprendo la finestra
parte subito un aggiornamento. Il monitor Bluetooth resta attivo. Il log carica
il testo nuovo quando viene aperto e registra solo i campi cambiati dopo la prima
fotografia completa dello stato. Nessun evento viene eliminato automaticamente.

### Tonalità del tema

La tavolozza accanto all'ingranaggio apre uno slider con lo spettro dei colori.
La modifica è immediata e mantiene saturazione e luminosità HSL dei colori
originali; layout, font e neutri restano invariati. Card selezionate, bordi,
popup, interruttori, volume attivo e pallini di attività seguono la palette.
Rosso REC, spunta verde di associazione e logo conservano i colori funzionali
o identificativi. “Ripristina petrolio” ripristina esattamente la palette originale.
La scelta viene salvata come `theme_hue` nella configurazione dopo una breve
pausa del cursore e ripristinata all'apertura. Anteprima accorpata ogni 33 ms,
salvataggio dopo 400 ms senza movimenti: nessun timer aggiuntivo quando inattivo.

La modalità chiara/scura ascolta le notifiche del portale desktop. Su KDE
OBYN ricarica anche il file dei colori GTK quando cambia, senza polling o
modifiche alla configurazione del sistema. La tonalità personalizzata rimane
indipendente. La revisione Arch 0.1.1-3 corregge il mancato aggiornamento
del CSS. Il cambio a caldo è stato verificato anche dall’utente nel proprio
profilo KDE; la conferma non si estende agli altri desktop.

## Autore e sostegno al progetto

OBYN è un'app gratuita di Daniele Frasca, distribuita con GPL-3.0-or-later.
Il modello scelto prevede sostegno volontario e personalizzazioni a pagamento.
Per richiedere una personalizzazione: [balthasar2222@gmail.com](mailto:balthasar2222@gmail.com).
Il collegamento è disponibile anche nelle informazioni dell’app e apre il
programma di posta configurato, senza inviare messaggi automaticamente.
[Sostieni OBYN tramite PayPal](https://paypal.me/colbren15df): contributo
volontario, senza importo prestabilito. Il pulsante nelle informazioni apre
la pagina PayPal; non effettua pagamenti automaticamente. Tutte le funzioni
dell’app rimangono disponibili anche senza contribuire.

## Distribuzione pubblica

Repository: [colbren15/obyn](https://github.com/colbren15/obyn).
[Versione di prova Arch 0.1.2-1](https://github.com/colbren15/obyn/releases/tag/v0.1.2-1),
con pacchetto, sorgenti e moduli riutilizzabili. Non pubblicato su AUR.

## Contrasto dei collegamenti

I link di contatto e sostegno mantengono il testo chiaro sulla superficie
del popover anche con accenti del tema di sistema diversi. Il focus resta
visibile e il colore segue la tonalità personalizzata. Correzione inclusa nella versione 0.1.2.

## Lingua dell’app

Italiano e inglese, con rilevamento della lingua del sistema e ripiego inglese
per le lingue non supportate. Nell’ingranaggio puoi scegliere Auto (lingua del sistema),
Italiano o English, anche senza un dispositivo selezionato. La preferenza
si applica dopo Esci da OBYN nel tray e successiva riapertura. Le nuove voci
del log generate dall’app seguono la lingua scelta; risposte esterne, MAC
e nomi dei dispositivi restano originali. I dialoghi GTK di sistema seguono
la lingua del desktop. Le traduzioni sono in po/, manutenzione in po/README.md.
La versione 0.1.2 include questi aggiornamenti.

Il log si chiude anche cliccando nel resto dell’app o passando a un’altra
finestra, senza cancellare gli eventi. Il clic esterno non attiva i controlli
sottostanti. I pulsanti del log condividono l’hover delle impostazioni.

## Indicatore REC — revisione Arch 0.1.2-2

Durante REC la barra del volume mostra il livello del microfono registrato,
con la stessa tonalità del tema. Al termine torna il controllo Volume.
Il livello usa il segnale scritto nel WAV (scala −60..0 dBFS) e può seguire
con un breve ritardo il buffering del registratore. Nessun secondo ingresso
audio viene aperto. Questa aggiunta è inclusa nel pacchetto 0.1.2-2.

L’utente ha confermato installazione, connessioni, registrazione/riascolto e
cambio tema della release 0.1.2-1 anche sul proprio mini PC Manjaro KDE.

Il movimento dell’indicatore è smussato a circa 30 fotogrammi al secondo,
con salita rapida e discesa graduale; le letture audio restano limitate a 10 Hz.
