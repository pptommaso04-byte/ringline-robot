# Robot Ringline – come funziona

## Cosa fa (ogni ora, da solo)
1. Legge i feed RSS in `feeds.json` (giornali, TV, siti di boxe).
2. Salva SOLO titolo, link, fonte e data. Mai l'articolo (copyright).
3. Tiene le notizie di boxe, toglie i doppioni.
4. Segna: confermata / rumor / da verificare, e i pugili citati (`boxers.json`).
5. Scrive `data/news.json` (lo legge il sito) e `data/log.txt` (quali feed funzionano).

## Provarlo
    python3 robot.py              # una volta
    python3 robot.py --loop 60    # ogni 60 minuti, senza fine

## Attivazione su hosting (la facciamo insieme)
- Serve un hosting con Python e "cron" (pianificatore).
- Riga cron, ogni ora:  `0 * * * * cd /percorso/robot && python3 robot.py`
- Prima di attivarlo: scrivi un contatto vero nella riga `UA` di robot.py.
- Dopo il primo giro apri `data/log.txt`: i feed con FAIL li sistemo io.

## Orari
`tz.py` converte da ora locale a Italia, UK, New York, Los Angeles.
Esempio: `python3 tz.py`.

## Stato onesto
- Testato qui solo con un feed di prova: da qui internet è limitato.
- I link dei feed vanno verificati sull'hosting.
- NON ancora fatti: storico incontri (Wikipedia/Wikidata, permesso e gratis), orari dai promoter, YouTube API. X più avanti.
