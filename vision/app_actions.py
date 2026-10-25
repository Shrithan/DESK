"""Discover installed Mac apps as declarative, one-shot cover-button targets."""
from functools import lru_cache
from pathlib import Path
import os
import plistlib
import re
import subprocess
import sys


@lru_cache(maxsize=1)
def installed_apps():
    if sys.platform!='darwin':return ()
    found={}
    for root in (Path('/System/Applications'),Path('/Applications'),Path.home()/'Applications'):
        if not root.is_dir():continue
        for directory,dirs,_ in os.walk(root):
            depth=len(Path(directory).relative_to(root).parts)
            for name in list(dirs):
                path=Path(directory)/name
                if path.suffix!='.app':continue
                dirs.remove(name)  # never descend into app bundles / helper applications
                try:
                    with (path/'Contents/Info.plist').open('rb') as f:info=plistlib.load(f)
                    bundle=info.get('CFBundleIdentifier','')
                    label=info.get('CFBundleDisplayName') or info.get('CFBundleName') or path.stem
                    if isinstance(bundle,str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,180}',bundle) and isinstance(label,str):
                        found.setdefault(bundle,(bundle,label[:100],str(path)))
                except (OSError,ValueError,plistlib.InvalidFileException):pass
            if depth>=2:dirs.clear()
    return tuple(sorted(found.values(),key=lambda item:item[1].lower())[:256])


class OpenApplication:
    def __init__(self,bundle,path,runner=subprocess.run):
        self.bundle,self.path,self.runner=bundle,Path(path),runner

    def trigger(self):
        try:
            with (self.path/'Contents/Info.plist').open('rb') as f:info=plistlib.load(f)
            if self.path.suffix!='.app' or info.get('CFBundleIdentifier')!=self.bundle:
                raise RuntimeError('Application changed. Refresh the app catalog before remapping.')
            self.runner(['/usr/bin/open','-a',str(self.path)],check=True,timeout=5,
                        stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,shell=False)
        except (OSError,subprocess.SubprocessError,ValueError) as exc:
            raise RuntimeError(f'Could not open {self.path.stem}. Check that it is still installed.') from None
