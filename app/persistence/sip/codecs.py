"""Codec conversion utilities for SIP telephony."""

import audioop
from typing import Literal

from app.helpers.logging import logger

CodecType = Literal["PCMU", "PCMA", "G722"]


class CodecConverter:
    """
    Convert between telephony codecs and PCM 16kHz 16-bit mono.

    Supported codecs:
    - PCMU (G.711 μ-law) - Most common in North America
    - PCMA (G.711 A-law) - Most common in Europe
    - G.722 - Wideband codec (future support)
    """

    @staticmethod
    def g711_ulaw_decode(data: bytes, sample_rate: int = 8000) -> bytes:
        """
        Decode G.711 μ-law to PCM 16kHz 16-bit mono.

        Args:
            data: G.711 μ-law encoded audio
            sample_rate: Input sample rate (typically 8000 Hz)

        Returns:
            PCM 16kHz 16-bit mono audio
        """
        try:
            # Decode μ-law to linear PCM (at input sample rate)
            pcm = audioop.ulaw2lin(data, 2)  # 2 bytes per sample (16-bit)

            # Resample to 16kHz if needed
            if sample_rate != 16000:
                pcm, _ = audioop.ratecv(
                    pcm,
                    2,  # sample width (16-bit)
                    1,  # channels (mono)
                    sample_rate,  # input rate
                    16000,  # output rate (16kHz)
                    None,  # state
                )

            return pcm
        except Exception:
            logger.exception("Error decoding G.711 μ-law")
            return b""

    @staticmethod
    def g711_ulaw_encode(pcm_16k: bytes) -> bytes:
        """
        Encode PCM 16kHz 16-bit mono to G.711 μ-law.

        Args:
            pcm_16k: PCM 16kHz 16-bit mono audio

        Returns:
            G.711 μ-law encoded audio at 8kHz
        """
        try:
            # Resample 16kHz -> 8kHz
            pcm_8k, _ = audioop.ratecv(
                pcm_16k,
                2,  # sample width (16-bit)
                1,  # channels (mono)
                16000,  # input rate
                8000,  # output rate
                None,  # state
            )

            # Encode to μ-law
            ulaw = audioop.lin2ulaw(pcm_8k, 2)
            return ulaw
        except Exception:
            logger.exception("Error encoding G.711 μ-law")
            return b""

    @staticmethod
    def g711_alaw_decode(data: bytes, sample_rate: int = 8000) -> bytes:
        """
        Decode G.711 A-law to PCM 16kHz 16-bit mono.

        Args:
            data: G.711 A-law encoded audio
            sample_rate: Input sample rate (typically 8000 Hz)

        Returns:
            PCM 16kHz 16-bit mono audio
        """
        try:
            # Decode A-law to linear PCM
            pcm = audioop.alaw2lin(data, 2)

            # Resample to 16kHz if needed
            if sample_rate != 16000:
                pcm, _ = audioop.ratecv(
                    pcm,
                    2,  # sample width
                    1,  # channels
                    sample_rate,  # input rate
                    16000,  # output rate
                    None,  # state
                )

            return pcm
        except Exception:
            logger.exception("Error decoding G.711 A-law")
            return b""

    @staticmethod
    def g711_alaw_encode(pcm_16k: bytes) -> bytes:
        """
        Encode PCM 16kHz 16-bit mono to G.711 A-law.

        Args:
            pcm_16k: PCM 16kHz 16-bit mono audio

        Returns:
            G.711 A-law encoded audio at 8kHz
        """
        try:
            # Resample 16kHz -> 8kHz
            pcm_8k, _ = audioop.ratecv(
                pcm_16k,
                2,  # sample width
                1,  # channels
                16000,  # input rate
                8000,  # output rate
                None,  # state
            )

            # Encode to A-law
            alaw = audioop.lin2alaw(pcm_8k, 2)
            return alaw
        except Exception:
            logger.exception("Error encoding G.711 A-law")
            return b""

    @staticmethod
    def decode(data: bytes, codec: CodecType, sample_rate: int = 8000) -> bytes:
        """
        Decode audio from specified codec to PCM 16kHz 16-bit mono.

        Args:
            data: Encoded audio data
            codec: Codec type ("PCMU", "PCMA", "G722")
            sample_rate: Input sample rate

        Returns:
            PCM 16kHz 16-bit mono audio
        """
        if codec == "PCMU":
            return CodecConverter.g711_ulaw_decode(data, sample_rate)
        elif codec == "PCMA":
            return CodecConverter.g711_alaw_decode(data, sample_rate)
        elif codec == "G722":
            # TODO: Implement G.722 decoding (requires external library)
            logger.warning("G.722 decoding not implemented yet")
            return b""
        else:
            logger.error("Unknown codec: %s", codec)
            return b""

    @staticmethod
    def encode(pcm_16k: bytes, codec: CodecType) -> bytes:
        """
        Encode PCM 16kHz 16-bit mono to specified codec.

        Args:
            pcm_16k: PCM 16kHz 16-bit mono audio
            codec: Codec type ("PCMU", "PCMA", "G722")

        Returns:
            Encoded audio data
        """
        if codec == "PCMU":
            return CodecConverter.g711_ulaw_encode(pcm_16k)
        elif codec == "PCMA":
            return CodecConverter.g711_alaw_encode(pcm_16k)
        elif codec == "G722":
            # TODO: Implement G.722 encoding
            logger.warning("G.722 encoding not implemented yet")
            return b""
        else:
            logger.error("Unknown codec: %s", codec)
            return b""
