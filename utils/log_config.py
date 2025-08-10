
from utils.logger import logger_manager, log_function

import os

# Activar Telegram si está definido en entorno
ENABLE_TELEGRAM = os.getenv("LOG_TELEGRAM_ERRORS", "False").lower() == "true"

# Decorador para logging de funciones
log_function = log_function

# Logger ya configurado para el módulo actual
# NOTA: se recomienda sobrescribirlo por módulo con __name__ si se desea
logger = logger_manager.setup_logger("main")
