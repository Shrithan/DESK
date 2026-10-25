import io
import json
import wave
import pytest
from vision.commands import parse_command
from vision.speech_input import CartesiaSpeechInput
from vision.voice import VoiceError


def wav():
    out=io.BytesIO()
    with wave.open(out,'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(b'\0\0'*16000)
    return out.getvalue()


@pytest.mark.parametrize('text,label',[('Map this can to be a joystick','can'),('Turn this mug into a joystick','cup'),('Can you map this book to a joystick?','book'),('Use this item as a joy stick',None)])
def test_positive_commands(text,label):
    assert parse_command(text)==dict(action='map_joystick',label=label,number=None)


def test_stop_negative_unsupported_and_numbered_commands():
    assert parse_command('stop keyboard control')['action']=='stop_keys'
    assert parse_command('Stop')['action']=='stop_keys'
    assert parse_command('Map object two as a joystick')['number']==2
    for text in ["Don't map this can to a joystick",'do not map','delete files','play music','map this to volume','']:
        assert parse_command(text)['action']=='unknown'


def test_cartesia_speech_contract_and_no_key_no_network():
    calls=[]
    def transport(request,timeout):
        calls.append(request)
        assert request.full_url=='https://api.cartesia.ai/stt' and timeout==20
        assert request.get_header('Cartesia-version')=='2026-08-14'
        assert b'name="model"\r\n\r\nink-whisper' in request.data and b'filename="command.wav"' in request.data
        return io.BytesIO(json.dumps({'text':'Map this can to a joystick'}).encode())
    stt=CartesiaSpeechInput(config=lambda:{'CARTESIA_API_KEY':'fixture'},transport=transport)
    result=stt.transcribe(wav());assert result['intent']['action']=='map_joystick' and len(calls)==1
    with pytest.raises(VoiceError):stt.transcribe(b'not audio')
    assert len(calls)==1
    stt.config=lambda:{}
    with pytest.raises(VoiceError):stt.transcribe(wav())
    assert len(calls)==1


def test_unknown_length_streaming_wav_is_normalized():
    audio=bytearray(wav());audio[40:44]=(0xffffffff).to_bytes(4,'little')
    def transport(request,timeout):
        # The uploaded file has a normal bounded data length, not the streaming sentinel.
        assert b'data\xff\xff\xff\xff' not in request.data
        return io.BytesIO(b'{"text":"Stop keyboard control"}')
    result=CartesiaSpeechInput(config=lambda:{'CARTESIA_API_KEY':'fixture'},transport=transport).transcribe(bytes(audio))
    assert result['intent']['action']=='stop_keys'
