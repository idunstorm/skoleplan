#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bygger den statiske siden (site/index.html) og abonnement-kalenderen
(site/skole.ics) ut fra data/plan.yaml + data/topics.yaml + data/manual.yaml.

Kjøres automatisk av GitHub Actions hver gang datafilene endres.
"""
import json, hashlib, datetime as dt
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SITE = ROOT / "site"
SITE.mkdir(exist_ok=True)

def load(name):
    p = DATA / name
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}

def active_source(plan, today=None):
    """Velg aktiv klasse/kilde ut fra dagens dato (siste 'fra' <= i dag)."""
    today = today or dt.date.today()
    aktiv = None
    for k in sorted(plan.get("kilder") or [], key=lambda x: str(x["fra"])):
        if dt.date.fromisoformat(str(k["fra"])) <= today:
            aktiv = k
    return aktiv

def date_of(week, dow, year):
    """Mandag=1 ... Fredag=5 -> ekte dato for gitt ISO-uke."""
    return dt.date.fromisocalendar(int(year), int(week), int(dow))

# ---------------------------------------------------------------- assemble PLAN
def assemble():
    plan = load("plan.yaml")
    src = active_source(plan)
    if src:
        plan["klasse"] = src.get("klasse", plan.get("klasse"))
        plan["doc9c"] = src.get("doc", plan.get("doc9c"))
    topics = load("topics.yaml") or {}
    manual = load("manual.yaml") or {}

    # Merge kuraterte temaoppsummeringer inn i temaer
    merged_temaer = []
    for t in plan.get("temaer", []):
        key = t.get("tema", "")
        c = topics.get(key, {})
        merged_temaer.append({
            "fag": t.get("fag", ""),
            "tema": key,
            "blurb": c.get("blurb", ""),
            "laerer": c.get("laerer", []),
            "laereplan": c.get("laereplan"),
            "ressurs": c.get("ressurs"),
            "sporsmal": c.get("sporsmal", []),
        })
    plan["temaer"] = merged_temaer

    # Vigilo-beskjeder
    plan["beskjeder"] = manual.get("beskjeder", []) or []

    # Overstyr/legg til enkeltdager
    over = {(d["uke"], d["dow"]): d for d in (manual.get("overstyr_dager") or [])}
    if over:
        days = {(d["uke"], d["dow"]): d for d in plan.get("dager", [])}
        days.update(over)
        plan["dager"] = [days[k] for k in sorted(days)]

    # ukelekse-nøkler som strenger (for JSON/JS-oppslag)
    plan["ukelekse"] = {str(k): v for k, v in (plan.get("ukelekse") or {}).items()}

    neste = plan.pop("neste", {}) or {}
    kalender = (manual.get("kalender") or {})
    return plan, neste, kalender

# ---------------------------------------------------------------- HTML
def build_html(plan, neste):
    tpl = (ROOT / "app_template.html").read_text(encoding="utf-8")
    tpl = tpl.replace("__PLAN_JSON__", json.dumps(plan, ensure_ascii=False))
    tpl = tpl.replace("__NESTE_JSON__", json.dumps(neste, ensure_ascii=False))
    (SITE / "index.html").write_text(tpl, encoding="utf-8")
    (SITE / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

# ---------------------------------------------------------------- ICS
OSLO_VTIMEZONE = (
    "BEGIN:VTIMEZONE\r\nTZID:Europe/Oslo\r\n"
    "BEGIN:DAYLIGHT\r\nTZOFFSETFROM:+0100\r\nTZOFFSETTO:+0200\r\nTZNAME:CEST\r\n"
    "DTSTART:19700329T020000\r\nRRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU\r\nEND:DAYLIGHT\r\n"
    "BEGIN:STANDARD\r\nTZOFFSETFROM:+0200\r\nTZOFFSETTO:+0100\r\nTZNAME:CET\r\n"
    "DTSTART:19701025T030000\r\nRRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU\r\nEND:STANDARD\r\n"
    "END:VTIMEZONE\r\n"
)

def esc(s):
    return str(s).replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")

def hh(t, default=8):
    return int(t.split(":")[0]) if t else default
def mm(t, default=0):
    return int(t.split(":")[1]) if t else default

def build_ics(plan, kalender):
    year = int(plan["aar"])
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    events = []
    uid = [0]

    def vevent(body):
        events.append(f"BEGIN:VEVENT\r\nUID:sp-{uid[0]}-{stamp}@samson\r\nDTSTAMP:{stamp}\r\n{body}END:VEVENT\r\n")
        uid[0] += 1

    def alarms(triggers, summ):
        out = ""
        for tr in triggers:
            out += f"BEGIN:VALARM\r\nACTION:DISPLAY\r\nDESCRIPTION:{esc(summ)}\r\nTRIGGER:{tr}\r\nEND:VALARM\r\n"
        return out

    def all_day(d, summ, triggers, desc=""):
        end = d + dt.timedelta(days=1)
        s = (f"DTSTART;VALUE=DATE:{d:%Y%m%d}\r\nDTEND;VALUE=DATE:{end:%Y%m%d}\r\n"
             f"TRANSP:TRANSPARENT\r\nSUMMARY:{esc(summ)}\r\n")
        if desc:
            s += f"DESCRIPTION:{esc(desc)}\r\n"
        s += alarms(triggers, summ)
        vevent(s)

    def timed(d, sh, sm, eh, em, summ, loc="", desc="", triggers=()):
        s = (f"DTSTART;TZID=Europe/Oslo:{d:%Y%m%d}T{sh:02d}{sm:02d}00\r\n"
             f"DTEND;TZID=Europe/Oslo:{d:%Y%m%d}T{eh:02d}{em:02d}00\r\n"
             f"TRANSP:TRANSPARENT\r\nSUMMARY:{esc(summ)}\r\n")
        if loc:
            s += f"LOCATION:{esc(loc)}\r\n"
        if desc:
            s += f"DESCRIPTION:{esc(desc)}\r\n"
        s += alarms(triggers, summ)
        vevent(s)

    for day in plan.get("dager", []):
        d = date_of(day["uke"], day["dow"], year)
        if kalender.get("turer", False):
            for ev in (day.get("hendelser") or []):
                if ev and ev.get("start"):
                    timed(d, hh(ev["start"]), mm(ev["start"]),
                          hh(ev.get("end", "14:00")), mm(ev.get("end", "14:00")),
                          ev["tittel"], ev.get("sted", ""), ev.get("slutt", ""),
                          ["-PT14H", "-PT1H"])
        if kalender.get("husk", True):
            for x in (day.get("husk") or []):
                all_day(d, "Husk: " + x["tekst"], ["-PT6H", "PT8H"])
        if kalender.get("lekser", True):
            for x in (day.get("lekser") or []):
                lead = (x.get("fag") + " – ") if x.get("fag") else ""
                all_day(d, "Lekse: " + lead + x["tekst"], ["-PT6H"])

    if kalender.get("vurderinger", True):
        for v in (plan.get("vurderinger") or []):
            if v.get("dato"):
                d = dt.date.fromisoformat(v["dato"])
                all_day(d, f"{v['fag']}: {v['tittel']}", ["-P6DT18H", "-P1DT6H", "PT8H"], v.get("note", ""))

    if kalender.get("beskjeder", True):
        trig = {"prove": ["-P6DT18H", "-P1DT6H", "PT8H"], "frist": ["-P1DT6H", "-PT6H"],
                "husk": ["-PT6H", "PT8H"], "info": ["-PT6H"]}
        for b in (plan.get("beskjeder") or []):
            if b.get("dato"):
                d = dt.date.fromisoformat(b["dato"])
                summ = b.get("tittel", "Beskjed")
                all_day(d, summ, trig.get(b.get("type", "info"), ["-PT6H"]), b.get("tekst", ""))

    if kalender.get("sondag", False):
        for w in plan.get("uker", []):
            man = date_of(w, 1, year)
            sun = man - dt.timedelta(days=1)
            timed(sun, 18, 0, 18, 15, f"Ukesoversikt: uke {w} ({plan['klasse']})",
                  "", "Se skoleplan-appen for uken.", ["-PT0M"])

    cal = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Skoleplan//Samson//NB\r\n"
           "CALSCALE:GREGORIAN\r\nMETHOD:PUBLISH\r\n"
           f"X-WR-CALNAME:Skole {plan['klasse']} – {plan['elev']}\r\n"
           "X-WR-TIMEZONE:Europe/Oslo\r\nREFRESH-INTERVAL;VALUE=DURATION:PT12H\r\n"
           "X-PUBLISHED-TTL:PT12H\r\n" + OSLO_VTIMEZONE + "".join(events) + "END:VCALENDAR\r\n")
    (SITE / "skole.ics").write_text(cal, encoding="utf-8")
    return len(events)

def main():
    plan, neste, kalender = assemble()
    build_html(plan, neste)
    n = build_ics(plan, kalender)
    # enkel .nojekyll så GitHub Pages ikke rører filene
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Bygget site/index.html og site/skole.ics ({n} kalenderhendelser) for {plan['klasse']} uke {plan['uker']}.")

if __name__ == "__main__":
    main()
