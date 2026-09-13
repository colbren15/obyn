# Traduzioni OBYN

Messaggi sorgente in italiano; catalogo inglese gettext. I file PO sono
modificabili con un editor o Poedit; i MO sono compilati e installabili.

```bash
bash tools/update-translations.sh
# Tradurre po/en.po, controllare eventuali voci fuzzy.
bash tools/compile-translations.sh
```

`tr()` traduce messaggi completi prima di `.format(...)`; non tradurre MAC,
UUID, nomi dispositivi, chiavi dei comandi o risposte originali BlueZ/PipeWire.
I segnaposto `{v0}`, `{count}` ecc. devono essere conservati. `ngettext()`
gestisce singolare/plurale; zero usa il plurale in italiano e inglese.

La preferenza `language` può essere auto/it/en. Si applica al prossimo avvio
completo (uscita dal tray), non alla sola riapertura della finestra nascosta.
Auto rispetta LC_ALL, LC_MESSAGES, LANG e LANGUAGE, con ripiego inglese
per lingue non supportate. Senza catalogo valido si ripiega sui messaggi
sorgente italiani; `catalog_loaded` permette di rilevare questa condizione.
I dialoghi nativi GTK seguono la lingua del desktop.

Per aggiungere una lingua estendere LanguageManager.supported, le opzioni
nel menu e gli script di compilazione/installazione, creare il relativo PO
con la corretta Plural-Forms, poi verificare testi e layout. Il modulo
riutilizzabile è obyn_components.languages: non dipende da GTK o OBYN.
