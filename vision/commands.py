"""Small explicit voice-command grammar. No arbitrary code or desktop actions."""
import re


def parse_command(text):
    if not isinstance(text,str) or len(text)>500:
        raise ValueError('Command transcript must be short text')
    text=re.sub(r'joy\s+stick','joystick',text,flags=re.I)
    words=re.sub(r'[^a-z0-9\s]',' ',text.lower()).split()
    phrase=' '.join(words)
    if not words:return dict(action='unknown')
    if any(w in words for w in ('not','dont','never')) or 'don t' in phrase:
        return dict(action='unknown')
    if phrase in ('stop','stop please','stop now'):return dict(action='stop_keys')
    if any(w in words for w in ('stop','disable','disarm','pause')) and any(w in words for w in ('keys','keyboard','control','controls','joystick','typing')):
        return dict(action='stop_keys')
    if 'joystick' not in words or not any(w in words for w in ('map','make','turn','use','set','assign')):
        return dict(action='unknown')
    nouns=[w for i,w in enumerate(words) if w in ('can','bottle','cup','mug','disk','box','book','phone') and not(w=='can' and i+1<len(words) and words[i+1] in ('you','i','we'))]
    label=nouns[0] if nouns else None
    if label=='mug':label='cup'
    number=None
    match=re.search(r'(?:object|item)\s+(\d+|one|two|three|four|five)\b',phrase)
    if match:
        value=match.group(1);number=int(value) if value.isdigit() else {'one':1,'two':2,'three':3,'four':4,'five':5}[value]
    return dict(action='map_joystick',label=label,number=number)
