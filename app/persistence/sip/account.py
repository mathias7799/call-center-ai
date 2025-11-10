"""SIP account management."""

import asyncio
from typing import TYPE_CHECKING, Any

from app.helpers.config_models.telephony import SipModel
from app.helpers.logging import logger

if TYPE_CHECKING:
    from app.persistence.sip.call import SipCall


class SipAccount:
    """
    SIP account handler for registration and authentication.

    Manages:
    - SIP registration with gateway
    - Authentication (digest)
    - Incoming call handling
    - Call state tracking
    """

    def __init__(self, config: SipModel, endpoint: Any):  # pj.Endpoint
        """
        Initialize SIP account.

        Args:
            config: SIP configuration
            endpoint: PJSIP Endpoint instance
        """
        self.config = config
        self.endpoint = endpoint
        self.calls: dict[str, "SipCall"] = {}
        self.registered = False

        logger.info(
            "SIP account initialized: %s@%s:%s",
            config.username,
            config.gateway_host,
            config.gateway_port,
        )

    async def register(self) -> bool:
        """
        Register with SIP gateway.

        Sends REGISTER request with authentication credentials.

        Returns:
            True if registration successful
        """
        try:
            logger.info(
                "Registering SIP account: %s@%s",
                self.config.username,
                self.config.gateway_host,
            )

            # TODO: Implement PJSIP registration
            # When PJSIP is integrated:
            # acc_cfg = pj.AccountConfig()
            # acc_cfg.idUri = f"sip:{self.config.username}@{self.config.gateway_host}"
            # acc_cfg.regConfig.registrarUri = f"sip:{self.config.gateway_host}:{self.config.gateway_port}"
            #
            # # Authentication
            # cred = pj.AuthCredInfo(
            #     "digest",
            #     "*",  # Realm (wildcard)
            #     self.config.username,
            #     0,
            #     self.config.password.get_secret_value()
            # )
            # acc_cfg.sipConfig.authCreds.append(cred)
            #
            # self.pj_account.create(acc_cfg)

            # For now, mark as not registered (stub mode)
            self.registered = False
            logger.warning("SIP registration not implemented (stub mode)")
            return False

        except Exception:
            logger.exception("Failed to register SIP account")
            return False

    async def unregister(self) -> bool:
        """
        Unregister from SIP gateway.

        Returns:
            True if unregistration successful
        """
        try:
            logger.info("Unregistering SIP account")
            self.registered = False
            return True
        except Exception:
            logger.exception("Failed to unregister SIP account")
            return False

    def on_incoming_call(self, call: "SipCall") -> None:
        """
        Handle incoming SIP call.

        Called by PJSIP when INVITE is received.

        Args:
            call: SipCall instance
        """
        logger.info(
            "Incoming SIP call from %s (call_id=%s)",
            call.remote_uri,
            call.call_id,
        )

        # Store call
        self.calls[call.call_id] = call

        # TODO: Trigger call event processing
        # This would create a task to handle the incoming call:
        # asyncio.create_task(self._handle_incoming_call(call))

    def on_reg_state(self, status: int, status_text: str) -> None:
        """
        Handle registration status change.

        Args:
            status: SIP status code
            status_text: Status description
        """
        logger.info("SIP registration status: %s (%s)", status, status_text)

        if status == 200:
            self.registered = True
            logger.info("SIP account successfully registered")
        else:
            self.registered = False
            logger.warning("SIP account not registered: %s", status_text)

    def get_call(self, call_id: str) -> "SipCall | None":
        """
        Get call by call ID.

        Args:
            call_id: SIP call ID

        Returns:
            SipCall instance or None
        """
        return self.calls.get(call_id)

    def remove_call(self, call_id: str) -> None:
        """
        Remove call from active calls.

        Args:
            call_id: SIP call ID
        """
        if call_id in self.calls:
            del self.calls[call_id]
            logger.debug("Removed call %s from active calls", call_id)
