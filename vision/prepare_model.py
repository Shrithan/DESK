"""Download official public weights and prepare a reusable local prompt profile.

No camera input is read. The one-time text encoder is about 242 MiB. All assets
are written to ignored outputs/models. The live server uses the saved profile
without downloading or encoding prompts per frame.
"""
import argparse
from pathlib import Path
import os
import urllib.request

PROMPTS=['soda can','bottle','cup','cardboard box','cell phone','book','pen','ball','computer mouse','keyboard','scissors','remote control','top of a soda can','bottle viewed from above','cup viewed from above','flat circular disk','hockey puck','coin','flat circular lid']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--size',choices=['s','m','l','x'],default='x')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    folder=root/'outputs/models';folder.mkdir(parents=True,exist_ok=True)
    os.environ['YOLO_CONFIG_DIR']=str(root/'outputs/.ultralytics')
    os.environ['MPLCONFIGDIR']=str(root/'outputs/.matplotlib')
    source=folder/f'yoloe-26{args.size}-seg.pt'
    if not source.exists():
        urllib.request.urlretrieve(f'https://github.com/ultralytics/assets/releases/download/v8.4.0/{source.name}',source)
    # Ultralytics resolves the one-time text encoder relative to the working folder.
    previous=Path.cwd()
    try:
        os.chdir(folder)
        from ultralytics import YOLOE, settings
        settings.update({'sync':False,'weights_dir':str(folder)})
        model=YOLOE(str(source))
        model.set_classes(PROMPTS)
        model.save(str(folder/f'desk-yoloe-{args.size}.pt'))
    finally:
        os.chdir(previous)
    print(f'Local desk-object detector ready: {folder / f"desk-yoloe-{args.size}.pt"}')


if __name__=='__main__':
    main()
