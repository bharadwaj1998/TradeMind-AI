"""
TradeMind AI — Entry Point
Run this file to launch the application:
    python main.py
"""
import sys
import os

# Ensure the project root is on sys.path when run as a script
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QIcon, QFont

from app.config import APP_NAME, APP_VERSION, APP_ORG
from app.database.manager import DatabaseManager
from app.ui.main_window import MainWindow


def main():
    # High-DPI support
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_ORG)

    # Set default font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Initialise database (creates tables if first run)
    db = DatabaseManager()
    db.initialise()

    # Launch main window
    window = MainWindow(db)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
