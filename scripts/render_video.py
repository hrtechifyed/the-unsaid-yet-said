#!/usr/bin/env python3
"""Phase 1 faceless renderer: approved script -> narration, captions, branded MP4 + thumbnail."""
import argparse, json, re, subprocess, time
from pathlib import Path

OUT=Path('/tmp/production')
FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'


def run(*args, retries=1):
    last=None
    for attempt in range(1,retries+1):
        print('+', ' '.join(map(str,args)), f'(attempt {attempt}/{retries})')
        try:
            subprocess.run(list(map(str,args)),check=True)
            return
        except subprocess.CalledProcessError as exc:
            last=exc
            if attempt<retries: time.sleep(min(8,2**attempt))
    raise last


def clean_script(text):
    # Remove fenced blocks: these are generally visual diagrams or production notes, not narration.
    text=re.sub(r'```.*?```',' ',text,flags=re.S)
    # Remove visual/on-screen/stage directions and timecodes.
    text=re.sub(r'(?im)^\s*(?:\*\*)?\[(?:VISUAL|ON[- ]SCREEN|B-ROLL|SFX|MUSIC)[^\]]*\](?:\*\*)?\s*$',' ',text)
    text=re.sub(r'(?im)^\s*(?:#{1,6}\s*)?\[?\d{1,2}:\d{2}(?:\s*[–—-]\s*\d{1,2}:\d{2})?\]?[^\n]*$',' ',text)
    # Remove script metadata lines and section headings so TTS does not narrate production labels.
    text=re.sub(r'(?im)^\s*(?:\*\*)?(?:Title|Channel|Estimated Run Time|Estimated Runtime|Run Time|Runtime)\s*:\s*.*$',' ',text)
    text=re.sub(r'(?im)^\s*#{1,6}\s+.*$',' ',text)
    # Remove source markers and markdown formatting while preserving spoken words.
    text=re.sub(r'\[S\d+(?:\s*[,;-]\s*S?\d+)*\]','',text)
    text=re.sub(r'[*_`#>]','',text)
    text=re.sub(r'(?m)^\s*[-+•]\s+','',text)
    text=re.sub(r'[ \t]+',' ',text)
    text=re.sub(r'\n\s*\n+','\n\n',text)
    return text.strip()


def safe_title(topic): return topic.strip()[:95]


def main():
    p=argparse.ArgumentParser(); p.add_argument('--topic',required=True); p.add_argument('--script',required=True); a=p.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    topic=safe_title(a.topic)
    script=clean_script(Path(a.script).read_text())
    words=len(re.findall(r"\b[\w’'-]+\b",script))
    if words < 80: raise RuntimeError(f'Approved narration is unexpectedly short ({words} words); refusing to render.')
    (OUT/'narration.txt').write_text(script)
    (OUT/'title.txt').write_text(topic.replace("'",'’'))

    run('edge-tts','--voice','en-US-GuyNeural','--rate=-4%','--file',str(OUT/'narration.txt'),
        '--write-media',str(OUT/'narration.mp3'),'--write-subtitles',str(OUT/'captions.srt'),retries=3)

    probe=subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(OUT/'narration.mp3')],text=True).strip()
    duration=float(probe)
    if duration < 20: raise RuntimeError('Narration duration is unexpectedly short; refusing to upload.')

    vf=(
      "drawbox=x=0:y=0:w=iw:h=90:color=black@0.55:t=fill,"
      f"drawtext=fontfile={FONT}:text='THE UNSAID\\, YET SAID':fontcolor=white:fontsize=34:x=60:y=28,"
      f"drawtext=fontfile={FONT}:textfile={OUT/'title.txt'}:fontcolor=white:fontsize=46:x=(w-text_w)/2:y=150:box=1:boxcolor=black@0.30:boxborderw=24,"
      f"subtitles={OUT/'captions.srt'}:force_style='FontName=DejaVu Sans,FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00101010,BorderStyle=3,Outline=1,Shadow=0,MarginV=48,Alignment=2',"
      f"drawtext=fontfile={FONT}:text='What isn’t said often says the most.  •  Powered by HRTechify':fontcolor=white@0.72:fontsize=22:x=(w-text_w)/2:y=h-52"
    )
    run('ffmpeg','-y','-f','lavfi','-i',f"color=c=0x171717:s=1920x1080:r=30:d={duration+0.5}",
        '-i',str(OUT/'narration.mp3'),'-vf',vf,'-map','0:v','-map','1:a','-c:v','libx264','-preset','medium','-crf','22',
        '-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-shortest',str(OUT/'video.mp4'))

    thumb=(
      f"drawtext=fontfile={FONT}:textfile={OUT/'title.txt'}:fontcolor=white:fontsize=62:x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.35:boxborderw=30,"
      f"drawtext=fontfile={FONT}:text='THE UNSAID\\, YET SAID':fontcolor=white:fontsize=34:x=54:y=48,"
      f"drawtext=fontfile={FONT}:text='Powered by HRTechify':fontcolor=white@0.75:fontsize=24:x=54:y=h-70"
    )
    run('ffmpeg','-y','-f','lavfi','-i','color=c=0x171717:s=1280x720','-frames:v','1','-vf',thumb,str(OUT/'thumbnail.jpg'))
    metadata={'title':topic,'description':f'{topic}\n\nTHE UNSAID, YET SAID\nWhat isn’t said often says the most.\nPowered by HRTechify','duration_seconds':round(duration,1),'privacy':'private','narration_word_count':words}
    (OUT/'metadata.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False))
    print('Rendered',OUT/'video.mp4','duration',duration,'narration_words',words)

if __name__=='__main__': main()
