"""RTP to WebSocket bridge for SIP telephony."""

import asyncio
from typing import Any

from app.helpers.logging import logger
from app.persistence.sip.codecs import CodecConverter, CodecType


class RtpWebSocketBridge:
    """
    Bridges RTP audio <-> WebSocket for existing audio pipeline.

    Architecture:
        RTP (G.711/G.722) <-> Decoder/Encoder <-> PCM 16kHz 16-bit mono <-> WebSocket

    Handles:
    - RTP packet reception and parsing
    - Codec decoding (G.711/G.722 -> PCM 16kHz)
    - WebSocket transmission
    - WebSocket reception
    - Codec encoding (PCM 16kHz -> G.711/G.722)
    - RTP packet transmission
    """

    def __init__(
        self,
        audio_media: Any,  # pj.AudioMedia when PJSIP is available
        codec: CodecType = "PCMU",
        call_id: str = "",
    ):
        """
        Initialize RTP WebSocket bridge.

        Args:
            audio_media: PJSIP AudioMedia object
            codec: RTP codec to use ("PCMU", "PCMA", "G722")
            call_id: SIP call ID for logging
        """
        self.audio_media = audio_media
        self.codec = codec
        self.call_id = call_id
        self.running = False

        # Queues for bidirectional audio
        self.incoming_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)
        self.outgoing_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)

        # Codec converter
        self.converter = CodecConverter()

        logger.info(
            "RTP bridge initialized: call_id=%s, codec=%s", call_id, codec
        )

    async def start(self) -> None:
        """
        Start bridging RTP <-> WebSocket queues.

        Runs two concurrent tasks:
        1. RTP -> decode -> incoming queue (for WebSocket send)
        2. Outgoing queue -> encode -> RTP (from WebSocket receive)
        """
        self.running = True
        logger.info("Starting RTP bridge for call %s", self.call_id)

        try:
            await asyncio.gather(
                self._rtp_to_queue(),
                self._queue_to_rtp(),
            )
        except Exception:
            logger.exception("Error in RTP bridge for call %s", self.call_id)
        finally:
            self.running = False

    async def stop(self) -> None:
        """Stop the RTP bridge and clean up resources."""
        logger.info("Stopping RTP bridge for call %s", self.call_id)
        self.running = False

        # Drain queues
        while not self.incoming_queue.empty():
            try:
                self.incoming_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        while not self.outgoing_queue.empty():
            try:
                self.outgoing_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def _rtp_to_queue(self) -> None:
        """
        Receive RTP packets, decode to PCM, push to incoming queue.

        This is called by the audio pipeline to get incoming audio from the call.
        """
        while self.running:
            try:
                # TODO: Get RTP frame from PJSIP AudioMedia
                # For now, this is a placeholder that would use:
                # frame = await self._get_rtp_frame()

                # Simulate receiving RTP data (replace with actual PJSIP integration)
                await asyncio.sleep(0.02)  # 20ms frames (typical for RTP)
                continue

                # When PJSIP is integrated:
                # 1. Get RTP frame from audio_media
                # 2. Decode using codec
                # pcm = self.converter.decode(frame, self.codec)
                # 3. Push to queue
                # await self.incoming_queue.put(pcm)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in RTP to queue for call %s", self.call_id)
                await asyncio.sleep(0.1)

    async def _queue_to_rtp(self) -> None:
        """
        Get PCM from outgoing queue, encode to codec, send as RTP.

        This is called when the audio pipeline wants to send audio to the call.
        """
        while self.running:
            try:
                # Get PCM audio from outgoing queue (sent by application via WebSocket)
                pcm = await asyncio.wait_for(
                    self.outgoing_queue.get(), timeout=1.0
                )

                # Encode PCM to RTP codec
                encoded = self.converter.encode(pcm, self.codec)

                # TODO: Send via RTP using PJSIP AudioMedia
                # For now, this is a placeholder
                # When PJSIP is integrated:
                # await self._send_rtp_frame(encoded)

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in queue to RTP for call %s", self.call_id)
                await asyncio.sleep(0.1)

    async def send_to_call(self, pcm_data: bytes) -> None:
        """
        Send PCM audio to the call (will be encoded and sent as RTP).

        Args:
            pcm_data: PCM 16kHz 16-bit mono audio
        """
        try:
            await self.outgoing_queue.put(pcm_data)
        except asyncio.QueueFull:
            logger.warning("Outgoing queue full for call %s, dropping audio", self.call_id)

    async def receive_from_call(self) -> bytes:
        """
        Receive PCM audio from the call (decoded from RTP).

        Returns:
            PCM 16kHz 16-bit mono audio
        """
        return await self.incoming_queue.get()
