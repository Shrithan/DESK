"""Generate the README's local, GitHub-compatible architecture artwork."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import math
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/assets'
OUT.mkdir(parents=True,exist_ok=True)
font_dir=Path('/System/Library/Fonts/Supplemental')
def font(size,bold=False):
    candidates=[font_dir/('Arial Bold.ttf' if bold else 'Arial.ttf'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]
    for path in candidates:
        if path.exists():return ImageFont.truetype(str(path),size)
    return ImageFont.load_default()
(OUT/'desk-banner.svg').write_text('''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="380" viewBox="0 0 1200 380" role="img" aria-labelledby="title desc">
<title id="title">DESK — Everyday objects. Extraordinary controls.</title><desc id="desc">A dark spatial grid with a golden tracked object, a slider and a joystick, beside the DESK wordmark.</desc>
<defs><linearGradient id="bg" x2="1" y2="1"><stop stop-color="#111e2e"/><stop offset="1" stop-color="#1c3645"/></linearGradient><pattern id="grid" width="36" height="36" patternUnits="userSpaceOnUse"><path d="M36 0H0V36" fill="none" stroke="#83abc7" stroke-opacity=".12"/></pattern><linearGradient id="gold" x2="1" y2="1"><stop stop-color="#ffe5a0"/><stop offset="1" stop-color="#c99438"/></linearGradient></defs>
<rect width="1200" height="380" rx="24" fill="url(#bg)"/><rect x="665" width="535" height="380" fill="url(#grid)"/>
<path d="M665 0V380" stroke="#82a3bb" stroke-opacity=".15"/>
<text x="58" y="57" fill="#e5c77e" font-family="Arial,sans-serif" font-size="12" letter-spacing="5">THE WORLD IS YOUR INTERFACE</text>
<text x="51" y="192" fill="#f2f6fb" font-family="Arial,sans-serif" font-size="144" font-weight="700" letter-spacing="-8">DESK</text>
<text x="58" y="245" fill="#d4e3ee" font-family="Arial,sans-serif" font-size="25">Everyday objects. Extraordinary controls.</text>
<text x="58" y="291" fill="#a2b7c9" font-family="Arial,sans-serif" font-size="15">Computer vision × voice × agentic setup × real output</text>
<rect x="58" y="321" width="216" height="26" rx="13" fill="#253e4d"/><text x="73" y="339" fill="#b5e5d4" font-family="Arial,sans-serif" font-size="11" letter-spacing="2">SEE IT. SAY IT. CONTROL IT.</text>
<g stroke="#e7c677" fill="none"><rect x="737" y="68" width="157" height="175" rx="14" stroke-dasharray="7 6" opacity=".7"/><ellipse cx="815" cy="111" rx="42" ry="15" fill="#314557" stroke-width="2"/><path d="M773 111V195C773 217 857 217 857 195V111" fill="#273e51" stroke-width="2"/><ellipse cx="815" cy="195" rx="42" ry="15" stroke-opacity=".35"/><path d="M802 105H829M810 100L821 100" stroke-width="4"/><circle cx="815" cy="154" r="6" fill="url(#gold)"/><path d="M799 154H782M832 154H849M815 138V121M815 170V187" opacity=".6"/></g>
<text x="744" y="267" fill="#bdd2df" font-family="Arial,sans-serif" font-size="11" letter-spacing="2">OBJECT_01 · TRACKED</text>
<path d="M914 153H967" stroke="#a7c5d8" stroke-dasharray="4 5"/><path d="M960 148L967 153L960 158" fill="none" stroke="#a7c5d8"/>
<rect x="994" y="78" width="130" height="212" rx="18" fill="#152a3b" stroke="#4b6578"/><text x="1013" y="108" fill="#8facbf" font-family="Arial,sans-serif" font-size="11" letter-spacing="2">CONTROL</text>
<path d="M1025 139H1093" stroke="#617d91" stroke-width="4" stroke-linecap="round"/><circle cx="1070" cy="139" r="9" fill="url(#gold)"/><circle cx="1059" cy="217" r="31" fill="none" stroke="#617d91"/><path d="M1059 217L1072 198" stroke="#e7c677" stroke-width="5"/><circle cx="1072" cy="198" r="8" fill="url(#gold)"/>
<text x="1016" y="269" fill="#b5e5d4" font-family="Arial,sans-serif" font-size="10" letter-spacing="2">INPUT → ACTION</text>
</svg>''')
W,H=1040,290
frames=[]
labels=[('01','SEE','Camera + masks'),('02','TRACK','Flow + identity'),('03','UNDERSTAND','Voice + ASI:One'),('04','ACT','Keys · MIDI · OS')]
for frame in range(64):
    phase=frame/64
    im=Image.new('RGB',(W,H),'#101d2b');d=ImageDraw.Draw(im)
    d.text((28,20),'FROM A REAL OBJECT TO A REAL ACTION',font=font(13,True),fill='#e8c77b')
    d.text((28,46),'Two loops. One physical interface.',font=font(12),fill='#a9bdcf')
    for i,(num,title,sub) in enumerate(labels):
        x=28+i*256
        d.rounded_rectangle((x,86,x+218,244),radius=16,fill='#1c3041',outline='#39566c',width=1)
        d.text((x+16,100),num,font=font(10,True),fill='#88a7c0')
        d.text((x+16,119),title,font=font(18,True),fill='#edf5fb')
        d.text((x+16,218),sub,font=font(11),fill='#a6bfce')
        if i<3:
            d.line((x+223,168,x+250,168),fill='#537185',width=2)
            px=x+223+int((phase*3%1)*27)
            d.ellipse((px-3,165,px+3,171),fill='#e8c77b')
        if i==0:
            cx=x+108+int(18*math.sin(phase*math.tau));cy=177
            d.rounded_rectangle((cx-30,cy-22,cx+30,cy+23),radius=7,fill='#d5ad58')
            d.rectangle((cx-38,cy-28,cx+38,cy+29),outline='#99f1cb',width=2)
            d.line((cx-8,cy,cx+8,cy),fill='#f2fbff',width=1);d.line((cx,cy-8,cx,cy+8),fill='#f2fbff',width=1)
        elif i==1:
            for j in range(6):
                xx=x+35+j*26;yy=179+int(12*math.sin(phase*math.tau+j*.6))
                d.line((xx-10,yy+6,xx,yy),fill='#71a5bb',width=2)
                d.ellipse((xx-3,yy-3,xx+3,yy+3),fill='#99f1cb')
        elif i==2:
            for j in range(20):
                xx=x+24+j*8;height=5+int(16*abs(math.sin(j*.65+phase*math.tau*2)))
                d.line((xx,177-height,xx,177+height),fill='#e8c77b',width=3)
        else:
            for j,key in enumerate('WASD'):
                xx=x+17+j*47
                selected=j==int(phase*4)%4
                d.rounded_rectangle((xx,157,xx+37,197),radius=7,fill='#e8c77b' if selected else '#263f53',outline='#557185')
                d.text((xx+10,167),key,font=font(14,True),fill='#162335' if selected else '#c0d4e2')
    d.text((28,263),'ILLUSTRATED FLOW / NOT A RECORDED CAMERA FEED OR PERFORMANCE BENCHMARK',font=font(9),fill='#7c98af')
    frames.append(im)
frames[0].save(OUT/'desk-pipeline.gif',save_all=True,append_images=frames[1:],duration=65,loop=0,optimize=True)
print('Generated desk-banner.svg and desk-pipeline.gif')
