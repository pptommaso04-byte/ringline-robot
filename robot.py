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
import json, re, sys, time, hashlib, html, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "data"; DATA.mkdir(exist_ok=True)
UA = "Mozilla/5.0 (compatible; RinglineBot/0.1; news aggregator, titles and links only)"
BOXING = re.compile(r"box|fury|joshua|usyk|inoue|canelo|face[sd]?\b|fight|bout|ko\b|knockout|champion|title|wbc|wba|ibf|wbo|heavyweight|weight|pugil|boxe|boxeo|combat", re.I)
RUMOR = re.compile(r"\b(rumou?r|reportedly|talks?|could|may|set to face|eyeing|targets?|wants?|linked|in negotiation|trattativ|podr[ií]a|según)\b", re.I)
CONFIRMED = re.compile(r"\b(confirmed|official|announced|signed|beats?|defeats?|stops?|wins?|retains?|stripped|ufficial|vince|batte|confirmad)\b", re.I)

def log(msg):
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}"
    print(line)
    with open(DATA / "log.txt", "a", encoding="utf-8") as f: f.write(line + "\n")

def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/xml, */*", "Accept-Language": "en-US,en;q=0.9", "Referer": "https://www.google.com/"})
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

def _google(text, tl):
    u = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=%s&dt=t&q=%s" % (tl, urllib.parse.quote(text))
    j = json.loads(fetch(u, timeout=15).decode("utf-8"))
    return "".join(p[0] for p in j[0] if p and p[0]).strip()

def _mymemory(text, tl):
    u = "https://api.mymemory.translated.net/get?langpair=en|%s&q=%s" % (tl, urllib.parse.quote(text))
    j = json.loads(fetch(u, timeout=15).decode("utf-8"))
    r = j["responseData"]["translatedText"].strip()
    if not r or "MYMEMORY WARNING" in r.upper(): raise ValueError("limite")
    return html.unescape(r)

def translate(text, tl):
    """Traduce un titolo (automatico). Prova due servizi gratuiti; se falliscono torna None."""
    for fn in (_google, _mymemory):
        try:
            r = fn(text, tl)
            if r and r.lower() != text.lower(): return r
            if r: return r
        except Exception: pass
    return None

def add_translations(news, limit=40):
    """Riusa le traduzioni gia' fatte (lette dal news.json precedente) e traduce solo le nuove."""
    old = {}
    try:
        for o in json.loads((DATA / "news.json").read_text(encoding="utf-8")).get("news", []):
            old[o["link"]] = o
    except Exception: pass
    done = fail = 0
    for n in news:
        o = old.get(n["link"], {})
        for tl in ("it", "es"):
            if n.get("lang") == tl: n["title_" + tl] = n["title"]; continue
            if o.get("title_" + tl): n["title_" + tl] = o["title_" + tl]; continue
            if done >= limit: continue
            r = translate(n["title"], tl)
            if r: n["title_" + tl] = r; done += 1
            else: fail += 1
    log(f"Traduzioni nuove {done}, non riuscite {fail}")

STARS = ["Oleksandr Usyk","Tyson Fury","Anthony Joshua","Naoya Inoue","Canelo","Terence Crawford","Gervonta Davis","Devin Haney","Ryan Garcia","Jaron Ennis","Dmitry Bivol","Artur Beterbiev","David Benavidez","Deontay Wilder","Daniel Dubois","Joseph Parker","Vasiliy Lomachenko","Jesse Rodriguez","Junto Nakatani","Katie Taylor","Amanda Serrano","Claressa Shields","Bakhram Murtazaliev","Jermall Charlo","Errol Spence","Keith Thurman","Shakur Stevenson","Teofimo Lopez","Jake Paul","Moses Itauma","Zurdo Ramirez","Christian Mbilli","Diego Pacheco","Callum Smith","Conor Benn","Chris Eubank","Hamzah Sheeraz","Janibek Alimkhanuly","Denzel Bentley","Joshua Buatsi","Willy Hutchinson","Fundora","Navarrete","Tszyu","Whyte","Chisora","Usyk","Inoue","Beterbiev","Bivol","Benavidez","Itauma","Dubois","Crawford","Haney","Stevenson","Pacheco","Zhilei Zhang","Hrgovic","Jarrell Miller"]
KEYS = [(re.compile(r"undisputed|unif(y|ied|ication)|mega.?fight|super.?fight|pound.for.pound"), 18),
        (re.compile(r"world title|world champion|heavyweight|stripped|vacant|ordered|mandatory|purse|signed|confirmed|official|announced"), 10),
        (re.compile(r"\b(wbc|wba|ibf|wbo|ring magazine)\b"), 10),
        (re.compile(r"beats?|defeats?|stops?|knocks? out|retains?|wins?|loses?|upset|ko\b|tko\b"), 8),
        (re.compile(r"weigh.?in|workout|training camp|sparring|instagram|tiktok|reaction|\bwatch\b|\bphotos?\b|\bvideo\b"), -10)]

def score_news(news):
    toks = []
    for n in news:
        toks.append(set(w for w in re.findall(r"[A-Z][a-zA-Z\-']{3,}", n["title"])))
    now = datetime.now(timezone.utc)
    for i, n in enumerate(news):
        low = n["title"].lower(); sc = 0
        stars = [a for a in STARS if re.search(r"\b" + re.escape(a.lower()) + r"\b", low)]
        sc += min(45, 25 * len(stars)) if stars else 0
        sc += 10 * bool(n.get("boxers"))
        for rx, pts in KEYS:
            if rx.search(low): sc += pts
        same = {n["source"]}
        for j, m in enumerate(news):
            if j != i and len(toks[i] & toks[j]) >= 2: same.add(m["source"])
        sc += min(30, 10 * (len(same) - 1))
        try: hrs = (now - datetime.fromisoformat(n["date"])).total_seconds() / 3600
        except Exception: hrs = 99
        sc += max(0, 30 - hrs / 2)
        n["score"] = int(max(0, sc)); n["sources_n"] = len(same)
    return news

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
    score_news(news)
    add_translations(news)
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
