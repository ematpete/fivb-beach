#!/usr/bin/env python3
"""Erzeugt data.json für die Beach-Volleyball-Seite aus dem FIVB VIS Web Service.

Quelle: FIVB Volleyball Information System (VIS), https://www.fivb.org/Vis2009/XmlRequest.asmx
Nur Python-Standardbibliothek – kein pip nötig.

Aufruf:   python generate.py            (Saison aus ENV SEASON, Default = aktuelles Jahr)
Ausgabe:  data.json  (wird von index.html geladen)
"""
import concurrent.futures as cf
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

VIS_URL = "https://www.fivb.org/Vis2009/XmlRequest.asmx"
UA = "beach-vis-generate/1.0 (+github pages)"
SEASON = int(os.environ.get("SEASON") or dt.date.today().year)
TODAY = dt.date.today().isoformat()
COUNTRY_FIX = {"01": "Great Britain"}

# ---------------------------------------------------------------- VIS-Zugriff
def vis(request_xml, retries=4):
    """Schickt ein <Request>-XML ans VIS, gibt das geparste Root-Element zurück."""
    data = urllib.parse.urlencode({"Request": request_xml}).encode()
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(VIS_URL, data=data, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return ET.fromstring(resp.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"VIS-Abfrage fehlgeschlagen: {last}")


def num(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def clean_country(c):
    return COUNTRY_FIX.get(c, c)


# ---------------------------------------------------------------- Turniere
# Rauschen, das in aelteren Saisons (vor der "BPT"-Marke ab 2023) mitkommt:
# Jugend-Quali, Zonal-/Satelliten-/Kontinentalverbands-Turniere, Multi-Sport-Games.
AGE_RE = re.compile(r"\bU1[0-9]\b|\bU2[0-9]\b|\bYouth\b|\bJunior\b", re.I)
NOISE_RE = re.compile(
    r"Snow Tour|Satellite|\bZonal\b|Sub[- ]?Zonal|Qualif|Development|Continental Cup|"
    r"\bTest\b|Training|\bAVC\b|\bCAVB\b|\bNORCECA\b|\bCSVP\b|\bASVBF\b|\bEEVZA\b|\bNEVZA\b|"
    r"African Games|Mediterranean.*Games|SEA Games|\bFISU\b|Commonwealth Games|King of the Court",
    re.I)
# Innerhalb der CEV-Sparte bewusst milder als NOISE_RE: "CEV Satellite <Ort>"/"CEV Zonal Event
# <Ort>" waren vor der "CEVP"-Kennung (ab 2023) der Name der regulaeren Erwachsenen-CEV-Tour
# (Aequivalent zum heutigen "CEV Tour") — mit dem allgemeinen NOISE_RE faelschlich als Rauschen
# rausgefiltert, obwohl es keine Jugend-/Qualifikationsturniere waren (empirisch an Teamzahlen
# und fehlenden Alters-Markern verifiziert, z.B. "CEV Zonal Event - Barcelona" 2016, 12 Teams).
CEV_NOISE_RE = re.compile(
    r"Snow Tour|Sub[- ]?Zonal|Qualif|Development|Continental Cup|"
    r"\bTest\b|Training|\bAVC\b|\bCAVB\b|\bNORCECA\b|\bCSVP\b|\bASVBF\b|\bEEVZA\b|\bNEVZA\b|"
    r"African Games|Mediterranean.*Games|SEA Games|\bFISU\b|Commonwealth Games|King of the Court",
    re.I)
# Nationale Verbandstouren (OeVV/DVV): VIS nutzt hier den Laendercode selbst als
# Code-Praefix statt einer Stadt-Abkuerzung (z.B. "MAUT0526" statt "MHAM2025" fuer eine
# echte BPT-Stadt) — zuverlaessiges Unterscheidungsmerkmal unabhaengig vom Turniernamen.
# 2023 alleine nutzte nochmal ein eigenes Zwischenformat mit "NT" im Code selbst (z.B.
# "MAUTNT01" statt "MAUT0123") — ohne das (NT)? fehlte eine komplette Saison ÖVV/DVV-Turniere.
# Vor 2023 (mind. bis 2013 zurueck) lief das Ganze nochmal anders: "N"+Land+laufende Nummer
# statt "M"/"W"+Land (z.B. "NAUT0219" statt "MAUT..."), mit einem eigenen Feld "Gender" pro
# Eintrag statt zwei parallelen M/W-Codes — s. NATIONAL_TOUR_RE-Nutzung in build_events() fuer
# die dafuer noetige andere Paarungslogik (Ort+Datum statt gemeinsamer Ziffern nach M/W).
NATIONAL_TOUR_RE = re.compile(r"^[MWN](AUT|GER)(NT)?\d+$")
NATIONAL_ORG = {"AUT": "OEVV", "GER": "DVV"}
NATIONAL_NAME_PREFIX_RE = re.compile(
    r"^(AUT NT|GER NT|GER RTB)\s*-\s*|"
    r"^(Austrian Beachvolleyball\s*Tour\s*Pro|German Beach Tour|Rock the Beach)\s+", re.I)

# FIVB-Profitour ueber das VIS-Strukturfeld "Type" statt ueber den Turniernamen erkennen: der
# Name ist Marketing und hat sich schon mehrfach geaendert ("BPT Elite16 Doha" 2023-2025,
# "BPT Elite Saquarema" 2026, "Beach Elite Joao Pessoa" ab 2027 - mit dem alten "\bBPT\b"-Check
# fiel 2027 dadurch die komplette Tour raus), der Type-Wert blieb dabei unveraendert.
# 3 = "WorldSeries" und 4 = "WorldChamp" laut VIS-Doku (BeachTournamentType), World Series ist ab
# 2027 die hoechste Stufe ueber Elite. 51-54 sind undokumentiert, aber 2022-2027 durchgaengig
# Elite/Challenge/Futures bzw. das Saisonfinale ("Doha Beach Pro Tour Finals 2022", "BPT Finals
# Doha 2023", "BPT The Finals Doha" - drei Namen fuer dasselbe Format).
# Ueber den Typ statt den Namen fehlten vorher unbemerkt: die komplette WM 2023 ("World
# Championships 2023 - Tlaxcala Mexico"), das Finale 2022 und 16 Futures 2023 ohne BPT-Praefix.
FIVB_TOUR_TYPE = {"3": "World Series", "4": "World Champs", "51": "Elite", "52": "Challenge",
                  "53": "Futures", "54": "Finals"}
# Typen, die wir als internationale FIVB-Tour erwarten wuerden — fallen solche durch classify(),
# warnt main() im Log (s. report_unclassified), statt dass eine Umbenennung still Turniere frisst.
# Dazu jeder unbekannte neue Typ ab 51 (so kamen 51-54 mit der Pro Tour dazu) ausser 55, das
# sind Kontinental-/WM-Qualifikationen (NORCECA, U18-Quali), die bewusst nicht aufgenommen werden.
FIVB_INTL_TYPES = {"0", "1", "2", "3", "4", "32", "33", "38", "39", "40", "41", "42"}
FIVB_IGNORED_TYPES = {"55"}
# Marken-/Stufenwoerter, die vorne im Namen stehen, bevor die Stadt kommt ("Beach World Series
# Dubai", "BPT Futures Coolangatta Beach"). Bewusst wortweise statt als feste Regex je Format:
# kleinere Umbenennungen ("Beach Pro Series ...") ergeben so weiterhin die richtige Stadt.
TOUR_NAME_WORDS = {"bpt", "beach", "fivb", "pro", "tour", "elite", "elite16", "challenge",
                   "future", "futures", "world", "series", "volleyball", "major", "16"}


def tour_city(name):
    # Organisatorische Klammerzusaetze gehoeren nicht zur Stadt ("Cervia (New dates confirmed)") —
    # ausser einer Verschiebung ("Negombo (postponed to 2025)"): das ist fuer die Saison relevant.
    words = re.sub(r"\s*\((?![^)]*postpon)[^)]*\)\s*$", "", name, flags=re.I).split()
    while words and words[0].lower() in TOUR_NAME_WORDS:
        words.pop(0)
    return " ".join(words) or name.strip()


def classify(name, code="", teams=None, season=None, default_city="", vis_type=""):
    """Nur relevante Turniere: FIVB Beach Pro Tour + CEV (+ deren Vorgaenger vor 2023) +
    OeVV/DVV-Nationaltouren + Senior-WM. Sonst None. Rueckgabe: (org, tier, city)."""
    n = name
    if re.search(r"CANCEL", n, re.I):
        return None
    # Ab 2023 (2022 lief ueber die Alt-Heuristik weiter unten und bleibt im Archiv so)
    if season is not None and season >= 2023 and vis_type in FIVB_TOUR_TYPE:
        tier = FIVB_TOUR_TYPE[vis_type]
        if tier == "Elite" and re.search(r"Elite\s*16", n, re.I):
            tier = "Elite16"
        if tier in ("World Champs", "Finals"):
            # Name traegt hier oft keine oder eine schlecht abtrennbare Stadt; DefaultCity ist
            # bei diesen Einzelevents (anders als bei der Tour, s. Kommentar oben) zuverlaessig.
            m_city = re.search(r"\s-\s*(.+)$", n)
            city = (default_city.strip() or (m_city.group(1).strip() if m_city else "")
                    or {"World Champs": "World Championships"}.get(tier, tier))
            return ("FIVB", tier, city)
        return ("FIVB", tier, tour_city(n))
    if re.search(r"\bBPT\b", n):
        tier = ("Elite16" if "Elite16" in n else "Elite" if "Elite" in n else
                "Challenge" if "Challenge" in n else "Futures" if re.search(r"Futures?", n) else "Event")
        city = re.sub(r"^BPT\s+(Elite16|Elite|Challenge|Futures?)\s+", "", n).strip()
        return ("FIVB", tier, city)
    # Senior-WM (ab 2023 nicht mehr "BPT"-getaggt, Name traegt meist keine Stadt — die
    # kommt daher aus DefaultCity). Wichtig fuer die Punkte-Regel (zaehlt fuer Entry/Seeding
    # Points), sonst faellt sie fuer Saisons >= 2023 komplett durchs Raster.
    if re.search(r"FIVB Beach Volleyball World Championships", n, re.I):
        return ("FIVB", "World Champs", default_city.strip() or "World Championships")
    # Nachwuchs-WM (z.B. "FIVB BVB U18 WCHs The Hague") — landet sonst in der allgemeinen
    # AGE_RE-Ausschlussregel weiter unten (dort bewusst fuer Zonal-Qualis/Satelliten gedacht,
    # nicht fuer die eigene FIVB-Flaggschiff-Nachwuchs-WM).
    m_youth = re.search(r"FIVB\s+BVB\s+U(\d{2})\s+WCHs?", n, re.I)
    if m_youth:
        return ("FIVB", "Youth Champs", default_city.strip() or f"U{m_youth.group(1)} World Championships")
    if "CEV Test" in n:
        return None
    if re.search(r"CEV|EuroBeachVolley|European Championship", n, re.I):
        if "EuroBeachVolley" in n:
            city = re.sub(r"\s+[MW]$", "", re.sub(r".*-\s*", "", n)).strip()
            return ("CEV", "EuroBeach", city or "EuroBeachVolley")
        if "European Championship" in n:
            m = re.search(r"U\d\d", n)
            # Nachwuchs-EM (U18/U20/U22) als eigene Stufe, damit sie sich im Frontend getrennt
            # filtern laesst. Die Senioren-EM lief bis 2024 unter dem Namen "European
            # Championships", seit 2025 nennt CEV dieselbe Veranstaltung "EuroBeachVolley" -
            # beides ist dasselbe Turnier, daher hier bewusst dieselbe Stufe wie "EuroBeach".
            if m:
                return ("CEV", "Youth EM", f"{m.group(0)} Europameisterschaft")
            return ("CEV", "EuroBeach", "EuroBeachVolley")
        if "Nations Cup" in n:
            if re.search(r"-\s*(MEN|WOMEN)", n):
                return ("CEV", "Nations Cup", "Nations Cup Finals")
            city = re.sub(r"\s*-\s*pool.*$", "", re.sub(r"^CEV\s+", "", n), flags=re.I).strip()
            return ("CEV", "Nations Cup", city)
        if n.startswith("CEVP"):
            return ("CEV", "CEV Tour", re.sub(r"^CEVP\s*-\s*", "", n).strip())
        # alte CEV-Turnierform (vor 2018): "ECH Final" ist wiederum nur ein weiterer
        # historischer Name derselben Senioren-EM/EuroBeachVolley, "Masters"-Tour explizit,
        # Rest nur wenn kein Jugend-Rauschen (Satellite/Zonal Event sind hier bewusst KEIN
        # Rauschen mehr, s. CEV_NOISE_RE oben)
        if re.search(r"\bECH\b", n) and not AGE_RE.search(n):
            city = re.sub(r"^CEV\s+ECH\s*(Final)?\s*-?\s*", "", n, flags=re.I).strip()
            return ("CEV", "EuroBeach", city or "EuroBeachVolley")
        if re.search(r"\bMasters\b", n, re.I):
            city = re.sub(r"^CEV\s+", "", re.sub(r"\s+Masters\b", "", n, flags=re.I)).strip()
            return ("CEV", "Masters", city)
        if CEV_NOISE_RE.search(n) or AGE_RE.search(n):
            return None
        city = re.sub(r"^CEV\s+(Satellite\s*-?\s*|Zonal Event\s*-?\s*)?", "", n, flags=re.I).strip()
        return ("CEV", "CEV", city)
    # MEVZA (Mitteleuropaeische Volleyball-Zonalverbindung: AUT/SUI/SLO/CRO/CZE/HUN/LUX ...) —
    # nur die Erwachsenen-Turnierserie, Jugend-Zonal-Qualis (U18/U20) explizit ausgeschlossen.
    # Der Name selbst hat sich mehrfach geaendert (nur "Zonal Tour" ist die aktuelle ab ~2024er
    # Form) — aeltere Saisons hiessen "MEVZA - Zonal Event - <Ort>", "MEVZA-Zonal Event-<Ort>"
    # oder sogar "<Ort> MEVZA Zonal" (Ort vor MEVZA) - alle empirisch gegen echte VIS-Daten
    # 2014-2020 verifiziert, DefaultCity ist bei diesen Turnieren leer und daher keine Option.
    if re.search(r"MEVZA", n, re.I) and re.search(r"Zonal", n, re.I) and not AGE_RE.search(n):
        if re.match(r"MEVZA", n, re.I):
            city = re.sub(r"^MEVZA\s*-?\s*Zonal\s*(Tour|Event)?\s*-?\s*", "", n, flags=re.I)
        else:
            city = re.split(r"MEVZA", n, flags=re.I)[0]
        city = re.sub(r"\s*/\s*(Men|Women)\s*$", "", city, flags=re.I).strip(" -")
        return ("MEVZA", "Zonal Tour", city or n.strip())
    # OeVV/DVV-Nationaltouren: erst NACH den BPT/CEV-Namensmustern pruefen, damit ein
    # zufaellig kollidierender Code (z.B. "MGER2025" fuer die echte CEV EuroBeachVolley
    # in Duesseldorf) nicht faelschlich als Nationaltour-Stopp durchrutscht.
    nat_m = NATIONAL_TOUR_RE.match(code)
    if nat_m and not NOISE_RE.search(n) and not AGE_RE.search(n):
        # DVV faehrt zwei eigenstaendige Serien unter demselben Code-Praefix "GER": die
        # Haupttour ("GER NT") und "Rock the Beach" (Kuestenstopps, "GER RTB" bzw. 2023 noch
        # als Klartext "Rock the Beach <Ort>" benannt) - getrennte Stufe, damit sie sich im
        # Frontend wie bei CEV EM/Youth EM separat filtern lassen.
        tier = "Rock the Beach" if re.match(r"GER\s+RTB", n, re.I) or re.search(r"Rock the Beach", n, re.I) else "National"
        city = NATIONAL_NAME_PREFIX_RE.sub("", n).strip() or n.strip()
        return (NATIONAL_ORG[nat_m.group(1)], tier, city)
    # Alte FIVB-Turnierform (vor 2023): kein "BPT"-Tag, Name = reiner Ortsname.
    # Unterscheidung Top-Tour vs. Zonal/Satellit/Quali ueber Hauptfeldgroesse,
    # da der Turniername selbst keine Stufe mehr angibt.
    if NOISE_RE.search(n) or AGE_RE.search(n):
        return None
    # Nur fuer Saisons vor der "BPT"-Marke (ab 2023) noetig – danach ist BPT die
    # verlaessliche Kennung und alles andere bewusst raus.
    if season is not None and season >= 2023:
        return None
    # Nationale Verbandstouren (Brasilien, Estland, Italien, ...) nutzen Codes wie
    # "NBRA0113"/"NEST0113" (Land-Praefix); die echte FIVB-Tour nutzt "M"/"W" + Stadtkuerzel
    # (z. B. "MGST2013"). Nur Letzteres zaehlt als internationaler Tour-Stopp.
    if teams is not None and teams >= 24 and code[:1] in "MW":
        base = code[1:]
        tier = "World Champs" if re.match(r"WCH", base, re.I) or "World Championship" in n else "World Tour"
        return ("FIVB", tier, n.strip())
    return None


def is_cancelled(t):
    """VIS-Turnierstatus 10 = Canceled (laut Fivb.Vis.Model, in der HTML-Doku fehlend). Allein
    nicht verlaesslich: "BPT Futures Songkhla - CANCELLED" steht auf Status 0, "CSVP ... Santiago
    (Cancelado)" auf 1 — daher Status ODER Namenszusatz. Status 11 (Postponed) bleibt bewusst
    drin: der Name traegt dann einen Hinweis wie "(Postponed to 2026)"."""
    return t.get("Status") == "10" or bool(re.search(r"CANCEL", t["Name"], re.I))


def report_unclassified(tournaments):
    """Internationale FIVB-Turniere, die classify() verworfen hat, im Log melden — unter GitHub
    Actions als ::warning::, das im Run-Ueberblick sichtbar ist. Grund: eine neue Namens-/Typ-
    Konvention (zuletzt "BPT" -> "Beach" fuer 2027) liess bisher eine ganze Saison still
    verschwinden, ohne dass es irgendwo auffiel."""
    seen = set()
    for t in tournaments:
        vt = t.get("Type", "")
        if vt in FIVB_IGNORED_TYPES or is_cancelled(t):
            continue
        if not (vt in FIVB_INTL_TYPES or (vt.isdigit() and int(vt) >= 51)):
            continue
        if classify(t["Name"], t.get("Code", ""), num(t.get("NbTeamsMainDraw")), num(t.get("Season")),
                    t.get("DefaultCity", ""), vt):
            continue
        key = (t["Name"].strip(), vt)
        if key in seen:
            continue
        seen.add(key)
        msg = f"nicht klassifiziert: {t['Name'].strip()} (Code {t.get('Code')}, Type {vt})"
        print(f"::warning title=Turnier verworfen::{msg}" if os.environ.get("GITHUB_ACTIONS")
              else f"[generate] WARNUNG {msg}")


def build_events(tournaments):
    """Paart Herren/Damen je Turnier und leitet Status aus dem Datum ab."""
    groups = {}
    for t in tournaments:
        if is_cancelled(t):
            continue
        cl = classify(t["Name"], t.get("Code", ""), num(t.get("NbTeamsMainDraw")), num(t.get("Season")),
                      t.get("DefaultCity", ""), t.get("Type", ""))
        if not cl:
            continue
        org, tier, city = cl
        # "World Championships 2023 - Tlaxcala Mexico": das Land steht im Frontend ohnehin direkt
        # neben der Stadt, sonst stuende es doppelt da.
        country = clean_country(t["CountryName"])
        if tier in ("World Champs", "Finals") and city.endswith(" " + country):
            city = city[:-len(country)].rstrip(" ,")
        code = t["Code"]
        if code[:1] in "MW":
            base = code[1:]
        elif code[:1] == "N":
            # Aeltere OeVV/DVV-Nationaltour-Saisons (vor 2023) nutzen ein "N"+Land-Praefix mit
            # fortlaufender, pro Geschlecht getrennter Nummer statt gemeinsamer Ziffern nach
            # M/W (z.B. "NAUT0219"/"NAUT0319" fuer denselben Innsbruck-Stopp) — die Ziffern
            # selbst taugen hier also nicht als Paarungsschluessel, Ort+Datum schon.
            base = f"N|{t['Name'].strip()}|{t['StartDateMainDraw']}"
        else:
            base = code
        g = groups.setdefault(base, {
            "org": org, "tier": tier, "city": city, "country": clean_country(t["CountryName"]),
            "start": t["StartDateMainDraw"], "end": t["EndDateMainDraw"], "M": None, "W": None})
        g["M" if t["Gender"] == "0" else "W"] = {"no": t["No"], "code": t["Code"]}
        g["start"] = min(g["start"], t["StartDateMainDraw"])
        g["end"] = max(g["end"], t["EndDateMainDraw"])
    events = sorted(groups.values(), key=lambda g: (g["start"], g["city"]))
    for e in events:
        e["status"] = ("finished" if e["end"] < TODAY else
                       "live" if e["start"] <= TODAY <= e["end"] else "upcoming")
    return events


# ---------------------------------------------------------------- Matches
def feeder(s):
    if not s:
        return ""
    m = re.search(r'<(Winner|Loser)\s+NoMatch="(\d+)"', s)
    return (m.group(1)[0] + m.group(2)) if m else ""


MATCH_FIELDS = (
    "NoInTournament TeamAName TeamBName MatchPointsA MatchPointsB LocalDate LocalTime Status "
    "RoundName RoundCode TeamAType TeamBType Court Venue City "
    "TeamAFederationCode TeamBFederationCode TeamAPositionInMainDraw TeamBPositionInMainDraw "
    "Referee1Name Referee1FederationCode Referee2Name Referee2FederationCode "
    "DurationSet1 DurationSet2 DurationSet3 Temperature Humidity NbSpectators "
    "BeginDateTimeUtc EndDateTimeUtc LiveStreamUri BuyTicketsUrl "
    "FastestServeTeamAPlayer1 FastestServeTeamAPlayer2 FastestServeTeamBPlayer1 FastestServeTeamBPlayer2 "
    "NoPlayerA1 NoPlayerA2 NoPlayerB1 NoPlayerB2 ResultType "
    "PointsTeamASet1 PointsTeamBSet1 PointsTeamASet2 PointsTeamBSet2 PointsTeamASet3 PointsTeamBSet3")


def get_matches(no):
    """Alle Matches eines Turniers inkl. Saetze, Dauer, Feeder-Links, Extras, Spieler-Nrn."""
    root = vis(f"<Request Type='GetBeachMatchList' Fields='{MATCH_FIELDS}'>"
               f"<Filter NoTournament='{no}'/></Request>")
    out, venue, city = [], "", ""
    for mm in root.iter("BeachMatch"):
        a = mm.attrib
        sets, durs = [], []
        for i in (1, 2, 3):
            x, y = a.get(f"PointsTeamASet{i}"), a.get(f"PointsTeamBSet{i}")
            if x not in ("", None) and y not in ("", None):
                sets.append([int(x), int(y)])
                durs.append(num(a.get(f"DurationSet{i}")))
        venue = venue or a.get("Venue", "")
        city = city or a.get("City", "")
        refs = []
        for i in (1, 2):
            rn = a.get(f"Referee{i}Name")
            if rn:
                refs.append(f"{rn}|{a.get(f'Referee{i}FederationCode') or ''}")
        sa, sb = a.get("MatchPointsA"), a.get("MatchPointsB")
        if sa in ("", None) and sb in ("", None) and sets:
            # VIS liefert bei manchen (z.B. nie sauber abgeschlossenen Walkover-)Matches die
            # Saetze, aber nie die Matchpunkte selbst nach - aus den Saetzen ableiten, sonst
            # bleibt der Punktestand im Frontend als "undefined" stehen.
            wa = sum(1 for s in sets if s[0] > s[1])
            wb = sum(1 for s in sets if s[1] > s[0])
            if wa != wb:
                sa, sb = str(wa), str(wb)
        rec = {
            "n": int(a["NoInTournament"]), "date": a.get("LocalDate"), "time": a.get("LocalTime"),
            "a": a.get("TeamAName"), "b": a.get("TeamBName"),
            "sa": sa, "sb": sb,
            "rc": a.get("RoundCode"), "rn": a.get("RoundName"), "st": a.get("Status"),
            "sets": sets, "fa": feeder(a.get("TeamAType")), "fb": feeder(a.get("TeamBType")),
            "d": durs, "ca": a.get("TeamAFederationCode"), "cb": a.get("TeamBFederationCode"),
            "crt": a.get("Court"),
            "sda": num(a.get("TeamAPositionInMainDraw")), "sdb": num(a.get("TeamBPositionInMainDraw")),
            "rf": refs,
            # globale VIS-Matchnummer (nicht die turnierinterne NoInTournament) — "No" wird von
            # VIS immer mitgeliefert, auch ohne es in Fields anzufordern. Identisch mit der
            # Match-ID, die volleyballworld.com fuer seine eigene (undokumentierte) Live-API
            # verwendet — als Fallback, wenn VIS selbst noch keinen Punktestand hochgeladen hat.
            "gn": num(a.get("No")),
            # Warum ein Match endete (VIS BeachMatchResultType): 0 regulaer, sonst 1-3 Forfeit,
            # 4-6 Verletzung, 7-9 aus dem Turnier, 10-12 disqualifiziert — je Team A/B/beide.
            # Nur abweichende Werte speichern (0 -> None -> faellt beim Aufraeumen unten weg).
            "rt": num(a.get("ResultType")) or None,
        }
        # optionale Extras (oft leer)
        for src, dst, f in [("Temperature", "temp", float), ("Humidity", "hum", num), ("NbSpectators", "spec", num)]:
            v = a.get(src)
            if v not in ("", None) and v != "0":
                rec[dst] = f(v)
        fs = [num(a.get(f"FastestServeTeam{t}Player{p}")) for t in "AB" for p in "12"]
        if any(fs):
            rec["fs"] = fs
        if a.get("BuyTicketsUrl"):
            rec["ticket"] = a["BuyTicketsUrl"]
        if a.get("BeginDateTimeUtc") and a.get("EndDateTimeUtc"):
            rec["ub"], rec["ue"] = a["BeginDateTimeUtc"], a["EndDateTimeUtc"]
        pa = [num(a.get("NoPlayerA1")), num(a.get("NoPlayerA2"))]
        pb = [num(a.get("NoPlayerB1")), num(a.get("NoPlayerB2"))]
        if any(pa):
            rec["pa"] = pa
        if any(pb):
            rec["pb"] = pb
        # leere Felder entfernen (Groesse sparen)
        for k in [k for k, v in rec.items() if v in ("", None, [])]:
            del rec[k]
        out.append(rec)
    return out, {"venue": venue, "city": city}


# ---------------------------------------------------------------- Spieler
PLAYER_FIELDS = ("No FirstName LastName FederationCode NationalityCode Birthdate Height "
                 "BirthPlace Languages BeachYearBegin BeachCurrentTeam")


def get_player(no):
    try:
        el = next(vis(f"<Request Type='GetPlayer' No='{no}' Fields='{PLAYER_FIELDS}'/>").iter("Player"))
    except Exception:  # noqa: BLE001
        return no, None
    a = el.attrib
    h = num(a.get("Height"))
    bio = {"fn": a.get("FirstName"), "ln": a.get("LastName"), "fed": a.get("FederationCode"),
           "nat": a.get("NationalityCode"), "bd": a.get("Birthdate"),
           "h": round(h / 10000) if h else None, "bp": a.get("BirthPlace"),
           "lg": a.get("Languages"), "yb": a.get("BeachYearBegin"), "tm": a.get("BeachCurrentTeam")}
    return no, {k: v for k, v in bio.items() if v not in ("", None)}


# ---------------------------------------------------------------- Hauptlauf
def main():
    print(f"[generate] Saison {SEASON} · Stand {TODAY}")
    tour = [t.attrib for t in vis(
        "<Request Type='GetBeachTournamentList' "
        "Fields='No Code Name CountryName DefaultCity StartDateMainDraw EndDateMainDraw Gender Type Season NbTeamsMainDraw Status'>"
        f"<Filter Season='{SEASON}'/></Request>").iter("BeachTournament")]
    events = build_events(tour)
    print(f"[generate] {len(events)} relevante Events (FIVB+CEV+ÖVV/DVV)")
    report_unclassified(tour)

    # Ergebnisse fuer gespielte/laufende Events – Herren- UND Damen-Turnier je Event
    todo = []
    for e in events:
        if e["status"] not in ("finished", "live"):
            continue
        if e.get("M"): todo.append(e["M"]["no"])
        if e.get("W"): todo.append(e["W"]["no"])
    print(f"[generate] Ergebnisse fuer {len(todo)} Turniere laden …")

    results, venues, players = {}, {}, set()
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for no, (ms, meta) in zip(todo, ex.map(get_matches, todo)):
            if ms:
                results[no] = ms
                venues[no] = meta
                for m in ms:
                    for p in (m.get("pa", []) + m.get("pb", [])):
                        if p:
                            players.add(p)
    print(f"[generate] {sum(len(v) for v in results.values())} Matches · {len(players)} Spieler")

    out = f"data/{SEASON}.json"
    profiles = {}
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        for no, bio in ex.map(get_player, sorted(players)):
            if bio:
                profiles[str(no)] = bio
    # VIS drosselt bei vielen Anfragen am Stueck zeitweise mit HTTP 403 — get_player() liefert dann
    # still None. Ohne Rueckfall wuerde ein einziger gedrosselter Lauf hunderte Profile aus der
    # Datei loeschen und so committen (lokal beobachtet: 2224 statt 2336 Profile). Bereits bekannte
    # Profile daher aus der bisherigen Datei weiterverwenden.
    missing = [str(p) for p in players if str(p) not in profiles]
    if missing:
        try:
            with open(out, encoding="utf-8") as f:
                prev = json.load(f).get("players", {})
        except (OSError, ValueError):
            prev = {}
        reused = [no for no in missing if no in prev]
        for no in reused:
            profiles[no] = prev[no]
        print(f"[generate] {len(missing)} Profile nicht abrufbar, {len(reused)} aus bisheriger Datei uebernommen")

    data = {"season": SEASON, "generated": TODAY, "events": events,
            "results": results, "venues": venues, "players": profiles}
    os.makedirs("data", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    size = os.path.getsize(out)
    print(f"[generate] {out} geschrieben ({size/1024:.0f} KB) · "
          f"{len(events)} Events, {len(results)} mit Ergebnissen, {len(profiles)} Profile")


if __name__ == "__main__":
    sys.exit(main())
