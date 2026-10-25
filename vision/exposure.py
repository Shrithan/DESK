"""Bounded, read-back-verified UVC exposure control for the Logitech C270."""
from pathlib import Path
import subprocess
import threading

BINARY=Path(__file__).resolve().parent.parent/'outputs/tools/uvc-util/uvc-util'


class WebcamExposure:
    def __init__(self,runner=subprocess.run,binary=BINARY):
        self.runner=runner;self.binary=binary;self.lock=threading.Lock()

    def _run(self,*args):
        if not self.binary.is_file():raise RuntimeError('Native exposure helper is not installed. See docs/camera-exposure.md.')
        try:result=self.runner([str(self.binary),*args],capture_output=True,text=True,timeout=3,check=False)
        except subprocess.TimeoutExpired:raise RuntimeError('USB exposure control timed out. Reconnect the webcam and retry.') from None
        if result.returncode:raise RuntimeError('The webcam did not accept the exposure request.')
        return result.stdout.strip()

    def _select(self):
        devices=self._run('-d')
        matches=[line for line in devices.splitlines() if '0x046d:0x0825' in line.lower()]
        if len(matches)!=1:raise ValueError('Connect exactly one C270 for hardware exposure control; identical cameras require explicit device selection.')
        return ['-V','0x046d:0x0825']

    def _get(self,selection,name):
        value=self._run(*selection,'-o',name).lower()
        if value in ('true','false'):return value=='true'
        try:return int(value)
        except ValueError:raise RuntimeError('The webcam returned an unreadable exposure setting.') from None

    def _status(self,selection):
        mode=self._get(selection,'auto-exposure-mode')
        exposure=self._get(selection,'exposure-time-abs')
        wb=self._get(selection,'auto-white-balance-temp')
        return dict(supported=True,camera='Logitech C270',locked=mode==1 and wb is False,exposure_locked=mode==1,
                    exposure_ms=round(exposure*.1,2),auto_white_balance=wb,
                    message='Exposure and white balance locked' if mode==1 and wb is False else 'Automatic camera adjustments are enabled')

    def status(self):
        with self.lock:
            try:return self._status(self._select())
            except (RuntimeError,ValueError,OSError,subprocess.TimeoutExpired) as exc:return dict(supported=False,locked=False,message=str(exc))

    def configure(self,label,locked):
        if type(locked) is not bool:raise ValueError('Choose locked or auto exposure.')
        if not isinstance(label,str) or 'c270' not in label.lower():raise ValueError('Native exposure locking currently supports the connected C270 only.')
        with self.lock:
            selection=self._select()
            if not locked:
                self._run(*selection,'-s','auto-exposure-mode=8','-s','auto-white-balance-temp=1')
                result=self._status(selection)
                if result['exposure_locked'] or not result['auto_white_balance']:raise RuntimeError('Camera auto-mode change could not be verified.')
                return result
            mode=self._get(selection,'auto-exposure-mode');exposure=self._get(selection,'exposure-time-abs')
            gain=self._get(selection,'gain');wb=self._get(selection,'auto-white-balance-temp')
            temperature=self._get(selection,'white-balance-temp')
            try:
                self._run(*selection,'-s','auto-exposure-mode=1','-s',f'exposure-time-abs={exposure}',
                          '-s',f'gain={gain}','-s','auto-white-balance-temp=0','-s',f'white-balance-temp={temperature}')
                result=self._status(selection)
                if not result['locked']:raise RuntimeError('The camera ignored the manual lock; hardware lock was not verified.')
                return result
            except Exception:
                # Avoid leaving a partially configured camera when one control fails.
                try:self._run(*selection,'-s',f'auto-exposure-mode={mode}','-s',f'auto-white-balance-temp={int(wb)}')
                except Exception:pass
                raise
