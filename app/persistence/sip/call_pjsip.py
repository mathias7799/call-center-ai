"""SIP call handling using PJSIP.

This module provides a proper PJSIP Call implementation that extends
pj.Call and implements the required callback methods.
"""

import uuid
from typing import TYPE_CHECKING, Any

from app.helpers.logging import logger
from app.persistence.sip.rtp_bridge import RtpWebSocketBridge

# Import PJSIP if available
try:
    import pjsua2 as pj
    PJSIP_AVAILABLE = True
except ImportError:
    PJSIP_AVAILABLE = False
    pj = None  # type: ignore

if TYPE_CHECKING:
    from app.persistence.sip.account_pjsip import PjsipAccount


class PjsipCall(pj.Call if PJSIP_AVAILABLE else object):  # type: ignore
    """
    SIP Call implementation extending pj.Call.

    This class properly extends PJSIP's Call class and implements
    the required callback methods for call events.

    Callbacks:
    - onCallState(): Call state changes (CONNECTING, CONFIRMED, DISCONNECTED)
    - onCallMediaState(): Media state changes (audio stream active/inactive)
    """

    def __init__(self, account: "PjsipAccount", call_id: int = -1):
        """
        Initialize PJSIP call.

        Args:
            account: PjsipAccount instance
            call_id: PJSIP call ID (for incoming calls) or -1 for outgoing
        """
        if PJSIP_AVAILABLE:
            if call_id >= 0:
                # Incoming call - pass call_id to parent
                super().__init__(account, call_id)
            else:
                # Outgoing call - don't pass call_id
                super().__init__(account)

        self.account = account
        self.call_id = str(uuid.uuid4())  # Our internal call ID
        self.pjsip_call_id = call_id
        self.remote_uri = ""
        self.local_uri = ""
        self.state = "DISCONNECTED"
        self.rtp_bridge: RtpWebSocketBridge | None = None
        self._state_callback = None
        self._media_callback = None

        logger.info("PjsipCall created: call_id=%s, pjsip_id=%s", self.call_id, call_id)

    def set_state_callback(self, callback):
        """Set callback for call state changes."""
        self._state_callback = callback

    def set_media_callback(self, callback):
        """Set callback for media state changes."""
        self._media_callback = callback

    def onCallState(self, prm: Any) -> None:  # pj.OnCallStateParam
        """
        Callback when call state changes.

        States include:
        - PJSIP_INV_STATE_NULL: Before INVITE sent/received
        - PJSIP_INV_STATE_CALLING: After INVITE sent
        - PJSIP_INV_STATE_INCOMING: After INVITE received
        - PJSIP_INV_STATE_EARLY: After response with To tag
        - PJSIP_INV_STATE_CONNECTING: After 2xx sent/received
        - PJSIP_INV_STATE_CONFIRMED: After ACK sent/received
        - PJSIP_INV_STATE_DISCONNECTED: Session terminated

        Args:
            prm: Call state parameters
        """
        if not PJSIP_AVAILABLE:
            return

        try:
            ci = self.getInfo()
            state_text = ci.stateText
            last_status = ci.lastStatusCode

            logger.info(
                "Call state: %s (code=%s) [call_id=%s]",
                state_text,
                last_status,
                self.call_id,
            )

            # Update state
            self.state = state_text
            self.remote_uri = ci.remoteUri

            # Handle specific states
            if ci.state == pj.PJSIP_INV_STATE_CONFIRMED:
                logger.info("✅ Call confirmed (answered): %s", self.call_id)

            elif ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
                logger.info("📵 Call disconnected: %s", self.call_id)

                # Clean up RTP bridge
                if self.rtp_bridge:
                    import asyncio
                    asyncio.create_task(self.rtp_bridge.stop())

                # Remove from account's active calls
                self.account.remove_call(self.call_id)

            # Notify application
            if self._state_callback:
                import asyncio
                asyncio.create_task(self._state_callback(self.call_id, state_text))

        except Exception:
            logger.exception("Error in onCallState callback")

    def onCallMediaState(self, prm: Any) -> None:  # pj.OnCallMediaStateParam
        """
        Callback when media state changes.

        This is called when RTP media becomes active or inactive.
        We use this to set up audio routing and the RTP bridge.

        Args:
            prm: Call media state parameters
        """
        if not PJSIP_AVAILABLE:
            return

        try:
            ci = self.getInfo()

            logger.info(
                "Media state changed: %s media streams [call_id=%s]",
                len(ci.media),
                self.call_id,
            )

            # Iterate through media streams
            for media_idx, media_info in enumerate(ci.media):
                logger.debug(
                    "  Media[%s]: type=%s, status=%s, dir=%s",
                    media_idx,
                    media_info.type,
                    media_info.status,
                    media_info.dir,
                )

                # Check if this is active audio media
                if (
                    media_info.type == pj.PJMEDIA_TYPE_AUDIO
                    and media_info.status == pj.PJSUA_CALL_MEDIA_ACTIVE
                ):
                    logger.info("🎵 Audio media active on index %s", media_idx)

                    # Get AudioMedia object
                    try:
                        audio_media = self.getAudioMedia(media_idx)

                        # Create RTP bridge
                        self.rtp_bridge = RtpWebSocketBridge(
                            audio_media=audio_media,
                            codec="PCMU",  # G.711 μ-law
                            call_id=self.call_id,
                        )

                        logger.info("RTP bridge created for call %s", self.call_id)

                        # Notify application
                        if self._media_callback:
                            import asyncio
                            asyncio.create_task(
                                self._media_callback(self.call_id, audio_media)
                            )

                    except Exception:
                        logger.exception(
                            "Failed to get AudioMedia for index %s", media_idx
                        )

        except Exception:
            logger.exception("Error in onCallMediaState callback")

    async def answer_call(self, status_code: int = 200) -> bool:
        """
        Answer incoming call.

        Args:
            status_code: SIP status code (default: 200 OK)

        Returns:
            True if answer was successful
        """
        if not PJSIP_AVAILABLE:
            logger.error("PJSIP not available")
            return False

        try:
            logger.info("Answering call: %s with code %s", self.call_id, status_code)

            # Create call operation parameters
            call_prm = pj.CallOpParam()
            call_prm.statusCode = status_code

            # Answer the call
            self.answer(call_prm)

            self.state = "CONNECTED"
            logger.info("✅ Call answered: %s", self.call_id)
            return True

        except Exception:
            logger.exception("Failed to answer call: %s", self.call_id)
            return False

    async def hangup_call(self) -> bool:
        """
        Hangup call (send SIP BYE).

        Returns:
            True if hangup successful
        """
        if not PJSIP_AVAILABLE:
            return False

        try:
            logger.info("Hanging up call: %s", self.call_id)

            # Stop RTP bridge first
            if self.rtp_bridge:
                await self.rtp_bridge.stop()
                self.rtp_bridge = None

            # Create hangup parameters
            prm = pj.CallOpParam()

            # Hangup the call
            self.hangup(prm)

            self.state = "DISCONNECTED"
            logger.info("✅ Call hung up: %s", self.call_id)

            # Remove from account
            self.account.remove_call(self.call_id)

            return True

        except Exception:
            logger.exception("Failed to hangup call: %s", self.call_id)
            return False

    def get_audio_bridge(self) -> RtpWebSocketBridge | None:
        """
        Get RTP-WebSocket bridge for this call.

        Returns:
            RtpWebSocketBridge instance or None
        """
        return self.rtp_bridge

    def get_info_dict(self) -> dict:
        """
        Get call information as dictionary.

        Returns:
            Dictionary with call details
        """
        if not PJSIP_AVAILABLE:
            return {
                "call_id": self.call_id,
                "state": "PJSIP_NOT_AVAILABLE",
            }

        try:
            ci = self.getInfo()
            return {
                "call_id": self.call_id,
                "state": ci.stateText,
                "remote_uri": ci.remoteUri,
                "local_uri": ci.localUri,
                "last_status": ci.lastStatusCode,
                "media_count": len(ci.media),
            }
        except Exception:
            logger.exception("Failed to get call info")
            return {
                "call_id": self.call_id,
                "state": "ERROR",
            }

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"PjsipCall(call_id={self.call_id}, "
            f"state={self.state}, "
            f"remote={self.remote_uri})"
        )
