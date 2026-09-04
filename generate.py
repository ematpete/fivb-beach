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


def classify(name, code="", teams=None, season=None, default_city=""):
    """Nur relevante Turniere: FIVB Beach Pro Tour + CEV (+ deren Vorgaenger vor 2023) +
    OeVV/DVV-Nationaltouren + Senior-WM. Sonst None. Rueckgabe: (org, tier, city)."""
    n = name
    if re.search(r"CANCEL", n, re.I):
        return None
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


def build_events(tournaments):
    """Paart Herren/Damen je Turnier und leitet Status aus dem Datum ab."""
    groups = {}
    for t in tournaments:
        cl = classify(t["Name"], t.get("Code", ""), num(t.get("NbTeamsMainDraw")), num(t.get("Season")),
                      t.get("DefaultCity", ""))
        if not cl:
            continue
        org, tier, city = cl
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
    "NoPlayerA1 NoPlayerA2 NoPlayerB1 NoPlayerB2 "
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
        "Fields='No Code Name CountryName DefaultCity StartDateMainDraw EndDateMainDraw Gender Type Season NbTeamsMainDraw'>"
        f"<Filter Season='{SEASON}'/></Request>").iter("BeachTournament")]
    events = build_events(tour)
    print(f"[generate] {len(events)} relevante Events (FIVB+CEV+ÖVV/DVV)")

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

    profiles = {}
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        for no, bio in ex.map(get_player, sorted(players)):
            if bio:
                profiles[str(no)] = bio

    data = {"season": SEASON, "generated": TODAY, "events": events,
            "results": results, "venues": venues, "players": profiles}
    os.makedirs("data", exist_ok=True)
    out = f"data/{SEASON}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    size = os.path.getsize(out)
    print(f"[generate] {out} geschrieben ({size/1024:.0f} KB) · "
          f"{len(events)} Events, {len(results)} mit Ergebnissen, {len(profiles)} Profile")


if __name__ == "__main__":
    sys.exit(main())
