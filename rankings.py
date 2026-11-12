"""Classifiche pubbliche (fatti: nomi e posizioni). Fonti: TBRB (letto da BoxingNews24) e WBA (pagina ufficiale).
Poche richieste (una pagina per fonte, ogni 6 ore). Scrive data/rankings.json."""
import json, re, html, time, urllib.request
from html.parser import HTMLParser
from datetime import datetime, timezone
from pathlib import Path

UA = "RinglineBot/0.1 (https://github.com/pptommaso04-byte/ringline-robot; public boxing facts, small volume)"
SOURCES = [
    {"id": "TBRB", "label": "TBRB (via BoxingNews24)", "url": "https://www.boxingnews24.com/boxing-ratings-rankings-wbo-wbc-ibf/"},
    {"id": "WBA", "label": "WBA (classifica ufficiale)", "url": "https://www.wbaboxing.com/wba-ranking"},
]
# (parola cercata nel titolo, nome standard) - dal piu' lungo al piu' corto
DIVS = [("super middleweight", "Super Middleweight"), ("light heavyweight", "Light Heavyweight"), ("junior middleweight", "Junior Middleweight"),
        ("super welterweight", "Junior Middleweight"), ("junior welterweight", "Junior Welterweight"), ("super lightweight", "Junior Welterweight"),
        ("junior lightweight", "Junior Lightweight"), ("super featherweight", "Junior Lightweight"), ("junior featherweight", "Junior Featherweight"),
        ("super bantamweight", "Junior Featherweight"), ("junior bantamweight", "Junior Bantamweight"), ("super flyweight", "Junior Bantamweight"),
        ("junior flyweight", "Junior Flyweight"), ("light flyweight", "Junior Flyweight"), ("heavyweight", "Heavyweight"), ("cruiserweight", "Cruiserweight"),
        ("middleweight", "Middleweight"), ("welterweight", "Welterweight"), ("lightweight", "Lightweight"), ("featherweight", "Featherweight"),
        ("bantamweight", "Bantamweight"), ("flyweight", "Flyweight"), ("strawweight", "Strawweight"), ("minimumweight", "Strawweight"),
        ("minimum", "Strawweight"), ("atomweight", "Atomweight")]


def fetch(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html", "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


class P(HTMLParser):
    """Segue i titoli e le tabelle. Ogni tabella prende la divisione dell'ultimo titolo visto."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.heads = []; self.tables = []; self.cur = None; self.row = None; self.cell = None
        self.last_div = None; self.last_p4p = False; self.last_sex = "M"; self.buf = ""; self.in_head = 0; self.depth = 0
    def handle_starttag(self, t, a):
        if t in ("h1", "h2", "h3", "h4", "h5", "h6", "strong", "b") and self.cur is None: self.in_head += 1; self.buf = ""
        if t == "table": self.cur = {"div": self.last_div, "p4p": self.last_p4p, "sex": self.last_sex, "rows": []}; self.depth += 1
        elif t == "tr" and self.cur is not None: self.row = []
        elif t in ("td", "th") and self.row is not None: self.cell = ""
    def handle_endtag(self, t):
        if t in ("h1", "h2", "h3", "h4", "h5", "h6", "strong", "b") and self.in_head:
            self.in_head -= 1; self._head(self.buf); self.buf = ""
        if t in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(re.sub(r"\s+", " ", self.cell).strip()); self.cell = None
        elif t == "tr" and self.row is not None and self.cur is not None:
            if any(self.row): self.cur["rows"].append(self.row)
            self.row = None
        elif t == "table" and self.cur is not None:
            self.tables.append(self.cur); self.cur = None; self.depth -= 1
    def handle_data(self, d):
        if self.cell is not None: self.cell += d
        elif self.in_head: self.buf += d
        elif self.cur is None and len(d.strip()) < 70 and d.strip(): self._head(d)
    def _head(self, text):
        low = re.sub(r"\s+", " ", text).strip().lower()
        if not low or len(low) > 70: return
        self.heads.append(low)
        fem = "women" in low or "female" in low
        if "pound" in low or "p4p" in low:
            self.last_p4p = True; self.last_div = None; self.last_sex = "F" if fem else "M"
            return
        for key, std in DIVS:
            if key in low:
                self.last_div = std; self.last_p4p = False; self.last_sex = "F" if fem else "M"
                return


def nice(n):
    n = re.sub(r"\s+", " ", n).strip()
    return n.title() if n.isupper() else n


def parse_tables(page):
    p = P(); p.feed(page)
    out = {"divisions": {}, "p4p_M": [], "p4p_F": []}
    for tb in p.tables:
        ranks, champ = [], None
        for row in tb["rows"]:
            cells = [c for c in row if c]
            if not cells: continue
            first = cells[0]
            is_champ = first in ("★", "*", "C", "Champion", "CHAMPION") or "★" in first
            m = re.match(r"^(\d{1,2})\.?$", first)
            if not (is_champ or m): continue
            name = next((c for c in cells[1:] if re.search(r"[A-Za-zÀ-ÿ]{2,}\s+[A-Za-zÀ-ÿ'.-]{2,}", c) and not re.match(r"^\d+-\d+", c) and "OPEN" not in c.upper()), None)
            if not name: continue
            country = next((c for c in cells[1:] if re.fullmatch(r"[A-Z]{3}", c)), "")
            rec = next((c for c in cells[1:] if re.match(r"^\d+-\d+-\d+", c)), "")
            e = {"name": nice(name), "country": country}
            if rec: e["record"] = rec
            if is_champ: champ = e
            else: e["rank"] = int(m.group(1)); ranks.append(e)
        if not ranks and not champ: continue
        if tb["p4p"]:
            (out["p4p_F"] if tb["sex"] == "F" else out["p4p_M"]).extend(ranks)
        elif tb["div"]:
            key = ("F: " if tb["sex"] == "F" else "") + tb["div"]
            out["divisions"][key] = {"champion": champ, "ranks": ranks}
    out["_heads"] = p.heads[:12]
    return out




# ---------- box-rank.com: WBC, IBF, WBO, RING (classifiche ufficiali ricopiate mese per mese) ----------
BR_ORGS = [("WBC", "wbc"), ("IBF", "ibf"), ("WBO", "wbo"), ("RING", "ring")]
BR_DIVS = [("Heavyweight", ["heavyweight"]), ("Bridgerweight", ["bridgerweight"]), ("Cruiserweight", ["cruiserweight"]),
           ("Light Heavyweight", ["light-heavyweight", "lightheavyweight"]), ("Super Middleweight", ["super-middleweight", "supermiddleweight"]),
           ("Middleweight", ["middleweight"]), ("Junior Middleweight", ["super-welterweight", "superwelterweight", "junior-middleweight", "light-middleweight"]),
           ("Welterweight", ["welterweight"]), ("Junior Welterweight", ["super-lightweight", "superlightweight", "junior-welterweight", "light-welterweight"]),
           ("Lightweight", ["lightweight"]), ("Junior Lightweight", ["super-featherweight", "superfeatherweight", "junior-lightweight"]),
           ("Featherweight", ["featherweight"]), ("Junior Featherweight", ["super-bantamweight", "superbantamweight", "junior-featherweight"]),
           ("Bantamweight", ["bantamweight"]), ("Junior Bantamweight", ["super-flyweight", "superflyweight", "junior-bantamweight"]),
           ("Flyweight", ["flyweight"]), ("Junior Flyweight", ["light-flyweight", "lightflyweight", "junior-flyweight"]),
           ("Strawweight", ["minimumweight", "strawweight", "minimum-weight"])]


class BR(HTMLParser):
    """Prima tabella della pagina: righe con numero/trofeo, nome e bandiera (testo alternativo dell'immagine)."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []; self.row = None; self.cell = None; self.t = 0
    def handle_starttag(self, t, a):
        a = dict(a)
        if t == "table": self.t += 1
        elif t == "tr" and self.t == 1: self.row = []
        elif t in ("td", "th") and self.row is not None: self.cell = ""
        elif t == "img" and self.cell is not None:
            self.cell += " [[" + (a.get("alt") or "") + "]] "
    def handle_data(self, d):
        if self.cell is not None: self.cell += d
    def handle_endtag(self, t):
        if t in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(re.sub(r"\s+", " ", self.cell).strip()); self.cell = None
        elif t == "tr" and self.row is not None:
            if self.row: self.rows.append(self.row)
            self.row = None
        elif t == "table": self.t -= 1


def parse_boxrank(page):
    p = BR(); p.feed(page)
    champ, ranks = None, []
    for row in p.rows:
        if len(row) < 2: continue
        first, rest = row[0], " ".join(row[1:])
        alts = re.findall(r"\[\[([^\]]*)\]\]", " ".join(row))
        text = re.sub(r"\[\[[^\]]*\]\]", " ", rest)
        country = next((re.sub(r"\s*flag$", "", a, flags=re.I).strip() for a in alts if a and "champion" not in a.lower() and "trophy" not in a.lower()), "")
        is_champ = "champion" in first.lower() or "trophy" in first.lower() or "champion" in text.lower() and not re.match(r"^\d+$", first.strip())
        m = re.match(r"^\s*(\d{1,3})\s*$", re.sub(r"\[\[[^\]]*\]\]", "", first))
        if not (is_champ or m): continue
        name = re.sub(r"\b(World |Interim |Super |Regular |Franchise )?Champion\b", " ", text, flags=re.I)
        name = re.sub(r"\b(NEW|RE-?ENTRY|Vacant)\b", " ", name)
        name = re.sub(r"\s[+\-−]\d+\b.*$", "", name)
        name = re.sub(r"\s+", " ", name).strip(" -•")
        if len(name.split()) < 2 or "OPEN" in name.upper(): continue
        e = {"name": nice(name), "country": country}
        if is_champ and champ is None: champ = e
        elif m: e["rank"] = int(m.group(1)); ranks.append(e)
    return {"champion": champ, "ranks": ranks}


def run_boxrank(data_dir, log, res):
    sp = Path(data_dir) / "boxrank_slugs.json"
    try: slugs = json.loads(sp.read_text(encoding="utf-8"))
    except Exception: slugs = {}
    for label, org in BR_ORGS:
        divs, nr, miss = {}, 0, []
        for std, cands in BR_DIVS:
            cands = ([slugs[std]] if slugs.get(std) else []) + [c for c in cands if c != slugs.get(std)]
            got = None
            for c in cands:
                try:
                    got = parse_boxrank(fetch("https://box-rank.com/rankings/org/%s/%s" % (org, c), timeout=30))
                    if got["ranks"]: slugs[std] = c; break
                    got = None
                except Exception: got = None
                time.sleep(0.4)
            if got:
                divs[std] = got; nr += len(got["ranks"])
            else: miss.append(std)
            time.sleep(0.4)
        if len(divs) >= 5:
            res[label] = {"divisions": divs, "p4p_M": [], "p4p_F": [], "label": label + " (via Box-Rank)",
                          "url": "https://box-rank.com/rankings/org/%s/heavyweight" % org,
                          "read": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            log(f"CLASSIFICHE OK {label}: {len(divs)} divisioni, {nr} posizioni" + (f" (mancano: {', '.join(miss)})" if miss else ""))
        else:
            log(f"CLASSIFICHE FAIL {label}: solo {len(divs)} divisioni, mancano: {', '.join(miss)}")
    sp.write_text(json.dumps(slugs, indent=1), encoding="utf-8")


def run_step(data_dir, log, max_age_h=6):
    p = Path(data_dir) / "rankings.json"
    cur = {}
    try: cur = json.loads(p.read_text(encoding="utf-8"))
    except Exception: pass
    if cur.get("updated"):
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(cur["updated"])).total_seconds() / 3600
        if age < max_age_h: return cur
    res = cur.get("sources", {})
    for s in SOURCES:
        try:
            d = parse_tables(fetch(s["url"]))
            nd = len(d["divisions"]); nr = sum(len(v["ranks"]) for v in d["divisions"].values())
            if nd < 5: raise ValueError("pochi dati: %d divisioni, titoli visti: %s" % (nd, d["_heads"][:8]))
            d.pop("_heads", None)
            d.update({"label": s["label"], "url": s["url"], "read": datetime.now(timezone.utc).isoformat(timespec="seconds")})
            res[s["id"]] = d
            log(f"CLASSIFICHE OK {s['id']}: {nd} divisioni, {nr} posizioni, p4p {len(d['p4p_M'])}+{len(d['p4p_F'])}")
        except Exception as e:
            log(f"CLASSIFICHE FAIL {s['id']}: {type(e).__name__} {e}")
    try: run_boxrank(data_dir, log, res)
    except Exception as e: log(f"CLASSIFICHE FAIL box-rank: {type(e).__name__} {e}")
    cur = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sources": res}
    p.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
    return cur
