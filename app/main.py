"""Entry point aplikasi MuMu Quick Tuner."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from app.config import load_config
from app.mumu import MuMuClient
from app.ui.main_window import MainWindow
from app.ui.widgets import THEME


def setup_logging(project_root: Path, level: str) -> None:
    log_dir = project_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_dir / "app.log", encoding="utf-8"),
    ]

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        handlers=handlers,
    )


def main() -> int:
    config = load_config()
    setup_logging(config.project_root, config.log_level)
    logger = logging.getLogger(__name__)
    logger.info("Memulai MuMu Quick Tuner")
    logger.info("MuMuManager: %s", config.manager)
    logger.info("Target device: %s (index=%s)", config.vm_name, config.vm_index)

    app = QApplication(sys.argv)
    app.setApplicationName("MuMu Quick Tuner")
    app.setOrganizationName("mumu-quick-tuner")
    app.setStyle("Fusion")
    app.setStyleSheet(THEME)

    client = MuMuClient(config.manager)
    window = MainWindow(config, client)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
