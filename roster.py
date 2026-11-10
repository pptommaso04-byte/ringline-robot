"""Elenco di tutti i pugili (Wikidata, dati liberi CC0) + campioni attuali (Wikipedia, CC BY-SA).
Si aggiorna una volta a settimana. Scrive data/roster.json."""
import json, re, time, html, urllib.request, urllib.parse
from datetime import datetime, timezone
from pathlib import Path

UA = "RinglineBot/0.1 (https://github.com/pptommaso04-byte/ringline-robot; public boxing facts, small volume)"
SPARQL = """
SELECT ?p (SAMPLE(?en) AS ?title) (MIN(?b) AS ?born) (SAMPLE(?g) AS ?gender) (SAMPLE(?cl) AS ?country) WHERE {
  ?p wdt:P106 wd:Q11338576 .
  ?a schema:about ?p ; schema:isPartOf <https://en.wikipedia.org/> ; schema:name ?en .
  ?p wdt:P569 ?b . FILTER(?b >= "1970-01-01T00:00:00Z"^^xsd:dateTime)
  OPTIONAL { ?p wdt:P21 ?g }
  OPTIONAL { ?p wdt:P27 ?c . ?c rdfs:label ?cl . FILTER(LANG(?cl) = "en") }
} GROUP BY ?p
"""
CHAMP_PAGES = ["List_of_current_world_boxing_champions", "List_of_female_boxers"]


def _get(url, timeout=90, accept="application/json"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def fetch_roster():
    u = "https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(SPARQL)
    rows = json.loads(_get(u, timeout=100, accept="application/sparql-results+json"))["results"]["bindings"]
    out = []
    for r in rows:
        v = lambda k: r.get(k, {}).get("value", "")
        title = v("title").strip()
        if not title: continue
        g = v("gender").rsplit("/", 1)[-1]
        out.append({"name": title, "qid": v("p").rsplit("/", 1)[-1], "born": v("born")[:10],
                    "country": v("country"), "sex": "F" if g == "Q6581072" else ("M" if g == "Q6581097" else "")})
    return out


def fetch_champions():
    """Titoli Wikipedia citati nella pagina dei campioni mondiali attuali (poi filtrati con l'elenco dei pugili)."""
    names = set()
    for page in CHAMP_PAGES[:1]:
        u = "https://en.wikipedia.org/w/api.php?action=parse&prop=text&format=json&formatversion=2&redirects=1&page=" + page
        t = json.loads(_get(u, timeout=40))["parse"]["text"]
        for tb in re.findall(r"<table.*?</table>", t, re.S):
            for m in re.finditer(r'<a [^>]*title="([^"#]+)"', tb):
                names.add(html.unescape(m.group(1)).strip())
    return names


def ensure(data_dir, log, max_age_days=7):
    """Restituisce l'elenco (lista di dict). Lo ricarica se piu' vecchio di una settimana. Mai bloccare il robot."""
    p = Path(data_dir) / "roster.json"
    cur = {}
    try: cur = json.loads(p.read_text(encoding="utf-8"))
    except Exception: pass
    if cur.get("updated"):
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(cur["updated"])).total_seconds() / 86400
        if age < max_age_days and cur.get("boxers"): return cur
    try:
        boxers = fetch_roster()
        if len(boxers) < 100: raise ValueError("elenco troppo corto: %d" % len(boxers))
        try: champs = sorted(fetch_champions())
        except Exception as e:
            champs = cur.get("champs", []); log(f"ROSTER campioni non letti: {type(e).__name__} {e}")
        names = {b["name"] for b in boxers}
        cur = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "boxers": boxers,
               "champs": [c for c in champs if c in names],
               "source": "Wikidata (CC0), Wikipedia (CC BY-SA)"}
        p.write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")
        log(f"ROSTER OK: {len(boxers)} pugili, {len(cur['champs'])} citati come campioni")
    except Exception as e:
        log(f"ROSTER FAIL {type(e).__name__} {e}")
    return cur
