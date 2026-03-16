#!/usr/bin/env python3
"""
ip_lookup.py
Géolocalisation en lot d'adresses IP via ip-api.com (gratuit, sans clé).

Usage :
    python3 ip_lookup.py                        # lit ip.txt, écrit output.json
    python3 ip_lookup.py -i ips.txt             # fichier source personnalisé
    python3 ip_lookup.py -i ips.txt -o res.csv  # sortie CSV
    python3 ip_lookup.py -i ips.txt --batch     # mode batch (100 IPs/requête)

Formats de sortie : json (défaut) ou csv
Limite gratuite ip-api.com : 1000 req/min en HTTP (pas de clé requise)
"""

import re
import csv
import json
import time
import logging
import argparse
import ipaddress
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


API_BASE     = "http://ip-api.com"
SINGLE_URL   = f"{API_BASE}/json/{{ip}}"
BATCH_URL    = f"{API_BASE}/batch"

# Champs demandés à l'API
FIELDS = ",".join([
    "status", "message",
    "query",
    "country", "countryCode", "regionName", "city", "zip",
    "lat", "lon", "timezone",
    "isp", "org", "as", "asname",
    "proxy", "vpn", "tor", "hosting",
])

RATE_LIMIT_DELAY = 0.07   # ~850 req/min — marge de sécurité sous la limite de 1000/min
BATCH_SIZE       = 100    # maximum supporté par ip-api.com
REQUEST_TIMEOUT  = 10     # secondes

# RFC 1918 + loopback + link-local + multicast + CGNAT
PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)



def build_session() -> requests.Session:
    """Session avec retry automatique sur erreurs réseau transitoires."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def is_valid_ip(ip: str) -> bool:
    """Vérifie qu'une chaîne est une adresse IP valide (v4 ou v6)."""
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def is_private(ip: str) -> bool:
    """Retourne True si l'IP est privée / réservée."""
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in PRIVATE_NETWORKS)
    except ValueError:
        return False


def read_ips(path: Path) -> list[str]:
    """
    Lit un fichier d'IPs (une par ligne).
    Ignore les lignes vides, commentaires (#) et IPs invalides.
    Déduplique en conservant l'ordre.
    """
    seen = set()
    valid, skipped_invalid, skipped_private = [], 0, 0

    for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        ip = line.strip()
        if not ip or ip.startswith("#"):
            continue
        if not is_valid_ip(ip):
            log.warning("L%d — IP invalide ignorée : %r", lineno, ip)
            skipped_invalid += 1
            continue
        if is_private(ip):
            log.debug("L%d — IP privée ignorée : %s", lineno, ip)
            skipped_private += 1
            continue
        if ip not in seen:
            seen.add(ip)
            valid.append(ip)

    log.info(
        "IPs chargées : %d valides, %d privées ignorées, %d invalides ignorées",
        len(valid), skipped_private, skipped_invalid,
    )
    return valid


def error_record(ip: str, reason: str) -> dict:
    return {"query": ip, "status": "error", "message": reason}


def lookup_single(session: requests.Session, ip: str) -> dict:
    """Requête unitaire pour une IP."""
    try:
        r = session.get(
            SINGLE_URL.format(ip=ip),
            params={"fields": FIELDS},
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        log.warning("%s — timeout", ip)
        return error_record(ip, "timeout")
    except requests.exceptions.HTTPError as e:
        log.warning("%s — HTTP %s", ip, e.response.status_code)
        return error_record(ip, f"http_{e.response.status_code}")
    except requests.exceptions.RequestException as e:
        log.warning("%s — erreur réseau : %s", ip, e)
        return error_record(ip, "network_error")


def lookup_batch(session: requests.Session, ips: list[str]) -> list[dict]:
    """Requête batch (jusqu'à 100 IPs par appel)."""
    payload = [{"query": ip, "fields": FIELDS} for ip in ips]
    try:
        r = session.post(
            BATCH_URL,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        if r.status_code == 429:
            log.warning("Rate limit atteint — pause 60s")
            time.sleep(60)
            r = session.post(BATCH_URL, json=payload, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        log.warning("Batch timeout — repli en mode unitaire")
        return [lookup_single(session, ip) for ip in ips]
    except requests.exceptions.RequestException as e:
        log.warning("Batch erreur réseau : %s — repli en mode unitaire", e)
        return [lookup_single(session, ip) for ip in ips]


def run_lookups(ips: list[str], batch_mode: bool) -> list[dict]:
    """Orchestre tous les appels API avec rate limiting."""
    session = build_session()
    results = []
    total = len(ips)

    if batch_mode:
        chunks = [ips[i:i + BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]
        for idx, chunk in enumerate(chunks, 1):
            log.info("Batch %d/%d — %d IPs", idx, len(chunks), len(chunk))
            results.extend(lookup_batch(session, chunk))
            if idx < len(chunks):
                time.sleep(RATE_LIMIT_DELAY * BATCH_SIZE)
    else:
        for idx, ip in enumerate(ips, 1):
            if idx % 50 == 0:
                log.info("Progression : %d/%d", idx, total)
            results.append(lookup_single(session, ip))
            if idx < total:
                time.sleep(RATE_LIMIT_DELAY)

    ok    = sum(1 for r in results if r.get("status") == "success")
    fail  = sum(1 for r in results if r.get("status") != "success")
    log.info("Terminé — %d succès, %d échecs", ok, fail)
    return results


CSV_COLUMNS = [
    "query", "status", "message",
    "country", "countryCode", "regionName", "city", "zip",
    "lat", "lon", "timezone",
    "isp", "org", "as", "asname",
    "proxy", "vpn", "tor", "hosting",
]


def write_json(results: list[dict], path: Path) -> None:
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("JSON écrit : %s (%d entrées)", path, len(results))


def write_csv(results: list[dict], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    log.info("CSV écrit : %s (%d lignes)", path, len(results))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Géolocalisation en lot d'adresses IP via ip-api.com"
    )
    parser.add_argument("-i", "--input",  default="ip.txt",     help="Fichier d'IPs source (défaut : ip.txt)")
    parser.add_argument("-o", "--output", default="output.json", help="Fichier de sortie (défaut : output.json)")
    parser.add_argument("--batch", action="store_true",          help="Mode batch : 100 IPs par requête (plus rapide)")
    parser.add_argument("--format", choices=["json", "csv"],     help="Format de sortie forcé (auto-détecté sinon)")
    args = parser.parse_args()

    input_path  = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        log.error("Fichier source introuvable : %s", input_path)
        raise SystemExit(1)

    # Détection du format de sortie
    fmt = args.format
    if not fmt:
        fmt = "csv" if output_path.suffix.lower() == ".csv" else "json"

    ips = read_ips(input_path)
    if not ips:
        log.error("Aucune IP valide trouvée dans %s", input_path)
        raise SystemExit(1)

    log.info(
        "Démarrage — %d IPs, mode %s, sortie %s (%s)",
        len(ips), "batch" if args.batch else "unitaire", output_path, fmt.upper(),
    )

    results = run_lookups(ips, batch_mode=args.batch)

    if fmt == "csv":
        write_csv(results, output_path)
    else:
        write_json(results, output_path)


if __name__ == "__main__":
    main()
