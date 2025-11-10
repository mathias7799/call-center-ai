# Local Testing Guide - SIP Integration

This guide explains how to run the Call Center AI application locally with SIP telephony support, using FreeSWITCH as a local SIP server.

## 🎯 Overview

The local testing setup includes:
- **Call Center AI Application** - Main application with SIP support
- **FreeSWITCH** - Open-source SIP server for testing
- **Redis** - Cache and pub/sub messaging
- **SQLite** - Local database (no Azure Cosmos DB needed)
- **Local Queues** - In-memory queues (no Azure Storage Queues needed)

## 📋 Prerequisites

1. **Docker & Docker Compose** installed
2. **Azure Services** (still required):
   - Azure OpenAI (for LLM)
   - Azure Speech Services (for STT/TTS)
   - Azure AI Search (for knowledge base)
3. **Optional**:
   - Twilio account (for SMS)
   - SIP softphone (Zoiper, Linphone, MicroSIP)

## 🚀 Quick Start

### 1. Clone and Setup

```bash
# Clone the repository
git clone <repository-url>
cd call-center-ai

# Copy environment template
cp .env.example .env

# Edit .env with your Azure credentials
nano .env
```

### 2. Configure Environment Variables

Edit `.env` and fill in at minimum:
```bash
# Required
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-key-here

AZURE_COGNITIVE_SERVICE_ENDPOINT=https://your-region.api.cognitive.microsoft.com/
AZURE_COGNITIVE_SERVICE_API_KEY=your-key-here

AZURE_SEARCH_ENDPOINT=https://your-search.search.windows.net
AZURE_SEARCH_API_KEY=your-key-here
```

### 3. Start Services

```bash
# Build and start all services
docker-compose up --build

# Or run in background
docker-compose up -d --build

# View logs
docker-compose logs -f app
```

### 4. Test the Setup

The application should now be running:
- **API**: http://localhost:8080
- **Health Check**: http://localhost:8080/health
- **FreeSWITCH**: localhost:5060 (SIP)

## 📞 Making Test Calls

### Option 1: Using a SIP Softphone

1. **Install a SIP softphone**:
   - **Zoiper** (Windows/Mac/Linux)
   - **Linphone** (Windows/Mac/Linux)
   - **MicroSIP** (Windows)

2. **Configure softphone**:
   ```
   Server: localhost (or your Docker host IP)
   Port: 5060
   Username: 5678
   Password: 5678
   Transport: UDP
   ```

3. **Make a call**:
   - Dial `1234` to reach the AI agent
   - The AI should answer and start conversation

### Option 2: Using FreeSWITCH Console

```bash
# Enter FreeSWITCH container
docker exec -it call-center-freeswitch fs_cli

# Make a test call from extension 5678 to AI agent (1234)
originate user/5678 &bridge(user/1234)
```

## 🏗️ Architecture

```
┌─────────────────┐
│  SIP Softphone  │ (Extension 5678)
│   (You/Test)    │
└────────┬────────┘
         │ SIP/RTP
         ▼
┌─────────────────┐
│   FreeSWITCH    │ (localhost:5060)
│   SIP Server    │
└────────┬────────┘
         │ SIP/RTP
         ▼
┌─────────────────┐
│  Call Center    │ (Extension 1234)
│   AI App        │
│  - PJSIP Stack  │
│  - STT/TTS      │
│  - LLM Chat     │
└─────────────────┘
```

## 📁 Directory Structure

```
call-center-ai/
├── app/                          # Application code
│   ├── persistence/
│   │   ├── sip/                  # SIP implementation
│   │   │   ├── account.py        # SIP account management
│   │   │   ├── call.py           # Call handling
│   │   │   ├── codecs.py         # Audio codec conversion
│   │   │   └── rtp_bridge.py    # RTP ↔ WebSocket bridge
│   │   └── sip_telephony.py      # ITelephony SIP implementation
├── freeswitch/
│   └── conf/                     # FreeSWITCH configuration
│       └── directory/default/
│           ├── 1234.xml          # AI Agent extension
│           └── 5678.xml          # Test user extension
├── data/                         # SQLite database (auto-created)
├── logs/                         # Application logs
├── config-local-sip.yaml        # Local SIP configuration
├── docker-compose.yml           # Docker orchestration
├── Dockerfile.local             # Local development Dockerfile
└── .env                         # Environment variables
```

## 🔧 Configuration Files

### config-local-sip.yaml

Main configuration file for local SIP testing:
```yaml
telephony:
  mode: sip
  sip:
    gateway_host: freeswitch
    gateway_port: 5060
    username: "1234"
    password: "1234"
    phone_number: "1234"
    transport: udp

database:
  mode: sqlite
  sqlite:
    database_path: ./data/calls.db

queue:
  mode: local
```

## 🐛 Troubleshooting

### Issue: Application won't start

```bash
# Check logs
docker-compose logs app

# Verify environment variables
docker-compose config

# Restart services
docker-compose restart
```

### Issue: Can't connect with SIP softphone

```bash
# Check FreeSWITCH status
docker exec -it call-center-freeswitch fs_cli -x "status"

# Check SIP registrations
docker exec -it call-center-freeswitch fs_cli -x "sofia status"

# Check if port is open
netstat -an | grep 5060
```

### Issue: No audio during call

```bash
# Check RTP ports
docker-compose logs freeswitch | grep RTP

# Verify codec support
docker exec -it call-center-freeswitch fs_cli -x "show codecs"

# Check firewall rules (RTP ports 10000-10100 should be open)
```

### Issue: PJSIP not installed

If you see errors about missing `pjsua2` module:
```bash
# Rebuild Docker image
docker-compose build --no-cache app

# Verify PJSIP installation
docker exec -it call-center-app python3 -c "import pjsua2; print('PJSIP OK')"
```

## 📊 Monitoring

### View Application Logs
```bash
docker-compose logs -f app
```

### View FreeSWITCH Logs
```bash
docker-compose logs -f freeswitch
```

### Check Call State
```bash
# API endpoint
curl http://localhost:8080/api/calls

# Health check
curl http://localhost:8080/health
```

## 🔐 Security Notes

For local testing:
- Default passwords (`1234`, `5678`) are acceptable
- FreeSWITCH only listens on localhost
- No external traffic allowed by default

For production:
- Change all passwords
- Use TLS for SIP (port 5061)
- Enable SRTP for encrypted media
- Implement proper authentication
- Use firewall rules to restrict access

## 📚 Next Steps

1. **Test basic calls** - Make calls and verify AI responses
2. **Test audio quality** - Check STT/TTS performance
3. **Test error handling** - Simulate network issues, hangups
4. **Load testing** - Multiple concurrent calls
5. **Production deployment** - Configure for real SIP gateway (Miralix, etc.)

## 🆘 Support

- **Documentation**: See `SIP_IMPLEMENTATION_GUIDE.md` for technical details
- **Issues**: Report bugs in GitHub issues
- **Configuration**: Check `config-local-sip.yaml` for all options

## 📝 Notes

- **PJSIP Integration**: Currently in stub mode. Full integration requires PJSIP Python bindings.
- **Audio Codecs**: G.711 (μ-law/A-law) supported via Python's `audioop` module
- **NAT Traversal**: Use STUN server if testing across networks
- **Firewalls**: Ensure RTP ports (10000-10100) are open

---

**Happy Testing!** 🎉
