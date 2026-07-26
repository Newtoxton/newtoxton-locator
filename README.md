# Newtoxton-Locator

**Academic / Educational Location Awareness Tool**
<img width="1536" height="1024" alt="locator_app" src="https://github.com/user-attachments/assets/8bdda6a1-26a1-4e98-b677-5918cfbc14e1" />

[![Python](https://img.shields.io/badge/Python-3-brightgreen.svg?style=flat-square)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square)](LICENSE)

Newtoxton-Locator is a proof-of-concept tool that demonstrates how a website can request and obtain precise location data (via the browser Geolocation API) together with basic device information.

It is intended **strictly for educational and authorized security-assessment purposes**.

> **Disclaimer**  
> This tool shows what data a malicious website *could* gather if a user grants location permission.  
> Use it only on systems you own or have explicit written permission to test.  
> Unauthorized use against third parties is illegal.

---

## What it captures

When a target grants location permission, the tool can receive:

**Location data**
- Latitude & Longitude
- Accuracy
- Altitude (when available)
- Direction & Speed (when the device is moving)
- Human-readable address (e.g. `Seattle, Washington | 47.60621, -122.33207`)

**Device information** (no extra permissions required)
- Operating System & Platform
- CPU cores & approximate RAM
- Screen resolution
- GPU vendor / renderer
- Browser name & version
- Public IP address + basic IP geolocation

---

## Why this is different from IP geolocation

| Method              | Typical Accuracy          | Notes                                      |
|---------------------|---------------------------|--------------------------------------------|
| IP Geolocation      | City / ISP level          | Often inaccurate, especially with VPN/proxy |
| Newtoxton-Locator   | ~10–30 m (with GPS)       | Uses the device’s real GPS / location hardware |

On devices without GPS (most laptops) it falls back to IP-based or cached coordinates.

---

## Available Templates

- NatGeo / NearYou
- Google Drive
- WhatsApp
- Telegram

Templates live in the `template/` directory and are selected interactively at runtime.

---

## Requirements

- Python 3
- PHP (built-in server)
- OpenSSH client (for Serveo tunnel)
- `requests` library

---

## Installation

### Kali Linux / Ubuntu / Parrot OS

```bash
git clone https://github.com/Newtoxton/newtoxton-locator.git
cd newtoxton-locator
sudo apt update
sudo apt install python3 python3-pip php
pip3 install requests
