# orchestrators/monitor_orchestrator.py
from utils.logger import logger_manager, log_function
import os
import time

logger = logger_manager.setup_logger(__name__)

class MonitorOrchestrator:
    def __init__(self, action_repo, autobuy_controller, autosell_controller, monitor_repo, price_service=None):
        """
        :param action_repo: Repositorio de acciones (acciones pendientes, aprobadas, procesadas)
        :param autobuy_controller: Controlador que ejecuta compras
        :param autosell_controller: Controlador que ejecuta ventas
        :param monitor_repo: Repositorio que guarda el estado de monitorización
        :param price_service: Servicio para obtener precios en tiempo real (opcional)
        """
        self.actions = action_repo
        self.autobuy = autobuy_controller
        self.autosell = autosell_controller
        self.monitor = monitor_repo
        self.price_service = price_service

        # Criterios de venta desde entorno
        self.take_profit_pct = float(os.getenv("TAKE_PROFIT_PCT", "50"))   # por defecto +50%
        self.stop_loss_pct = float(os.getenv("STOP_LOSS_PCT", "-20"))      # por defecto -20%

    @log_function
    def run(self):
        """Ejecuta todas las tareas del orquestador."""
        self._procesar_autorizadas()
        self._actualizar_monitoreos_activos()
        self._procesar_ventas_automaticas()

    def _procesar_autorizadas(self):
        """Ejecuta compra y añade a monitorización las acciones aprobadas."""
        aprobadas = self.actions.list_all(estado="aprobada", limit=50)
        if not aprobadas:
            return

        logger.info(f"Procesando {len(aprobadas)} acciones aprobadas...")

        for r in aprobadas:
            pair = r["pair_address"]
            tipo = r["tipo"]
            if str(tipo).lower() != "compra":
                logger.debug(f"Saltando {pair}: tipo {tipo} no es compra")
                continue

            try:
                logger.info(f"Ejecutando compra autorizada para {pair}")
                result = self.autobuy.ejecutar_compra_por_pair(pair)

                if result and result.get("ok"):
                    tx_hash = result.get("tx_hash")
                    token_address = r.get("token_address")

                    self.monitor.iniciar(
                        pair_address=pair,
                        token_address=token_address,
                        tx_hash=tx_hash,
                        entry_price=result.get("entry_price", 0.0),
                        cantidad=result.get("cantidad", 0.0),
                        timestamp=int(time.time())
                    )

                    self.actions.marcar_procesada(pair)
                    logger.info(f"Compra ejecutada y monitor iniciada para {pair}")
                else:
                    self.actions.marcar_error(pair, motivo="Compra fallida")
                    logger.warning(f"Compra fallida para {pair}")
            except Exception as e:
                logger.exception(f"Error procesando aprobada {pair}: {e}")
                self.actions.marcar_error(pair, motivo=str(e))

    def _actualizar_monitoreos_activos(self):
        """Actualiza precios y PnL de las posiciones en monitorización."""
        activos = self.monitor.listar_activos(limit=100)
        if not activos:
            return

        logger.debug(f"Actualizando {len(activos)} monitoreos activos...")

        for pos in activos:
            try:
                pair_addr = pos["pair_address"]
                entry_price = pos.get("entry_price", 0.0)

                # Obtener precio actual
                current_price = None
                if self.price_service:
                    current_price = self.price_service.get_price_by_pair(pair_addr)
                else:
                    current_price = pos.get("last_price", 0.0)

                # Calcular PnL %
                pnl_pct = 0.0
                if current_price and entry_price:
                    pnl_pct = ((current_price - entry_price) / entry_price) * 100

                # Actualizar en DB
                self.monitor.actualizar_estado(
                    pair_address=pair_addr,
                    last_price=current_price,
                    pnl_percent=pnl_pct,
                    timestamp=int(time.time())
                )

                logger.debug(f"[{pair_addr}] Precio={current_price:.8f} | PnL={pnl_pct:.2f}%")
            except Exception as e:
                logger.exception(f"Error actualizando monitoreo {pos}: {e}")

    def _procesar_ventas_automaticas(self):
        """Vende automáticamente posiciones que cumplen criterios de salida."""
        activos = self.monitor.listar_activos(limit=100)
        if not activos:
            return

        for pos in activos:
            try:
                pair_addr = pos["pair_address"]
                token_addr = pos["token_address"]
                entry_price = pos.get("entry_price", 0.0)
                cantidad = pos.get("cantidad", 0.0)
                pnl_pct = pos.get("pnl_percent", 0.0)

                # Verificar criterios de venta
                if pnl_pct >= self.take_profit_pct:
                    motivo = f"Take Profit alcanzado (+{pnl_pct:.2f}%)"
                elif pnl_pct <= self.stop_loss_pct:
                    motivo = f"Stop Loss alcanzado ({pnl_pct:.2f}%)"
                else:
                    continue  # no vende

                logger.info(f"[VENTA AUTO] {pair_addr} {motivo}")

                # Ejecutar venta
                result = self.autosell.ejecutar_venta_por_pair(pair_addr, cantidad)
                if result and result.get("ok"):
                    self.monitor.marcar_vendido(
                        pair_address=pair_addr,
                        tx_hash=result.get("tx_hash"),
                        pnl_percent=pnl_pct,
                        motivo=motivo
                    )
                    logger.info(f"Venta ejecutada para {pair_addr}: {motivo}")
                else:
                    logger.warning(f"Venta fallida para {pair_addr}: {motivo}")

            except Exception as e:
                logger.exception(f"Error procesando venta automática {pos}: {e}")
