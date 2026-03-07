def main():
    import sys
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from .config import Config
    from .gui import MainWindow

    app = QApplication(sys.argv)
    # Use high-DPI pixmaps on modern displays
    try:
        app.setAttribute(Qt.AA_UseHighDpiPixmaps)
    except Exception:
        pass
    app.setApplicationName("P2000 Pulse")
    cfg = Config()
    w = MainWindow(cfg)
    w.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
