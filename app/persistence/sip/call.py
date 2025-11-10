"""SIP call handling."""

import uuid
from typing import Any

from app.helpers.logging import logger
from app.persistence.sip.rtp_bridge import RtpWebSocketBridge


class SipCall:
    """
    Handler for individual SIP calls.

    Manages:
    - Call state (INVITE, RINGING, CONNECTED, DISCONNECTED)
    - SDP negotiation
    - RTP audio bridge
    - Call termination
    """

    def __init__(self, account: Any, pj_call_id: str | None = None):  # pj.Call
        """
        Initialize SIP call.

        Args:
            account: SipAccount instance
            pj_call_id: PJSIP call ID (optional, for incoming calls)
        """
        self.account = account
        self.pj_call_id = pj_call_id
        self.call_id = str(uuid.uuid4())
        self.remote_uri = ""
        self.local_uri = ""
        self.state = "DISCONNECTED"
        self.rtp_bridge: RtpWebSocketBridge | None = None

        logger.info("SIP call created: call_id=%s", self.call_id)

    async def answer(self, status_code: int = 200) -> bool:
        """
        Answer incoming call with SIP 200 OK.

        Args:
            status_code: SIP status code (default: 200 OK)

        Returns:
            True if answer was successful
        """
        try:
            logger.info("Answering SIP call: call_id=%s, status=%s", self.call_id, status_code)

            # TODO: Send SIP 200 OK using PJSIP
            # When PJSIP is integrated:
            # call_prm = pj.CallOpParam()
            # call_prm.statusCode = status_code
            # self.pj_call.answer(call_prm)

            self.state = "CONNECTED"
            logger.info("SIP call answered: call_id=%s", self.call_id)
            return True

        except Exception:
            logger.exception("Failed to answer SIP call: call_id=%s", self.call_id)
            return False

    async def hangup(self) -> bool:
        """
        Terminate call with SIP BYE.

        Returns:
            True if hangup was initiated successfully
        """
        try:
            logger.info("Hanging up SIP call: call_id=%s", self.call_id)

            # Stop RTP bridge first
            if self.rtp_bridge:
                await self.rtp_bridge.stop()
                self.rtp_bridge = None

            # TODO: Send SIP BYE using PJSIP
            # When PJSIP is integrated:
            # call_prm = pj.CallOpParam()
            # self.pj_call.hangup(call_prm)

            self.state = "DISCONNECTED"

            # Remove from account's active calls
            self.account.remove_call(self.call_id)

            logger.info("SIP call hung up: call_id=%s", self.call_id)
            return True

        except Exception:
            logger.exception("Failed to hangup SIP call: call_id=%s", self.call_id)
            return False

    def on_state_change(self, state: str) -> None:
        """
        Handle call state change.

        Args:
            state: New call state (CALLING, INCOMING, EARLY, CONNECTING, CONFIRMED, DISCONNECTED)
        """
        logger.info("SIP call state changed: call_id=%s, state=%s", self.call_id, state)
        self.state = state

        if state == "DISCONNECTED":
            # Clean up resources
            if self.rtp_bridge:
                logger.info("Stopping RTP bridge for disconnected call: call_id=%s", self.call_id)
                # Note: This is sync callback from PJSIP, but we need async
                # In real implementation, we'd schedule the async cleanup

    def on_media_state(self, media_active: bool) -> None:
        """
        Handle media state change.

        Called when RTP media becomes active or inactive.

        Args:
            media_active: True if media is now active
        """
        logger.info(
            "SIP call media state changed: call_id=%s, active=%s",
            self.call_id,
            media_active,
        )

        if media_active:
            # TODO: Set up RTP bridge when PJSIP is integrated
            # audio_media = self.pj_call.getAudioMedia(0)
            # self.rtp_bridge = RtpWebSocketBridge(
            #     audio_media=audio_media,
            #     codec="PCMU",  # G.711 μ-law
            #     call_id=self.call_id,
            # )
            pass

    def get_audio_bridge(self) -> RtpWebSocketBridge | None:
        """
        Get the RTP WebSocket bridge for this call.

        Returns:
            RtpWebSocketBridge instance or None
        """
        return self.rtp_bridge

    def __repr__(self) -> str:
        """String representation of SIP call."""
        return f"SipCall(call_id={self.call_id}, state={self.state}, remote={self.remote_uri})"
