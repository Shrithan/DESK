"""Detected-object cover inputs. Values only: no key presses or native actions."""
import threading
import time
from vision.cover import CoverButton, HandDetector
from vision.objects import overlap


class ObjectButtons:
    def __init__(self,snapshot,hand_factory=HandDetector,clock=time.monotonic):
        self.snapshot,self.hand_factory,self.clock=snapshot,hand_factory,clock
        self.hand=None;self.buttons={};self.lock=threading.Lock()

    def add(self,oid):
        if not isinstance(oid,str):raise ValueError('Choose a detected object.')
        with self.lock:
            sample=self.snapshot(oid,True);now=self.clock()
            if not sample or not sample['tracked'] or now-sample['stamp']>.35:
                raise ValueError('Show the detected object uncovered first.')
            if oid not in self.buttons and len(self.buttons)>=8:raise ValueError('Use at most eight button objects at once.')
            if self.hand is None:self.hand=self.hand_factory()
            if self.hand.coverage(sample['frame'],sample['bbox'],now)>.15:
                raise ValueError('Uncover the object before mapping it as a button.')
            self.buttons[oid]=dict(button=CoverButton(sample['frame'],sample['bbox'],now),frame_id=None,
                                   state=dict(value=0,phase='learning',presses=0,fire=False))
            return dict(object_id=oid,**self.buttons[oid]['state'])

    def update(self,ids):
        if not isinstance(ids,list) or len(ids)>8 or any(not isinstance(i,str) for i in ids):raise ValueError('Invalid button object list.')
        with self.lock:
            self.buttons={oid:b for oid,b in self.buttons.items() if oid in ids}
            results={};now=self.clock()
            for oid,item in self.buttons.items():
                sample=self.snapshot(oid,True);button=item['button']
                if not sample or now-sample['stamp']>.35:
                    button.phase='missing';button.since=None
                    item['state']=dict(value=0,phase='missing',presses=button.count,fire=False)
                elif sample['frame_id']!=item['frame_id']:
                    item['frame_id']=sample['frame_id']
                    if sample['frame'].shape!=button.shape:
                        item['state']=dict(value=0,phase='remap after camera change',presses=button.count,fire=False)
                        results[oid]=item['state'];continue
                    coverage=self.hand.coverage(sample['frame'],button.bbox,now)
                    if sample['tracked'] and coverage<.08 and overlap(sample['bbox'],button.bbox)<.65:
                        count=button.count
                        button=item['button']=CoverButton(sample['frame'],sample['bbox'],now)
                        button.count=count  # visible object moved; learn its new clear appearance
                    state=button.step(sample['frame'],coverage,now)
                    # Release the binary signal as soon as the hand clears;
                    # the longer uncover dwell only debounces the next press.
                    item['state']=dict(state,value=int(state['phase']=='pressed' and coverage>.3 and state['appearance_change']>.06))
                    item['state']['model_tracked']=bool(sample['tracked'])
                    item['state']['reason']=(
                        'Uncovered · ready' if state['phase']=='ready' else
                        'Covered' if item['state']['value'] else
                        'Hold cover briefly' if state['phase']=='covering' else
                        'Uncover the object to learn its clear view' if state['phase']=='learning' else
                        'No hand detected over the saved object' if coverage<.08 else
                        'Waiting for the original clear appearance')
                results[oid]=dict(item['state'])
            return dict(buttons=results)

    def close(self):
        with self.lock:
            self.buttons.clear()
            if self.hand:self.hand.close();self.hand=None

    def assigned_ids(self):
        with self.lock:return set(self.buttons)

    def status(self):
        with self.lock:
            return dict(buttons={oid:dict(item['state'],bbox=list(item['button'].bbox)) for oid,item in self.buttons.items()})
