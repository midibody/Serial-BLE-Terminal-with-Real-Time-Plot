import sys
import asyncio

from PySide6.QtWidgets import QApplication

from terminal import GraphicTerminal

def main():
    # determine mode from command line
    mode = "COM"
    if len(sys.argv) > 1 and sys.argv[1].upper() == "BLE":
        mode = "BLE"

    app = QApplication(sys.argv)
    window = GraphicTerminal(mode=mode)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
