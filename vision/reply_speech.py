"""Cartesia spoken planner replies, shared with the isolated voice-lab integration."""
import json
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from vision.voice import configuration, VoiceError


class ReplySpeech:
    """Speak the validated agent explanation, isolated from production fixed phrases."""
    def __init__(self,config=configuration,transport=urlopen):
        self.config,self.transport=config,transport
        self.lock=threading.Lock()

    def speak(self,text):
        if not isinstance(text,str) or not 1<=len(text.strip())<=800:
            raise ValueError('Speech must contain 1–800 characters.')
        c=self.config();key=c.get('CARTESIA_API_KEY')
        if not key:raise VoiceError('Add CARTESIA_API_KEY to the local .env.')
        if not self.lock.acquire(blocking=False):raise VoiceError('Speech synthesis is busy.',429)
        try:
            payload=dict(model_id=c.get('CARTESIA_MODEL_ID') or 'sonic-3.6',transcript=text,
                         voice=c.get('CARTESIA_VOICE_ID') or '47c38ca4-5f35-497b-b1a3-415245fb35e1',
                         output_format=dict(container='wav',encoding='pcm_s16le',sample_rate=24000),language='en')
            request=Request('https://api.cartesia.ai/tts/bytes',data=json.dumps(payload).encode(),method='POST',
                            headers={'Authorization':'Bearer '+key,'Cartesia-Version':'2026-08-14','Content-Type':'application/json'})
            try:
                with self.transport(request,timeout=20) as response:audio=response.read(4_000_001)
            except HTTPError as exc:raise VoiceError(f'Cartesia speech failed (HTTP {exc.code}). Check key, voice, model and quota.',502) from None
            except (URLError,OSError,TimeoutError):raise VoiceError('Cartesia speech timed out or is unavailable.',502) from None
            if len(audio)>4_000_000 or not (audio[:4]==b'RIFF' and audio[8:12]==b'WAVE'):
                raise VoiceError('Cartesia returned invalid WAV audio.',502)
            return audio
        finally:self.lock.release()

