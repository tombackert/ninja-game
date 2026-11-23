import io
import sys

from scripts.logger import get_logger


def test_logger_info_output():
    buf = io.StringIO()
    logger = get_logger("test")
    logger.stream = buf  # type: ignore
    logger.info("Hello", "World")
    out = buf.getvalue()
    assert "INFO" in out and "Hello World" in out


def test_logger_follows_sys_stdout(monkeypatch):
    buf = io.StringIO()
    logger = get_logger("test")
    monkeypatch.setattr(sys, "stdout", buf)
    logger.warn("redirected")
    assert "redirected" in buf.getvalue()


def test_logger_without_console(monkeypatch):
    """A windowed app started from Explorer has sys.stdout None."""
    monkeypatch.setattr(sys, "stdout", None)
    get_logger("test").error("dropped, not a crash")


def test_state_manager_starts_without_console(monkeypatch):
    from scripts.state_manager import StateManager

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    StateManager()
