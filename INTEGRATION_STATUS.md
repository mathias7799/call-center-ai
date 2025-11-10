# Integration Status - Telephony Abstraction

This document assesses the current status of the telephony abstraction layer and identifies what remains to be done.

## Summary

**Status: Interface Ready, Application Integration Pending**

✅ **Complete:**
- `ITelephony` interface fully defined with all necessary methods
- `AzureCommunicationServicesTelephony` fully implemented
- `SipTelephony` stub ready for implementation
- Configuration system supports mode switching
- SQLite storage and local queues working

⚠️ **Partially Complete:**
- Application code still directly uses `CallAutomationClient` instead of `ITelephony`
- Need to refactor `call_events.py`, `call_utils.py`, and `main.py` to use interface

## Current Architecture Issues

### Issue 1: Direct Azure SDK Usage

**Problem:** The application code bypasses the interface layer.

**Current Code (call_events.py):**
```python
async def on_new_call(
    callback_url: str,
    client: CallAutomationClient,  # ❌ Direct Azure SDK type
    incoming_context: str,
    phone_number: str,
    wss_url: str,
) -> bool:
    # ...
    answer_call_result = await client.answer_call(...)  # ❌ Direct SDK call
```

**Should Be:**
```python
async def on_new_call(
    callback_url: str,
    telephony: ITelephony,  # ✅ Uses interface
    incoming_context: str,
    phone_number: str,
    wss_url: str,
) -> bool:
    # ...
    call_id, server_id = await telephony.answer_call(...)  # ✅ Interface call
```

### Issue 2: CallConnectionClient Pattern

**Problem:** Azure SDK uses a two-level pattern:
- `CallAutomationClient` (top level, obtained once)
- `CallConnectionClient` (per-call, obtained via `get_call_connection()`)

The current code does this:
```python
def _use_call_client(client: CallAutomationClient, voice_id: str) -> CallConnectionClient:
    return client.get_call_connection(call_connection_id=voice_id)

# Then later:
call_client = await _use_call_client(client, call.voice_id)
await call_client.hang_up(is_for_everyone=True)
```

**Our Interface:** Uses a flat design - all methods take `call_connection_id` directly:
```python
await telephony.hangup_call(call_connection_id=call.voice_id)
```

This is **intentional** and **better** - it's simpler and more compatible with SIP (which doesn't have this two-level pattern).

### Issue 3: Main.py Initialization

**Current:**
```python
# main.py
_communication_services_jwks_client = jwt.PyJWKClient(...)

async def _use_automation_client() -> CallAutomationClient:
    return CallAutomationClient(...)
```

**Should Be:**
```python
# main.py
_telephony = CONFIG.telephony.instance  # Gets ITelephony implementation

# Use throughout the app
await _telephony.answer_call(...)
```

## What Needs to Change

### 1. Main Application Entry (main.py)

**Current Lines 101-108:**
```python
# Azure Communication Services
_source_caller = PhoneNumberIdentifier(CONFIG.communication_services.phone_number)
logger.info("Using phone number %s", CONFIG.communication_services.phone_number)
_communication_services_jwks_client = jwt.PyJWKClient(
    cache_keys=True,
    uri="https://acscallautomation.communication.azure.com/calling/keys",
)
```

**Change To:**
```python
# Telephony (pluggable provider)
_telephony = CONFIG.telephony.instance
logger.info("Using telephony provider: %s", CONFIG.telephony.mode.value)

# Source caller - get from telephony config
if CONFIG.telephony.mode == TelephonyModeEnum.AZURE_COMMUNICATION_SERVICES:
    _source_caller = PhoneNumberIdentifier(CONFIG.communication_services.phone_number)
elif CONFIG.telephony.mode == TelephonyModeEnum.SIP:
    _source_caller = CONFIG.telephony.sip.phone_number
```

**Current Line 1132-1154:**
```python
async def _use_automation_client() -> CallAutomationClient:
    """Get the call automation client for Azure Communication Services."""
    logger.debug("Using Automation Client...")
    return CallAutomationClient(...)
```

**Change To:**
```python
def _get_telephony() -> ITelephony:
    """Get the configured telephony provider."""
    return _telephony
```

### 2. Call Events (call_events.py)

**Function: `on_new_call` (lines 54-101)**

**Current:**
```python
async def on_new_call(
    callback_url: str,
    client: CallAutomationClient,
    incoming_context: str,
    phone_number: str,
    wss_url: str,
) -> bool:
    streaming_options = MediaStreamingOptions(...)

    try:
        answer_call_result = await client.answer_call(
            callback_url=callback_url,
            cognitive_services_endpoint=CONFIG.cognitive_service.endpoint,
            incoming_call_context=incoming_context,
            media_streaming=streaming_options,
        )
        logger.info("Answered call (%s)", answer_call_result.call_connection_id)
        return True
    except ClientAuthenticationError:
        ...
```

**Change To:**
```python
async def on_new_call(
    callback_url: str,
    telephony: ITelephony,
    incoming_context: str,
    phone_number: PhoneNumber,
    wss_url: str,
) -> bool:
    try:
        call_connection_id, server_call_id = await telephony.answer_call(
            callback_url=callback_url,
            incoming_context=incoming_context,
            phone_number=phone_number,
            wss_url=wss_url,
        )
        logger.info("Answered call (%s)", call_connection_id)
        return True
    except Exception:
        logger.exception("Error answering call")
        return False
```

**Function: `on_call_connected` (lines 104-146)**

**Current:**
```python
async def on_call_connected(
    call: CallStateModel,
    client: CallAutomationClient,
    scheduler: Scheduler,
    server_call_id: str,
) -> None:
    await asyncio.gather(
        _handle_ivr_language(...),
        _handle_recording(call=call, client=client, server_call_id=server_call_id),
    )
```

**Change To:**
```python
async def on_call_connected(
    call: CallStateModel,
    telephony: ITelephony,
    scheduler: Scheduler,
    server_call_id: str,
) -> None:
    await asyncio.gather(
        _handle_ivr_language(...),
        _handle_recording(call=call, telephony=telephony, server_call_id=server_call_id),
    )
```

### 3. Call Utils (call_utils.py)

**Function: `handle_automation_tts` (lines 136-176)**

**Current:**
```python
async def handle_automation_tts(
    client: CallAutomationClient,
    call: CallStateModel,
    context: ContextEnum,
    text: str,
) -> None:
    with _detect_hangup():
        assert call.voice_id, "Voice ID is required"
        call_client = await _use_call_client(client, call.voice_id)
        await call_client.play_media(...)
```

**Change To:**
```python
async def handle_automation_tts(
    telephony: ITelephony,
    call: CallStateModel,
    context: ContextEnum,
    text: str,
) -> None:
    try:
        assert call.voice_id, "Voice ID is required"
        await telephony.play_media(
            call_connection_id=call.voice_id,
            text=text,
            context=_context_serializer({context}),
        )
    except Exception:
        logger.exception("Error playing media")
        raise CallHangupException
```

**Function: `handle_hangup` (lines 423-438)**

**Current:**
```python
async def handle_hangup(
    client: CallAutomationClient,
    call: CallStateModel,
) -> None:
    with _detect_hangup():
        assert call.voice_id, "Voice ID is required"
        call_client = await _use_call_client(client, call.voice_id)
        await call_client.hang_up(is_for_everyone=True)
```

**Change To:**
```python
async def handle_hangup(
    telephony: ITelephony,
    call: CallStateModel,
) -> None:
    try:
        assert call.voice_id, "Voice ID is required"
        await telephony.hangup_call(call_connection_id=call.voice_id)
    except Exception:
        logger.exception("Error hanging up call")
        raise CallHangupException
```

**Function: `start_audio_streaming` (lines 462-480)**

**Current:**
```python
async def start_audio_streaming(
    client: CallAutomationClient,
    call: CallStateModel,
) -> None:
    with _detect_hangup():
        assert call.voice_id, "Voice ID is required"
        call_client = await _use_call_client(client, call.voice_id)
        await call_client._call_media_client.start_media_streaming(...)
```

**Change To:**
```python
async def start_audio_streaming(
    telephony: ITelephony,
    call: CallStateModel,
) -> None:
    try:
        assert call.voice_id, "Voice ID is required"
        await telephony.start_media_streaming(call_connection_id=call.voice_id)
    except Exception:
        logger.exception("Error starting media streaming")
        raise CallHangupException
```

### 4. Remove Azure-Specific Helpers

**Delete or Make Optional:**
```python
# call_utils.py lines 528-537
@lru_acache()
async def _use_call_client(
    client: CallAutomationClient, voice_id: str
) -> CallConnectionClient:
    # This is Azure-specific and no longer needed
```

**Simplify Error Detection:**
```python
# call_utils.py lines 510-525
@contextmanager
def _detect_hangup() -> Generator[None]:
    """Generic hangup detection (not Azure-specific)."""
    try:
        yield
    except Exception as e:
        # Check for common hangup indicators
        error_msg = str(e).lower()
        if any(indicator in error_msg for indicator in [
            "call already terminated",
            "call hung up",
            "not found",
            "disconnected"
        ]):
            logger.debug("Call hung up")
            raise CallHangupException
        raise
```

## Benefits of This Refactoring

### 1. **Vendor Independence**
Once refactored, switching between Azure and SIP is just a config change:
```yaml
telephony:
  mode: sip  # Change this one line
```

### 2. **Simplified Code**
No more two-level client pattern:
```python
# Before:
client = await _use_automation_client()
call_client = await _use_call_client(client, voice_id)
await call_client.hang_up()

# After:
await telephony.hangup_call(call_connection_id=voice_id)
```

### 3. **Easier Testing**
Mock the `ITelephony` interface for unit tests:
```python
class MockTelephony(ITelephony):
    async def answer_call(self, ...):
        return ("mock-call-id", "mock-server-id")
```

### 4. **SIP Ready**
Once refactored, implementing SIP in `sip_telephony.py` immediately works across the entire application.

## Implementation Checklist

- [ ] Refactor `main.py` to use `CONFIG.telephony.instance`
- [ ] Update `on_new_call` in `call_events.py`
- [ ] Update `on_call_connected` in `call_events.py`
- [ ] Update all helper functions in `call_utils.py`:
  - [ ] `handle_automation_tts`
  - [ ] `handle_realtime_tts`
  - [ ] `handle_recognize_ivr`
  - [ ] `handle_hangup`
  - [ ] `handle_transfer`
  - [ ] `start_audio_streaming`
  - [ ] `stop_audio_streaming`
- [ ] Update `call_llm.py` if it uses `client` directly
- [ ] Update `llm_utils.py` if it uses `client` directly
- [ ] Remove `_use_call_client` helper (Azure-specific)
- [ ] Simplify `_detect_hangup` to be provider-agnostic
- [ ] Update all function calls to pass `telephony` instead of `client`
- [ ] Test with Azure Communication Services (backward compatibility)
- [ ] Implement SIP stack
- [ ] Test with local FreeSWITCH
- [ ] Test with production Miralix gateway

## Estimated Effort

**Refactoring Application Code:** 1-2 days
- Straightforward find/replace style changes
- Main risk is missing a usage spot
- Comprehensive grep can identify all locations

**Testing:** 1 day
- Verify Azure Communication Services still works
- Test all call flows
- Regression testing

**Total:** 2-3 days to complete the refactoring

## Next Steps

Would you like me to:
1. **Proceed with the refactoring** - Update all the application code to use `ITelephony`
2. **Create a test harness first** - Build tests to ensure nothing breaks
3. **Start with SIP implementation** - Implement the full SIP stack in parallel
4. **Review specific files** - Deep dive into any particular file/function

The foundation is solid - we just need to complete the integration!
