# P2000 Pulse

P2000 Pulse is a lightweight Linux desktop notifier for Dutch P2000 emergency alerts. It
scrapes alarmfase1.nl for region, city or postcode-based incidents and provides a compact
Qt-based GUI for configuring monitoring and viewing recent alerts.

--

## What changed (current behavior)

- Notifications include a clickable action that opens the report location in Google Maps.
- The app now avoids notifying on alerts that already existed when the monitor starts
	(priming logic skips older alerts on Start).
- City lists and network operations run in background threads so the GUI remains responsive.
- System tray usage was removed; when desktop notifications do not support actions the
	app falls back to a non-modal popup so alerts remain visible.
- The app no longer forces a custom theme by default — it uses the system Qt look.

--

## Highlights

- Compact PySide6 GUI for region/city/postcode monitoring.
- Desktop notifications with service-aware icons and an `OK` action that opens Google Maps.
- Background monitoring thread and background city loader keep the UI reactive.
- Persistent configuration at `~/.config/p2000_notifier/config.json`.

--

## Quickstart

Prerequisites: Python 3.10+ and a virtual environment.

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# (optional) for DBus/notification actions on some desktop environments
pip install notify2
# Start the GUI
./run.sh
# or
python3 -m p2000_notifier.main
```

Notes:
- `notify2` provides DBus notification actions on Linux but is not guaranteed to show
	action buttons on every desktop environment; the app includes fallbacks.

--

## Configuration

The GUI exposes options for `region_path`, city selection, `use_postcode`, `postcode`,
`update_interval` (seconds) and `show_notifications`. Use the GUI `Save` button to persist
settings; the config file is written to `~/.config/p2000_notifier/config.json`.

--

## Implementation notes

- GUI: PySide6 (Qt for Python).
- Scraping: `requests` + `beautifulsoup4` + `lxml`.
- Geocoding: Nominatim (and PDOK where available) for address → lat/lon lookup.
- Notifications: the app attempts DBus-based notifications with actions (`notify2`), falls
	back to `notify-send` when available, and finally shows an in-app non-modal popup if
	actions are not supported by the desktop notification server.
- Threading: `MonitorWorker` polls for new alerts on a background thread; `CityLoader`
	fetches city lists in the background to avoid blocking the UI.

--

## Troubleshooting

- If notification action buttons do not appear, try installing `notify2` and ensure your
	desktop environment supports notification actions. As a fallback the app will show a
	popup that lets you open the location in your browser.
- If you see immediate alerts when starting the monitor, that should only happen if an
	alert's timestamp is newer than your system clock; otherwise the app skips older alerts
	on startup.

--

## 💖 Support the Project

All donations go towards your chosen charity. You can pick any charity you'd like, and 5% is retained due to Ko-Fi fees. As a thank you, your name will be listed as a supporter/donor in a GitHub project. Feel free to email me at thedjskywalker@gmail.com for proof! :)

[![Ko-Fi](https://img.shields.io/badge/Ko--Fi-Support%20me-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white)](https://ko-fi.com/nigel1992)
[![PayPal](https://img.shields.io/badge/PayPal-Donate-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://www.paypal.com/donate/?hosted_button_id=KYV9ARF99ZSCE)

---

## Contributing

Contributions welcome. For UI or scraping changes, open an issue so we can coordinate on
rate limits and UX. When submitting PRs, include short notes on how the change was tested
and which desktop environments you validated on.

--

## License

Add a `LICENSE` file to choose an open-source license (MIT recommended).
