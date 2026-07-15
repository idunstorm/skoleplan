# Skoleplan – Samson (9C → 10A)

En liten selvoppdaterende løsning: en **infoside** og en **abonnement-kalender** for skolens ukeplaner, som holder seg oppdatert av seg selv via GitHub.

- **Infoside** (legges på hjemskjermen): temaer, «hva de skal lære», prøver, lekser, ting å huske, turer og Vigilo-beskjeder – med kontroll på dagens dato og hvilken uke som gjelder.
- **Kalender** (`skole.ics`): abonnerer du på den én gang, kommer prøver, frister, «husk gymtøy/svømmetøy» og beskjeder inn i din vanlige kalender – som **heldags og «ledig»**, så det aldri legger seg oppå jobbkalenderen.

Alt bygges av **GitHub Actions** (gratis). Hver natt sjekkes 9C-planen for endringer; hver gang data endres, bygges siden og kalenderen på nytt og publiseres til **GitHub Pages**.

---

## Slik kommer du i gang (én gang, ~10 min)

1. **Lag et GitHub-repo** (f.eks. `skoleplan`) og last opp alle filene i denne mappen (behold mappestrukturen, inkludert `.github/`).
2. **Slå på Pages:** Repoet → **Settings → Pages → Build and deployment → Source: GitHub Actions.**
3. Gå til **Actions**-fanen, velg *«Bygg og publiser skoleplan»* → **Run workflow** (eller bare vent til nattkjøringen).
4. Når jobben er grønn, ligger sidene her:
   - **Infoside:** `https://<brukernavn>.github.io/<repo>/`
   - **Kalender:** `https://<brukernavn>.github.io/<repo>/skole.ics`

### Legg siden på hjemskjermen
- **iPhone (Safari):** Del → «Legg til på Hjem-skjerm».
- **Android (Chrome):** ⋮ → «Legg til på startskjerm».

### Abonnér på kalenderen (auto-oppdaterer)
- **iPhone:** Innstillinger → Kalender → Kontoer → Legg til konto → Annet → **Legg til abonnert kalender** → lim inn kalender-URL-en (bytt `https://` med `webcal://` om den ikke vil).
- **Google Kalender (PC):** Andre kalendere → **Fra URL** → lim inn kalender-URL-en.
- Lag den gjerne som en **egen kalender** («Skole – Samson»), så holder den seg adskilt.

---

## Legge inn Vigilo-info (og annet)

Åpne **`data/manual.yaml`** (kan redigeres rett i GitHub, også fra mobil: åpne fila → blyant-ikonet → Commit). Legg til beskjeder:

```yaml
beskjeder:
  - {dato: "2026-09-15", type: "prove", tittel: "Prøve i matematikk", tekst: "Kapittel 1–2"}
  - {dato: "2026-09-03", type: "info",  tittel: "Foreldremøte", tekst: "Kl. 18:00"}
```

`type` kan være `info`, `husk`, `frist` eller `prove` (prøver får varsel 7 og 2 dager før). Lagre → siden og kalenderen oppdaterer seg automatisk i løpet av et minutt eller to.

Eller: send meg (Claude) teksten fra Vigilo, så gir jeg deg en ferdig linje.

---

## Hva skjer automatisk – og hva krever ett lite steg

**Helt automatisk**
- Bygging + publisering av side og kalender hver gang du endrer en datafil.
- Daglig sjekk av om 9C-planen er endret. Ukenummeret oppdateres automatisk.
- «Hvilken uke gjelder nå» og alle datovarsler.
- Vigilo-beskjeder.

**Ett lite steg (ved en helt ny toukersplan)**
Selve timeplanen/leksene i Google-dokumentet har et format som varierer mye (tabeller som kollapser på turdager osv.). For å unngå å vise **feil info på barnets plan**, fyller vi ikke dette inn helt automatisk. Når en ny plan oppdages, får du en **e-post/«sak»** i GitHub med planens fag/temaer og rå tekst. Da enten:
- sender du meg lenken, så får du en oppdatert `data/plan.yaml` (+ `topics.yaml`) tilbake på minuttet, **eller**
- redigerer du filene selv (de er godt kommentert).

---

## Filene

| Fil | Hva |
|-----|-----|
| `data/plan.yaml` | Selve toukersplanen (uker, timeplan, husk, lekser, temaer). |
| `data/topics.yaml` | Kuraterte «hva de skal lære»-oppsummeringer, læreplan-lenker og diskusjonsspørsmål per tema. |
| `data/manual.yaml` | Vigilo-beskjeder + hvilke kategorier som skal med i kalenderen. |
| `build.py` | Bygger `site/index.html` + `site/skole.ics`. |
| `check.py` | Daglig endringssjekk + varsel. |
| `app_template.html` | Selve web-appen (data settes inn ved bygging). |
| `.github/workflows/site.yml` | Kjører alt automatisk. |

## Overgangen til 10A (skjer automatisk)
Systemet bytter fra 9C til 10A **automatisk 11. august 2026** (se `kilder:` i `data/plan.yaml`). Fra da av følger nattjobben 10A-planen, og siden viser 10A. Den første 10A-planen fylles inn på vanlig måte via varselet (send lenken til Claude, eller rediger `plan.yaml`). Vil du bytte dato, endre `fra:` under `kilder:`.

## Kjøre lokalt (valgfritt)
```bash
pip install -r requirements.txt
python build.py           # lager site/index.html + site/skole.ics
```
