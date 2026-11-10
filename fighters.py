#!/usr/bin/env python3
"""Ringline - storico incontri dei pugili (solo libreria standard di Python).

Cosa fa:
 1. per ogni pugile in fighters.json legge la tabella degli incontri su Wikipedia (inglese)
 2. la controlla con un'altra lingua di Wikipedia (italiano o spagnolo)
 3. un incontro e' "verificato" (check) se compare uguale in 2 fonti (stessa data + stesso avversario)
 4. se due fonti dicono cose diverse sullo stesso incontro: segnato "da verificare"
 5. scrive data/fighters/<nome>.json e data/fighters/index.json (il sito li legge)

NON usa BoxRec (vieta di copiare i dati). Wikipedia: testo sotto licenza CC BY-SA,
il sito deve scrivere "Fonte: Wikipedia" accanto allo storico.

Ogni giro del robot aggiorna al massimo pochi pugili (i piu' vecchi), per non stressare Wikipedia.
"""
import json, re, html, time, unicodedata, urllib.request, urllib.parse
from html.parser import HTMLParser
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
UA = "RinglineBot/0.1 (https://github.com/pptommaso04-byte/ringline-robot; public boxing facts, small volume)"

MONTHS = {}
for lang, names in {
    "en": "january february march april may june july august september october november december",
    "it": "gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre dicembre",
    "es": "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre",
    "fr": "janvier février mars avril mai juin juillet août septembre octobre novembre décembre",
    "de": "januar februar märz april mai juni juli august september oktober november dezember",
    "pt": "janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro",
}.items():
    for i, m in enumerate(names.split(), 1):
        MONTHS[m] = i
        MONTHS[m[:3]] = i
MONTHS["sept"] = 9; MONTHS["mär"] = 3; MONTHS["févr"] = 2
MONTHS["set"] = 9   # it: set
MONTHS["ago"] = 8   # it/es: ago

HEAD = {
    "opp": ("opponent", "avversario", "oponente", "rival", "adversaire", "adversário", "adversario", "gegner"),
    "res": ("result", "risultato", "resultado", "résultat", "ergebnis"),
    "type": ("type", "method", "metodo", "método", "tipo", "méthode", "methode", "art"),
    "round": ("round", "ronda", "riprese", "time", "runde", "rodada", "tour"),
    "date": ("date", "data", "fecha", "datum"),
    "loc": ("location", "luogo", "lugar", "venue", "sede", "lieu", "ort", "local"),
    "notes": ("notes", "note", "notas", "anmerkungen", "bemerkungen"),
    "rec": ("record", "récord", "bilancio"),
    "no": ("no.", "n°", "nº", "n.", "#", "no"),
}


def slug(name):
    s = unicodedata.normalize("NFD", name)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


# ---------- lettura tabelle HTML (solo stdlib) ----------
class TableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []; self._t = None; self._row = None; self._cell = None; self._skip = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            self._t = []
        elif tag == "tr" and self._t is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag in ("style", "script"):
            self._skip += 1
        elif tag == "sup" and "reference" in (a.get("class") or ""):
            self._skip += 1
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip()); self._cell = None
        elif tag == "tr" and self._row is not None and self._t is not None:
            if self._row: self._t.append(self._row)
            self._row = None
        elif tag == "table" and self._t is not None:
            self.tables.append(self._t); self._t = None
        elif tag in ("style", "script") or tag == "sup":
            if self._skip: self._skip -= 1

    def handle_data(self, d):
        if self._cell is not None and not self._skip:
            self._cell.append(d)


def col_map(header):
    m = {}
    for i, h in enumerate(header):
        hl = h.lower().strip()
        for key, words in HEAD.items():
            if key in m: continue
            if any(hl == w or (len(w) > 3 and w in hl) for w in words):
                m[key] = i
    return m


def parse_date(s):
    s = (s or "").strip().lower()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m: return "%s-%s-%s" % m.groups()
    y = re.search(r"\b(19|20)\d{2}\b", s)
    if not y: return ""
    year = int(y.group(0))
    mon = None
    for w in re.findall(r"[a-zà-ú]+", s):
        if w in MONTHS: mon = MONTHS[w]; break
    d = re.search(r"\b(\d{1,2})\b", re.sub(r"\b(19|20)\d{2}\b", "", s))
    if not (mon and d): return "%04d" % year
    return "%04d-%02d-%02d" % (year, mon, int(d.group(1)))


def norm_result(s):
    t = norm(s)
    if t.startswith(("win", "vitt", "victoria", "victoire", "sieg", "vitoria", "w ")) or t == "w": return "W"
    if t.startswith(("loss", "sconf", "derrota", "defaite", "niederlage", "l ")) or t == "l": return "L"
    if t.startswith(("draw", "pareg", "empate", "match nul", "unentschieden", "d ")) or t == "d": return "D"
    if t.startswith(("nc", "no contest", "no cont", "senza")): return "NC"
    return ""


def clean(s):
    return re.sub(r"\[\w+\]|\s+", " ", s or "").strip()


def parse_fights(page_html):
    p = TableParser(); p.feed(page_html)
    best = []
    for t in p.tables:
        if len(t) < 3: continue
        hi = None
        for i, row in enumerate(t[:3]):
            cm = col_map(row)
            if "opp" in cm and "res" in cm and "date" in cm: hi = i; break
        if hi is None: continue
        cm = col_map(t[hi]); fights = []
        for row in t[hi + 1:]:
            if len(row) <= max(cm.values()): continue
            r = norm_result(row[cm["res"]])
            if not r: continue
            f = {"result": r, "opponent": clean(row[cm["opp"]]), "date": parse_date(row[cm["date"]])}
            for k in ("type", "round", "loc", "notes"):
                f[k] = clean(row[cm[k]]) if k in cm and cm[k] < len(row) else ""
            if "no" in cm and cm["no"] < len(row) and row[cm["no"]].strip().isdigit(): f["n"] = int(row[cm["no"]])
            fights.append(f)
        if len(fights) > len(best): best = fights
    return best


def wiki_html(lang, title):
    u = "https://%s.wikipedia.org/w/api.php?action=parse&prop=text&format=json&formatversion=2&redirects=1&disableeditsection=1&page=%s" % (lang, urllib.parse.quote(title.replace(" ", "_")))
    j = json.loads(fetch(u))
    if "parse" not in j: raise ValueError(j.get("error", {}).get("code", "nopage"))
    return j["parse"]["text"]


def wiki_search(lang, name):
    u = "https://%s.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit=1&srsearch=%s" % (lang, urllib.parse.quote(name + " boxer"))
    j = json.loads(fetch(u)); hits = j.get("query", {}).get("search", [])
    return hits[0]["title"] if hits else None


def get_fights(lang, name, title=None):
    for tt in [title or name, None]:
        try:
            if tt is None:
                tt = wiki_search(lang, name)
                if not tt: return [], None
            fights = parse_fights(wiki_html(lang, tt))
            if fights: return fights, tt
        except Exception:
            continue
    return [], None


# ---------- controllo incrociato ----------
def same_opp(a, b):
    a, b = norm(a), norm(b)
    if not a or not b: return False
    la, lb = a.split()[-1], b.split()[-1]
    return a == b or la == lb or a in b or b in a


def cross_check(primary, others):
    """primary: lista incontri (en). others: {lang: lista}. Aggiunge verified / src / conflict."""
    for f in primary:
        f["src"] = ["en"]; f["verified"] = False; f["conflict"] = False
        for lang, lst in others.items():
            for g in lst:
                if g["date"] and g["date"] == f["date"] and same_opp(g["opponent"], f["opponent"]):
                    f["src"].append(lang)
                    if g["result"] != f["result"]: f["conflict"] = True
                    break
        f["verified"] = len(f["src"]) >= 2 and not f["conflict"]
    return primary


def build(entry):
    name = entry["name"]; w = entry.get("wiki", {})
    prim, ptitle = get_fights("en", name, w.get("en"))
    if not prim: return None
    others = {}
    for lang in ("it", "es", "fr", "de", "pt"):
        lst, tt = get_fights(lang, name, w.get(lang))
        if lst: others[lang] = lst
    fights = cross_check(prim, others)
    if not any(f.get("n") for f in fights):
        for i, f in enumerate(reversed(fights), 1): f["n"] = i
    rec = {"w": 0, "l": 0, "d": 0, "nc": 0}
    for f in fights:
        rec[{"W": "w", "L": "l", "D": "d", "NC": "nc"}[f["result"]]] += 1
    return {"name": name, "slug": slug(name), "wiki_title": ptitle, "langs": ["en"] + list(others),
            "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "record": rec, "total": len(fights), "verified": sum(1 for f in fights if f["verified"]),
            "conflicts": sum(1 for f in fights if f["conflict"]),
            "source": "Wikipedia, varie lingue (CC BY-SA)", "fights": fights}


def run_step(data_dir, log, limit=5, max_age_h=20, budget_s=150):
    """Aggiorna al massimo `limit` pugili, i piu' vecchi o mai letti."""
    cfgp = HERE / "fighters.json"
    if not cfgp.exists(): return
    cfg = json.loads(cfgp.read_text(encoding="utf-8"))
    out = Path(data_dir) / "fighters"; out.mkdir(parents=True, exist_ok=True)
    ip = out / "index.json"
    try: index = json.loads(ip.read_text(encoding="utf-8"))
    except Exception: index = {}
    now = datetime.now(timezone.utc)

    def age(e):
        ent = index.get(e["name"], {})
        us = [x for x in (ent.get("updated"), ent.get("tried")) if x]
        if not us: return 1e9
        return (now - datetime.fromisoformat(max(us))).total_seconds() / 3600
    base = [e for e in cfg["fighters"] if age(e) >= max_age_h]
    base.sort(key=age, reverse=True)
    # pugili dall'elenco Wikidata: prima quelli citati nelle notizie, poi i campioni, poi i piu' giovani
    extra = []
    try:
        import roster
        ro = roster.ensure(data_dir, log)
        have = {e["name"] for e in cfg["fighters"]}
        champs = set(ro.get("champs", []))
        try: titles = " ".join(n.get("title", "") for n in json.loads((Path(data_dir) / "news.json").read_text(encoding="utf-8")).get("news", [])).lower()
        except Exception: titles = ""
        def prio(b):
            sur = b["name"].split()[-1].lower()
            in_news = len(sur) >= 4 and re.search(r"\b" + re.escape(sur) + r"\b", titles) is not None
            return (0 if in_news else 1, 0 if b["name"] in champs else 1, -int((b.get("born") or "1970")[:4]))
        for b in sorted(ro.get("boxers", []), key=prio):
            if b["name"] in have: continue
            e = {"name": b["name"], "wiki": {"en": b["name"]}}
            ent = index.get(b["name"], {})
            us = [x for x in (ent.get("updated"), ent.get("tried")) if x]
            hrs = (now - datetime.fromisoformat(max(us))).total_seconds() / 3600 if us else 1e9
            # chi non ha tabella: riprova dopo 30 giorni; chi ha dati: aggiorna ogni 3 giorni
            if hrs >= (720 if (ent and not ent.get("slug")) else (72 if ent else 0)):
                extra.append(e)
            if len(extra) >= limit: break
    except Exception as ex:
        log(f"ROSTER ERRORE {type(ex).__name__} {ex}")
    todo = (base + extra)[:limit]
    t0 = time.time(); done = 0
    for e in todo:
        if time.time() - t0 > budget_s: break
        try:
            d = build(e)
        except Exception as ex:
            d = None; log(f"STORICO FAIL {e['name']}: {type(ex).__name__} {ex}")
        if d:
            (out / (d["slug"] + ".json")).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            index[e["name"]] = {"slug": d["slug"], "updated": d["updated"], "total": d["total"],
                                "verified": d["verified"], "record": d["record"], "langs": d["langs"]}
            log(f"STORICO OK   {e['name']}: {d['total']} incontri, {d['verified']} verificati ({'+'.join(d['langs'])})")
            done += 1
        else:
            prev = index.get(e["name"], {})
            prev["tried"] = now.isoformat(timespec="seconds"); index[e["name"]] = prev
            log(f"STORICO NO   {e['name']}: tabella non trovata")
        time.sleep(1)
    ip.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"Storico: aggiornati {done} pugili, in elenco {len(cfg['fighters'])}+{len(extra)} dall'elenco Wikidata, con dati {sum(1 for v in index.values() if v.get('slug'))}")
