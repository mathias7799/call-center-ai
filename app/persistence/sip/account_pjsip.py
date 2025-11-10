"""SIP account management using PJSIP.

This module provides a proper PJSIP Account implementation that extends
pj.Account and implements the required callback methods.
"""

import asyncio
from typing import TYPE_CHECKING, Any

from app.helpers.config_models.telephony import SipModel
from app.helpers.logging import logger

# Import PJSIP if available
try:
    import pjsua2 as pj
    PJSIP_AVAILABLE = True
except ImportError:
    PJSIP_AVAILABLE = False
    pj = None  # type: ignore

if TYPE_CHECKING:
    from app.persistence.sip.call_pjsip import PjsipCall


class PjsipAccount(pj.Account if PJSIP_AVAILABLE else object):  # type: ignore
    """
    SIP Account implementation extending pj.Account.

    This class properly extends PJSIP's Account class and implements
    the required callback methods for account events.

    Callbacks:
    - onRegState(): Registration status changes
    - onIncomingCall(): Incoming SIP INVITE
    """

    def __init__(self, config: SipModel):
        """
        Initialize PJSIP account.

        Args:
            config: SIP configuration
        """
        if PJSIP_AVAILABLE:
            super().__init__()

        self.config = config
        self.calls: dict[str, "PjsipCall"] = {}
        self.registered = False
        self._incoming_call_callback = None

        logger.info(
            "PjsipAccount initialized for %s@%s",
            config.username,
            config.gateway_host,
        )

    def create_and_register(self, endpoint: Any) -> None:  # pj.Endpoint
        """
        Create account configuration and register with gateway.

        Args:
            endpoint: PJSIP Endpoint instance

        Raises:
            RuntimeError: If PJSIP not available or registration fails
        """
        if not PJSIP_AVAILABLE or not pj:
            raise RuntimeError("PJSIP not available")

        # Create account configuration
        acc_cfg = pj.AccountConfig()

        # Set SIP URI
        acc_cfg.idUri = f"sip:{self.config.username}@{self.config.gateway_host}"

        # Set registrar URI
        acc_cfg.regConfig.registrarUri = (
            f"sip:{self.config.gateway_host}:{self.config.gateway_port}"
        )

        # Add authentication credentials
        cred = pj.AuthCredInfo()
        cred.scheme = "digest"
        cred.realm = "*"  # Wildcard realm
        cred.username = self.config.username
        cred.dataType = 0  # Plain text password
        cred.data = self.config.password.get_secret_value()

        acc_cfg.sipConfig.authCreds.append(cred)

        # Optional: Configure NAT traversal (STUN)
        if self.config.stun_server:
            acc_cfg.natConfig.stunServer.append(self.config.stun_server)
            logger.info("STUN server configured: %s", self.config.stun_server)

        # Create the account
        try:
            self.create(acc_cfg)
            logger.info("Account created and registration initiated")
        except Exception:
            logger.exception("Failed to create/register account")
            raise

    def set_incoming_call_callback(self, callback):
        """
        Set callback for incoming calls.

        Args:
            callback: Async callable that receives (call_id, remote_uri)
        """
        self._incoming_call_callback = callback

    def onRegState(self, prm: Any) -> None:  # pj.OnRegStateParam
        """
        Callback when registration state changes.

        This is called by PJSIP when registration status changes
        (e.g., 200 OK, 401 Unauthorized, timeout, etc.)

        Args:
            prm: Registration state parameters
        """
        if not PJSIP_AVAILABLE:
            return

        try:
            ai = self.getInfo()
            status = ai.regStatus
            status_text = ai.regStatusText

            logger.info(
                "Registration state changed: %s (%s)",
                status,
                status_text,
            )

            # Update registration status
            if status == 200:  # OK
                self.registered = True
                logger.info("✅ Successfully registered with SIP gateway")
            else:
                self.registered = False
                if status >= 400:
                    logger.error("❌ Registration failed: %s %s", status, status_text)
                else:
                    logger.warning("⚠️ Registration status: %s %s", status, status_text)

        except Exception:
            logger.exception("Error in onRegState callback")

    def onIncomingCall(self, prm: Any) -> None:  # pj.OnIncomingCallParam
        """
        Callback when incoming SIP INVITE is received.

        This is called by PJSIP when a new incoming call arrives.
        We need to create a Call object and decide whether to answer.

        Args:
            prm: Incoming call parameters (contains call_id)
        """
        if not PJSIP_AVAILABLE:
            return

        try:
            from app.persistence.sip.call_pjsip import PjsipCall

            # Create Call object for this incoming call
            call = PjsipCall(self, call_id=prm.callId)

            # Get call info
            ci = call.getInfo()
            remote_uri = ci.remoteUri
            call_id_str = str(prm.callId)

            logger.info(
                "📞 Incoming call from %s (call_id=%s)",
                remote_uri,
                call_id_str,
            )

            # Store call
            self.calls[call_id_str] = call

            # Notify application about incoming call
            if self._incoming_call_callback:
                # Schedule async callback
                asyncio.create_task(
                    self._incoming_call_callback(call_id_str, remote_uri)
                )
            else:
                logger.warning("No incoming call callback configured, auto-answering")
                # Auto-answer if no callback (development mode)
                call_prm = pj.CallOpParam()
                call_prm.statusCode = 200
                call.answer(call_prm)

        except Exception:
            logger.exception("Error handling incoming call")

    def get_call(self, call_id: str) -> "PjsipCall | None":
        """
        Get call by ID.

        Args:
            call_id: SIP call ID

        Returns:
            PjsipCall instance or None
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

    async def unregister(self) -> bool:
        """
        Unregister from SIP gateway.

        Returns:
            True if unregistration successful
        """
        try:
            if PJSIP_AVAILABLE and self.registered:
                # Call PJSIP's setRegistration to unregister
                self.setRegistration(False)
                logger.info("Unregistration initiated")
                self.registered = False
            return True
        except Exception:
            logger.exception("Failed to unregister")
            return False
