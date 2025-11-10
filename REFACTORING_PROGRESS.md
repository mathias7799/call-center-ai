# ITelephony Refactoring Progress

**Status: In Progress (30% Complete)**
**Last Updated:** Current session
**Goal:** Refactor application to use ITelephony interface for SIP integration

## ✅ Completed

### 1. Interface & Configuration (100%)
- [x] Created `ITelephony` interface with all methods
- [x] Added `stop_media_streaming()` method
- [x] Created `TelephonyModel` configuration
- [x] Created `AzureCommunicationServicesTelephony` implementation
- [x] Created `SipTelephony` stub implementation
- [x] Integrated telephony config into RootModel

### 2. main.py (90%)
- [x] Replaced `_use_automation_client()` with `_get_telephony()`
- [x] Initialize `_telephony` from CONFIG.telephony.instance
- [x] Updated phone number selection based on telephony mode
- [x] Created generic callback URLs (_TELEPHONY_WSS_TPL, _TELEPHONY_CALLBACK_TPL)
- [x] Updated `call_event()` to pass `telephony` to `on_new_call()`
- [x] Updated WebSocket handler to pass `telephony` to `on_audio_connected()`
- [x] Updated all event handlers in callback to pass `telephony`:
  - [x] on_call_connected
  - [x] on_call_disconnected
  - [x] on_ivr_recognized
  - [x] on_automation_recognize_error
  - [x] on_automation_play_completed
  - [x] on_transfer_error
- [ ] **TODO:** Handle outbound calls (lines 421-429) - needs `initiate_call()` method in ITelephony

### 3. call_events.py (10%)
- [x] Updated `on_new_call()` signature and implementation
- [ ] **TODO:** Update remaining functions (see below)

## ⚠️ In Progress

### call_events.py Functions

**Priority 1 - Call Lifecycle:**
- [ ] `on_call_connected()` (line 89) - Used when call is answered
- [ ] `on_call_disconnected()` (line 148) - Used when call ends
- [ ] `on_audio_connected()` (line 224) - Main audio processing loop

**Priority 2 - IVR & Recognition:**
- [ ] `_handle_ivr_language()` (line 322) - Language selection IVR
- [ ] `on_ivr_recognized()` (line 382) - IVR choice detected
- [ ] `handle_recognize_ivr()` (line 412) - Start IVR recognition
- [ ] `on_automation_recognize_error()` (line 496) - IVR error handling

**Priority 3 - Media Playback:**
- [ ] `_handle_recognize()` (line 459) - Generic recognition handler
- [ ] `on_play_started()` (line 544) - Media playback started
- [ ] `on_automation_play_completed()` (line 557) - Media playback completed

**Priority 4 - Recording & Transfer:**
- [ ] `_handle_recording()` (line 790) - Start call recording
- [ ] `on_transfer_error()` (line 817) - Transfer failed handling

## 🔴 Not Started

### call_utils.py Functions

**All functions need updating:**
- [ ] `handle_automation_tts()` (line 136)
- [ ] `handle_realtime_tts()` (line 232)
- [ ] `handle_recognize_ivr()` (line 355)
- [ ] `handle_hangup()` (line 423)
- [ ] `handle_transfer()` (line 441)
- [ ] `start_audio_streaming()` (line 462)
- [ ] `stop_audio_streaming()` (line 483)
- [ ] Remove `_use_call_client()` (line 528) - Azure-specific helper
- [ ] Simplify `_detect_hangup()` (line 510) - Make vendor-agnostic

### call_llm.py

Check if it uses `client` parameter:
- [ ] Search for `CallAutomationClient` references
- [ ] Update any functions that take `client` parameter

### llm_utils.py

Check if it uses `client` parameter:
- [ ] Search for `CallAutomationClient` references
- [ ] Update any functions that take `client` parameter

## 📋 Refactoring Checklist

### Phase 1: call_events.py (Current)

```bash
# Functions to update (order matters):
1. on_call_connected()      # Line 89
2. _handle_ivr_language()    # Line 322
3. on_ivr_recognized()       # Line 382
4. _handle_recognize()       # Line 459
5. on_automation_recognize_error() # Line 496
6. on_play_started()         # Line 544
7. on_automation_play_completed()  # Line 557
8. _handle_recording()       # Line 790
9. on_transfer_error()       # Line 817
10. on_audio_connected()     # Line 224 (LAST - most complex)
```

### Phase 2: call_utils.py

```bash
# Functions to update:
1. handle_automation_tts()
2. handle_realtime_tts()
3. handle_recognize_ivr()
4. handle_hangup()
5. handle_transfer()
6. start_audio_streaming()
7. stop_audio_streaming()

# Functions to remove/simplify:
8. _use_call_client()  # Delete - Azure-specific
9. _detect_hangup()    # Simplify - make vendor-agnostic
```

### Phase 3: Testing

```bash
# Test with existing Azure setup:
1. Run the application
2. Make a test call
3. Verify all events work:
   - Call answered
   - IVR language selection
   - Speech recognition
   - LLM conversation
   - Hangup
4. Check logs for errors
```

## 🔧 Example Refactoring Pattern

**Before:**
```python
async def some_handler(
    call: CallStateModel,
    client: CallAutomationClient,
    scheduler: Scheduler,
) -> None:
    call_client = await _use_call_client(client, call.voice_id)
    await call_client.play_media(...)
```

**After:**
```python
async def some_handler(
    call: CallStateModel,
    telephony: ITelephony,
    scheduler: Scheduler,
) -> None:
    await telephony.play_media(
        call_connection_id=call.voice_id,
        text=text,
        context=context,
    )
```

## 📊 Estimated Remaining Work

- **call_events.py:** 4-6 hours (10 functions)
- **call_utils.py:** 3-4 hours (9 functions)
- **Testing:** 2-3 hours
- **Bug fixes:** 2-3 hours
- **Total:** 11-16 hours (1.5-2 days)

## 🎯 Next Steps

### Immediate (Next Session)

1. **Complete call_events.py:**
   - Start with `on_call_connected()` (line 89)
   - Work through the priority list above
   - Test each function as you go

2. **Update call_utils.py:**
   - Batch update all `handle_*` functions
   - Remove Azure-specific helpers
   - Simplify error handling

3. **Test:**
   - Run with existing Azure configuration
   - Verify all call flows work
   - Check for import errors or missing methods

### After Refactoring (SIP Implementation)

Once refactoring is complete and tested:

1. **Add pjsua2 to dependencies**
2. **Implement SIP stack** (follow SIP_IMPLEMENTATION_GUIDE.md)
3. **Test with local FreeSWITCH**
4. **Deploy to production with Miralix**

## 📝 Notes

- **Backward Compatibility:** All changes maintain compatibility with Azure Communication Services
- **Error Handling:** Simplified to be vendor-agnostic (catch generic exceptions)
- **Phone Number:** Correctly selected based on telephony mode (Azure vs SIP)
- **URLs:** Generic callback/WebSocket URLs work for both providers

## 🐛 Known Issues / TODOs

1. **Outbound Calls:** Need to add `initiate_call()` method to ITelephony interface
2. **JWT Validation:** Currently disabled in WebSocket handler (line 588-589 in main.py)
3. **Media Streaming:** Azure-specific implementation details need abstraction
4. **Recording:** Recording URL format may differ between providers

## 📚 Related Documents

- `INTEGRATION_STATUS.md` - Detailed integration assessment
- `SIP_IMPLEMENTATION_GUIDE.md` - Complete SIP implementation plan
- `MIGRATION_GUIDE.md` - User-facing migration guide

## ⚡ Quick Continue Command

To continue where we left off:

```python
# Edit these files next (in order):
1. app/helpers/call_events.py - Line 89 (on_call_connected)
2. app/helpers/call_events.py - Line 322 (_handle_ivr_language)
3. app/helpers/call_events.py - Line 382 (on_ivr_recognized)
# ... continue with checklist above
```

**Current commit:** `905a945` - "refactor: Begin ITelephony interface integration (Part 1)"
**Branch:** `claude/reduce-dependencies-011CUzuUhHtcnkbr8rfWeMjn`
