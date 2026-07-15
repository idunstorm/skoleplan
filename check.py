#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Daglig sjekk: henter 9C-planen, ser om ukenummer/innhold har endret seg.
Ved endring:
  - skriver _incoming/ny-plan.md (varsel + rå tekst du/Claude kan bruke)
  - (valgfritt, AUTO_APPLY=1) oppdaterer uker + dato i data/plan.yaml
Ellers: gjør ingenting.

Kjøres av GitHub Actions (se .github/workflows/check.yml).
Krever nett – kjører derfor på GitHub, ikke lokalt i sandkassen.
"""
import os, re, sys, json, hashlib, datetime as dt
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
INCOMING = ROOT / "_incoming"
STATE = ROOT / ".state.json"

FAG = ["Norsk", "Matematikk", "Naturfag", "Samfunnsfag", "KRLE", "Engelsk",
       "Musikk", "Kunst & håndverk", "Kunst og håndverk", "Kroppsøving",
       "Mat og helse", "Språk/arbeidslivsfag", "Språk/Arbeidslivsfag",
       "Fransk", "Spansk", "Tysk", "Arbeidslivsfag"]

def active_source(plan, today=None):
    today = today or dt.date.today()
    aktiv = None
    for k in sorted(plan.get("kilder") or [], key=lambda x: str(x["fra"])):
        if dt.date.fromisoformat(str(k["fra"])) <= today:
            aktiv = k
    return aktiv

def fetch(url):
    import requests
    r = requests.get(url, timeout=30, headers={"User-Agent": "skoleplan-bot/1.0"})
    r.raise_for_status()
    return r.text

def to_text(html):
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser").get_text("\n")
    except Exception:
        return re.sub(r"<[^>]+>", " ", html)

def parse_weeks(text):
    m = re.search(r"uke\s*(\d{1,2})\s*(?:&|\+|og)\s*(\d{1,2})", text, re.I)
    if m:
        return [int(m.group(1)), int(m.group(2))]
    m = re.search(r"uke\s*(\d{1,2})", text, re.I)
    return [int(m.group(1))] if m else []

def parse_topics(text):
    """Finn 'Fag: Tema' i topptabellen. Returnerer liste av {fag, tema}."""
    # Rydd whitespace
    t = re.sub(r"[ \t]+", " ", text)
    # Bygg regex som finner et fag-navn (evt. med '9c ' foran) fulgt av ':'
    fagpat = "|".join(sorted((re.escape(f) for f in FAG), key=len, reverse=True))
    rx = re.compile(r"(?:\b9[a-d]\s+)?(" + fagpat + r")\s*:\s*(.*)", re.I)
    found = []
    seen = set()
    for line in t.splitlines():
        line = line.strip()
        m = rx.match(line)
        if not m:
            continue
        fag = m.group(1).strip()
        tema = m.group(2).strip()
        # kutt tema ved neste fag-navn eller etter rimelig lengde
        tema = re.split(r"\s+(?:" + fagpat + r")\s*:", tema)[0].strip()
        tema = tema.split("\n")[0].strip()
        if len(tema) > 70:
            tema = tema[:70].rsplit(" ", 1)[0] + " …"
        key = fag.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append({"fag": fag, "tema": tema})
    return found

def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}

def save_state(s):
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")

def set_output(**kv):
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")

def apply_to_plan(weeks, topics):
    """Oppdater kun uker + fag/tema + dato i plan.yaml, behold kommentarer."""
    from ruamel.yaml import YAML
    y = YAML()
    y.preserve_quotes = True
    p = DATA / "plan.yaml"
    doc = y.load(p.read_text(encoding="utf-8"))
    # Trygt: bare ukenummer + dato oppdateres automatisk. Temaer/timeplan
    # tas via varselet, for å ikke vise feil/uferdig info på barnets plan.
    if weeks:
        from ruamel.yaml.comments import CommentedSeq
        seq = CommentedSeq(weeks)
        seq.fa.set_flow_style()
        doc["uker"] = seq
    doc["oppdatert"] = dt.date.today().isoformat()
    with p.open("w", encoding="utf-8") as f:
        y.dump(doc, f)

def main():
    plan = yaml.safe_load((DATA / "plan.yaml").read_text(encoding="utf-8"))
    src = active_source(plan)
    url = (src or {}).get("doc") or plan["doc9c"]
    if src:
        print(f"Aktiv kilde: {src.get('klasse')} (fra {src.get('fra')})")

    fixture = None
    if "--fixture" in sys.argv:
        fixture = sys.argv[sys.argv.index("--fixture") + 1]

    html = Path(fixture).read_text(encoding="utf-8") if fixture else fetch(url)
    text = to_text(html)
    weeks = parse_weeks(text)
    topics = parse_topics(text)
    digest = hashlib.sha256(re.sub(r"\s+", " ", text).encode("utf-8")).hexdigest()[:16]

    state = load_state()
    cur_weeks = plan.get("uker", [])
    changed = (digest != state.get("hash")) or (weeks and weeks != cur_weeks)
    new_plan = bool(weeks) and weeks != cur_weeks

    print(f"Oppdaget uker={weeks} (nåværende i plan.yaml={cur_weeks}); "
          f"{len(topics)} fag/tema; endret={changed}; ny plan={new_plan}")

    save_hash = True
    if changed:
        applied = False
        parse_failed = False
        err_msg = ""
        # Full, automatisk tolkning av hele planen via Claude (llm_plan.py).
        if os.environ.get("AUTO_APPLY", "1") == "1":
            try:
                import llm_plan
                info = llm_plan.apply_from_doc(text)
                applied = True
                print(f"LLM: tolket full plan automatisk: {info}")
            except ValueError as e:
                # Validering feilet -> tolkningen så feil ut. Behold forrige plan.
                parse_failed = True
                err_msg = f"Validering feilet: {e}"
                print(f"{err_msg}\nBeholder forrige (gyldige) plan.")
            except Exception as e:
                # API/nett-feil (trolig forbigående). Behold plan og prøv igjen senere.
                parse_failed = True
                save_hash = False   # ikke lagre hash -> ny sjekk prøver på nytt
                err_msg = f"Tolkning feilet (forbigående?): {e}"
                print(f"{err_msg}\nBeholder forrige plan, prøver igjen ved neste kjøring.")

        # Varsel-fil (kun nyttig når automatikken IKKE lyktes)
        if parse_failed:
            INCOMING.mkdir(exist_ok=True)
            lines = [f"# Klarte ikke tolke ny ukeplan automatisk "
                     f"({'uke ' + '–'.join(map(str, weeks)) if weeks else 'ukjent uke'})",
                     "",
                     f"- Oppdaget: {dt.datetime.now().isoformat(timespec='minutes')}",
                     f"- Uker i planen nå: {weeks}  (plan.yaml hadde {cur_weeks})",
                     f"- Kilde: {url}",
                     f"- Feil: {err_msg}",
                     "",
                     "Forrige plan er beholdt, så appen viser fortsatt gyldig info.",
                     "For å fikse: send lenken over til Claude, så får du en oppdatert "
                     "`data/plan.yaml` tilbake – eller kjør workflowen på nytt.",
                     "", "## Fag og temaer (grovlest)", ""]
            for t in topics:
                lines.append(f"- **{t['fag']}**: {t['tema']}")
            lines += ["", "## Rå tekst fra planen", "", "```", text.strip()[:6000], "```"]
            (INCOMING / "ny-plan.md").write_text("\n".join(lines), encoding="utf-8")

        set_output(changed="true", new_plan=str(new_plan).lower(),
                   weeks="-".join(map(str, weeks)), applied=str(applied).lower(),
                   parse_failed=str(parse_failed).lower())
    else:
        set_output(changed="false")

    if save_hash:
        state["hash"] = digest
        state["weeks"] = weeks
        state["checked"] = dt.datetime.now().isoformat(timespec="minutes")
        save_state(state)

if __name__ == "__main__":
    main()
