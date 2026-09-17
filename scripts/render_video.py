#!/usr/bin/env python3
"""Phase 1 faceless renderer: approved script -> narration, captions, branded MP4 + thumbnail."""
import argparse, json, re, subprocess
from pathlib import Path

OUT=Path('/tmp/production')
FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'


def run(*args):
    print('+', ' '.join(map(str,args)))
    subprocess.run(list(map(str,args)),check=True)


def clean_script(text):
    text=re.sub(r'\[S\d+(?:\s*[,;-]\s*S?\d+)*\]','',text)
    text=re.sub(r'[*_`#>]','',text)
    text=re.sub(r'\n{3,}','\n\n',text)
    return text.strip()


def safe_title(topic):
    return topic.strip()[:95]


def main():
    p=argparse.ArgumentParser(); p.add_argument('--topic',required=True); p.add_argument('--script',required=True); a=p.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    topic=safe_title(a.topic)
    script=clean_script(Path(a.script).read_text())
    if len(script.split()) < 80: raise RuntimeError('Approved script is unexpectedly short; refusing to render.')
    (OUT/'narration.txt').write_text(script)
    (OUT/'title.txt').write_text(topic.replace("'",'’'))

    # Zero-secret MVP narrator. Voice provider can be swapped without changing approval gates.
    run('edge-tts','--voice','en-US-GuyNeural','--rate=-4%','--file',str(OUT/'narration.txt'),
        '--write-media',str(OUT/'narration.mp3'),'--write-subtitles',str(OUT/'captions.srt'))

    probe=subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(OUT/'narration.mp3')],text=True).strip()
    duration=float(probe)
    if duration < 20: raise RuntimeError('Narration duration is unexpectedly short; refusing to upload.')

    vf=(
      "drawbox=x=0:y=0:w=iw:h=90:color=black@0.55:t=fill,"
      f"drawtext=fontfile={FONT}:text='THE UNSAID, YET SAID':fontcolor=white:fontsize=34:x=60:y=28,"
      f"drawtext=fontfile={FONT}:textfile={OUT/'title.txt'}:fontcolor=white:fontsize=46:x=(w-text_w)/2:y=150:box=1:boxcolor=black@0.30:boxborderw=24,"
      f"subtitles={OUT/'captions.srt'}:force_style='FontName=DejaVu Sans,FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00101010,BorderStyle=3,Outline=1,Shadow=0,MarginV=48,Alignment=2',"
      f"drawtext=fontfile={FONT}:text='What isn’t said often says the most.  •  Powered by HRTechify':fontcolor=white@0.72:fontsize=22:x=(w-text_w)/2:y=h-52"
    )
    run('ffmpeg','-y','-f','lavfi','-i',f"color=c=0x171717:s=1920x1080:r=30:d={duration+0.5}",
        '-i',str(OUT/'narration.mp3'),'-vf',vf,'-map','0:v','-map','1:a','-c:v','libx264','-preset','medium','-crf','22',
        '-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-shortest',str(OUT/'video.mp4'))

    thumb=(
      f"drawtext=fontfile={FONT}:textfile={OUT/'title.txt'}:fontcolor=white:fontsize=62:x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.35:boxborderw=30,"
      f"drawtext=fontfile={FONT}:text='THE UNSAID, YET SAID':fontcolor=white:fontsize=34:x=54:y=48,"
      f"drawtext=fontfile={FONT}:text='Powered by HRTechify':fontcolor=white@0.75:fontsize=24:x=54:y=h-70"
    )
    run('ffmpeg','-y','-f','lavfi','-i','color=c=0x171717:s=1280x720','-frames:v','1','-vf',thumb,str(OUT/'thumbnail.jpg'))
    metadata={'title':topic,'description':f'{topic}\n\nTHE UNSAID, YET SAID\nWhat isn’t said often says the most.\nPowered by HRTechify','duration_seconds':round(duration,1),'privacy':'private'}
    (OUT/'metadata.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False))
    print('Rendered',OUT/'video.mp4','duration',duration)

if __name__=='__main__': main()
