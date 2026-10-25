"""Bundle Cal's frontend into already-served assets; no backend routes required."""
from pathlib import Path
import base64
ROOT=Path(__file__).resolve().parents[1]
WEB=ROOT/'vision/web'
MARKER='/* BEGIN CAL BEAR PRESENTATION BUNDLE */'
def bundle(path,extra):
    original=path.read_text().split(MARKER)[0].rstrip()
    path.write_text(original+'\n\n'+MARKER+'\n'+extra.rstrip()+'\n')
art=base64.b64encode((WEB/'bear/cal-bear-talking.webp').read_bytes()).decode()
bundle(WEB/'module-agent.js',"const BEAR_ARTWORK='data:image/webp;base64,"+art+"';\n"+(WEB/'bear/interface.js').read_text()+'\n'+(WEB/'bear/face.js').read_text())
bundle(WEB/'fusion.css',(WEB/'bear/style.css').read_text())
