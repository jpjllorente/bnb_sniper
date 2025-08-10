from repositories.action_repository import ActionRepository
from models.token import Token
from utils.log_config import log_function

_VALID_TYPES = {"compra", "venta"}  # mantenemos tus valores en español

class TelegramController:
    def __init__(self, repository: ActionRepository | None = None) -> None:
        self.repo = repository or ActionRepository()

    @log_function
    def registrar_accion(self, token: Token, tipo: str) -> None:
        """
        Registra una nueva acción pendiente ('compra' o 'venta').
        """
        tipo_limpio = (tipo or "").strip().lower()
        if tipo_limpio not in _VALID_TYPES:
            raise ValueError(f"Tipo de acción inválido: {tipo}")
        self.repo.registrar_accion(token.pair_address, tipo_limpio)

    @log_function
    def autorizar_accion(self, pair_address: str) -> None:
        self.repo.autorizar_accion(pair_address)

    @log_function
    def cancelar_accion(self, pair_address: str) -> None:
        self.repo.cancelar_accion(pair_address)

    @log_function
    def obtener_estado(self, pair_address: str) -> str | None:
        return self.repo.obtener_estado(pair_address)

    @log_function
    def obtener_tipo(self, pair_address: str) -> str | None:
        # Pasarela directa al repo; tu ActionRepository ya lo tiene
        return self.repo.obtener_tipo(pair_address)
