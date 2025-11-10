# SIP Integration Examples

This document provides practical examples for using the SIP telephony implementation.

## Table of Contents
- [Basic Usage](#basic-usage)
- [Configuration Examples](#configuration-examples)
- [Testing Examples](#testing-examples)
- [Integration Examples](#integration-examples)
- [Troubleshooting](#troubleshooting)

## Basic Usage

### 1. Starting the Application with SIP

```bash
# Using Docker Compose (recommended for local testing)
docker-compose up

# Or run locally (requires PJSIP installed)
make dev
```

### 2. Making a Test Call

**Using a SIP Softphone:**

1. Install Zoiper, Linphone, or MicroSIP
2. Configure:
   - Server: `localhost:5060`
   - Username: `5678`
   - Password: `5678`
3. Dial `1234` to reach the AI agent

**Using FreeSWITCH CLI:**

```bash
# Enter FreeSWITCH container
docker exec -it call-center-freeswitch fs_cli

# Make a call from extension 5678 to AI agent (1234)
originate user/5678 &bridge(user/1234)

# Check active calls
show calls

# Check SIP registrations
sofia status
```

### 3. Checking SIP Status

```bash
# Quick status check
make sip-status

# Or manually:
docker exec call-center-freeswitch fs_cli -x "status"
docker exec call-center-freeswitch fs_cli -x "sofia status"
docker exec call-center-freeswitch fs_cli -x "show calls"
```

## Configuration Examples

### Example 1: Local Development with FreeSWITCH

```yaml
# config-local-sip.yaml
telephony:
  mode: sip
  sip:
    gateway_host: freeswitch  # Docker service name
    gateway_port: 5060
    username: "1234"
    password: "1234"
    phone_number: "1234"
    transport: udp
    rtp_port_range_start: 10000
    rtp_port_range_end: 20000

database:
  mode: sqlite
  sqlite:
    database_path: ./data/calls.db

queue:
  mode: local
```

### Example 2: Production with Miralix Gateway

```yaml
# config-production-sip.yaml
telephony:
  mode: sip
  sip:
    gateway_host: sip.miralix.yourdomain.com
    gateway_port: 5061  # TLS
    username: "ai-agent-001"
    password: ${SIP_PASSWORD}  # From environment
    phone_number: "+15551234567"
    transport: tls  # Secure transport
    rtp_port_range_start: 10000
    rtp_port_range_end: 20000
    stun_server: stun.miralix.com:3478  # NAT traversal

database:
  mode: cosmos  # Azure Cosmos DB for production
  cosmos:
    endpoint: ${COSMOS_ENDPOINT}
    key: ${COSMOS_KEY}
    database: calls

queue:
  mode: azure  # Azure Storage Queues for production
  azure:
    connection_string: ${AZURE_STORAGE_CONNECTION_STRING}
```

### Example 3: Hybrid Mode (SIP + Azure Services)

```yaml
# config-hybrid.yaml
telephony:
  mode: sip  # SIP for telephony
  sip:
    gateway_host: your-gateway.example.com
    gateway_port: 5060
    username: "agent"
    password: ${SIP_PASSWORD}
    phone_number: "+15555551234"
    transport: tcp

# Still use Azure for AI services
llm:
  fast:
    mode: azure
    azure:
      endpoint: ${AZURE_OPENAI_ENDPOINT}
      deployment: gpt-4o-mini
      api_key: ${AZURE_OPENAI_API_KEY}

resources:
  cognitive_service:
    endpoint: ${AZURE_COGNITIVE_SERVICE_ENDPOINT}
    api_key: ${AZURE_COGNITIVE_SERVICE_API_KEY}
```

## Testing Examples

### Example 1: Test Call Flow

```python
# test_sip_call_flow.py
import asyncio
from app.persistence.sip_telephony import SipTelephony
from app.helpers.config_models.telephony import SipModel

async def test_call_flow():
    # Initialize SIP telephony
    config = SipModel(
        gateway_host="localhost",
        gateway_port=5060,
        username="1234",
        password="1234",
        phone_number="1234",
        transport="udp",
    )

    sip = SipTelephony(config)

    # Check readiness
    status = await sip.readiness()
    print(f"SIP Status: {status}")

    # Simulate incoming call
    call_id, server_id = await sip.answer_call(
        callback_url="http://localhost:8080/callback",
        incoming_context="call-123",
        phone_number="+15555551234",
        wss_url="ws://localhost:8080/audio",
    )

    print(f"Call answered: {call_id}")

    # Play TTS
    await sip.play_media(
        call_connection_id=call_id,
        text="<speak>Hello, how can I help you?</speak>",
        context="greeting",
    )

    # Hangup after 5 seconds
    await asyncio.sleep(5)
    await sip.hangup_call(call_id)

    print("Call completed")

if __name__ == "__main__":
    asyncio.run(test_call_flow())
```

### Example 2: Test Audio Codec Conversion

```python
# test_codecs.py
from app.persistence.sip.codecs import CodecConverter
import wave

# Create test PCM audio (16kHz, 16-bit, mono)
pcm_16k = b'\x00\x00' * 16000  # 1 second of silence

# Encode to G.711 μ-law
ulaw = CodecConverter.g711_ulaw_encode(pcm_16k)
print(f"PCM size: {len(pcm_16k)} bytes")
print(f"G.711 size: {len(ulaw)} bytes")
print(f"Compression ratio: {len(pcm_16k) / len(ulaw):.2f}x")

# Decode back to PCM
pcm_decoded = CodecConverter.g711_ulaw_decode(ulaw)
print(f"Decoded size: {len(pcm_decoded)} bytes")

# Save to WAV file
with wave.open("test_output.wav", "wb") as wf:
    wf.setnchannels(1)  # Mono
    wf.setsampwidth(2)  # 16-bit
    wf.setframerate(16000)  # 16kHz
    wf.writeframes(pcm_decoded)

print("Saved to test_output.wav")
```

### Example 3: Test RTP Bridge

```python
# test_rtp_bridge.py
import asyncio
from app.persistence.sip.rtp_bridge import RtpWebSocketBridge

async def test_bridge():
    # Create RTP bridge (without real AudioMedia for now)
    bridge = RtpWebSocketBridge(
        audio_media=None,  # Would be pj.AudioMedia in real use
        codec="PCMU",
        call_id="test-call-123",
    )

    # Simulate sending audio to call
    test_pcm = b'\x00\x00' * 160  # 10ms of audio
    await bridge.send_to_call(test_pcm)
    print("Audio sent to call")

    # Check queues
    print(f"Outgoing queue size: {bridge.outgoing_queue.qsize()}")
    print(f"Incoming queue size: {bridge.incoming_queue.qsize()}")

if __name__ == "__main__":
    asyncio.run(test_bridge())
```

## Integration Examples

### Example 1: Custom Call Handler

```python
# custom_call_handler.py
from app.persistence.itelephony import ITelephony
from app.helpers.logging import logger

class MyCallHandler:
    def __init__(self, telephony: ITelephony):
        self.telephony = telephony

    async def handle_incoming_call(self, call_id: str):
        """Handle an incoming call with custom logic."""
        logger.info(f"Handling incoming call: {call_id}")

        try:
            # Answer call
            await self.telephony.answer_call(
                callback_url="http://localhost:8080/callback",
                incoming_context=call_id,
                phone_number="+15555551234",
                wss_url="ws://localhost:8080/audio",
            )

            # Play greeting
            await self.telephony.play_media(
                call_connection_id=call_id,
                text="<speak>Welcome to our service!</speak>",
                context="greeting",
            )

            # Start recording
            recording_id = await self.telephony.start_recording(
                call_connection_id=call_id,
                server_call_id=call_id,
            )

            if recording_id:
                logger.info(f"Recording started: {recording_id}")

            # Handle conversation...

        except Exception as e:
            logger.exception(f"Error handling call: {e}")
            await self.telephony.hangup_call(call_id)
```

### Example 2: SIP Event Webhooks

```python
# sip_webhooks.py
from fastapi import FastAPI, Request
from app.persistence.sip_telephony import SipTelephony

app = FastAPI()
sip_telephony = None  # Initialize from config

@app.post("/sip/incoming")
async def handle_incoming_call(request: Request):
    """Handle incoming SIP call webhook."""
    data = await request.json()

    call_id = data.get("call_id")
    from_number = data.get("from")

    # Answer call using SIP telephony
    connection_id, server_id = await sip_telephony.answer_call(
        callback_url="http://localhost:8080/sip/events",
        incoming_context=call_id,
        phone_number=from_number,
        wss_url="ws://localhost:8080/audio",
    )

    return {
        "status": "answered",
        "call_id": connection_id,
    }

@app.post("/sip/events")
async def handle_sip_events(request: Request):
    """Handle SIP call events."""
    data = await request.json()
    event_type = data.get("type")
    call_id = data.get("call_id")

    if event_type == "call_connected":
        # Start conversation
        pass
    elif event_type == "call_disconnected":
        # Clean up
        pass

    return {"status": "ok"}
```

## Troubleshooting

### Problem: PJSIP not available

```bash
# Check if PJSIP is installed
python3 -c "import pjsua2; print('OK')"

# If not, install it
make install-pjsip

# Or manually
./scripts/install-pjsip.sh
```

### Problem: Can't connect to FreeSWITCH

```bash
# Check if FreeSWITCH is running
docker ps | grep freeswitch

# Check FreeSWITCH logs
docker logs call-center-freeswitch

# Restart FreeSWITCH
docker-compose restart freeswitch

# Check SIP port
netstat -an | grep 5060
```

### Problem: No audio in call

```bash
# Check RTP ports
docker logs call-center-app | grep RTP

# Verify codec support
docker exec call-center-freeswitch fs_cli -x "show codecs"

# Test codec conversion
python3 -m app.persistence.sip.codecs
```

### Problem: Call connects but no speech recognition

```bash
# Check WebSocket connection
docker logs call-center-app | grep WebSocket

# Verify audio pipeline
docker logs call-center-app | grep "audio streaming"

# Check Azure Speech Services credentials
docker exec call-center-app env | grep AZURE_COGNITIVE
```

## Additional Resources

- **LOCAL_TESTING_GUIDE.md** - Complete local testing guide
- **SIP_IMPLEMENTATION_GUIDE.md** - Technical implementation details
- **SIP_STATUS.md** - Current implementation status
- **Makefile** - All available commands

## Getting Help

If you encounter issues:

1. Check the logs: `make docker-logs`
2. Verify configuration: `docker-compose config`
3. Test components individually (see examples above)
4. Review FreeSWITCH status: `make sip-status`

---

**Happy Testing!** 🎉
