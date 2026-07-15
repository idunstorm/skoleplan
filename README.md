# Skoleplan – Samson (9C → 10A)

En liten selvoppdaterende løsning: en **infoside** og en **abonnement-kalender** for skolens ukeplaner, som holder seg oppdatert av seg selv via GitHub.

- **Infoside** (legges på hjemskjermen): temaer, «hva de skal lære», prøver, lekser, ting å huske, turer og Vigilo-beskjeder – med kontroll på dagens dato og hvilken uke som gjelder.
- **Kalender** (`skole.ics`): abonnerer du på den én gang, kommer prøver, frister, «husk gymtøy/svømmetøy» og beskjeder inn i din vanlige kalender – som **heldags og «ledig»**, så det aldri legger seg oppå jobbkalenderen.

Alt bygges av **GitHub Actions** (gratis). Hver natt sjekkes 9C-planen for endringer; hver gang data endres, bygges siden og kalenderen på nytt og publiseres til **GitHub Pages**.

---

## Slik kommer du i gang (én gang, ~10 min)

1. **Lag et GitHub-repo** (f.eks. `skoleplan`) og last opp alle filene i denne mappen (behold mappestrukturen, inkludert `.github/`).
2. **Slå på Pages:** Repoet → **Settings → Pages → Build and deployment → Source: GitHub Actions.**
3. **Legg inn API-nøkkelen** (for automatisk plan-tolkning): lag en nøkkel på **console.anthropic.com** (sett gjerne et utgiftstak) → repoet → **Settings → Secrets and variables → Actions → New repository secret** → navn `ANTHROPIC_API_KEY`, lim inn nøkkelen.
4. Gå til **Actions**-fanen, velg *«Bygg og publiser skoleplan»* → **Run workflow** (eller bare vent til nattkjøringen).
5. Når jobben er grønn, ligger sidene her:
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

## Hva skjer automatisk

**Alt – helt uten manuelt arbeid:**
- Daglig sjekk av om planen er endret.
- Når en ny plan oppdages, **leser Claude hele planen** (`llm_plan.py`): timeplan, lekser, «husk gymtøy/turklær», turer med oppmøtetid/-sted, temaer og prøver – og skriver `data/plan.yaml` + nye temaer i `topics.yaml`.
- Side og kalender bygges og publiseres på nytt.
- «Hvilken uke gjelder nå», alle datovarsler og Vigilo-beskjeder.

**Sikkerhetsnett:** hver tolkning valideres (ukenumre stemmer med overskriften, hver skoledag har timeplan eller en hendelse osv.). Består den ikke valideringen, **beholdes forrige plan** – appen viser aldri åpenbart feil info – og du får en GitHub-sak om at automatikken bør sjekkes. Da kan du sende lenken til Claude eller rette filene selv.

> **Krever en Anthropic API-nøkkel** (egen «pay-as-you-go»-konto, *ikke* et Claude-abonnement). Nøkkelen leses bare når planen faktisk endrer seg – typisk noen få kroner i måneden. Se oppsett-steget over. Vil du bytte modell: sett miljøvariabelen `SKOLEPLAN_MODEL` (standard `claude-opus-4-8`).

---

## Filene

| Fil | Hva |
|-----|-----|
| `data/plan.yaml` | Selve toukersplanen (uker, timeplan, husk, lekser, temaer). |
| `data/topics.yaml` | Kuraterte «hva de skal lære»-oppsummeringer, læreplan-lenker og diskusjonsspørsmål per tema. |
| `data/manual.yaml` | Vigilo-beskjeder + hvilke kategorier som skal med i kalenderen. |
| `build.py` | Bygger `site/index.html` + `site/skole.ics`. |
| `check.py` | Daglig endringssjekk – utløser automatisk tolkning. |
| `llm_plan.py` | Leser planen med Claude → full `plan.yaml` (+ `topics.yaml`), med validering. |
| `app_template.html` | Selve web-appen (data settes inn ved bygging). |
| `.github/workflows/site.yml` | Kjører alt automatisk. |

## Overgangen til 10A (skjer automatisk)
Systemet bytter fra 9C til 10A **automatisk 11. august 2026** (se `kilder:` i `data/plan.yaml`). Fra da av følger nattjobben 10A-planen, og den første 10A-planen tolkes automatisk som alle andre. Vil du bytte dato, endre `fra:` under `kilder:`.

## Kjøre lokalt (valgfritt)
```bash
pip install -r requirements.txt
python build.py           # lager site/index.html + site/skole.ics
```
