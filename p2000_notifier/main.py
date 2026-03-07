def main():
    import sys
    from PySide6.QtWidgets import QApplication
    from .config import Config
    from .gui import MainWindow

    app = QApplication(sys.argv)
    cfg = Config()
    w = MainWindow(cfg)
    w.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
