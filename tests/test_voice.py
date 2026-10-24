import io
import json
import pytest
from urllib.error import HTTPError
from vision.voice import CartesiaVoice, VoiceError, PHRASES

AUDIO = b'RIFF' + b'\x00'*4 + b'WAVE' + b'fake fixture'

def test_no_key_and_unknown_event_never_call_provider():
    def fail(*args, **kwargs):
        pytest.fail('Unexpected network call')
    voice = CartesiaVoice(config=lambda: {}, transport=fail)
    assert not voice.status()['configured']
    for event in ('test', 'not-an-event', []):
        with pytest.raises(VoiceError): voice.speak(event)


def test_request_contract_cache_and_rate_limit():
    calls=[]
    def transport(request, timeout):
        calls.append(request)
        assert timeout == 8
        return io.BytesIO(AUDIO)
    voice=CartesiaVoice(config=lambda: {'CARTESIA_API_KEY':'fixture-secret'}, transport=transport, clock=lambda: 10)
    assert voice.speak('test')==AUDIO
    request=calls[0]
    assert request.full_url=='https://api.cartesia.ai/tts/bytes'
    assert request.get_header('Authorization')=='Bearer fixture-secret'
    assert request.get_header('Cartesia-version')=='2026-08-14'
    body=json.loads(request.data)
    assert body['transcript']==PHRASES['test']
    assert isinstance(body['voice'],str)
    assert body['model_id']=='sonic-3.6'
    assert voice.speak('test')==AUDIO and len(calls)==1
    with pytest.raises(VoiceError) as e:voice.speak('joystick_ready')
    assert e.value.status==429
    assert 'fixture-secret' not in json.dumps(voice.status())


def test_upstream_errors_are_sanitized_and_unlock():
    def fail(request, timeout):raise HTTPError(request.full_url,401,'secret-provider-body',{},None)
    voice=CartesiaVoice(config=lambda: {'CARTESIA_API_KEY':'fixture-secret'}, transport=fail)
    with pytest.raises(VoiceError) as e:voice.speak('test')
    assert e.value.status==502 and 'secret' not in str(e.value)
    assert not voice.lock.locked()


def test_bad_audio_rejected():
    voice=CartesiaVoice(config=lambda: {'CARTESIA_API_KEY':'fixture'}, transport=lambda *a,**kw:io.BytesIO(b'not audio'))
    with pytest.raises(VoiceError,match='invalid audio'):voice.speak('test')


def test_busy_voice_does_not_wait():
    voice=CartesiaVoice(config=lambda: {'CARTESIA_API_KEY':'fixture'})
    voice.lock.acquire()
    with pytest.raises(VoiceError) as e:voice.speak('test')
    assert e.value.status==429
    voice.lock.release()
