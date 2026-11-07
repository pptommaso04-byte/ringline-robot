#!/usr/bin/env python3
"""Ringline - robot notizie 24/7 (solo libreria standard di Python, nessuna installazione).

Cosa fa, ogni volta che parte:
 1. legge tutti i feed RSS di feeds.json
 2. tiene SOLO: titolo, link, fonte, data (mai l'articolo: copyright)
 3. tiene solo le notizie di boxe, toglie i doppioni
 4. segna ogni notizia: confermata / rumor, e quali pugili cita
 5. scrive data/news.json (il sito legge questo file) e data/log.txt

Uso:  python3 robot.py            (una volta)
      python3 robot.py --loop 60  (ogni 60 minuti, senza fine)
"""
import json, re, sys, time, hashlib, html, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "data"; DATA.mkdir(exist_ok=True)
UA = "RinglineBot/0.1 (news aggregator; titoli e link soltanto; contatto: SCRIVI-QUI-IL-TUO-CONTATTO)"
BOXING = re.compile(r"box|fury|joshua|usyk|inoue|canelo|face[sd]?\b|fight|bout|ko\b|knockout|champion|title|wbc|wba|ibf|wbo|heavyweight|weight|pugil|boxe|boxeo|combat", re.I)
RUMOR = re.compile(r"\b(rumou?r|reportedly|talks?|could|may|set to face|eyeing|targets?|wants?|linked|in negotiation|trattativ|podr[ií]a|según)\b", re.I)
CONFIRMED = re.compile(r"\b(confirmed|official|announced|signed|beats?|defeats?|stops?|wins?|retains?|stripped|ufficial|vince|batte|confirmad)\b", re.I)

def log(msg):
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}"
    print(line)
    with open(DATA / "log.txt", "a", encoding="utf-8") as f: f.write(line + "\n")

def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def text(el, *names):
    for n in names:
        for child in el:
            if child.tag.split("}")[-1] == n and (child.text or child.attrib.get("href")):
                return (child.text or child.attrib.get("href")).strip()
    return ""

def parse(raw, name, lang):
    root = ET.fromstring(raw); out = []
    for it in root.iter():
        if it.tag.split("}")[-1] not in ("item", "entry"): continue
        title = html.unescape(re.sub(r"<[^>]+>", "", text(it, "title"))).strip()
        link = text(it, "link")
        if not link:
            for c in it:
                if c.tag.split("}")[-1] == "link" and c.attrib.get("href"): link = c.attrib["href"]
        date = text(it, "pubDate", "published", "updated", "date")
        try: d = parsedate_to_datetime(date).astimezone(timezone.utc)
        except Exception:
            try: d = datetime.fromisoformat(date.replace("Z", "+00:00"))
            except Exception: d = datetime.now(timezone.utc)
        if title and link:
            out.append({"title": title[:300], "link": link, "source": name, "lang": lang, "date": d.isoformat(timespec="seconds")})
    return out

def classify(n, boxers):
    t = n["title"]
    n["status"] = "rumor" if RUMOR.search(t) and not CONFIRMED.search(t) else ("confirmed" if CONFIRMED.search(t) else "unverified")
    low = t.lower()
    n["boxers"] = [b for b in boxers if b.lower() in low or (len(b.split()[-1]) >= 4 and re.search(r"\b" + re.escape(b.split()[-1].lower()) + r"\b", low))]
    return n

def run(feeds_file="feeds.json", feeds_override=None):
    cfg = json.loads((HERE / feeds_file).read_text(encoding="utf-8"))
    boxers = json.loads((HERE / "boxers.json").read_text(encoding="utf-8")) if (HERE / "boxers.json").exists() else []
    allnews, ok, bad = [], 0, 0
    for f in (feeds_override or cfg["feeds"]):
        try:
            raw = fetch(f["url"]) if not f["url"].startswith("file:") else Path(f["url"][5:]).read_bytes()
            items = parse(raw, f["name"], f.get("lang", "en")); ok += 1
            log(f"OK   {f['name']}: {len(items)} articoli")
            allnews += items
        except Exception as e:
            bad += 1; log(f"FAIL {f['name']}: {type(e).__name__} {e}")
    seen, news = set(), []
    for n in sorted(allnews, key=lambda x: x["date"], reverse=True):
        if not BOXING.search(n["title"]): continue
        k = hashlib.md5(re.sub(r"\W+", "", n["title"].lower()).encode()).hexdigest()
        if k in seen: continue
        seen.add(k); news.append(classify(n, boxers))
    news = news[:300]
    out = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "feeds_ok": ok, "feeds_failed": bad, "news": news}
    (DATA / "news.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"Scritte {len(news)} notizie (feed ok {ok}, falliti {bad})")
    return out

if __name__ == "__main__":
    if "--loop" in sys.argv:
        mins = int(sys.argv[sys.argv.index("--loop") + 1])
        while True:
            try: run()
            except Exception as e: log(f"ERRORE {e}")
            time.sleep(mins * 60)
    else:
        run()
