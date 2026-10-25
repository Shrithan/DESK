"""Short, user-started microphone clips to Cartesia Ink. Audio stays in memory."""
import io
import json
import secrets
import threading
import wave
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from vision.voice import configuration, VoiceError
from vision.commands import parse_command


class CartesiaSpeechInput:
    def __init__(self,config=configuration,transport=urlopen):
        self.config,self.transport=config,transport
        self.lock=threading.Lock()

    def transcribe(self,audio):
        if len(audio)>1_200_000:raise VoiceError('Voice clip is too large',413)
        try:
            with wave.open(io.BytesIO(audio),'rb') as f:
                rate=f.getframerate()
                if f.getnchannels()!=1 or f.getsampwidth()!=2 or not 8000<=rate<=96000:raise ValueError()
                frames=f.readframes(rate*13)
                duration=len(frames)/(rate*2)
                if not .2<=duration<=12:raise ValueError()
            # Streaming TTS WAVs may use an unknown-length header. Send a complete WAV.
            canonical=io.BytesIO()
            with wave.open(canonical,'wb') as out:
                out.setnchannels(1);out.setsampwidth(2);out.setframerate(rate);out.writeframes(frames)
            audio=canonical.getvalue()
        except (wave.Error,EOFError,ValueError,ZeroDivisionError):
            raise VoiceError('Use a mono PCM WAV command lasting 0.2 to 12 seconds.',400) from None
        key=self.config().get('CARTESIA_API_KEY')
        if not key:raise VoiceError('Add CARTESIA_API_KEY to .env to enable voice commands.')
        if not self.lock.acquire(blocking=False):raise VoiceError('Another voice command is being transcribed.',429)
        try:
            boundary='phantom-'+secrets.token_hex(12)
            pieces=[]
            for name,value in [('model','ink-whisper'),('language','en')]:
                pieces.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
            pieces.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="command.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode(),audio,f'\r\n--{boundary}--\r\n'.encode()])
            request=Request('https://api.cartesia.ai/stt',data=b''.join(pieces),headers={
                'Authorization':f'Bearer {key}','Cartesia-Version':'2026-08-14','Content-Type':f'multipart/form-data; boundary={boundary}'},method='POST')
            try:
                with self.transport(request,timeout=20) as response:
                    data=json.loads(response.read(64_001))
            except HTTPError as exc:
                raise VoiceError('Cartesia rejected the key or speech request. Check API access and credits.',502) from None
            except (URLError,OSError,TimeoutError,ValueError):
                raise VoiceError('Cartesia transcription is unavailable. No mapping was changed.',502) from None
            text=data.get('text') if isinstance(data,dict) else None
            if not isinstance(text,str) or len(text)>500:raise VoiceError('Cartesia returned an invalid command transcript.',502)
            return dict(transcript=text,intent=parse_command(text),provider='cartesia',model='ink-whisper')
        finally:self.lock.release()
