# Beach Volleyball 2026 — FIVB & CEV Kalender + Ergebnisse

Statische Seite (`index.html`), die ihre Daten aus `data.json` lädt.
`data.json` wird von `generate.py` aus dem **FIVB VIS Web Service** erzeugt und
per GitHub Action **stündlich automatisch** aktualisiert. Kein Server nötig.

```
index.html                 → die Seite (lädt data.json, Refresh-Button)
data.json                  → aktuelle Daten (von generate.py erzeugt)
generate.py                → VIS-Abruf → data.json (nur Python-Standardlib)
.github/workflows/update.yml → Cron: erzeugt data.json neu & committet
.nojekyll                  → GitHub Pages liefert alles unverändert aus
```

## Einmal einrichten (ca. 5 Minuten)

1. **Repo anlegen** und diese Dateien pushen:
   ```bash
   cd "fivb-beach"
   git init -b main
   git add .
   git commit -m "Beach VIS – Kalender & Ergebnisse"
   git remote add origin git@github.com:DEINNAME/fivb-beach.git
   git push -u origin main
   ```

2. **GitHub Pages aktivieren:**
   Repo → *Settings* → *Pages* → *Source:* **Deploy from a branch** →
   Branch **main**, Ordner **/(root)** → *Save*.
   Nach ~1 Min ist die Seite unter `https://DEINNAME.github.io/fivb-beach/` live.

3. **Automatische Updates:**
   Repo → *Actions* → ggf. Workflows aktivieren. Der Cron läuft dann stündlich.
   Sofort testen: *Actions* → **VIS-Daten aktualisieren** → **Run workflow**.

4. **(Optional) Eigene Domain** (z. B. `fivb.12ndr.at`):
   *Settings* → *Pages* → *Custom domain* eintragen und beim DNS einen
   `CNAME` auf `DEINNAME.github.io` setzen.

## Lokal testen

```bash
python generate.py          # erzeugt/aktualisiert data.json
python -m http.server 8000  # dann http://localhost:8000 öffnen
```
> Direkt per Doppelklick (`file://`) blockt der Browser das Laden von `data.json`.
> Deshalb den kleinen lokalen Server benutzen (oder einfach GitHub Pages).

## So funktioniert das Update

- Der **⟳ Aktualisieren**-Button auf der Seite lädt `data.json` neu.
- Die **GitHub Action** ruft stündlich `generate.py` auf, schreibt `data.json`
  neu und committet nur bei Änderungen. GitHub Pages veröffentlicht automatisch.
- **Takt ändern:** in `.github/workflows/update.yml` die `cron`-Zeile anpassen
  (z. B. `*/30 * * * *` = alle 30 Min; kürzer als ~5 Min ist bei GitHub-Cron nicht zuverlässig).

## Datenquelle

FIVB Volleyball Information System (VIS) — `GetBeachTournamentList`,
`GetBeachMatchList`, `GetPlayer`. Inoffiziell, ohne Gewähr; keine Verbindung
zu FIVB oder CEV.
