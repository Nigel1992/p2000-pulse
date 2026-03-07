"""Minimal PySide6 GUI + system tray monitor for P2000 alerts."""
from __future__ import annotations

import textwrap
import traceback
import re

from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QTextEdit,
    QSystemTrayIcon,
    QMenu,
    QMessageBox,
    QStyle,
    QCheckBox,
)
from PySide6.QtGui import QIcon, QAction, QPixmap, QPainter, QFont, QIntValidator
from PySide6.QtCore import QThread, Signal, QTimer, Qt

from .config import Config
from .scraper import fetch_latest
from .scraper import fetch_region_cities
from .utils import geocode_nominatim, haversine_km


class MonitorWorker(QThread):
    new_alert = Signal(dict)
    log = Signal(str)
    error = Signal(str)

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self._running = False
        self._last_id = None

    def run(self) -> None:
        import time

        self._running = True
        while self._running:
            try:
                # support postcode mode (uses /postcode/<NNNN>/) or region/city mode
                use_postcode = bool(self.config.data.get("use_postcode"))
                if use_postcode:
                    pc = (self.config.data.get("postcode") or "").strip()
                    if not pc:
                        self.log.emit("Postcode mode selected but no postcode configured")
                    else:
                        fetch_path = f"postcode/{pc}"
                        data = fetch_latest(fetch_path)
                        if data:
                            if data.get("id") != self._last_id:
                                self._last_id = data.get("id")
                                self.new_alert.emit(data)
                                self.log.emit(f"New alert: {data.get('message','')[:120]}")
                        else:
                            self.log.emit(f"No calls found for postcode {pc}")
                else:
                    region_path = self.config.data.get("region_path", "").strip()
                    if not region_path:
                        self.log.emit("No region_path configured")
                    else:
                        # If a canonical city path was saved (user selected a city), build a per-city URL
                        city_path = (self.config.data.get("city_path") or "").strip()
                        fetch_path = f"{region_path.strip('/')}/{city_path.strip('/')}" if city_path else region_path
                        data = fetch_latest(fetch_path)
                        if data:
                            if data.get("id") != self._last_id:
                                self._last_id = data.get("id")
                                self.new_alert.emit(data)
                                self.log.emit(f"New alert: {data.get('message','')[:120]}")
                        else:
                            self.log.emit("No calls found for region")
            except Exception as e:
                tb = traceback.format_exc()
                self.error.emit(str(e) + "\n" + tb)
            # wait interval but allow prompt stop
            interval = int(self.config.data.get("update_interval") or 90)
            for _ in range(interval):
                if not self._running:
                    break
                time.sleep(1)
        self.log.emit("Monitor stopped")

    def stop(self) -> None:
        self._running = False
        self.wait(2000)


class MainWindow(QWidget):
    def __init__(self, config: Config):
        super().__init__()
        self.setWindowTitle("P2000 Notifier")
        self.config = config
        self.worker: MonitorWorker | None = None

        self._build_ui()
        self._load_config_to_ui()
        self._create_tray()

    def _build_ui(self) -> None:
        form = QFormLayout()

        # Region selector (pre-populated) and manual override
        self.region_combo = QComboBox()
        # mapping display name -> canonical region path segment used by alarmfase1.nl
        REGION_MAP = {
            "Amsterdam-Amstelland": "Amsterdam-Amstelland",
            "Brabant Noord": "Brabant-Noord",
            "Brabant Zuid-Oost": "Brabant-Zuid-Oost",
            "Drenthe": "Drenthe",
            "Flevoland": "Flevoland",
            "Friesland": "Friesland",
            "Gelderland Midden": "Gelderland-Midden",
            "Gelderland Zuid": "Gelderland-Zuid",
            "Gooi en Vechtstreek": "Gooi-en-Vechtstreek",
            "Groningen": "Groningen",
            "Haaglanden": "Haaglanden",
            "Hollands Midden": "Hollands-Midden",
            "IJsselland": "IJsselland",
            "Kennemerland": "Kennemerland",
            "Limburg Noord": "Limburg-Noord",
            "Limburg Zuid": "Limburg-Zuid",
            "Midden- en West-Brabant": "Midden-en-West-Brabant",
            "Noord- en Oost-Gelderland": "Noord-en-Oost-Gelderland",
            "Noord-Holland Noord": "Noord-Holland-Noord",
            "Rotterdam-Rijnmond": "Rotterdam-Rijnmond",
            "Twente": "Twente",
            "Utrecht": "Utrecht",
            "Zaanstreek-Waterland": "Zaanstreek-Waterland",
            "Zeeland": "Zeeland",
            "Zuid-Holland Zuid": "Zuid-Holland-Zuid",
        }
        for label, path in REGION_MAP.items():
            self.region_combo.addItem(label, path)

        self.load_btn = QPushButton("Load cities")
        self.load_btn.clicked.connect(self._on_load_cities)

        region_h = QHBoxLayout()
        region_h.addWidget(self.region_combo)
        region_h.addWidget(self.load_btn)
        form.addRow("Region:", region_h)

        # City selector (populated after loading cities)
        self.city_combo = QComboBox()
        self.city_combo.setEditable(True)
        # allow user to type a city name or postal code if not listed
        if self.city_combo.lineEdit():
            self.city_combo.lineEdit().setPlaceholderText("Type city or postal code (e.g., 1108)")
            # enforce numeric-only, max-4 when user begins typing digits
            self.city_combo.lineEdit().textEdited.connect(self._on_city_text_edited)
        self.city_combo.setToolTip("Type a 4-digit postal code or select a city from the list")
        self.city_combo.currentTextChanged.connect(self._on_city_selected)
        form.addRow("City (optional):", self.city_combo)

        # manual region path removed (use region selector)

        # address/geocode input removed

        # coordinates removed

        self.radius_input = QDoubleSpinBox()
        self.radius_input.setRange(0.0, 500.0)
        self.radius_input.setDecimals(1)
        self.radius_input.setValue(0.0)
        self.radius_input.setEnabled(False)
        self.radius_input.setToolTip("Radius disabled in this mode")
        form.addRow("Radius (km, disabled):", self.radius_input)

        self.interval_input = QSpinBox()
        self.interval_input.setRange(30, 3600)
        form.addRow("Poll interval (s):", self.interval_input)

        self.notifications_checkbox = QCheckBox("Show desktop notifications")
        form.addRow(self.notifications_checkbox)

        # Postcode mode: allow using /postcode/XXXX/ instead of region/city
        postcode_h = QHBoxLayout()
        self.use_postcode_cb = QCheckBox("Use postcode")
        self.postcode_input = QLineEdit()
        self.postcode_input.setPlaceholderText("1109")
        self.postcode_input.setMaxLength(4)
        self.postcode_input.setEnabled(False)
        # sanitize input to digits only
        self.postcode_input.textEdited.connect(self._on_postcode_edited)
        self.use_postcode_cb.toggled.connect(self._on_use_postcode_toggled)
        postcode_h.addWidget(self.use_postcode_cb)
        postcode_h.addWidget(self.postcode_input)
        form.addRow("Postcode mode:", postcode_h)

        btn_h = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self._on_save)
        self.start_btn = QPushButton("Start Monitor")
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn = QPushButton("Stop Monitor")
        self.stop_btn.clicked.connect(self._on_stop)
        self.stop_btn.setEnabled(False)
        btn_h.addWidget(self.save_btn)
        btn_h.addWidget(self.start_btn)
        btn_h.addWidget(self.stop_btn)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFixedHeight(180)

        v = QVBoxLayout(self)
        v.addLayout(form)
        v.addLayout(btn_h)
        v.addWidget(QLabel("Activity / last alert:"))
        v.addWidget(self.log_text)

    def _create_tray(self) -> None:
        self.tray = QSystemTrayIcon(self)
        icon = self.style().standardIcon(QStyle.SP_ComputerIcon)
        self.tray.setIcon(icon)
        self.tray.setVisible(True)

        # remember default icon so we can temporarily swap to service icons
        self.default_icon = icon

        menu = QMenu()
        show_action = QAction("Show")
        show_action.triggered.connect(self.showNormal)
        quit_action = QAction("Quit")
        quit_action.triggered.connect(self._on_quit)
        menu.addAction(show_action)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)

    def _load_config_to_ui(self) -> None:
        d = self.config.data
        cfg_region = d.get("region_path") or ""
        # try to set combo to the config region if present (stored as canonical path)
        if cfg_region:
            idx = self.region_combo.findData(cfg_region)
            if idx >= 0:
                self.region_combo.setCurrentIndex(idx)
            else:
                # not in predefined list; insert fallback entry with same canonical path
                try:
                    self.region_combo.insertItem(0, cfg_region, cfg_region)
                    self.region_combo.setCurrentIndex(0)
                except Exception:
                    pass
        # load saved city and optional canonical city_path into combo if present
        cfg_city = d.get("city") or ""
        cfg_city_path = d.get("city_path") or ""
        if cfg_city_path:
            # if we have a canonical saved path, insert it at top with its data
            display = cfg_city if cfg_city else cfg_city_path.replace('-', ' ').title()
            try:
                self.city_combo.insertItem(0, display, cfg_city_path)
                self.city_combo.setCurrentIndex(0)
            except Exception:
                pass
        elif cfg_city:
            # no canonical path saved; insert/choose the plain display value
            idxc = self.city_combo.findText(cfg_city)
            if idxc >= 0:
                self.city_combo.setCurrentIndex(idxc)
            else:
                try:
                    self.city_combo.insertItem(0, cfg_city)
                    self.city_combo.setCurrentIndex(0)
                except Exception:
                    pass
            # load postcode mode
            use_pc = bool(d.get("use_postcode"))
            pc = d.get("postcode") or ""
            self.use_postcode_cb.setChecked(use_pc)
            self.postcode_input.setText(pc)
            # enable/disable region controls depending on mode
            self._on_use_postcode_toggled(use_pc)

    def _on_city_text_edited(self, text: str) -> None:
        """If the user types digits, restrict to digits only and max 4 characters.

        Non-digit names (city names) are left untouched.
        """
        if not text:
            return
        # if input begins with a digit, treat as postal code and sanitize
        if re.match(r"^\d", text):
            digits = re.sub(r"\D", "", text)[:4]
            if digits != text:
                # programmatically set the sanitized text
                try:
                    le = self.city_combo.lineEdit()
                    if le:
                        le.setText(digits)
                except Exception:
                    pass
        # nothing else to do here; city text sanitization handled above

    def _save_ui_to_config(self) -> None:
        # region_path: prefer manual override if visible and non-empty, else selected combo's canonical path
        region_val = ""
        # QComboBox stores path in itemData (second parameter)
        data = self.region_combo.currentData() if getattr(self, "region_combo", None) else None
        region_val = data if data else (self.region_combo.currentText() if getattr(self, "region_combo", None) else "")
        self.config.data["region_path"] = region_val
        # store selected city for convenience and save canonical city path if available
        city_val = self.city_combo.currentText() if getattr(self, "city_combo", None) else ""
        city_data = self.city_combo.currentData() if getattr(self, "city_combo", None) else None
        if city_val:
            # if looks like a postal code (starts with digit), store only the 4-digit numeric part
            if re.match(r"^\d", city_val):
                city_val = re.sub(r"\D", "", city_val)[:4]
            self.config.data["city"] = city_val
        else:
            self.config.data.pop("city", None)
        # save canonical city path when the user selected from the scraped list
        if city_data:
            self.config.data["city_path"] = city_data
        else:
            self.config.data.pop("city_path", None)
        # coordinates removed; radius disabled
        self.config.data["radius_km"] = 0.0
        # postcode mode
        use_pc = bool(getattr(self, 'use_postcode_cb', None) and self.use_postcode_cb.isChecked())
        self.config.data["use_postcode"] = use_pc
        if use_pc:
            pc = re.sub(r"\D", "", (self.postcode_input.text() or ""))[:4]
            self.config.data["postcode"] = pc
        else:
            self.config.data.pop("postcode", None)
            self.config.data.pop("use_postcode", None)
        self.config.data["update_interval"] = int(self.interval_input.value())
        self.config.data["show_notifications"] = bool(self.notifications_checkbox.isChecked())
        self.config.save()
        self._log("Config saved")

    def _on_save(self) -> None:
        try:
            self._save_ui_to_config()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save config: {e}")

    def _on_geocode(self) -> None:
        # geocode UI removed
        pass

    def _on_start(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        self._on_save()
        self.worker = MonitorWorker(self.config)
        self.worker.new_alert.connect(self._on_new_alert)
        self.worker.log.connect(self._log)
        self.worker.error.connect(self._on_error)
        self.worker.start()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._log("Monitor started")

    def _on_stop(self) -> None:
        if self.worker:
            self.worker.stop()
            self.worker = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._log("Monitor stopped by user")

    def _on_new_alert(self, data: dict) -> None:
        service = (data.get('service_type') or data.get('service') or '').strip()
        emoji_title = ''
        if service:
            emoji_map = {'ambulance': '🚑', 'politie': '🚓', 'brandweer': '🚒'}
            emoji_title = emoji_map.get(service.lower(), '')
        title = f"{emoji_title} P2000 {data.get('priority_code','')} - {data.get('city','')}"
        # format message
        msg = data.get('message') or data.get('title') or ''
        self._log(textwrap.shorten(msg, width=800, placeholder='...'))
        if self.config.data.get('show_notifications', True):
            # choose a tray message icon by service type
            if service.lower().startswith('ambulance'):
                mi = QSystemTrayIcon.Critical
            elif service.lower().startswith('politie'):
                mi = QSystemTrayIcon.Warning
            else:
                mi = QSystemTrayIcon.Information
            # set a temporary tray icon representing the service
            try:
                svc_icon = self._service_icon(service) if service else None
                if svc_icon:
                    self.tray.setIcon(svc_icon)
                self.tray.showMessage(title, msg, mi, 15000)
                # restore default icon after a short delay
                QTimer.singleShot(5000, lambda: self.tray.setIcon(self.default_icon))
            except Exception:
                # fallback to simple notification
                self.tray.showMessage(title, msg, QSystemTrayIcon.Information, 15000)

    def _on_load_cities(self) -> None:
        # determine canonical region path from the region selector
        region_path = self.region_combo.currentData() or self.region_combo.currentText()
        if not region_path:
            QMessageBox.information(self, "Load cities", "Select a region first.")
            return
        self._log(f"Loading cities for {region_path}...")
        try:
            cities = fetch_region_cities(region_path)
        except Exception as e:
            QMessageBox.warning(self, "Load cities failed", f"Failed to load cities for {region_path}: {e}")
            return
        # preserve any typed-in value so a user-entered postal code isn't lost
        prev = self.city_combo.currentText() if getattr(self, 'city_combo', None) else ''
        self.city_combo.clear()
        if not cities:
            # no city list found; keep previous typed value if present
            if prev:
                self.city_combo.addItem(prev)
                self.city_combo.setCurrentIndex(0)
            else:
                self.city_combo.addItem("All")
            self._log("No cities found or page parsing failed")
        else:
            inserted_prev = False
            # cities may be a list of (display, path) tuples or plain strings (back-compat)
            if cities and isinstance(cities[0], (list, tuple)):
                displays = [d for d, _ in cities]
                if prev and prev not in displays and prev != "All":
                    self.city_combo.addItem(prev)
                    inserted_prev = True
                for disp, token in cities:
                    self.city_combo.addItem(disp, token)
            else:
                if prev and prev not in cities and prev != "All":
                    self.city_combo.addItem(prev)
                    inserted_prev = True
                for c in cities:
                    self.city_combo.addItem(c)
            if inserted_prev:
                self.city_combo.setCurrentIndex(0)
            self._log(f"Loaded {len(cities)} cities for {region_path}")

    def _on_city_selected(self, text: str) -> None:
        # nothing to do when a city is selected (address UI removed)
        return

    def _on_error(self, text: str) -> None:
        self._log("Error: " + text)

    def _on_postcode_edited(self, text: str) -> None:
        # keep only digits, max 4
        if not text:
            return
        digits = re.sub(r"\D", "", text)[:4]
        if digits != text:
            try:
                self.postcode_input.setText(digits)
            except Exception:
                pass

    def _on_use_postcode_toggled(self, checked: bool) -> None:
        # when using postcode, disable region/city controls
        try:
            self.postcode_input.setEnabled(bool(checked))
            self.region_combo.setEnabled(not checked)
            self.load_btn.setEnabled(not checked)
            self.city_combo.setEnabled(not checked)
        except Exception:
            pass

    def _service_icon(self, service: str) -> QIcon | None:
        # render a simple emoji-based icon for the given service
        if not service:
            return None
        emo_map = {'ambulance': '🚑', 'politie': '🚓', 'brandweer': '🚒'}
        emoji = emo_map.get(service.lower(), '')
        if not emoji:
            return None
        try:
            pix = QPixmap(64, 64)
            pix.fill(Qt.transparent)
            painter = QPainter(pix)
            font = QFont()
            font.setPointSize(36)
            painter.setFont(font)
            painter.drawText(pix.rect(), Qt.AlignCenter, emoji)
            painter.end()
            return QIcon(pix)
        except Exception:
            return None

    def _log(self, text: str) -> None:
        from datetime import datetime

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_text.append(f"[{ts}] {text}")

    def _on_quit(self) -> None:
        self._on_stop()
        QApplication.quit()
