# SIP Implementation Guide

This guide provides a complete roadmap for implementing SIP telephony support to work with gateways like Miralix, FreeSWITCH, or Asterisk.

## Current Status

✅ **Complete:**
- ITelephony interface defined
- Configuration model ready
- Stub implementation with architecture documentation
- All methods specified and documented

⚠️ **Needs Implementation:**
- SIP protocol handling (signaling)
- RTP audio streaming
- Codec conversion
- WebSocket bridge for existing audio pipeline

## Architecture Overview

### High-Level Flow

```
┌─────────────────┐
│  SIP Gateway    │  (Miralix/FreeSWITCH/Asterisk)
│  (PBX/Trunk)    │
└────────┬────────┘
         │ SIP (UDP/TCP/TLS 5060)
         │ RTP (UDP 10000-20000)
         ▼
┌─────────────────────────────────────────────────────────┐
│               SipTelephony Implementation                │
│  ┌────────────────────┐      ┌──────────────────────┐  │
│  │  SIP Stack         │      │  RTP Handler         │  │
│  │  - INVITE/200 OK   │      │  - G.711/G.722       │  │
│  │  - ACK/BYE         │      │  - RTCP (QoS)        │  │
│  │  - REFER (transfer)│      │  - DTMF (RFC 4733)   │  │
│  └─────────┬──────────┘      └──────────┬───────────┘  │
│            │                            │              │
│            │   ┌───────────────────────┘              │
│            ▼   ▼                                        │
│  ┌─────────────────────────────────────────┐           │
│  │  Codec Converter (G.711/G.722 <-> PCM)  │           │
│  └─────────────────┬───────────────────────┘           │
│                    │                                    │
│                    │ PCM 16kHz 16-bit mono              │
│                    ▼                                    │
│  ┌──────────────────────────────────────────┐          │
│  │    WebSocket Bridge (bi-directional)     │          │
│  └─────────────────┬────────────────────────┘          │
└────────────────────┼───────────────────────────────────┘
                     │
                     │ WebSocket
                     ▼
┌──────────────────────────────────────────────────────────┐
│         Existing Audio Pipeline (Unchanged)               │
│  ┌──────────┐  ┌─────┐  ┌──────┐  ┌──────┐  ┌──────┐  │
│  │ AECStream│  │ STT │  │ LLM  │  │ TTS  │  │ Out  │  │
│  └──────────┘  └─────┘  └──────┘  └──────┘  └──────┘  │
└──────────────────────────────────────────────────────────┘
```

### Call Flow - Inbound Call

```
SIP Gateway         SipTelephony           Audio Pipeline
     │                    │                      │
     │─────INVITE────────>│                      │
     │                    │ Create call state    │
     │                    │ Allocate RTP port    │
     │<────200 OK─────────│ (with SDP)           │
     │─────ACK───────────>│                      │
     │                    │                      │
     │═════RTP Audio═════>│                      │
     │                    │ Decode G.711         │
     │                    │ -> PCM 16kHz         │
     │                    │──────Audio──────────>│
     │                    │                      │ STT -> LLM
     │                    │<─────Audio───────────│ TTS
     │                    │ PCM -> G.711         │
     │<════RTP Audio══════│                      │
     │                    │                      │
     │─────BYE───────────>│                      │
     │<────200 OK─────────│                      │
     │                    │ Clean up RTP         │
     │                    │ Release port         │
```

## Implementation Plan

### Phase 1: Library Selection & Setup (Day 1)

#### Option A: pjsua2 (Recommended)

**Pros:**
- Battle-tested, used in production worldwide
- Full SIP/SDP/RTP stack
- Excellent codec support (G.711, G.722, Opus, etc.)
- NAT traversal (STUN/TURN) built-in
- Python bindings available
- PJSIP is the gold standard for SIP

**Cons:**
- Larger dependency
- C++ library with Python bindings (requires compilation)
- Learning curve

**Installation:**
```bash
# Install system dependencies (Debian/Ubuntu)
sudo apt-get install build-essential python3-dev \
    libasound2-dev libssl-dev

# Install pjsua2
pip install pjsua2

# Or build from source for custom codecs
git clone https://github.com/pjsip/pjproject.git
cd pjproject
./configure --enable-shared --disable-sound --disable-video
make dep && make
cd pjsip-apps/src/python
python setup.py install
```

#### Option B: aiosip (Alternative)

**Pros:**
- Pure Python, asyncio-native
- Easier to integrate with existing FastAPI code
- Lightweight
- Good for simple SIP scenarios

**Cons:**
- Less mature than PJSIP
- Limited codec support (needs separate RTP library)
- May need additional libraries for RTP (aiortc)
- Less battle-tested

**Installation:**
```bash
pip install aiosip aiortc
```

**Recommendation:** Use **pjsua2** for production reliability, especially for call center use case.

### Phase 2: Basic SIP Implementation (Days 2-3)

#### 2.1 Create SIP Account Manager

```python
# app/persistence/sip/account.py
import pjsua2 as pj
from app.helpers.config_models.telephony import SipModel

class SipAccount(pj.Account):
    """SIP account handler for registration and authentication."""

    def __init__(self, config: SipModel):
        super().__init__()
        self.config = config
        self.calls: dict[str, 'SipCall'] = {}

    def onRegState(self, prm: pj.OnRegStateParam):
        """Called when registration status changes."""
        ai = self.getInfo()
        logger.info(
            "SIP registration status: %s (%s)",
            ai.regStatus,
            ai.regStatusText
        )

    def onIncomingCall(self, prm: pj.OnIncomingCallParam):
        """Called when receiving an incoming call."""
        call = SipCall(self, call_id=prm.callId)
        call_info = call.getInfo()

        logger.info(
            "Incoming SIP call from %s to %s",
            call_info.remoteUri,
            call_info.localUri
        )

        self.calls[prm.callId] = call
        # Trigger call event processing
        asyncio.create_task(self._handle_incoming_call(call))
```

#### 2.2 Implement SIP Call Handler

```python
# app/persistence/sip/call.py
class SipCall(pj.Call):
    """Handler for individual SIP calls."""

    def __init__(self, account, call_id=None):
        super().__init__(account, call_id)
        self.rtp_bridge = None
        self.call_id_str = str(uuid.uuid4())

    def onCallState(self, prm: pj.OnCallStateParam):
        """Called when call state changes."""
        ci = self.getInfo()
        logger.info(
            "Call %s state: %s",
            self.call_id_str,
            ci.stateText
        )

        if ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
            # Clean up
            if self.rtp_bridge:
                self.rtp_bridge.stop()

    def onCallMediaState(self, prm: pj.OnCallMediaStateParam):
        """Called when media state changes."""
        ci = self.getInfo()

        for mi in ci.media:
            if mi.type == pj.PJMEDIA_TYPE_AUDIO and \
               mi.status == pj.PJSUA_CALL_MEDIA_ACTIVE:
                # Media is active, set up audio
                am = self.getAudioMedia(mi.index)
                self._setup_audio_bridge(am)
```

#### 2.3 Implement RTP Bridge

```python
# app/persistence/sip/rtp_bridge.py
import asyncio
from typing import AsyncIterator

class RtpWebSocketBridge:
    """
    Bridges RTP audio <-> WebSocket for existing pipeline.

    Handles:
    - RTP packet reception
    - Codec decoding (G.711/G.722 -> PCM 16kHz)
    - WebSocket transmission
    - WebSocket reception
    - Codec encoding (PCM 16kHz -> G.711/G.722)
    - RTP packet transmission
    """

    def __init__(
        self,
        audio_media: pj.AudioMedia,
        codec: str = "PCMU",  # G.711 μ-law
    ):
        self.audio_media = audio_media
        self.codec = codec
        self.running = False

        # Queues for audio data
        self.incoming_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.outgoing_queue: asyncio.Queue[bytes] = asyncio.Queue()

    async def start(self):
        """Start bridging RTP <-> queues."""
        self.running = True
        await asyncio.gather(
            self._rtp_to_queue(),
            self._queue_to_rtp(),
        )

    async def _rtp_to_queue(self):
        """Receive RTP, decode, push to queue."""
        while self.running:
            # Get RTP packet from PJSIP
            frame = await self._get_rtp_frame()

            # Decode to PCM 16kHz
            pcm = self._decode_codec(frame)

            # Push to incoming queue for WebSocket
            await self.incoming_queue.put(pcm)

    async def _queue_to_rtp(self):
        """Get from queue, encode, send as RTP."""
        while self.running:
            # Get PCM from outgoing queue (from WebSocket)
            pcm = await self.outgoing_queue.get()

            # Encode to G.711/G.722
            encoded = self._encode_codec(pcm)

            # Send via RTP
            await self._send_rtp_frame(encoded)

    def _decode_codec(self, data: bytes) -> bytes:
        """Decode G.711/G.722 to PCM 16kHz 16-bit."""
        if self.codec == "PCMU":
            # G.711 μ-law decoding
            # TODO: Implement or use library (audioop, pydub, etc.)
            pass
        elif self.codec == "PCMA":
            # G.711 A-law decoding
            pass
        elif self.codec == "G722":
            # G.722 decoding (requires separate library)
            pass

    def _encode_codec(self, pcm: bytes) -> bytes:
        """Encode PCM 16kHz 16-bit to G.711/G.722."""
        # Mirror of _decode_codec
        pass
```

### Phase 3: Integration with Existing Code (Days 4-5)

#### 3.1 Complete SipTelephony Implementation

Update `app/persistence/sip_telephony.py` to use PJSIP:

```python
class SipTelephony(ITelephony):
    _config: SipModel
    _endpoint: pj.Endpoint
    _transport: pj.TransportConfig
    _account: SipAccount

    def __init__(self, config: SipModel):
        self._config = config
        self._init_pjsip()

    def _init_pjsip(self):
        """Initialize PJSIP stack."""
        self._endpoint = pj.Endpoint()
        self._endpoint.libCreate()

        # Configure endpoint
        ep_cfg = pj.EpConfig()
        ep_cfg.logConfig.level = 4
        ep_cfg.logConfig.consoleLevel = 4
        self._endpoint.libInit(ep_cfg)

        # Create transport
        transport_type = {
            "udp": pj.PJSIP_TRANSPORT_UDP,
            "tcp": pj.PJSIP_TRANSPORT_TCP,
            "tls": pj.PJSIP_TRANSPORT_TLS,
        }[self._config.transport]

        tcfg = pj.TransportConfig()
        tcfg.port = self._config.gateway_port
        self._transport = self._endpoint.transportCreate(
            transport_type,
            tcfg
        )

        # Start endpoint
        self._endpoint.libStart()

        # Create and register account
        self._register_account()

    def _register_account(self):
        """Register with SIP gateway."""
        acc_cfg = pj.AccountConfig()
        acc_cfg.idUri = f"sip:{self._config.username}@{self._config.gateway_host}"
        acc_cfg.regConfig.registrarUri = (
            f"sip:{self._config.gateway_host}:{self._config.gateway_port}"
        )

        # Authentication
        cred = pj.AuthCredInfo(
            "digest",
            "*",  # Realm (wildcard)
            self._config.username,
            0,
            self._config.password.get_secret_value()
        )
        acc_cfg.sipConfig.authCreds.append(cred)

        # Create account
        self._account = SipAccount(self._config)
        self._account.create(acc_cfg)

    async def answer_call(
        self,
        callback_url: str,
        incoming_context: str,  # SIP call-id from event
        phone_number: PhoneNumber,
        wss_url: str,
    ) -> tuple[str, str]:
        """Answer an incoming SIP call."""
        # Parse incoming_context to get SIP call
        sip_call = self._account.calls.get(incoming_context)
        if not sip_call:
            raise ValueError(f"Call {incoming_context} not found")

        # Answer the call
        call_prm = pj.CallOpParam()
        call_prm.statusCode = 200
        sip_call.answer(call_prm)

        # Return call IDs
        return (incoming_context, incoming_context)
```

#### 3.2 NO Changes Needed in Application Code!

The beauty of the ITelephony interface is that **the application code doesn't need to change**.

Files like `call_events.py`, `call_utils.py`, `main.py` will work with both Azure Communication Services and SIP because they use the same interface.

The only change needed is in configuration:

```yaml
telephony:
  mode: sip
  sip:
    gateway_host: 192.168.1.100  # Your Miralix/FreeSWITCH IP
    gateway_port: 5060
    username: "agent1234"
    password: "your_password"
    phone_number: "1234"  # Extension number
    transport: udp
```

### Phase 4: Codec Implementation (Day 6)

#### 4.1 Install Codec Libraries

```bash
# G.711 (μ-law, A-law) - Built into Python
# Use audioop module

# G.722 - Requires library
pip install g722

# Or for comprehensive codec support
pip install pydub ffmpeg-python
```

#### 4.2 Implement Codec Conversion

```python
# app/persistence/sip/codecs.py
import audioop
import array

class CodecConverter:
    """Convert between telephony codecs and PCM 16kHz."""

    @staticmethod
    def g711_ulaw_decode(data: bytes, sample_rate: int = 8000) -> bytes:
        """Decode G.711 μ-law to PCM."""
        # Decode μ-law to linear PCM
        pcm_8k = audioop.ulaw2lin(data, 2)  # 2 bytes per sample

        # Resample 8kHz -> 16kHz
        pcm_16k, _ = audioop.ratecv(
            pcm_8k,
            2,  # sample width
            1,  # channels
            8000,  # input rate
            16000,  # output rate
            None  # state
        )
        return pcm_16k

    @staticmethod
    def g711_ulaw_encode(pcm_16k: bytes) -> bytes:
        """Encode PCM to G.711 μ-law."""
        # Resample 16kHz -> 8kHz
        pcm_8k, _ = audioop.ratecv(
            pcm_16k,
            2,  # sample width
            1,  # channels
            16000,  # input rate
            8000,  # output rate
            None  # state
        )

        # Encode to μ-law
        ulaw = audioop.lin2ulaw(pcm_8k, 2)
        return ulaw
```

### Phase 5: Testing & Local Setup (Days 7-8)

#### 5.1 Local FreeSWITCH Setup (Docker)

```bash
# docker-compose.yml
version: '3'
services:
  freeswitch:
    image: signalwire/freeswitch:latest
    ports:
      - "5060:5060/udp"  # SIP
      - "5060:5060/tcp"   # SIP/TCP
      - "10000-20000:10000-20000/udp"  # RTP
    volumes:
      - ./freeswitch/conf:/etc/freeswitch
    environment:
      - SOUND_RATES=8000:16000:32000:48000
```

Configure FreeSWITCH extension:

```xml
<!-- freeswitch/conf/directory/default/1234.xml -->
<include>
  <user id="1234">
    <params>
      <param name="password" value="1234"/>
      <param name="vm-password" value="1234"/>
    </params>
    <variables>
      <variable name="toll_allow" value="domestic,international,local"/>
      <variable name="accountcode" value="1234"/>
      <variable name="user_context" value="default"/>
      <variable name="effective_caller_id_name" value="Extension 1234"/>
      <variable name="effective_caller_id_number" value="1234"/>
    </variables>
  </user>
</include>
```

Start FreeSWITCH:
```bash
docker-compose up -d
```

#### 5.2 Test with SoftPhone

1. Install a SIP softphone (Zoiper, Linphone, or MicroSIP)
2. Configure to connect to your FreeSWITCH:
   - Server: localhost:5060
   - Username: 5678  (another extension)
   - Password: 5678
3. Call extension 1234 (your AI agent)
4. Should connect and hear the AI agent respond!

#### 5.3 Configuration for Local Testing

```yaml
# config-sip-local.yaml
public_domain: http://localhost:8080

telephony:
  mode: sip
  sip:
    gateway_host: localhost
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

# ... rest of config
```

Run the application:
```bash
python -m app.main --config config-sip-local.yaml
```

### Phase 6: Production Deployment with Miralix

#### 6.1 Miralix Configuration

Connect to your Miralix gateway (example):

```yaml
telephony:
  mode: sip
  sip:
    gateway_host: sip.miralix.yourdomain.com
    gateway_port: 5060
    username: "ai-agent-001"
    password: "secure_password"
    phone_number: "+15551234567"
    transport: tcp  # or tls for security
    rtp_port_range_start: 10000
    rtp_port_range_end: 20000
    stun_server: stun.miralix.com:3478
```

#### 6.2 Firewall Rules

Open ports on your server:
```bash
# SIP signaling
sudo ufw allow 5060/tcp
sudo ufw allow 5060/udp

# RTP media
sudo ufw allow 10000:20000/udp
```

#### 6.3 NAT Traversal

For servers behind NAT, enable STUN in config and ensure proper port forwarding.

## Summary: What Needs to Be Done

### Code Changes Required:

1. ✅ **ITelephony interface** - Complete
2. ✅ **Configuration** - Complete
3. ✅ **Azure implementation** - Complete
4. ⚠️ **SIP implementation** - Needs full implementation:
   - Install pjsua2
   - Implement SipAccount, SipCall classes
   - Implement RtpWebSocketBridge
   - Implement codec conversion
   - Wire up to ITelephony interface

### Dependencies to Add:

```toml
# pyproject.toml
dependencies = [
  # ... existing dependencies
  "pjsua2~=2.14",  # SIP/RTP stack
  # OR for pure Python:
  # "aiosip~=0.2",
  # "aiortc~=1.5",
]
```

### Testing Strategy:

1. **Local Development:**
   - FreeSWITCH in Docker
   - SIP softphone (Zoiper)
   - Test calls between softphone and AI agent

2. **Staging:**
   - Test with real Miralix gateway
   - Verify NAT traversal
   - Load testing

3. **Production:**
   - Deploy with proper firewall rules
   - Monitor call quality (RTCP stats)
   - Set up alerting

## Estimated Timeline

- **Week 1:** Library setup + basic SIP implementation (Phases 1-2)
- **Week 2:** RTP bridge + codec conversion (Phases 3-4)
- **Week 3:** Testing + bug fixes (Phases 5-6)
- **Week 4:** Production deployment + monitoring

**Total:** 3-4 weeks for production-ready SIP integration

## Next Steps

Ready to implement? Let me know and I can:
1. Implement the full SIP stack
2. Set up local testing environment
3. Create integration tests
4. Deploy to staging/production

The interface is solid and ready - now we just need to fill in the SIP implementation!
