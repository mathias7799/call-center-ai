# SIP Telephony Testing Guide

Quick guide for testing the SIP telephony implementation.

## 🚀 Quick Start (5 minutes)

### 1. Install PJSIP
```bash
make install-pjsip
make test-pjsip  # Verify installation
```

### 2. Start Services
```bash
# Setup environment
cp .env.example .env
# Edit .env with your Azure credentials

# Start complete stack
make docker-up

# Verify all services are healthy
make health
```

### 3. Test with SIP Softphone

**Configure your SIP softphone** (e.g., Zoiper, Linphone, or Bria):
```
Server/Domain: localhost
Port: 5060
Username: 5678
Password: 5678
Transport: UDP
```

**Call extension 1234** to reach the AI agent

## 🎯 What Should Happen

1. **SIP Registration**:
   - Your softphone should register successfully
   - Check: `make sip-status` shows your registration

2. **Outgoing Call**:
   - Dial 1234 from your softphone
   - Call should connect within 1-2 seconds
   - Check logs: `make docker-logs`

3. **Audio Flow**:
   - You should hear the AI agent's greeting
   - Speak to test STT (Speech-to-Text)
   - AI should respond with TTS (Text-to-Speech)

4. **Complete Flow**:
```
Your Voice → Softphone → FreeSWITCH → SIP/RTP → Python App
          → AudioMediaPort → Codec Conversion → WebSocket
          → Azure STT → LLM → Azure TTS
          → WebSocket → Codec Conversion → AudioMediaPort
          → RTP/SIP → FreeSWITCH → Softphone → Your Ears
```

## 🔍 Troubleshooting

### Check Service Status
```bash
# Overall health
make health

# SIP system detailed status
make sip-status

# View logs
make docker-logs           # Application
make docker-logs-freeswitch # FreeSWITCH
```

### Common Issues

**1. "PJSIP not available"**
```bash
# Install PJSIP
make install-pjsip

# Verify
python3 -c "import pjsua2; print(pjsua2.Endpoint.version())"
```

**2. "Connection refused" (Port 5060)**
```bash
# Check FreeSWITCH is running
docker ps | grep freeswitch

# Restart if needed
docker-compose restart freeswitch
```

**3. "No audio" / "One-way audio"**
```bash
# Check RTP ports
netstat -an | grep "10000:10100"

# Check application logs for AudioMediaPort activity
make docker-logs | grep -i "audio\|rtp\|frame"
```

**4. "Registration failed"**
```bash
# Check FreeSWITCH logs
make docker-logs-freeswitch | grep -i "register\|auth"

# Verify extension exists
docker exec call-center-freeswitch fs_cli -x "list_users"
```

## 📊 Test Scenarios

### Scenario 1: Basic Call
- [ ] Register softphone (extension 5678)
- [ ] Call extension 1234
- [ ] Call connects
- [ ] Hear AI greeting
- [ ] Hangup works

### Scenario 2: Audio Quality
- [ ] Speak clearly to AI
- [ ] AI understands (check STT logs)
- [ ] AI responds naturally
- [ ] No audio dropouts or distortion
- [ ] No echo or feedback

### Scenario 3: Call Lifecycle
- [ ] Make multiple consecutive calls
- [ ] Each call connects properly
- [ ] No resource leaks
- [ ] Clean disconnection

### Scenario 4: Error Handling
- [ ] Call with invalid extension (should reject)
- [ ] Hangup during conversation (should cleanup)
- [ ] Network interruption (should recover)

## 🔬 Advanced Testing

### Test Audio Codec Conversion
```bash
# Test codec conversion manually
python3 << 'EOF'
from app.persistence.sip.codecs import CodecConverter

converter = CodecConverter()

# Test G.711 encode/decode
pcm = b'\x00\x01' * 160  # 320 bytes PCM
g711 = converter.g711_ulaw_encode(pcm)
decoded = converter.g711_ulaw_decode(g711)

print(f"PCM: {len(pcm)} bytes")
print(f"G.711: {len(g711)} bytes")
print(f"Decoded: {len(decoded)} bytes")
print("✅ Codec test passed" if len(decoded) == 640 else "❌ Test failed")
EOF
```

### Test RTP Bridge (requires active call)
```bash
# During an active call, check bridge stats in logs
make docker-logs | grep -i "bridge stats"

# Should show:
# - frames_received > 0
# - frames_sent > 0
# - Low queue sizes (<10)
```

### Monitor PJSIP Event Loop
```bash
# Check event loop is running
make docker-logs | grep "PJSIP event loop"

# Should see:
# - "PJSIP event loop starting"
# - Regular activity every 50ms
# - No errors or exceptions
```

## 📈 Performance Metrics

### Expected Metrics:
- **Call Setup Time**: < 2 seconds
- **Audio Latency**: < 200ms (round-trip)
- **Packet Loss**: < 1%
- **Frame Rate**: 50 frames/sec (20ms frames)
- **CPU Usage**: < 10% per call
- **Memory**: ~50MB per call

### Monitor Performance:
```bash
# Check application resource usage
docker stats call-center-app

# Check audio frame statistics
make docker-logs | grep "frames_received\|frames_sent"
```

## 🐛 Debug Mode

Enable detailed logging:
```bash
# Edit docker-compose.yml
environment:
  - LOG_LEVEL=DEBUG

# Restart
make docker-restart

# View detailed logs
make docker-logs
```

## ✅ Success Criteria

Your SIP implementation is working correctly if:
- [ ] Softphone registers successfully
- [ ] Calls connect within 2 seconds
- [ ] Audio is clear in both directions
- [ ] STT accurately transcribes speech
- [ ] TTS responses are natural
- [ ] Calls hangup cleanly
- [ ] No errors in logs
- [ ] Frame statistics show activity
- [ ] Resource usage is reasonable

## 🎉 Next Steps

Once basic testing works:
1. **Test with real gateway** (Miralix/production SIP server)
2. **Load testing** (multiple concurrent calls)
3. **Audio quality optimization** (jitter buffer, packet loss handling)
4. **Add optional features** (call transfer, recording, etc.)
5. **Production deployment**

## 📚 Additional Resources

- Full testing guide: `LOCAL_TESTING_GUIDE.md`
- Implementation details: `SIP_IMPLEMENTATION_GUIDE.md`
- Code examples: `EXAMPLES.md`
- Status: `SIP_STATUS.md`

## 🆘 Getting Help

If you encounter issues:
1. Check logs: `make docker-logs` and `make docker-logs-freeswitch`
2. Review status: `make sip-status`
3. Check health: `make health`
4. Verify PJSIP: `make test-pjsip`
5. Review documentation above

---

**Quick Commands Reference:**
```bash
make docker-up              # Start everything
make health                 # Check services
make sip-status            # SIP detailed status
make docker-logs           # Application logs
make docker-logs-freeswitch # FreeSWITCH logs
make sip-test-call         # Test call via CLI
make quick-test            # Run quick tests
make docker-down           # Stop everything
```
