# ip_lookup.py

Géolocalisation en lot d'adresses IP via [ip-api.com](http://ip-api.com) — gratuit, sans clé API requise.

---

## Fonctionnalités

- Traitement unitaire ou **batch** (100 IPs/requête)
- **Validation** des IPs avant envoi (format, IPv4/IPv6)
- **Filtre automatique** des IPs privées et réservées (RFC 1918, loopback, CGNAT…)
- **Déduplication** des IPs en entrée
- **Rate limiting** intégré (respect de la limite gratuite : 1000 req/min)
- **Retry automatique** sur erreurs transitoires (429, 5xx)
- Sortie **JSON** ou **CSV** (auto-détecté selon l'extension)
- Données enrichies : pays, ville, ISP, ASN, fuseau horaire, détection proxy/VPN/Tor

---

## Prérequis

- Python 3.8+
- Bibliothèque `requests`

---

## Installation

```bash
# Cloner le dépôt
git clone https://github.com/<votre-repo>/ip_lookup.git
cd ip_lookup

# Créer un environnement virtuel et installer la dépendance
python3 -m venv venv
source venv/bin/activate      # macOS / Linux
# venv\Scripts\activate       # Windows

pip install requests
```

> **macOS (Homebrew)** — Si `pip install` échoue avec `externally-managed-environment`, utilise obligatoirement l'environnement virtuel ci-dessus.

---

## Usage

### Préparer le fichier d'IPs

Créer un fichier `ip.txt` avec une IP par ligne :

```
8.8.8.8
1.1.1.1
208.67.222.222
# ceci est un commentaire, ignoré
192.168.1.1    # IP privée, ignorée automatiquement
```

### Lancer le script

```bash
# Basique — lit ip.txt, écrit output.json
python3 ip_lookup.py

# Fichiers personnalisés
python3 ip_lookup.py -i mes_ips.txt -o resultats.json

# Sortie CSV
python3 ip_lookup.py -i mes_ips.txt -o resultats.csv

# Mode batch (recommandé pour > 100 IPs — beaucoup plus rapide)
python3 ip_lookup.py -i mes_ips.txt --batch -o resultats.json

# Sans activer le venv (macOS / Linux)
venv/bin/python3 ip_lookup.py -i mes_ips.txt -o resultats.json
```

### Arguments

| Argument | Défaut | Description |
|---|---|---|
| `-i`, `--input` | `ip.txt` | Fichier source contenant les IPs (une par ligne) |
| `-o`, `--output` | `output.json` | Fichier de sortie |
| `--batch` | désactivé | Mode batch : 100 IPs par requête |
| `--format` | auto | Forcer le format de sortie : `json` ou `csv` |

---

## Données retournées

| Champ | Description |
|---|---|
| `query` | Adresse IP interrogée |
| `status` | `success` ou `fail` |
| `country` | Pays |
| `countryCode` | Code pays ISO (ex : `SN`) |
| `regionName` | Région / État |
| `city` | Ville |
| `zip` | Code postal |
| `lat` / `lon` | Coordonnées approximatives |
| `timezone` | Fuseau horaire (ex : `Africa/Dakar`) |
| `isp` | Fournisseur d'accès |
| `org` | Organisation |
| `as` | Numéro ASN |
| `asname` | Nom de l'AS |
| `proxy` | Détection proxy |
| `vpn` | Détection VPN |
| `tor` | Détection nœud Tor |
| `hosting` | Hébergeur / datacenter |

---

## Exemple de sortie JSON

```json
[
  {
    "query": "8.8.8.8",
    "status": "success",
    "country": "United States",
    "countryCode": "US",
    "regionName": "California",
    "city": "Mountain View",
    "isp": "Google LLC",
    "org": "Google Public DNS",
    "as": "AS15169",
    "proxy": false,
    "vpn": false,
    "tor": false
  },
  {
    "query": "192.0.2.1",
    "status": "fail",
    "message": "private range"
  }
]
```

---

## Comportement sur les IPs non routables

Les IPs privées, loopback et réservées sont filtrées **avant** l'envoi à l'API :

| Plage | Type | Traitement |
|---|---|---|
| `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` | RFC 1918 (privées) | Ignorée |
| `127.0.0.0/8` | Loopback | Ignorée |
| `169.254.0.0/16` | Link-local | Ignorée |
| `100.64.0.0/10` | CGNAT | Ignorée |
| `224.0.0.0/4` | Multicast | Ignorée |
| `::1` | Loopback IPv6 | Ignorée |
| `fc00::/7` | ULA IPv6 (privées) | Ignorée |

---

## Limites

- **HTTP uniquement** en version gratuite (pas HTTPS) — usage sur réseau interne ou local recommandé
- **1000 requêtes/min** en mode gratuit — le rate limiting intégré gère cela automatiquement
- La **géolocalisation est approximative** (précision ville, pas adresse exacte)
- Les données de détection proxy/VPN/Tor peuvent être **incomplètes** sur le plan gratuit
