#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM-tolkning av ukeplanen -> full data/plan.yaml (+ nye temaer i topics.yaml).

Leser Google-dokumentet (rå tekst), sender det til Claude med et STRENGT
JSON-skjema, validerer resultatet, og skriver planen inn i plan.yaml uten å
røre statiske felter (klasse, elev, valgfag, kilder, neste ...).

Sikkerhet: hvis tolkningen ikke består valideringen, kastes en feil og
kaller-koden beholder forrige (gyldige) plan. Vi viser aldri åpenbart feil
info på barnets plan.

Kjøres av GitHub Actions. Krever ANTHROPIC_API_KEY (egen API-konto, ikke
et Claude-abonnement) og nett.

Lokal test uten API:
  python llm_plan.py --self-test        # validerer at dagens plan.yaml er "gyldig"
"""
import os
import re
import sys
import json
import datetime as dt
from pathlib import Path

import yaml
from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
PLAN = DATA / "plan.yaml"
TOPICS = DATA / "topics.yaml"

MODEL = os.environ.get("SKOLEPLAN_MODEL", "claude-opus-4-8")

# ---------------------------------------------------------------------------
# JSON-skjema for det Claude skal returnere (structured outputs, strict).
# Nullbare felter er anyOf[string,null] så modellen alltid fyller nøkkelen.
# ---------------------------------------------------------------------------
def _nullable(t):
    return {"anyOf": [{"type": t}, {"type": "null"}]}

_TIME = {
    "type": "object",
    "properties": {
        "t": {"type": "string"},                 # "08:30–09:30"
        "f": {"type": "string"},                 # fag
        "nb": _nullable("string"),               # kort merknad ("Rydde/levere CB")
    },
    "required": ["t", "f", "nb"],
    "additionalProperties": False,
}
_LEKSE = {
    "type": "object",
    "properties": {"fag": _nullable("string"), "tekst": {"type": "string"}},
    "required": ["fag", "tekst"],
    "additionalProperties": False,
}
_HUSK = {
    "type": "object",
    "properties": {"tekst": {"type": "string"}},
    "required": ["tekst"],
    "additionalProperties": False,
}
_HEND = {
    "type": "object",
    "properties": {
        "tittel": {"type": "string"},
        "sted": _nullable("string"),
        "slutt": _nullable("string"),
        "start": _nullable("string"),           # "HH:MM" eller null
        "end": _nullable("string"),
    },
    "required": ["tittel", "sted", "slutt", "start", "end"],
    "additionalProperties": False,
}
_DAG = {
    "type": "object",
    "properties": {
        "uke": {"type": "integer"},
        "dow": {"type": "integer"},             # 1=man ... 5=fre
        "spesial": {"type": "boolean"},         # tur/aktivitetsdag (ikke vanlig timeplan)
        "ferie": {"type": "boolean"},
        "timer": {"type": "array", "items": _TIME},
        "lekser": {"type": "array", "items": _LEKSE},
        "husk": {"type": "array", "items": _HUSK},
        "hendelser": {"type": "array", "items": _HEND},
    },
    "required": ["uke", "dow", "spesial", "ferie", "timer", "lekser", "husk", "hendelser"],
    "additionalProperties": False,
}
_TEMA = {
    "type": "object",
    "properties": {
        "fag": {"type": "string"},
        "tema": {"type": "string"},
        "blurb": {"type": "string"},                          # 1 setning
        "laerer": {"type": "array", "items": {"type": "string"}},   # "hva de skal lære"
        "sporsmal": {"type": "array", "items": {"type": "string"}}, # diskusjonsspørsmål
    },
    "required": ["fag", "tema", "blurb", "laerer", "sporsmal"],
    "additionalProperties": False,
}
_VURD = {
    "type": "object",
    "properties": {
        "fag": {"type": "string"},
        "tittel": {"type": "string"},
        "dato": _nullable("string"),            # "YYYY-MM-DD" eller null
        "note": _nullable("string"),
    },
    "required": ["fag", "tittel", "dato", "note"],
    "additionalProperties": False,
}
_UKELEKSE = {
    "type": "object",
    "properties": {"uke": {"type": "integer"}, "tekst": {"type": "string"}},
    "required": ["uke", "tekst"],
    "additionalProperties": False,
}

SCHEMA = {
    "type": "object",
    "properties": {
        "uker": {"type": "array", "items": {"type": "integer"}},
        "temaer": {"type": "array", "items": _TEMA},
        "vurderinger": {"type": "array", "items": _VURD},
        "ukelekse": {"type": "array", "items": _UKELEKSE},
        "dager": {"type": "array", "items": _DAG},
    },
    "required": ["uker", "temaer", "vurderinger", "ukelekse", "dager"],
    "additionalProperties": False,
}

SYSTEM = """\
Du tolker en norsk toukers LÆRINGSPLAN (ukeplan) fra et Google-dokument til \
strukturert JSON. Planen gjelder eleven {elev} i klasse {klasse}, valgfag \
{valgfag}, skoleår {aar}. Vær nøyaktig – dette vises på et barns skoleplan, så \
det er bedre å utelate usikker info enn å gjette feil.

STRUKTUR I DOKUMENTET
- Øverst en tabell med "Fag: Tema" og kompetansemål under hvert fag.
- Så en timeplan-tabell med kolonner Mandag–Fredag og rader per klokkeslett.
- En "Ukeinfo"-kolonne og fritekst med turer, beskjeder og "Hjemmearbeid".

SLIK FYLLER DU JSON
- uker: de to ukenumrene planen gjelder (fra overskriften, f.eks. "Uke 25+26").
- dager: én rad per skoledag (dow 1=mandag ... 5=fredag) for BEGGE uker (10 dager).
  * Vanlig dag: fyll "timer" med {{t, f, nb}} der t er tidsrom "08:30–09:30",
    f er faget, nb er en kort merknad hvis cellen har en (ellers null). spesial=false.
  * Turdag/aktivitetsdag (cellen spenner over hele dagen, f.eks. "Byvandring",
    "Trefjellstur"): sett spesial=true, timer=[], og legg turen i "hendelser"
    med tittel, sted (oppmøtested), slutt (avslutningsinfo), start "HH:MM",
    end "HH:MM" (utled klokkeslett fra teksten, f.eks. "kl.11" -> "11:00";
    bruk "14:00" som end hvis sluttid ikke er oppgitt). ferie=true kun for
    dager merket ferie/fri.
- Bruk KUN elevens valgfag ({valgfag}) – ikke andre språkvalg som tysk/spansk.
- lekser: konkrete lekser knyttet til riktig dag ("Hjemmearbeid: Til tirsdag: ...").
- husk: ting eleven må ta med. Legg til "Husk gymtøy (kroppsøving – <tema>)" på
  kroppsøvingsdager; svømmetøy på svømming; klær etter vær / matpakke på turdager;
  og eksplisitte "ta med"-beskjeder fra dokumentet.
- vurderinger: prøver/innleveringer nevnt i planen ({{fag, tittel, dato, note}}).
  Sett dato=null hvis ingen dato er oppgitt, og note="Dato ikke oppgitt i planen –
  sjekk Vigilo/Google Classroom." i så fall.
- ukelekse: generell ukelekse per uke hvis oppgitt (ellers tom tekst).
- temaer: ett objekt per fag/tema i topptabellen. blurb=1 kort setning på norsk;
  laerer=punktliste "hva de skal lære" (omskriv kompetansemålene til klar norsk);
  sporsmal=2–3 gode diskusjonsspørsmål en forelder kan stille. IKKE finn på nettlenker.

Returner kun data som faktisk står i (eller trygt kan utledes fra) dokumentet.\
"""


# ---------------------------------------------------------------------------
# Henting av dokumentet (samme kilde-logikk som check.py)
# ---------------------------------------------------------------------------
def active_source(plan, today=None):
    today = today or dt.date.today()
    aktiv = None
    for k in sorted(plan.get("kilder") or [], key=lambda x: str(x["fra"])):
        if dt.date.fromisoformat(str(k["fra"])) <= today:
            aktiv = k
    return aktiv


def fetch_text(url):
    import requests
    from bs4 import BeautifulSoup
    r = requests.get(url, timeout=30, headers={"User-Agent": "skoleplan-bot/1.0"})
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser").get_text("\n")


def header_weeks(text):
    m = re.search(r"uke\s*(\d{1,2})\s*(?:&|\+|og)\s*(\d{1,2})", text, re.I)
    if m:
        return [int(m.group(1)), int(m.group(2))]
    m = re.search(r"uke\s*(\d{1,2})", text, re.I)
    return [int(m.group(1))] if m else []


# ---------------------------------------------------------------------------
# LLM-kall
# ---------------------------------------------------------------------------
def call_claude(text, ctx):
    import anthropic
    client = anthropic.Anthropic()  # leser ANTHROPIC_API_KEY fra miljøet
    system = SYSTEM.format(**ctx)
    resp = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
        system=system,
        messages=[{"role": "user", "content": "RÅ TEKST FRA UKEPLANEN:\n\n" + text[:60000]}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"Claude avslo forespørselen: {resp.stop_details}")
    out = next((b.text for b in resp.content if b.type == "text"), None)
    if not out:
        raise RuntimeError("Tomt svar fra Claude.")
    return json.loads(out)


# ---------------------------------------------------------------------------
# Validering – fanger åpenbart feil/uferdig tolkning
# ---------------------------------------------------------------------------
def validate(data, want_weeks=None):
    errs = []
    uker = data.get("uker") or []
    if not (1 <= len(uker) <= 2) or not all(isinstance(w, int) and 1 <= w <= 53 for w in uker):
        errs.append(f"ugyldige uker: {uker!r}")
    if want_weeks and set(uker) != set(want_weeks):
        errs.append(f"uker {uker} matcher ikke overskriften {want_weeks}")

    dager = data.get("dager") or []
    by_week = {}
    for d in dager:
        by_week.setdefault(d["uke"], set()).add(d["dow"])
    for w in uker:
        got = by_week.get(w, set())
        missing = {1, 2, 3, 4, 5} - got
        if missing:
            errs.append(f"uke {w} mangler dager (dow {sorted(missing)})")

    for d in dager:
        tag = f"uke {d['uke']} dow {d['dow']}"
        if d.get("ferie"):
            continue
        has_timer = bool(d.get("timer"))
        has_event = bool(d.get("hendelser"))
        if not has_timer and not has_event:
            errs.append(f"{tag}: tom dag (verken timeplan eller hendelse)")
        for t in d.get("timer") or []:
            if not re.search(r"\d{1,2}[:.]\d{2}", t.get("t", "")):
                errs.append(f"{tag}: time uten klokkeslett: {t.get('t')!r}")

    if not data.get("temaer"):
        errs.append("ingen temaer tolket")

    if errs:
        raise ValueError("Validering feilet:\n  - " + "\n  - ".join(errs))
    return True


# ---------------------------------------------------------------------------
# Skriving tilbake til plan.yaml / topics.yaml (bevarer statiske felter)
# ---------------------------------------------------------------------------
def _yaml():
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    return y


def write_plan(data):
    y = _yaml()
    doc = y.load(PLAN.read_text(encoding="utf-8"))

    from ruamel.yaml.comments import CommentedSeq
    uker = CommentedSeq(data["uker"]); uker.fa.set_flow_style()
    doc["uker"] = uker

    doc["ukelekse"] = {int(u["uke"]): u["tekst"] for u in data.get("ukelekse", [])}
    doc["temaer"] = [{"fag": t["fag"], "tema": t["tema"]} for t in data.get("temaer", [])]
    doc["vurderinger"] = [
        {"fag": v["fag"], "tittel": v["tittel"], "dato": v.get("dato"), "note": v.get("note")}
        for v in data.get("vurderinger", [])
    ]

    dager = []
    for d in data["dager"]:
        row = {"uke": d["uke"], "dow": d["dow"]}
        if d.get("spesial"):
            row["spesial"] = True
        if d.get("ferie"):
            row["ferie"] = True
        row["timer"] = [
            ({"t": t["t"], "f": t["f"], "nb": t["nb"]} if t.get("nb") else {"t": t["t"], "f": t["f"]})
            for t in d.get("timer", [])
        ]
        row["lekser"] = [
            ({"fag": x["fag"], "tekst": x["tekst"]} if x.get("fag") else {"tekst": x["tekst"]})
            for x in d.get("lekser", [])
        ]
        row["husk"] = [{"tekst": x["tekst"]} for x in d.get("husk", [])]
        row["hendelser"] = []
        for h in d.get("hendelser", []):
            ev = {"tittel": h["tittel"]}
            for k in ("sted", "slutt", "start", "end"):
                if h.get(k) is not None:
                    ev[k] = h[k]
            row["hendelser"].append(ev)
        dager.append(row)
    doc["dager"] = dager
    doc["oppdatert"] = dt.date.today().isoformat()

    with PLAN.open("w", encoding="utf-8") as f:
        y.dump(doc, f)


def merge_topics(data):
    """Legg til nye temaer i topics.yaml uten å røre kuraterte oppføringer."""
    y = _yaml()
    doc = y.load(TOPICS.read_text(encoding="utf-8"))
    added = []
    for t in data.get("temaer", []):
        tema = t["tema"]
        if tema in doc:
            continue
        doc[tema] = {
            "blurb": t.get("blurb", ""),
            "laerer": list(t.get("laerer", [])),
            "laereplan": None,   # aldri autogenererte lenker
            "ressurs": None,
            "sporsmal": list(t.get("sporsmal", [])),
        }
        added.append(tema)
    if added:
        with TOPICS.open("w", encoding="utf-8") as f:
            y.dump(doc, f)
    return added


# ---------------------------------------------------------------------------
# Hovedinngang – kalles fra check.py
# ---------------------------------------------------------------------------
def apply_from_doc(text=None):
    """Tolk planen og skriv plan.yaml + topics.yaml. Kaster ved valideringsfeil."""
    plan = yaml.safe_load(PLAN.read_text(encoding="utf-8"))
    src = active_source(plan) or {}
    ctx = {
        "elev": plan.get("elev", ""),
        "klasse": src.get("klasse") or plan.get("klasse", ""),
        "valgfag": plan.get("valgfag", ""),
        "aar": plan.get("aar", dt.date.today().year),
    }
    if text is None:
        url = src.get("doc") or plan["doc9c"]
        text = fetch_text(url)

    data = call_claude(text, ctx)
    validate(data, want_weeks=header_weeks(text) or None)
    write_plan(data)
    added = merge_topics(data)
    return {"uker": data["uker"], "dager": len(data["dager"]),
            "temaer": len(data["temaer"]), "nye_temaer": added}


def self_test():
    """Sjekk at dagens plan.yaml er 'gyldig' etter valideringsreglene."""
    plan = yaml.safe_load(PLAN.read_text(encoding="utf-8"))
    data = {
        "uker": plan.get("uker", []),
        "temaer": plan.get("temaer", []),
        "vurderinger": plan.get("vurderinger", []),
        "dager": plan.get("dager", []),
    }
    validate(data, want_weeks=plan.get("uker"))
    print("self-test OK: dagens plan.yaml består valideringen "
          f"({len(data['dager'])} dager, uker {data['uker']}).")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        info = apply_from_doc()
        print("Tolket plan:", json.dumps(info, ensure_ascii=False))
