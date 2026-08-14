# Beach Volleyball 2013–2026 — FIVB & CEV Kalender + Ergebnisse

Statische Seite (`index.html`), die ihre Daten pro Saison aus `data/<jahr>.json`
lädt (Saison-Auswahl oben rechts). Jede Datei wird von `generate.py` aus dem
**FIVB VIS Web Service** erzeugt. Die aktuelle Saison wird per GitHub Action
**stündlich automatisch** aktualisiert, ältere Saisons sind abgeschlossen und
werden nicht mehr neu erzeugt. Kein Server nötig.

```
index.html                 → die Seite (Saison-Auswahl, lädt data/<jahr>.json, Refresh-Button)
data/<jahr>.json           → Daten je Saison (von generate.py erzeugt), 2013–heute
generate.py                → VIS-Abruf → data/<jahr>.json (nur Python-Standardlib)
.github/workflows/update.yml → Cron: erzeugt die aktuelle Saison neu & committet
.nojekyll                  → GitHub Pages liefert alles unverändert aus
```

## Vor 2023: heuristische Klassifizierung

Die "Beach Pro Tour"-Marke (`BPT Elite16/Challenge/Futures`) gibt es erst seit
2023. Für ältere Saisons hat das VIS keine Turnier-Stufe im Namen — Turniere
heißen schlicht nach der Austragungsstadt. `generate.py` grenzt dort die
internationale FIVB-Tour über zwei Signale ab:

- **Turniercode:** internationale Tour-Stopps nutzen `M`/`W` + Stadtkürzel
  (z. B. `MGST2013` = Gstaad); nationale Verbandstouren nutzen `N` + Länderkürzel
  (z. B. `NBRA0113` = Brasilien-Landestour) und werden ausgeschlossen.
- **Hauptfeldgröße:** mind. 24 Teams (`NbTeamsMainDraw`), sonst Zonal-/Satelliten-
  /Qualifikationsniveau.

Dazu kommt eine Ausschlussliste für Jugend- (U17–U22), Schnee-Volleyball-,
Satelliten- und Multi-Sport-Events (Games). Das ist ein Best-Effort-Ansatz,
keine exakte Rekonstruktion der historischen Tour-Stufen — einzelne Ein-/
Ausordnungen können abweichen. CEV-Events vor 2023 werden analog behandelt
(`Masters`-Tour, `ECH`-Finals als EM erkannt; Schnee-Tour/Satellite/Jugend-Pools
ausgeschlossen).

## Neue Saison zum Archiv hinzufügen

Am Jahreswechsel einmalig die abgeschlossene Vorsaison ins Archiv aufnehmen:

```bash
SEASON=2027 python generate.py   # erzeugt data/2027.json
git add data/2027.json && git commit -m "data: Saison 2027 archivieren"
```

Die Saison-Auswahl im Frontend berechnet den Jahresbereich automatisch
(2013 bis aktuelles Kalenderjahr) — kein Eintrag in `index.html` nötig.

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

4. **(Optional) Eigene Domain** (z. B. `test.fivb.com`):
   *Settings* → *Pages* → *Custom domain* eintragen und beim DNS einen
   `CNAME` auf `DEINNAME.github.io` setzen.

## Lokal testen

```bash
python generate.py          # erzeugt/aktualisiert data/<aktuelles-jahr>.json
python -m http.server 8000  # dann http://localhost:8000 öffnen
```
> Direkt per Doppelklick (`file://`) blockt der Browser das Laden von `data/*.json`.
> Deshalb den kleinen lokalen Server benutzen (oder einfach GitHub Pages).

## So funktioniert das Update

- Der **⟳ Aktualisieren**-Button lädt die Datei der aktuell gewählten Saison neu.
- Die **GitHub Action** ruft stündlich `generate.py` auf, schreibt die Datei der
  laufenden Saison (`data/<jahr>.json`) neu und committet nur bei Änderungen.
  GitHub Pages veröffentlicht automatisch. Archiv-Saisons werden dabei nicht
  angefasst.
- **Takt ändern:** in `.github/workflows/update.yml` die `cron`-Zeile anpassen
  (z. B. `*/30 * * * *` = alle 30 Min; kürzer als ~5 Min ist bei GitHub-Cron nicht zuverlässig).

## Datenquelle

FIVB Volleyball Information System (VIS) — `GetBeachTournamentList`,
`GetBeachMatchList`, `GetPlayer`. Inoffiziell, ohne Gewähr; keine Verbindung
zu FIVB oder CEV.
