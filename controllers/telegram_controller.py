from repositories.action_repository import ActionRepository
from models.token import Token
from utils.logger import log_function

class TelegramController:
    def __init__(self, repository: ActionRepository | None = None) -> None:
        self.repo = repository or ActionRepository()

    @log_function
    def registrar_accion(self, token: Token, tipo: str) -> None:
        """
        Registra una nueva acción pendiente ('compra' o 'venta').
        """
        self.repo.registrar_accion(token.pair_address, tipo)

    @log_function
    def autorizar_accion(self, pair_address: str) -> None:
        """
        Marca una acción como 'aprobada'.
        """
        self.repo.autorizar_accion(pair_address)

    @log_function
    def cancelar_accion(self, pair_address: str) -> None:
        """
        Marca una acción como 'cancelada'.
        """
        self.repo.cancelar_accion(pair_address)

    @log_function
    def obtener_estado(self, pair_address: str) -> str | None:
        """
        Devuelve el estado actual de la acción.
        """
        return self.repo.obtener_estado(pair_address)