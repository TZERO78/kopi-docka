# Kopi‑Docka

**Robuste Cold‑Backups für Docker‑Umgebungen mit Kopia**

Kopi‑Docka sichert komplette Docker‑Stacks („Backup‑Units“) mit minimaler Downtime. Das Tool stoppt Container kurz, snapshotet Rezepte (Compose/Inspect) und Volumes in ein Kopia‑Repository und startet die Services wieder.

> **Wichtig:** Kopi‑Docka macht **konsequent Cold‑Backups**. Separate, inkonsistente Datenbank‑Dumps sind **nicht** Teil des Workflows.

---

## Features

- 🔒 **Konsistente Cold‑Backups**: Stop → Snapshot → Start.
- 🧩 **Backup‑Units**: Gruppierung nach Compose‑Stacks oder Standalone‑Containern.
- 🧾 **Rezepte**: Compose‑Dateien & `docker inspect` (mit Secret‑Redaktion) werden gesichert.
- 📦 **Volumes**: Tar‑Stream mit Besitzer/ACLs/xattrs, optimiert für Dedupe.
- 🏷️ **Tags & Backup‑IDs**: Alle Snapshots tragen `unit` + `` (Pflicht), damit Restore sauber gruppiert.
- 🧰 **Kopia‑Policies**: Retention (daily/weekly/monthly/yearly) pro Unit werden gesetzt.
- 🧪 **Dry‑Run**: Vollständige Simulation ohne Änderungen.
- 🛟 **Disaster‑Recovery‑Bundle**: Ein gepacktes, verschlüsseltes Paket mit Repo‑Infos & Recovery‑Script.
- 🐧 **systemd‑freundlich**: Daemon + Timer‑Units, Watchdog‑Support, Locking.

---

## Architektur

### 1) Discovery

- Findet alle laufenden Container und Volumes.
- Gruppiert Container zu **Backup‑Units** (Compose‑Stacks bevorzugt, sonst Standalone).
- Ermittelt Compose‑Datei (über Compose‑Label), Mounts, Labels und relevante Umgebungsvariablen.
- Kennzeichnet Datenbank‑Container **nur informativ** (keine separaten DB‑Dumps mehr).

### 2) Backup‑Pipeline (Cold)

- **Backup‑ID** wird pro Lauf erzeugt (z. B. `YYYYMMDDThhmmssZ`), ist **Pflicht** und gruppiert alle Snapshots eines Laufs.
- **Stop** der betroffenen Container (graceful via `docker stop -t <timeout>`).
- **Rezepte sichern**
  - `docker-compose.yml` (falls vorhanden)
  - `docker inspect` je Container; ENV mit Mustern `PASS|SECRET|KEY|TOKEN|API|AUTH` werden zu `***REDACTED***` ersetzt
  - Kopia‑Snapshot mit Tags `{type: recipe, unit, backup_id, timestamp}`
- **Volumes sichern** (parallel bis `parallel_workers`)
  - Tar‑Stream: `tar -cf - --numeric-owner --xattrs --acls --one-file-system --mtime=@0 --clamp-mtime --sort=name [-‑‑exclude …] -C <mountpoint> .`
  - In Kopia via `snapshot create --stdin --stdin-file <virtual-path>`
  - Tags: `{type: volume, unit, volume, backup_id, timestamp, size_bytes}`
- **Start** der Container (Health‑Aware: wartet bei vorhandenem Healthcheck bis `healthy`, sonst kurzer Sleep).
- **Policies**: Pro Unit werden auf `recipes/UNIT`, `volumes/UNIT` Retention‑Policies gesetzt (`keep-daily/weekly/monthly/yearly`).
- **Optional**: Disaster‑Recovery‑Bundle erzeugen und gemäß `recovery_bundle_retention` rotieren.

### 3) Restore (Wizard)

- Listet verfügbare **Restore‑Points** gruppiert nach `(unit, backup_id)`.
- Auswahl eines Restore‑Points → Rezepte werden in ein Arbeitsverzeichnis wiederhergestellt.
- Für **jedes Volume** wird ein sicheres Restore‑Skript erzeugt:
  - Stoppe betroffene Container
  - Sicherheits‑Tar des aktuellen Volumes
  - Restore des Snapshots per Stream in das Ziel‑Volume (inkl. Owner/ACLs/xattrs)
  - Neustart der Container
- **Compose‑Hinweise**: Nur **modernes** `docker compose up -d` wird dokumentiert (keine Legacy‑Fallbacks).
- Hinweise auf redaktierte Secrets in Inspect‑Dumps.

### Tags & Gruppierung

- **Pflicht‑Tags**: `unit`, `backup_id`, `type` (`recipe|volume`), `timestamp`.
- Volumes zusätzlich mit `volume` (+ optional `size_bytes`).
- Der Restore‑Wizard filtert ausschließlich über diese Tags; `backup_id` ist der primäre Gruppierungsschlüssel.

### Fehlertoleranz & Logging

- Fehler je Teilaufgabe werden im Metadata‑Report gesammelt.
- Container werden am Ende **immer** neu gestartet (Best‑Effort), auch bei Fehlern.
- Strukturierte Logs mit Kontext (`unit`, `volume`, `backup_type`).

### Parallelität & Ressourcen

- `parallel_workers = auto` nutzt RAM/CPU‑Heuristik, Obergrenze = CPU‑Kerne.
- **Kein künstlicher Task‑Timeout** – `task_timeout` ist entfernt; bestehende Werte `0` bedeuten „kein Timeout“.

### Grenzen

- Kurzer **Downtime‑Peak** je Unit (Cold‑Backup‑Prinzip).
- Keine inkonsistenten Live‑DB‑Dumps – Quelle der Wahrheit sind die Volumes.

---

## Voraussetzungen

- Linux (systemd empfohlen)
- Docker (Engine & CLI)
- Kopia (CLI)
- `tar`
- Python 3.10+

Prüfen:

```bash
which docker && docker --version
which kopia && kopia --version
which tar
python3 --version
```

---

## Installation

### Über Pip (empfohlen via pipx)

```bash
pipx install .
# oder klassisch
pip install -e .
```

### Binärpfade

Die CLI wird als `kopi-docka` installiert. Prüfe `which kopi-docka`.

---

## Konfiguration

Standard‑Suchpfade (erste gefundene Datei gewinnt):

- Systemweit: `/etc/kopi-docka.conf`
- Benutzer: `~/.config/kopi-docker/config.conf`

### Beispiel `kopi-docka.conf`

```ini
[kopia]
repository_path = /backup/kopia-repo
password = changeme-very-secret
compression = zstd-fastest
encryption = aes256
cache_directory = /var/cache/kopia

[backup]
backup_base_path = /backup/kopi-docka
parallel_workers = auto
stop_timeout = 30
start_timeout = 60
exclude_patterns = ["*.tmp", "*.cache", "lost+found"]
update_recovery_bundle = false
recovery_bundle_path = /backup/recovery
recovery_bundle_retention = 3

[retention]
daily = 7
weekly = 4
monthly = 12
yearly = 2

[logging]
level = INFO
```

Hinweise:

- **parallel\_workers**: `auto` nutzt RAM/CPU‑Heuristik; feste Zahl möglich.
- **exclude\_patterns**: wird an `tar` übergeben (`--exclude`).
- **task\_timeout**: entfällt – es gibt keinen künstlichen Timeout. (Wenn vorhanden und `0`, bedeutet das „kein Timeout“.)
- Datenbanken werden nicht separat gedumpt; die Volumes sind Quelle der Wahrheit.

---

## Schnellstart

1. **Repository initialisieren/verbinden**

```bash
kopi-docka init
```

2. **Units anzeigen**

```bash
kopi-docka list --units
```

3. **Trockenlauf** (ohne Änderungen)

```bash
kopi-docka backup --dry-run
```

4. **Backup starten**

```bash
kopi-docka backup
```

Nach jedem Backup werden Snapshots mit `` + `` getaggt. Policies (Retention) werden pro Unit gesetzt.

---

## Restore (Wizard)

Interaktiven Restore starten:

```bash
kopi-docka restore
```

- Wähle Unit und **Backup‑Punkt (backup\_id)**.
- Wizard:
  - Rezepte wiederherstellen (Compose + Inspect, evtl. Secret‑Platzhalter beachten).
  - Befehle/Skripte für Volume‑Restore erzeugen (inkl. Sicherheits‑Backup des aktuellen Volumes).
  - Hinweise zum Neustart (Compose oder manuell).

**Compose**: Nutze bevorzugt `docker compose up -d` (modern). Legacy `docker-compose` wird nicht mehr dokumentiert.

---

## Disaster‑Recovery‑Bundle

Optional automatisch nach einem erfolgreichen Backup oder manuell erzeugen:

```bash
kopi-docka disaster-recovery
```

Inhalt (verschlüsselt):

- Repo‑Status/Config (`kopia-repository.json`)
- `kopia-password.txt` (nutzt Config‑Passwort)
- `kopi-docka.conf`
- `recover.sh` (automatisches Re‑Onboarding inkl. Repo‑Connect)
- `backup-status.json`
- Begleitdateien: `*.README` (Passwort & Schritte), `*.PASSWORD` (Passwort, 0600)

Rotation gesteuert über `recovery_bundle_retention`.

---

## Systemd‑Integration

**Units schreiben**

```bash
sudo kopi-docka write-units
sudo systemctl daemon-reload
```

**Timer aktivieren (täglich 02:00 mit Zufalls‑Jitter)**

```bash
sudo systemctl enable --now kopi-docka.timer
systemctl status kopi-docka.timer
```

**Daemon (optional, wenn kein Timer):**

```bash
kopi-docka daemon --interval-minutes 1440
```

> Empfehlung: systemd‑Timer benutzen; der Daemon kann zusätzlich laufen und Watchdog bedienen.

Logs:

```bash
journalctl -u kopi-docka --no-pager -n 200
```

---

## Performance & Tuning

- **parallel\_workers**: `auto` nutzt RAM/CPU‑Heuristik; reduziere bei knapper RAM‑Situation.
- **Excludes**: unnötige Pfade/Dateien ausschließen → schneller, kleinere Deltas.
- **Kopia Cache**: `KOPIA_CACHE_DIRECTORY` (Config) auf schnellem Datenträger.
- **Retention**: sinnvoll wählen; Policies werden pro Unit via `kopia policy set` angewandt.

---

## Troubleshooting

**Docker/Kopia gefunden?**

```bash
kopi-docka doctor
which docker && docker --version
which kopia && kopia --version
```

**Repo‑Status & Snapshots**

```bash
kopia repository status
kopia snapshot list --json | jq '.'
```

**Platz prüfen**

```bash
df -h
```

**Berechtigungen**

- Zugriff auf `/var/run/docker.sock` (Gruppe `docker` oder root) sicherstellen.
- Schreibrechte auf `repository_path` und `backup_base_path`.

**Healthchecks**

- Beim Start wartet Kopi‑Docka (falls vorhanden) auf `healthy`; sonst kurzer Sleep.

---

## Sicherheit

- Inspect‑Dumps: Environment‑Variablen mit Muster (`PASS`, `SECRET`, `KEY`, `TOKEN`, `API`, `AUTH`) werden redacted.
- DR‑Bundle ist mit OpenSSL (`aes-256-cbc`, `pbkdf2`) verschlüsselt. Passwort liegt in `*.README`/`*.PASSWORD` – sicher aufbewahren!
- Zugriff auf Docker‑Socket bedeutet Root‑ähnliche Rechte – nur vertrauenswürdigen Usern geben.

---

## FAQ

**Warum keine Live‑/Hot‑Backups von Datenbanken?**\
Cold‑Backups sind konsistent, einfach und robust. Kein Drift, keine Tool‑Matrix, klarer Restore‑Pfad.

**Kann ich einzelne Dateien aus Volumes wiederherstellen?**\
Ja, per `kopia snapshot restore <id> <pfad>` oder Mount‑/Streaming‑Variante (siehe Restore‑Wizard‑Anweisungen/Skripte).

**Wie wähle ich einen älteren Backup‑Stand?**\
Im Restore‑Wizard die passende **backup\_id** wählen. Snapshots sind nach `unit` + `backup_id` gruppiert.

---

## Lizenz & Mitmachen

- Lizenz: MIT (oder passend zu eurem Projekt ergänzen)
- Issues/PRs willkommen ✨

---

## Kurzreferenz

```bash
# Repo einrichten
kopi-docka init

# Units anzeigen
kopi-docka list --units

# Dry‑Run
kopi-docka backup --dry-run

# Backup
kopi-docka backup

# Restore‑Wizard
kopi-docka restore

# DR‑Bundle
kopi-docka disaster-recovery

# systemd‑Units schreiben
sudo kopi-docka write-units
sudo systemctl enable --now kopi-docka.timer
```

