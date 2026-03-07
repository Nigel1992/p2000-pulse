# P2000 Pulse

P2000 Pulse is a polished Linux desktop notifier for Dutch P2000 emergency alerts. It scrapes
alarmfase1.nl for region, city or postcode-based incidents and shows rich system-tray
notifications with a modern Qt-based UI.

--

## Highlights

- Modern, dark-themed PySide6 GUI with a compact dashboard and tray integration.
- Region and city selectors (scrapes alarmfase1.nl region pages).
- Optional postcode mode for direct postcode monitoring.
- Desktop notifications with service-aware icons (ambulance, politie, brandweer).
- Persistent configuration stored in `~/.config/p2000_notifier/config.json`.

--

## Quickstart (developer)

Prerequisites: Python 3.10+ and a virtual environment.

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Start the GUI
python3 -m p2000_notifier.main
```

Alternatively (developer-friendly):

```bash
# Run from repo root without installing package
python -c "import sys; sys.path.insert(0, '$(pwd)'); from p2000_notifier.main import main; main()"
```

The first run creates the config file at `~/.config/p2000_notifier/config.json`.

--

## Configuration

Configurable settings include `region_path`, `city`/`city_path`, `use_postcode`, `postcode`,
`update_interval` (seconds) and `show_notifications`.

Use the GUI `Save` button to persist changes.

--

## Development notes

- GUI: implemented with PySide6 (Qt for Python). Styles are applied via an application
	stylesheet for a modern look without extra dependencies.
- Scraping uses `requests` + `beautifulsoup4` + `lxml`.
- Geocoding fallback uses Nominatim; respect their usage policy.

--

## Contributing

Contributions are welcome. For changes to the UI or scraping, please open an issue first
so we can discuss design and rate limits for scraping.

--

## License

This repository currently contains a scaffold. Add a `LICENSE` file to choose an
open-source license (MIT recommended).

--

Thank you for trying P2000 Pulse — enjoy the new UI! If you'd like, I can also
add a small screenshot example or package an AppImage for easier distribution.
