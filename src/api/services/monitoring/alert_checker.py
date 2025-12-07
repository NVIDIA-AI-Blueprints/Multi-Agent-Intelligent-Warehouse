"""
Background Alert Checker Service

Periodically checks performance metrics and logs alerts.
"""

import asyncio
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class AlertChecker:
    """Background service to check performance alerts periodically."""

    def __init__(self, performance_monitor):
        self.performance_monitor = performance_monitor
        self._running = False
        self._check_task: Optional[asyncio.Task] = None
        self._check_interval = 60  # Check every 60 seconds

    async def start(self) -> None:
        """Start the alert checker background task."""
        if self._running:
            return

        self._running = True
        self._check_task = asyncio.create_task(self._check_loop())
        logger.info("Alert checker started")

    async def stop(self) -> None:
        """Stop the alert checker background task."""
        self._running = False

        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass

        logger.info("Alert checker stopped")

    async def _check_loop(self) -> None:
        """Main loop to check alerts periodically."""
        while self._running:
            try:
                await asyncio.sleep(self._check_interval)
                if self._running:
                    await self._check_alerts()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in alert check loop: {e}")

    async def _check_alerts(self) -> None:
        """Check for performance alerts and log them."""
        try:
            alerts = await self.performance_monitor.check_alerts()

            if alerts:
                for alert in alerts:
                    severity = alert.get("severity", "info")
                    message = alert.get("message", "")
                    alert_type = alert.get("alert_type", "unknown")

                    if severity == "critical":
                        logger.critical(f"🚨 CRITICAL ALERT [{alert_type}]: {message}")
                    elif severity == "warning":
                        logger.warning(f"⚠️  WARNING ALERT [{alert_type}]: {message}")
                    else:
                        logger.info(f"ℹ️  INFO ALERT [{alert_type}]: {message}")

                logger.info(f"Found {len(alerts)} active performance alerts")
            else:
                logger.debug("No active performance alerts")

        except Exception as e:
            logger.error(f"Error checking alerts: {e}")


# Global alert checker instance
_alert_checker: Optional[AlertChecker] = None


def get_alert_checker(performance_monitor):
    """Get or create the global alert checker instance."""
    global _alert_checker
    if _alert_checker is None:
        _alert_checker = AlertChecker(performance_monitor)
    return _alert_checker

