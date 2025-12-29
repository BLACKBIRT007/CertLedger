from __future__ import annotations
from PySide6 import QtWidgets
import sys
from certledger.app import CertLedgerWindow

def main():
    app = QtWidgets.QApplication(sys.argv)
    win = CertLedgerWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
