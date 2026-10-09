# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
python3 generate.py                 # regenerate data/<current-year>.json from the VIS API
SEASON=2018 python3 generate.py     # regenerate one specific season
python3 -m http.server 8000         # serve locally → http://localhost:8000
```

`file://` does not work — the browser blocks `fetch('./data/*.json')`, so always use the local
server. `generate.py` uses only the Python standard library (no pip install needed).

There is no build step, no linter, and no test suite. `index.html` is the deployed artifact —
edit it directly. Changes go live via GitHub Pages as soon as they are pushed to `main`.

### Verifying changes without a browser

There is no headless browser runner wired up. The established way to check logic changes is to
extract the relevant function into a standalone script and run it against real data from
`data/*.json` — either with `python3` (reimplementing the logic) or `osascript -l JavaScript`
(running the JS directly). Sanity-check that a change affects the number of rows/cases you
expect, not just that it runs.

Syntax check after editing `index.html` (catches unbalanced braces in the inline script/style):

```bash
python3 - <<'EOF'
import re
c=open('index.html').read()
for tag in ('script','style'):
    for i,s in enumerate(re.findall(rf'<{tag}>(.*?)</{tag}>', c, re.S)):
        print(tag, i, s.count('{')-s.count('}'))
EOF
```

## Architecture

Three files matter: `generate.py` (data), `index.html` (the entire frontend), and
`.github/workflows/update.yml` (the cron that keeps the current season fresh).

### Data pipeline

`generate.py` queries the FIVB VIS SOAP/XML service (`GetBeachTournamentList`,
`GetBeachMatchList`, `GetPlayer`) and writes one self-contained `data/<year>.json` per season:

```
{ season, generated, events[], results{tno: match[]}, venues{tno:{venue,city}}, players{no: bio} }
```

- `events[]` — one entry per tournament *stop*, pairing the men's and women's tournaments:
  `{org, tier, city, country, start, end, status, M:{no,code}, W:{no,code}}`. `org` is one of
  `FIVB`/`CEV`/`OEVV`/`DVV`/`MEVZA`; `status` is `finished`/`live`/`upcoming`.
- `results` is keyed by VIS tournament number (`e.M.no` / `e.W.no`), **not** by event.
- Match records use terse keys to keep the JSON small: `n` (no. in tournament), `a`/`b` (team
  names), `sa`/`sb` (sets won), `ca`/`cb` (federation codes), `rc`/`rn` (round code/name),
  `st` (VIS status; ≥12 = finished, see below), `sets`, `d` (set durations), `sda`/`sdb` (seeds),
  `pa`/`pb` (player numbers), `gn` (**global** VIS match number, distinct from `n`), `rt`
  (VIS ResultType, only if not a normal finish).

The GitHub Action regenerates only the current and next season every 20 minutes and commits
only on change. Archived seasons are never touched — regenerating one is a deliberate manual act.

### `classify()` is the heart of `generate.py`

VIS has no clean "tour tier" field, and its naming/coding conventions have changed repeatedly
over the years. `classify(name, code, teams, season, default_city)` returns `(org, tier, city)`
or `None` (= irrelevant, drop it), and is a stack of empirically-derived special cases:

- **FIVB pro tour (2023+) is classified by the VIS `Type` field, not the name** (`FIVB_TOUR_TYPE`:
  3 World Series, 4 World Champs, 51/52/53 Elite/Challenge/Futures, 54 Finals). The names are
  marketing and keep changing (`BPT Elite16 Doha` → `BPT Elite Saquarema` → `Beach Elite Joao
  Pessoa` in 2027); the name-based check silently dropped the whole 2027 tour, the 2023 World
  Championships and 16 Futures. City comes from stripping brand words (`tour_city()`).
- **`report_unclassified()`** warns (as `::warning::` in GitHub Actions) when a tournament of an
  international FIVB type is dropped. Check the Actions run summary for these after a new season
  appears — that is how the next rename will show up.
- **Order matters.** BPT/CEV name patterns are checked *before* the national-tour code pattern,
  so that e.g. `MGER2025` (CEV EuroBeachVolley in Düsseldorf) is not mistaken for a DVV stop.
- **Pre-2023 FIVB** (incl. 2022, which already has Types 51–53 but stays on the old path so the
  archive does not shift) has no `BPT` marker; the tour is inferred from code shape (`M`/`W` +
  city abbreviation) plus main-draw size ≥ 24.
- **ÖVV/DVV national tours** are identified by code prefix, which has three historical formats:
  `MAUT0126` (2024+), `MAUTNT01` (2023 only), `NAUT0219` (2013–2022, which additionally uses a
  separate `Gender` field instead of parallel M/W codes — hence the different pairing key in
  `build_events()`).
- **`NOISE_RE` vs `CEV_NOISE_RE`**: the general noise filter drops `Satellite`/`Zonal`, but those
  words were the legitimate names of the regular adult CEV tour before 2023, so the CEV branch
  uses a milder regex.

Every one of these branches exists because a real gap was found in real data. Before changing
one, query VIS directly for the affected seasons and inspect the raw names/codes — do not
reason about it from the code alone.

### Frontend (`index.html`)

Single file: inline `<style>`, inline `<script>`, no framework, no bundler. The current
season's JSON is **embedded** in the file as `let DATA = {...}` (line ~886) so the page renders
instantly; `bootstrapSeason()` then silently re-fetches the live file on load.

Key state:

- `DATA` — the active season. `state` — list filters (`{q, org, tiers, country}`).
- `cur` — the open tournament in the drawer, plus `drawerView` (`list`/`chrono`/`seeds`/`ranking`),
  `listPhase` (`quali`/`pool`/`ko`), `bracketMode` (KO shown as bracket, not a separate view),
  `chronoDay`.
- `seasonCache` — all seasons, lazily loaded by `ensureAllSeasonsLoaded()` for cross-season
  head-to-head, player profiles, and points breakdowns.
- Persisted in `localStorage`: `theme`, `lang`, `countryPref`, `genderPref`.

Round classification drives almost every view. `macroOf(rc,rn)` maps a round code to
`quali`/`group`/`inter`/`final`; `roundRank()` orders rounds (finals first); `isPool()`/`isQuali()`
are the primitives. Bracket and list views must filter on the same predicates — several past bugs
came from one path excluding pool/quali codes while another did not.

### i18n

German is the default; `t('deutsch','english')` is called inline at each text site rather than
through a key table. Static markup text is handled once in `applyStaticI18n()`. **Never compare
against a translated string in logic** — a past bug filtered on `result !== 'noch nicht gestartet'`,
which silently broke in English. Compare against language-neutral fields (`cls`, `lastMatch`, …).

### External data sources at runtime

`data/*.json` is the primary source, but the page also calls live endpoints directly from the
browser (all CORS-open):

- **FIVB VIS** (`fivb.org/Vis2009/XmlRequest.asmx`) — the ⟳ Live button and the entry/seed list
  fetch fresher data than the hourly cron. Official, authoritative.
- **`GetImage.asmx`** — player portraits. Always pass `Width=` so FIVB resizes server-side
  (originals are >1MB, resized ~5KB).
- **VIS `GetBeachLive`** (per match, by global match number `gn`, JSON via `Accept:
  application/json`) — official live score; pass the last `Version` and VIS answers
  `{"data":{"noChanges":null}}` if nothing changed. First source in `enrichWithLiveScores()`.
- **volleyballworld.com** (undocumented) — world ranking, live scores when VIS lags behind, match
  photos. Strictly best-effort supplements: every call is wrapped so that failure degrades
  silently and never breaks a feature.

### VIS documentation

The HTML docs at `fivb.org/VisSDK/VisWebService/` are incomplete (e.g. tournament types stop at
50, tournament status lacks Canceled/Postponed). The authoritative source is the official model
package `https://www.fivb.org/VisSDK/Fivb.Vis.Model.zip` — its `Fivb.Vis.Model.xml` lists every
enum value name (`F:Fivb.Vis.Beach.<Enum>.Val_<Name>`), request type and field. Numeric values
are on the HTML page of the same name where it exists. Known values worth remembering:

- Tournament `Type`: 51–55 = ProTourElite16/Challenge/Futures/Finals/WorldChampionshipQualification.
- Tournament `Status`: 10 = Canceled, 11 = Postponed — not reliable alone, names say otherwise
  sometimes, so `is_cancelled()` checks status *or* name.
- Match `Status`: ≥12 means finished (12 Finished, 13 OfficialResult, 14 Corrected, 15 Closed),
  3–11 = set in progress. Some archived matches really are stuck mid-match, hence `decisiveSets`.
- Match `ResultType` (stored as `rt`, only when ≠0): 1–12 = forfeit/injury/out/disqualified for
  team A, B or both (three values per kind).

VIS throttles quickly with HTTP 403 (a few seasons of `generate.py` in a row, or ~4 parallel
requests, were enough). Avoid bulk querying from a local machine.

## Conventions

- **Never commit or push without explicit confirmation from the user**, no matter how small the
  change. Ask first, every time.
- Comments are in German and explain *why*, especially where a non-obvious VIS quirk or a
  previously-fixed bug is involved. Preserve them; they are the institutional memory of this
  codebase. Match that style when adding code.
- Beware VIS byes: a bye is recorded as a *finished* 0:0 match with only one team side present.
  Any code that counts results, derives standings, or decides "still in the draw" must skip
  matches where `isBye(m)`.
- Walkovers may be finished with neither scores nor sets — guard with `Number.isNaN` before
  aggregating, or a single match poisons a whole pool table with `NaN`.
