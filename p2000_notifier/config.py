import json
import os

DEFAULT_CONFIG = {
    "region_path": "limburg-zuid/maastricht/",
    "update_interval": 90,
    "radius_km": 10.0,
    "latitude": None,
    "longitude": None,
    "show_notifications": True
}

class Config:
    """Simple JSON-backed config stored in ~/.config/p2000_notifier/config.json"""

    def __init__(self, path: str | None = None):
        if path:
            self.path = path
        else:
            config_dir = os.path.join(os.path.expanduser("~"), ".config", "p2000_notifier")
            os.makedirs(config_dir, exist_ok=True)
            self.path = os.path.join(config_dir, "config.json")
        self.data = DEFAULT_CONFIG.copy()
        self.load()

    def load(self) -> None:
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    # allow partial overrides
                    if isinstance(d, dict):
                        self.data.update(d)
        except Exception:
            # ignore errors and use defaults
            pass

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
