import logging
import sys
from pathlib import Path

LOG_NAME = "user_api"
LOG_LEVEL = logging.DEBUG
LOG_FILE = Path("logs/app.log")

# Создаём папку для логов, если её нет
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(LOG_NAME)
logger.setLevel(LOG_LEVEL)

# Чтобы избежать дублирования логов при повторных вызовах
logger.propagate = False
if not logger.handlers:
    # Формат логов
    log_format = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.DEBUG)
    stream_handler.setFormatter(log_format)

    # Обработчик для файла
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(log_format)

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)


# Пример использования
if __name__ == "__main__":
    logger.info("Логгер настроен. Можно использовать logger в проекте.")
    logger.debug("Debug-сообщение (увидите только в консоли).")
    logger.info("Info-сообщение (пишется и в файл, и в консоль).")
    logger.warning("Warning-сообщение.")
    logger.error("Error-сообщение.")
    logger.critical("Critical-сообщение.")
