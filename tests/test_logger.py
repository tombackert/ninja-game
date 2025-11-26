import io

from scripts.logger import get_logger


def test_logger_info_output():
    buf = io.StringIO()
    logger = get_logger("test")
    logger.stream = buf  # type: ignore
    logger.info("Hello", "World")
    out = buf.getvalue()
    assert "INFO" in out and "Hello World" in out
