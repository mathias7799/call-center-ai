"""RTP to WebSocket bridge for SIP telephony."""

import asyncio
import queue
import threading
from typing import Any

from app.helpers.logging import logger
from app.persistence.sip.codecs import CodecConverter, CodecType

# Import PJSIP if available
try:
    import pjsua2 as pj

    PJSIP_AVAILABLE = True
except ImportError:
    PJSIP_AVAILABLE = False
    pj = None  # type: ignore


class CustomAudioMediaPort(pj.AudioMediaPort if PJSIP_AVAILABLE else object):  # type: ignore
    """
    Custom PJSIP AudioMediaPort for frame-level audio access.

    This port captures incoming audio frames (RTP → Queue) and
    provides outgoing audio frames (Queue → RTP) with real-time codec conversion.
    """

    def __init__(self, call_id: str, converter: CodecConverter, codec: CodecType):
        """
        Initialize custom audio media port.

        Args:
            call_id: Call ID for logging
            converter: Codec converter instance
            codec: RTP codec ("PCMU", "PCMA")
        """
        if PJSIP_AVAILABLE:
            super().__init__()

        self.call_id = call_id
        self.converter = converter
        self.codec = codec

        # Thread-safe queues for frame exchange
        # Using standard queue (not asyncio) since callbacks run in PJSIP thread
        self.incoming_frames: queue.Queue[bytes] = queue.Queue(maxsize=100)
        self.outgoing_frames: queue.Queue[bytes] = queue.Queue(maxsize=100)

        # Stats
        self.frames_received = 0
        self.frames_sent = 0

        logger.debug("CustomAudioMediaPort created for call %s", call_id)

    def onFrameReceived(self, frame: Any) -> None:  # pj.MediaFrame
        """
        Callback when audio frame arrives from call (RTP → here).

        Decodes the frame from G.711 to PCM 16kHz and queues it.

        Args:
            frame: MediaFrame from PJSIP containing encoded audio
        """
        if not PJSIP_AVAILABLE:
            return

        try:
            # Get frame data as bytes
            if not frame.buf or len(frame.buf) == 0:
                return

            frame_data = bytes(frame.buf)
            self.frames_received += 1

            # Decode from G.711 (8kHz) to PCM 16kHz
            pcm_data = self.converter.decode(frame_data, self.codec)

            # Put in queue (non-blocking)
            try:
                self.incoming_frames.put_nowait(pcm_data)
            except queue.Full:
                logger.warning(
                    "Incoming frame queue full for call %s, dropping frame",
                    self.call_id,
                )

        except Exception:
            logger.exception("Error in onFrameReceived for call %s", self.call_id)

    def onFrameRequested(self, frame: Any) -> None:  # pj.MediaFrame
        """
        Callback when PJSIP needs audio to send to call (here → RTP).

        Gets PCM audio from queue, encodes to G.711, and fills frame buffer.

        Args:
            frame: MediaFrame to fill with encoded audio
        """
        if not PJSIP_AVAILABLE:
            return

        try:
            # Try to get PCM data from outgoing queue
            try:
                pcm_data = self.outgoing_frames.get_nowait()
            except queue.Empty:
                # No data available - send silence
                # G.711 μ-law silence is 0xFF (0x7F for A-law)
                silence_byte = 0xFF if self.codec == "PCMU" else 0x7F
                silence_frame = bytes([silence_byte] * 160)  # 20ms @ 8kHz
                frame.buf = silence_frame
                frame.size = len(silence_frame)
                return

            # Encode PCM 16kHz to G.711 8kHz
            encoded_data = self.converter.encode(pcm_data, self.codec)

            # Fill frame buffer
            frame.buf = encoded_data
            frame.size = len(encoded_data)
            self.frames_sent += 1

        except Exception:
            logger.exception("Error in onFrameRequested for call %s", self.call_id)

    def get_stats(self) -> dict:
        """Get statistics about frame processing."""
        return {
            "frames_received": self.frames_received,
            "frames_sent": self.frames_sent,
            "incoming_queue_size": self.incoming_frames.qsize(),
            "outgoing_queue_size": self.outgoing_frames.qsize(),
        }


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
            audio_media: PJSIP AudioMedia object from the call
            codec: RTP codec to use ("PCMU", "PCMA", "G722")
            call_id: SIP call ID for logging
        """
        self.audio_media = audio_media
        self.codec = codec
        self.call_id = call_id
        self.running = False

        # Async queues for WebSocket communication
        self.incoming_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)
        self.outgoing_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)

        # Codec converter
        self.converter = CodecConverter()

        # Custom audio media port for frame-level access
        self.media_port: CustomAudioMediaPort | None = None

        # Bridge tasks
        self._bridge_tasks: list[asyncio.Task] = []

        logger.info(
            "RTP bridge initialized: call_id=%s, codec=%s", call_id, codec
        )

    async def start(self) -> None:
        """
        Start bridging RTP <-> WebSocket queues.

        Creates custom audio media port, connects it to call audio,
        and runs bridge tasks to move audio between PJSIP and async queues.
        """
        if not PJSIP_AVAILABLE or not self.audio_media:
            logger.error("Cannot start RTP bridge: PJSIP not available")
            return

        self.running = True
        logger.info("Starting RTP bridge for call %s", self.call_id)

        try:
            # Create custom audio media port
            self.media_port = CustomAudioMediaPort(
                self.call_id, self.converter, self.codec
            )

            # Get audio format from call's audio media
            port_info = self.audio_media.getPortInfo()
            audio_format = port_info.format

            # Create the port with same format as call audio
            self.media_port.createPort("bridge_port", audio_format)
            logger.info("Created audio media port for call %s", self.call_id)

            # Connect bidirectional audio streams:
            # 1. Call audio → our port (for receiving/capture)
            self.audio_media.startTransmit(self.media_port)
            # 2. Our port → call audio (for sending/playback)
            self.media_port.startTransmit(self.audio_media)

            logger.info("Connected audio streams for call %s", self.call_id)

            # Start bridge tasks to move audio between queues
            self._bridge_tasks = [
                asyncio.create_task(self._thread_to_async_bridge()),
                asyncio.create_task(self._async_to_thread_bridge()),
            ]

            # Wait for tasks to complete
            await asyncio.gather(*self._bridge_tasks)

        except Exception:
            logger.exception("Error in RTP bridge for call %s", self.call_id)
        finally:
            self.running = False
            await self._cleanup()

    async def stop(self) -> None:
        """Stop the RTP bridge and clean up resources."""
        logger.info("Stopping RTP bridge for call %s", self.call_id)
        self.running = False

        # Cancel bridge tasks
        for task in self._bridge_tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to finish
        if self._bridge_tasks:
            await asyncio.gather(*self._bridge_tasks, return_exceptions=True)

        await self._cleanup()

    async def _cleanup(self) -> None:
        """Clean up resources."""
        if not PJSIP_AVAILABLE:
            return

        try:
            # Stop audio transmission
            if self.media_port and self.audio_media:
                try:
                    self.audio_media.stopTransmit(self.media_port)
                    self.media_port.stopTransmit(self.audio_media)
                except Exception:
                    logger.exception("Error stopping audio transmission")

            # Log stats
            if self.media_port:
                stats = self.media_port.get_stats()
                logger.info("RTP bridge stats for call %s: %s", self.call_id, stats)

        except Exception:
            logger.exception("Error in RTP bridge cleanup")

        # Drain async queues
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

    async def _thread_to_async_bridge(self) -> None:
        """
        Bridge thread-safe queue (from PJSIP) to async queue (for WebSocket).

        Moves decoded PCM audio from CustomAudioMediaPort to WebSocket queue.
        This runs continuously, polling the thread-safe queue and moving data.
        """
        logger.debug("Starting thread→async bridge for call %s", self.call_id)

        while self.running:
            try:
                if not self.media_port:
                    await asyncio.sleep(0.01)
                    continue

                # Poll thread-safe queue (non-blocking)
                try:
                    pcm_data = self.media_port.incoming_frames.get_nowait()

                    # Put in async queue for WebSocket
                    await self.incoming_queue.put(pcm_data)

                except queue.Empty:
                    # No data available, sleep briefly
                    await asyncio.sleep(0.01)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception(
                    "Error in thread→async bridge for call %s", self.call_id
                )
                await asyncio.sleep(0.1)

        logger.debug("Stopped thread→async bridge for call %s", self.call_id)

    async def _async_to_thread_bridge(self) -> None:
        """
        Bridge async queue (from WebSocket) to thread-safe queue (for PJSIP).

        Moves PCM audio from WebSocket to CustomAudioMediaPort for encoding/transmission.
        This runs continuously, waiting for WebSocket data and forwarding it.
        """
        logger.debug("Starting async→thread bridge for call %s", self.call_id)

        while self.running:
            try:
                if not self.media_port:
                    await asyncio.sleep(0.01)
                    continue

                # Get PCM from async queue (with timeout to check running flag)
                try:
                    pcm_data = await asyncio.wait_for(
                        self.outgoing_queue.get(), timeout=0.5
                    )

                    # Put in thread-safe queue for PJSIP
                    try:
                        self.media_port.outgoing_frames.put_nowait(pcm_data)
                    except queue.Full:
                        logger.warning(
                            "Outgoing frame queue full for call %s", self.call_id
                        )

                except asyncio.TimeoutError:
                    # No data within timeout, continue loop
                    continue

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception(
                    "Error in async→thread bridge for call %s", self.call_id
                )
                await asyncio.sleep(0.1)

        logger.debug("Stopped async→thread bridge for call %s", self.call_id)

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
