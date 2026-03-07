# P2000 Pulse

P2000 Pulse is a lightweight Linux desktop notifier for P2000 (Netherlands emergency alerts).
It scrapes alarmfase1.nl for region, city or postcode-based alerts and shows desktop notifications.

## Quickstart

Requirements: Python 3.10+, a virtual environment, and the project `requirements.txt`.

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Run the GUI (from project root):
python -c "import sys; sys.path.insert(0, '$(pwd)'); from p2000_notifier.main import main; main()"
```

Notes:
- If you prefer, install `gh` (GitHub CLI) to create and push the repo easily.
- The app stores settings in `~/.config/p2000_notifier/config.json`.

## Features

- Select region and load cities (uses alarmfase1.nl region pages)
- Optional postcode mode (monitors /postcode/<NNNN>/)
- System tray notifications with simple ambulance/police/brandweer icons

## Sources / Acknowledgements

This project was developed using and inspired by the following sources:

- alarmfase1.nl — the website scraped for P2000 alerts: https://www.alarmfase1.nl/
- MalumAtire832/P2000 (GitHub) — reference implementation and research: https://github.com/MalumAtire832/P2000
- malosaaa/ha-p2000 (Home Assistant integration) — scraping patterns and ideas: https://github.com/malosaaa/ha-p2000
- PDOK Locatieserver / BAG — authoritative Dutch address data: https://www.pdok.nl/
- Nominatim (OpenStreetMap) — geocoding fallback: https://nominatim.org/
- BeautifulSoup — HTML parsing: https://www.crummy.com/software/BeautifulSoup/
- PySide6 (Qt for Python) — GUI toolkit: https://pypi.org/project/PySide6/
- requests — HTTP client: https://requests.readthedocs.io/
- lxml — XML/HTML parser used by BeautifulSoup: https://lxml.de/

If you re-use or redistribute parts of this project, please check the original
source licenses of the referenced projects.

## Contributing

Contributions welcome. Open an issue or PR after creating a fork.

## License

No license chosen yet — add a `LICENSE` file to open-source under your preferred terms.
# P2000 Notifier (Linux)

Lightweight Linux desktop app that scrapes alarmfase1.nl for P2000 alerts, runs in the background (system tray) and notifies you of new incidents within a configured radius.

Features
- Enter `region_path` (example: `limburg-zuid/maastricht/`) to monitor.
- Set your location (lat/lon or geocode an address) and radius in km.
- Background polling with desktop notifications via system tray.

Requirements
- Python 3.10+
- See `requirements.txt`.

Quick start

1. Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

2. Run the app:

```bash
python3 -m p2000_notifier.main
```

The first run creates a config at `~/.config/p2000_notifier/config.json`.

Notes
- The app scrapes HTML pages on alarmfase1.nl  respect their terms of service and use a reasonable poll interval (default 90s).
- Geocoding uses Nominatim (OpenStreetMap). Follow Nominatim usage policy if you will geocode frequently.

License: MIT (project scaffold)
