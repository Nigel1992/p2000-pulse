"""Minimal PySide6 GUI + system tray monitor for P2000 alerts."""
from __future__ import annotations

import textwrap
import traceback
import re
import subprocess
import tempfile
import shutil
import os
from datetime import datetime
import webbrowser
from urllib.parse import quote_plus

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
    QMessageBox,
    QStyle,
    QCheckBox,
)
from PySide6.QtGui import QIcon, QPixmap, QPainter, QFont, QIntValidator, QColor, QBrush, QRadialGradient
from PySide6.QtCore import QThread, Signal, QTimer, Qt, QRect

# Application stylesheet: modern dark theme (neutral grey accents)
STYLE = """
QWidget {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #0b0b0b, stop:1 #1a1a1a);
    color: #e6eef6;
    font-family: "Segoe UI", "Roboto", "Helvetica", "Arial";
    font-size: 10pt;
}
#titleLabel {
    font-size: 20pt;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: 0.4px;
}
#subtitleLabel {
    color: rgba(255,255,255,0.78);
    font-size: 9pt;
}
QPushButton {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #3a3a3a, stop:1 #2d2d2d);
    color: #e6eef6;
    border: 1px solid rgba(255,255,255,0.06);
    padding: 8px 12px;
    border-radius: 8px;
}
QPushButton:disabled { background-color: rgba(255,255,255,0.04); color: rgba(255,255,255,0.5); }
QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #4a4a4a, stop:1 #333333); }
QPushButton#flatButton { background: transparent; color: #cfe9ff; border: none; padding: 0; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.06);
    padding: 6px;
    border-radius: 6px;
    color: #e6eef6;
}
QTextEdit {
    background: rgba(0,0,0,0.18);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 6px;
}
QLabel { color: #dfefff; }
"""

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
        primed = False
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
                            if not primed:
                                # on startup, don't notify existing/older alerts; prime last_id
                                iso = data.get("absolute_time_str") or ""
                                try:
                                    if iso:
                                        dt = datetime.fromisoformat(iso)
                                        try:
                                            if dt.tzinfo:
                                                dt = dt.astimezone()
                                        except Exception:
                                            pass
                                        if dt < datetime.now():
                                            self._last_id = data.get("id")
                                            primed = True
                                            self.log.emit("Monitor started — existing alert skipped")
                                        else:
                                            if data.get("id") != self._last_id:
                                                self._last_id = data.get("id")
                                                self.new_alert.emit(data)
                                                self.log.emit(f"New alert: {data.get('message','')[:120]}")
                                            primed = True
                                    else:
                                        # no timestamp available — just prime and skip notifying
                                        self._last_id = data.get("id")
                                        primed = True
                                except Exception:
                                    self._last_id = data.get("id")
                                    primed = True
                            else:
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
                            if not primed:
                                iso = data.get("absolute_time_str") or ""
                                try:
                                    if iso:
                                        dt = datetime.fromisoformat(iso)
                                        try:
                                            if dt.tzinfo:
                                                dt = dt.astimezone()
                                        except Exception:
                                            pass
                                        if dt < datetime.now():
                                            self._last_id = data.get("id")
                                            primed = True
                                            self.log.emit("Monitor started — existing alert skipped")
                                        else:
                                            if data.get("id") != self._last_id:
                                                self._last_id = data.get("id")
                                                self.new_alert.emit(data)
                                                self.log.emit(f"New alert: {data.get('message','')[:120]}")
                                            primed = True
                                    else:
                                        self._last_id = data.get("id")
                                        primed = True
                                except Exception:
                                    self._last_id = data.get("id")
                                    primed = True
                            else:
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


class CityLoader(QThread):
    """Background thread to fetch city lists so the UI stays responsive."""
    done = Signal(list)
    error = Signal(str)
    started_loading = Signal()
    finished_loading = Signal()

    def __init__(self, region_path: str, timeout: int = 15):
        super().__init__()
        self.region_path = region_path
        self.timeout = timeout

    def run(self) -> None:
        try:
            try:
                self.started_loading.emit()
            except Exception:
                pass
            cities = fetch_region_cities(self.region_path, timeout=self.timeout)
            self.done.emit(cities)
        except Exception as e:
            try:
                self.error.emit(str(e))
            except Exception:
                pass
        finally:
            try:
                self.finished_loading.emit()
            except Exception:
                pass


class MainWindow(QWidget):
    def __init__(self, config: Config):
        super().__init__()
        self.setWindowTitle("P2000 Notifier")
        self.setMinimumSize(720, 520)
        self.config = config
        self.worker: MonitorWorker | None = None
        self._dark = True

        # apply app-wide style and icon
        self._apply_style()
        self.app_icon = QIcon(self._app_pixmap(64))
        self.setWindowIcon(self.app_icon)

        self._build_ui()
        self._load_config_to_ui()
        # system tray removed — no tray will be created
        # store the last notification's map URL so clicks on Qt notifications can open it
        self._last_map_url: str | None = None
        # background city loader thread handle
        self._city_loader: CityLoader | None = None

    def _build_ui(self) -> None:
        form = QFormLayout()

        # Header with app icon and title
        header_h = QHBoxLayout()
        logo_lbl = QLabel()
        logo_pix = self._app_pixmap(56)
        logo_lbl.setPixmap(logo_pix)
        logo_lbl.setFixedSize(56, 56)
        title_v = QVBoxLayout()
        title_lbl = QLabel("P2000 Pulse")
        title_lbl.setObjectName("titleLabel")
        sub_lbl = QLabel("Real-time Dutch emergency alerts")
        sub_lbl.setStyleSheet("color: rgba(255,255,255,0.78); font-size:10pt;")
        title_v.addWidget(title_lbl)
        sub_lbl.setObjectName('subtitleLabel')
        title_v.addWidget(sub_lbl)
        header_h.addWidget(logo_lbl)
        header_h.addLayout(title_v)
        header_h.addStretch()
        # theme is fixed to dark; theme toggle removed

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
        self.load_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))
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
        self.save_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.save_btn.clicked.connect(self._on_save)
        self.start_btn = QPushButton("Start Monitor")
        self.start_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn = QPushButton("Stop Monitor")
        self.stop_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaStop))
        self.stop_btn.clicked.connect(self._on_stop)
        self.stop_btn.setEnabled(False)
        btn_h.addWidget(self.save_btn)
        btn_h.addWidget(self.start_btn)
        btn_h.addWidget(self.stop_btn)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFixedHeight(220)

        v = QVBoxLayout(self)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(12)
        v.addLayout(header_h)
        v.addSpacing(8)
        v.addLayout(form)
        v.addLayout(btn_h)
        v.addWidget(QLabel("Activity / last alert:"))
        v.addWidget(self.log_text)

    # system tray removed; no tray icon or menu is created

    def _apply_style(self) -> None:
        # Theming disabled by user request — do not apply any application stylesheet.
        return

    def _app_pixmap(self, size: int = 64) -> QPixmap:
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        try:
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.Antialiasing)
            rect = pix.rect().adjusted(2, 2, -2, -2)
            grad = QRadialGradient(rect.center(), rect.width() / 2)
            grad.setColorAt(0.0, QColor("#4FC3F7"))
            grad.setColorAt(1.0, QColor("#0288D1"))
            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(rect)
            font = QFont()
            font.setBold(True)
            font.setPointSize(int(size / 3))
            painter.setFont(font)
            painter.setPen(QColor("white"))
            painter.drawText(rect, Qt.AlignCenter, "P2")
            painter.end()
        except Exception:
            pass
        return pix

    def _toggle_theme(self) -> None:
        try:
            app = QApplication.instance()
            if not app:
                return
            if getattr(self, '_dark', True):
                app.setStyleSheet("")
                self._dark = False
            else:
                app.setStyleSheet(STYLE)
                self._dark = True
        except Exception:
            pass

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
        emoji_map = {'ambulance': '🚑', 'politie': '🚓', 'brandweer': '🚒'}
        emoji = emoji_map.get(service.lower(), '') if service else ''
        priority = (data.get('priority_code') or '').strip()
        city = (data.get('city') or '').strip()
        title = f"{emoji} P2000 {priority} — {city}" if (priority or city) else f"{emoji} P2000 Alert"

        # message and timestamp from scraped data (prefer the absolute ISO timestamp)
        msg = (data.get('message') or data.get('title') or '').strip()
        ts = self._format_alert_timestamp(data)
        # compose a clear body that shows when the report occurred
        body = f"Reported: {ts}\n\n{msg}"

        # log a concise entry
        self._log(f"{ts} — {textwrap.shorten(msg, width=500, placeholder='...')}")

        # build a Google Maps link for the report location when possible
        map_url = None
        try:
            lat = data.get('latitude')
            lon = data.get('longitude')
            if lat is not None and lon is not None:
                map_url = f"https://www.google.com/maps/search/?api=1&query={float(lat)},{float(lon)}"
            else:
                parts = []
                addr = (data.get('address') or '').strip()
                pc = (data.get('postalcode') or '').strip()
                city = (data.get('city') or '').strip()
                if addr:
                    parts.append(addr)
                if pc:
                    parts.append(pc)
                if city:
                    parts.append(city)
                if parts:
                    q = ' '.join(parts)
                    map_url = "https://www.google.com/maps/search/?api=1&query=" + quote_plus(q)
                else:
                    # fallback: use the source link if available
                    link = data.get('link')
                    if link:
                        map_url = link
        except Exception:
            map_url = None

        if map_url:
            # Do not include the raw link in notifications; show a short hint instead
            body += "\n\nPress OK to open in Google Maps."
            self._last_map_url = map_url
        else:
            self._last_map_url = None

        if not self.config.data.get('show_notifications', True):
            return

        # determine urgency for the notification and a fallback QMessageBox icon
        if service.lower().startswith('ambulance'):
            urgency = 'critical'
            mb_icon = QMessageBox.Critical
        elif service.lower().startswith('politie'):
            urgency = 'normal'
            mb_icon = QMessageBox.Warning
        else:
            urgency = 'normal'
            mb_icon = QMessageBox.Information

        # try to send a rich notification (notify2/notify-send); create icon image if possible
        icon_path = None
        try:
            icon_path = self._create_notification_image(service, title, ts, msg)
        except Exception:
            icon_path = None

        sent = False
        try:
            sent = self._send_desktop_notification(title, body, icon_path, urgency=urgency, timeout_ms=15000)
        except Exception:
            sent = False

        if not sent:
            try:
                # Fallback to a non-modal QMessageBox so the user still sees the alert
                mb = QMessageBox(self)
                mb.setWindowTitle(title)
                mb.setText(body)
                mb.setIcon(mb_icon)
                mb.setStandardButtons(QMessageBox.Ok)
                mb.setModal(False)
                mb.show()
                # auto-close after timeout
                try:
                    QTimer.singleShot(10000, lambda m=mb: m.close() if m and m.isVisible() else None)
                except Exception:
                    pass
            except Exception:
                pass

        # cleanup temp icon file (if any) after a short delay so the notification can use it
        if icon_path and os.path.exists(icon_path):
            try:
                QTimer.singleShot(10000, lambda p=icon_path: os.remove(p) if os.path.exists(p) else None)
            except Exception:
                try:
                    os.remove(icon_path)
                except Exception:
                    pass

    def _on_load_cities(self) -> None:
        # determine canonical region path from the region selector
        region_path = self.region_combo.currentData() or self.region_combo.currentText()
        if not region_path:
            QMessageBox.information(self, "Load cities", "Select a region first.")
            return
        # avoid concurrent loads
        if getattr(self, '_city_loader', None) and getattr(self._city_loader, 'isRunning', lambda: False)():
            self._log("City load already in progress")
            return

        prev = self.city_combo.currentText() if getattr(self, 'city_combo', None) else ''
        # mark UI busy
        self._log(f"Loading cities for {region_path}...")
        self.load_btn.setEnabled(False)
        self.region_combo.setEnabled(False)
        self.city_combo.setEnabled(False)

        # start background loader
        loader = CityLoader(region_path)
        self._city_loader = loader
        loader.done.connect(lambda cities, rp=region_path, prev=prev: self._on_cities_loaded(cities, rp, prev))
        loader.error.connect(lambda e, rp=region_path: QMessageBox.warning(self, "Load cities failed", f"Failed to load cities for {rp}: {e}"))
        loader.started_loading.connect(lambda: None)
        loader.finished_loading.connect(self._on_cities_load_finished)
        loader.start()

    def _on_city_selected(self, text: str) -> None:
        # nothing to do when a city is selected (address UI removed)
        return

    def _on_cities_loaded(self, cities: list, region_path: str, prev: str) -> None:
        """Handle the loaded cities list on the main thread."""
        try:
            self.city_combo.clear()
            if not cities:
                if prev:
                    self.city_combo.addItem(prev)
                    self.city_combo.setCurrentIndex(0)
                else:
                    self.city_combo.addItem("All")
                self._log("No cities found or page parsing failed")
            else:
                inserted_prev = False
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
        except Exception as e:
            self._log(f"Error updating city list: {e}")

    def _on_cities_load_finished(self) -> None:
        """Re-enable UI after city loading finishes."""
        try:
            self.load_btn.setEnabled(True)
            self.region_combo.setEnabled(True)
            self.city_combo.setEnabled(True)
        except Exception:
            pass
        finally:
            try:
                self._city_loader = None
            except Exception:
                pass

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
        # render a compact circular icon with a colored background and an emoji
        if not service:
            return None
        emo_map = {'ambulance': '🚑', 'politie': '🚓', 'brandweer': '🚒'}
        emoji = emo_map.get(service.lower(), '')
        try:
            size = 64
            pix = QPixmap(size, size)
            pix.fill(Qt.transparent)
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.Antialiasing)
            rect = pix.rect().adjusted(4, 4, -4, -4)
            color_map = {
                'ambulance': QColor('#E53935'),
                'politie': QColor('#1E88E5'),
                'brandweer': QColor('#F4511E')
            }
            bg = color_map.get(service.lower(), QColor('#607D8B'))
            painter.setBrush(QBrush(bg))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(rect)
            font = QFont()
            font.setPointSize(36)
            painter.setFont(font)
            painter.setPen(QColor('white'))
            painter.drawText(rect, Qt.AlignCenter, emoji)
            painter.end()
            return QIcon(pix)
        except Exception:
            return None

    def _format_alert_timestamp(self, data: dict) -> str:
        iso = data.get('absolute_time_str') or ''
        if iso:
            try:
                dt = datetime.fromisoformat(iso)
                try:
                    if dt.tzinfo:
                        dt = dt.astimezone()
                except Exception:
                    pass
                return dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
        date = data.get('date') or ''
        time = data.get('time') or ''
        if date and time:
            return f"{date} {time}"
        if time:
            return time
        if date:
            return date
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    def _create_notification_image(self, service: str, title: str, ts: str, msg: str, size: tuple[int, int] = (420, 140)) -> str:
        w, h = size
        pix = QPixmap(w, h)
        pix.fill(Qt.transparent)
        try:
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.Antialiasing)

            # subtle background
            grad = QRadialGradient(pix.rect().center(), max(w, h) / 1.5)
            grad.setColorAt(0.0, QColor("#0b1a26"))
            grad.setColorAt(1.0, QColor("#071021"))
            painter.fillRect(pix.rect(), QBrush(grad))

            # left circular badge
            circ_size = h - 24
            circ_rect = QRect(12, 12, circ_size, circ_size)
            color_map = {
                'ambulance': QColor('#E53935'),
                'politie': QColor('#1E88E5'),
                'brandweer': QColor('#F4511E')
            }
            emo_map = {'ambulance': '🚑', 'politie': '🚓', 'brandweer': '🚒'}
            bg = color_map.get((service or '').lower(), QColor('#607D8B'))
            emo = emo_map.get((service or '').lower(), '')

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(bg))
            painter.drawEllipse(circ_rect)

            # emoji inside circle
            font = QFont()
            font.setPointSize(int(circ_size * 0.45))
            painter.setFont(font)
            painter.setPen(QColor('white'))
            painter.drawText(circ_rect, Qt.AlignCenter, emo)

            # right side: title, timestamp, short message
            x = circ_rect.right() + 12
            right_w = w - x - 16

            title_rect = QRect(x, 12, right_w, 30)
            font_t = QFont()
            font_t.setBold(True)
            font_t.setPointSize(12)
            painter.setFont(font_t)
            painter.setPen(QColor('#e6eef6'))
            painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, title)

            # timestamp
            font_ts = QFont()
            font_ts.setPointSize(9)
            painter.setFont(font_ts)
            painter.setPen(QColor('#bcdcff'))
            painter.drawText(QRect(x, title_rect.bottom() + 4, right_w, 18), Qt.AlignLeft | Qt.AlignVCenter, ts)

            # message body (shortened)
            font_b = QFont()
            font_b.setPointSize(9)
            painter.setFont(font_b)
            painter.setPen(QColor('#d5e9ff'))
            short = textwrap.shorten(msg.replace('\n', ' '), width=180, placeholder='…')
            painter.drawText(QRect(x, title_rect.bottom() + 26, right_w, h - title_rect.bottom() - 36), Qt.TextWordWrap, short)

            painter.end()
        except Exception:
            pass

        tf = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
        tf.close()
        try:
            pix.save(tf.name)
            return tf.name
        except Exception:
            try:
                os.remove(tf.name)
            except Exception:
                pass
            raise

    def _send_desktop_notification(self, title: str, body: str, icon_path: str | None = None, *, urgency: str = 'normal', timeout_ms: int = 15000) -> bool:
        # Try DBus-backed Python notify (notify2) with an explicit action if available
        try:
            import notify2
            try:
                notify2.init("P2000 Notifier")
                n = notify2.Notification(title, body, icon_path or "")
                urg_map = {
                    'low': getattr(notify2, 'URGENCY_LOW', 0),
                    'normal': getattr(notify2, 'URGENCY_NORMAL', 1),
                    'critical': getattr(notify2, 'URGENCY_CRITICAL', 2),
                }
                n.set_urgency(urg_map.get(urgency, urg_map['normal']))
                n.set_timeout(int(timeout_ms))
                url = getattr(self, '_last_map_url', None)
                if url:
                    try:
                        # add an action labelled 'OK' that opens the URL (matches hint text)
                        def _notify_open_cb(n_obj, action, url=url):
                            try:
                                webbrowser.open(url)
                            except Exception:
                                pass

                        n.add_action('open', 'OK', _notify_open_cb)
                    except Exception:
                        pass
                n.show()
                return True
            except Exception:
                pass
        except Exception:
            pass

        # Fallback: external notify-send (may not support click callbacks)
        try:
            if shutil.which('notify-send'):
                cmd = [
                    'notify-send',
                    title,
                    body,
                ]
                if icon_path:
                    cmd += ['-i', icon_path]
                cmd += ['-u', 'critical' if urgency == 'critical' else 'normal']
                cmd += ['-t', str(timeout_ms)]
                subprocess.run(cmd, check=False)
                return True
        except Exception:
            pass

        return False

    # system tray removed; activation/message handlers are not needed

    def _log(self, text: str) -> None:
        from datetime import datetime

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_text.append(f"[{ts}] {text}")

    def _on_quit(self) -> None:
        self._on_stop()
        QApplication.quit()

    def _on_open_maps_triggered(self) -> None:
        # removed: previously opened Maps from tray menu; kept for compatibility
        return
