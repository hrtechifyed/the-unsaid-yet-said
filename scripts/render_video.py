#!/usr/bin/env python3
"""Free faceless renderer: approved script -> expressive TTS + rich editorial visuals + captions + thumbnail."""
import argparse, json, math, re, subprocess, time, textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path('/tmp/production')
FONT_REG = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONT_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
W, H = 1920, 1080
MIN_SPOKEN_WORDS = 900
MIN_DURATION_SECONDS = 420
MAX_DURATION_SECONDS = 600

BG = '#16110F'
PANEL = '#241A17'
PANEL_2 = '#31221C'
CREAM = '#F7E7C6'
ORANGE = '#F28A2E'
GOLD = '#E7B34E'
RED = '#9E2F27'
WHITE = '#FFF9F0'
MUTED = '#CDBFAE'
GREEN = '#61B788'

def run(*args, retries=1):
    last = None
    for attempt in range(1, retries + 1):
        print('+', ' '.join(map(str, args)), f'(attempt {attempt}/{retries})')
        try:
            subprocess.run(list(map(str, args)), check=True)
            return
        except subprocess.CalledProcessError as exc:
            last = exc
            if attempt < retries:
                time.sleep(min(8, 2 ** attempt))
    raise last

def ffprobe_duration(path):
    out = subprocess.check_output([
        'ffprobe','-v','error','-show_entries','format=duration',
        '-of','default=nw=1:nk=1',str(path)
    ], text=True).strip()
    return float(out)

def words(text):
    return re.findall(r"\b[\w’'-]+\b", text)

def clean_narration(text):
    text = re.sub(r'~~~.*?~~~', ' ', text, flags=re.S)
    text = re.sub(r'(?im)^\s*\[VISUAL:.*?\]\s*$', ' ', text)
    text = re.sub(r'(?im)^\s*(?:\*\*)?(?:Narrator|Voiceover|VO|Host|Presenter)\s*:\s*(?:\*\*)?\s*$', ' ', text)
    text = re.sub(r'(?im)^\s*(?:\*\*)?(?:Title|Channel|Estimated Run Time|Estimated Runtime|Run Time|Runtime)\s*:\s*.*$', ' ', text)
    text = re.sub(r'(?im)^\s*#{1,6}\s+.*$', ' ', text)
    text = re.sub(r'\[S\d+(?:\s*[,;-]\s*S?\d+)*\]', '', text)
    text = re.sub(r'[*_#>]', '', text)
    text = re.sub(r'(?m)^\s*[-+•]\s+', '', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n+', '\n\n', text)
    return text.strip()

def split_sentences(text):
    text = re.sub(r'\[S\d+(?:\s*[,;-]\s*S?\d+)*\]', '', text)
    text = re.sub(r'[*_#>]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return []
    return re.split(r'(?<=[.!?])\s+(?=[A-Z“"0-9])', text)

def parse_visual_blocks(raw):
    pat = re.compile(r'(?im)^\s*\[VISUAL:\s*(.*?)\]\s*$')
    matches = list(pat.finditer(raw))
    blocks = []
    if not matches:
        return [('Core idea', clean_narration(raw))]
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i+1].start() if i+1 < len(matches) else len(raw)
        blocks.append((m.group(1).strip(), raw[start:end].strip()))
    return blocks

def chunk_blocks(raw, max_words=30):
    scenes = []
    for desc, block in parse_visual_blocks(raw):
        sentences = split_sentences(block)
        buf, count = [], 0
        for sent in sentences:
            sw = len(words(sent))
            if buf and count + sw > max_words:
                scenes.append({'desc': desc, 'text': ' '.join(buf)})
                buf, count = [], 0
            buf.append(sent)
            count += sw
        if buf:
            scenes.append({'desc': desc, 'text': ' '.join(buf)})
    return [s for s in scenes if words(s['text'])]

def font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)

def gradient_background():
    img = Image.new('RGB', (W, H), BG)
    px = img.load()
    c1 = (22,17,15)
    c2 = (49,29,22)
    for y in range(H):
        t = y/(H-1)
        base = tuple(int(c1[i]*(1-t)+c2[i]*t) for i in range(3))
        for x in range(W):
            dx = (x-W*0.78)/(W*0.9)
            dy = (y-H*0.12)/(H*1.2)
            lift = max(0.0, 1.0 - math.sqrt(dx*dx+dy*dy)) * 18
            px[x,y] = tuple(min(255, int(v+lift)) for v in base)
    return img

def rr(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)

def wrapped(draw, text, box, fnt, fill=WHITE, spacing=10, align='left'):
    x1,y1,x2,y2 = box
    avg = max(10, int((x2-x1)/(fnt.size*0.56)))
    lines = textwrap.wrap(text, width=avg, break_long_words=False, break_on_hyphens=False)
    draw.multiline_text((x1,y1), '\n'.join(lines), font=fnt, fill=fill, spacing=spacing, align=align)
    return lines

def chrome(draw, scene_no, total):
    draw.rectangle((0,0,W,88), fill='#120D0C')
    draw.text((58,24), 'THE UNSAID, YET SAID', font=font(30, True), fill=CREAM)
    rr(draw,(W-360,22,W-58,66),22,fill=PANEL_2)
    draw.text((W-332,31),'Powered by HRTechify',font=font(19,True),fill=GOLD)
    draw.rectangle((0,H-13,W,H), fill='#0E0A09')
    draw.rectangle((0,H-13,int(W*(scene_no/max(1,total))),H), fill=ORANGE)

def draw_stat_bars(draw, stats, title):
    draw.text((110,145), title, font=font(52,True), fill=CREAM)
    y=285
    for label,val,color in stats:
        draw.text((125,y), label, font=font(30,True), fill=WHITE)
        draw.text((1650,y-2), f'{val}%', font=font(38,True), fill=color)
        rr(draw,(125,y+55,1780,y+93),19,fill='#3A2D27')
        width=int((1780-125)*max(0,min(val,100))/100)
        rr(draw,(125,y+55,125+width,y+93),19,fill=color)
        y += 150

def draw_scene(scene, idx, total, path):
    text = scene['text']
    desc = scene['desc']
    lower = (desc + ' ' + text).lower()
    img = gradient_background()
    draw = ImageDraw.Draw(img)
    chrome(draw, idx+1, total)
    draw.ellipse((W-500,120,W-70,550), outline='#5A3328', width=3)
    draw.ellipse((W-420,200,W-130,490), outline='#7B4632', width=2)
    draw.line((90,120,90,H-80), fill='#6A3B2C', width=2)

    if 'promotion notification' in lower or ('next step' in lower and 'employee says no' in lower):
        draw.text((118,150),'A promotion arrives.',font=font(56,True),fill=CREAM)
        rr(draw,(360,310,1560,790),36,fill=PANEL,outline='#704B3D',width=2)
        draw.text((440,375),'PROMOTION OPPORTUNITY',font=font(27,True),fill=GOLD)
        draw.text((440,440),'People Manager',font=font(58,True),fill=WHITE)
        draw.text((440,525),'Bigger title  •  Broader scope  •  More visibility',font=font(27),fill=MUTED)
        rr(draw,(440,635,780,720),18,fill='#2E4F3A')
        draw.text((540,658),'ACCEPT',font=font(28,True),fill=WHITE)
        rr(draw,(830,635,1170,720),18,fill=RED)
        draw.text((925,658),'DECLINE',font=font(28,True),fill=WHITE)
        draw.text((1210,655),'Then the employee says no.',font=font(26,True),fill=CREAM)

    elif 'signal' in lower and 'motive' in lower:
        draw.text((150,300),'SIGNAL',font=font(96,True),fill=ORANGE)
        draw.text((640,300),'≠',font=font(105,True),fill=CREAM)
        draw.text((820,300),'MOTIVE',font=font(96,True),fill=GOLD)
        draw.text((154,455),'Observe the decision.',font=font(38),fill=WHITE)
        draw.text((154,515),'Do not invent the reason.',font=font(38,True),fill=CREAM)
        rr(draw,(150,630,1180,760),28,fill=PANEL)
        wrapped(draw,text,(205,665,1110,750),font(28),fill=MUTED)

    elif '38%' in text and '62%' in text:
        draw.text((118,145),'Management is not the default destination',font=font(50,True),fill=CREAM)
        rr(draw,(120,310,900,725),32,fill=PANEL)
        rr(draw,(1020,310,1800,725),32,fill=PANEL)
        draw.text((210,395),'38%',font=font(108,True),fill=ORANGE)
        draw.text((1100,395),'62%',font=font(108,True),fill=GOLD)
        draw.multiline_text((210,545),'Interested in becoming\na people manager here',font=font(30,True),fill=WHITE,spacing=8)
        draw.multiline_text((1100,545),'Preferred to remain\nindividual contributors',font=font(30,True),fill=WHITE,spacing=8)
        draw.text((122,815),'Visier survey • 1,000 U.S. full-time individual contributors • Aug 2023',font=font(24),fill=MUTED)

    elif '40%' in text and '39%' in text:
        draw_stat_bars(draw,[
            ('Expected stress / pressure',40,ORANGE),
            ('Longer / more hours',39,GOLD),
            ('Better compensation',71,GREEN),
            ('Better benefits',45,'#7AB3D7')
        ],'What changes the management equation?')

    elif all(v in text for v in ['67%','64%','58%','9%']):
        draw_stat_bars(draw,[
            ('Time with family & friends',67,ORANGE),
            ('Physical & mental health',64,GOLD),
            ('Travel',58,'#7AB3D7'),
            ('Becoming a people manager',9,RED)
        ],'Ambition can exist in more than one dimension')

    elif '36%' in text and 'different organization' in lower:
        draw.text((120,165),'“No” can mean “not this version.”',font=font(62,True),fill=CREAM)
        rr(draw,(135,360,800,760),34,fill=PANEL)
        draw.text((255,430),'36%',font=font(118,True),fill=ORANGE)
        draw.multiline_text((225,590),'would consider people\nmanagement elsewhere',font=font(30,True),fill=WHITE,spacing=8)
        draw.line((920,360,920,760),fill='#6E4637',width=3)
        wrapped(draw,'This team. This timing. This workload. This compensation. This level of support.',
                (1020,390,1730,735),font(38,True),fill=GOLD,spacing=18)

    elif 'manager engagement in india' in lower and '39%' in text and '30%' in text:
        draw.text((120,150),'Manager engagement in India',font=font(55,True),fill=CREAM)
        draw.line((250,760,1650,760),fill='#7A5647',width=4)
        draw.line((330,300,330,760),fill='#7A5647',width=4)
        pts=[(620,430),(1380,575)]
        draw.line(pts,fill=ORANGE,width=12)
        for x,y,val,yr in [(620,430,'39%','2024'),(1380,575,'30%','2025')]:
            draw.ellipse((x-24,y-24,x+24,y+24),fill=GOLD)
            draw.text((x-62,y-110),val,font=font(48,True),fill=WHITE)
            draw.text((x-52,800),yr,font=font(32,True),fill=MUTED)
        draw.text((120,900),'Context, not a claim about any individual employee’s motive.',font=font(26),fill=MUTED)

    elif 'observe' in lower and 'verify' in lower and 'act' in lower:
        draw.text((120,145),'A better response to the signal',font=font(56,True),fill=CREAM)
        labels=[('1','OBSERVE','without labelling'),('2','ASK','what growth means'),('3','VERIFY','role design & reward'),('4','ACT','create real alternatives')]
        positions=[(120,315),(990,315),(120,615),(990,615)]
        cols=[ORANGE,GOLD,'#7AB3D7',GREEN]
        for (n,t,s),(x,y),c in zip(labels,positions,cols):
            rr(draw,(x,y,x+760,y+220),28,fill=PANEL,outline='#604033',width=2)
            draw.ellipse((x+35,y+35,x+105,y+105),fill=c)
            draw.text((x+60,y+48),n,font=font(28,True),fill=BG)
            draw.text((x+140,y+38),t,font=font(43,True),fill=WHITE)
            draw.text((x+140,y+105),s,font=font(27),fill=MUTED)

    elif 'is management the only way up' in lower or 'individual contributor' in lower or 'individual-contributor' in lower:
        draw.text((120,150),'Is management the only way up?',font=font(62,True),fill=CREAM)
        rr(draw,(130,345,850,790),34,fill=PANEL)
        rr(draw,(1070,345,1790,790),34,fill=PANEL)
        draw.text((250,410),'EXPERT TRACK',font=font(42,True),fill=GOLD)
        draw.text((1195,410),'MANAGER TRACK',font=font(42,True),fill=ORANGE)
        draw.multiline_text((250,510),'Deeper craft\nBroader decisions\nGreater influence\nNo direct reports required',font=font(31),fill=WHITE,spacing=18)
        draw.multiline_text((1195,510),'People leadership\nTeam outcomes\nCoaching\nOrganizational scope',font=font(31),fill=WHITE,spacing=18)

    elif 'don’t defend the offer' in lower or "don't defend the offer" in lower or 'better response is curiosity' in lower:
        draw.text((125,210),'DON’T DEFEND THE OFFER.',font=font(67,True),fill=ORANGE)
        draw.text((125,315),'DIAGNOSE THE SIGNAL.',font=font(67,True),fill=CREAM)
        rr(draw,(125,485,1760,825),32,fill=PANEL)
        wrapped(draw,text,(190,545,1690,790),font(32),fill=WHITE,spacing=16)

    else:
        phrases = re.split(r'[,;:]', text)
        key = max(phrases, key=lambda p: len(words(p)), default=text).strip()
        if len(key) > 110:
            key = ' '.join(words(key)[:16]) + '…'
        draw.text((125,165),'WHAT IS BEING COMMUNICATED?',font=font(27,True),fill=GOLD)
        wrapped(draw,key,(125,260,1510,560),font(58,True),fill=CREAM,spacing=16)
        rr(draw,(125,675,1510,850),28,fill=PANEL)
        wrapped(draw,text,(175,715,1450,825),font(27),fill=MUTED,spacing=12)

    img.save(path, quality=95)

def thumbnail(out):
    img = gradient_background()
    draw = ImageDraw.Draw(img)
    draw.rectangle((0,0,W,100),fill='#120D0C')
    draw.text((70,30),'THE UNSAID, YET SAID',font=font(31,True),fill=CREAM)
    draw.text((W-390,34),'Powered by HRTechify',font=font(23,True),fill=GOLD)
    draw.text((105,200),'WHEN A HIGH PERFORMER',font=font(36,True),fill=ORANGE)
    draw.text((105,265),'SAYS NO TO PROMOTION',font=font(72,True),fill=WHITE)
    rr(draw,(105,430,975,730),34,fill=PANEL)
    draw.text((170,495),'SIGNAL',font=font(70,True),fill=ORANGE)
    draw.text((540,495),'≠',font=font(78,True),fill=CREAM)
    draw.text((680,495),'MOTIVE',font=font(70,True),fill=GOLD)
    rr(draw,(1120,350,1780,790),34,fill=PANEL_2)
    draw.text((1250,455),'PROMOTION',font=font(38,True),fill=CREAM)
    rr(draw,(1240,585,1630,680),20,fill=RED)
    draw.text((1355,610),'DECLINE',font=font(31,True),fill=WHITE)
    draw.text((110,900),'What is the decision really telling you?',font=font(34,True),fill=MUTED)
    img.resize((1280,720),Image.Resampling.LANCZOS).save(out,quality=94)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--topic', required=True)
    p.add_argument('--script', required=True)
    a = p.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    topic = a.topic.strip()[:95]
    raw = Path(a.script).read_text()
    narration = clean_narration(raw)
    wc = len(words(narration))
    if wc < MIN_SPOKEN_WORDS:
        raise RuntimeError(f'QUALITY GATE FAILED: approved narration has {wc} spoken words; minimum is {MIN_SPOKEN_WORDS}.')

    (OUT/'narration.txt').write_text(narration)
    run('edge-tts','--voice','en-IN-PrabhatNeural','--rate=+12%','--file',str(OUT/'narration.txt'),
        '--write-media',str(OUT/'narration.mp3'),'--write-subtitles',str(OUT/'captions.srt'),retries=3)

    duration = ffprobe_duration(OUT/'narration.mp3')
    if duration < MIN_DURATION_SECONDS:
        raise RuntimeError(f'QUALITY GATE FAILED: narration is {duration:.1f}s; minimum is {MIN_DURATION_SECONDS}s.')
    if duration > MAX_DURATION_SECONDS:
        raise RuntimeError(f'QUALITY GATE FAILED: narration is {duration:.1f}s; maximum is {MAX_DURATION_SECONDS}s for the 7–10 minute target.')

    scenes = chunk_blocks(raw, max_words=30)
    if len(scenes) < 12:
        raise RuntimeError(f'VISUAL QUALITY GATE FAILED: only {len(scenes)} scenes were generated.')

    counts = [max(1, len(words(s['text']))) for s in scenes]
    total_words = sum(counts)
    durations = [duration * c / total_words for c in counts]
    durations = [max(5.0, min(12.0, d)) for d in durations]
    scale = duration / sum(durations)
    durations = [d * scale for d in durations]

    scene_dir = OUT/'scenes'
    scene_dir.mkdir(exist_ok=True)
    for i, scene in enumerate(scenes):
        draw_scene(scene, i, len(scenes), scene_dir/f'scene_{i:03d}.png')

    concat = []
    for i, d in enumerate(durations):
        concat += [f"file '{(scene_dir/f'scene_{i:03d}.png').as_posix()}'", f'duration {d:.4f}']
    concat.append(f"file '{(scene_dir/f'scene_{len(scenes)-1:03d}.png').as_posix()}'")
    (OUT/'slides.txt').write_text('\n'.join(concat))

    vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
        f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,"
        "zoompan=z='min(zoom+0.00008,1.025)':d=1:s=1920x1080:fps=30,"
        f"subtitles={OUT/'captions.srt'}:"
        "force_style='FontName=DejaVu Sans,FontSize=21,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00100D0B,BorderStyle=3,BackColour=&H880E0A09,Outline=1,Shadow=0,MarginV=42,Alignment=2'"
    )
    run('ffmpeg','-y','-f','concat','-safe','0','-i',str(OUT/'slides.txt'),
        '-i',str(OUT/'narration.mp3'),'-vf',vf,'-r','30',
        '-map','0:v','-map','1:a','-c:v','libx264','-preset','veryfast','-crf','20',
        '-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-shortest',str(OUT/'video.mp4'))

    thumbnail(OUT/'thumbnail.jpg')
    metadata = {
        'title': topic,
        'description': f'{topic}\n\nTHE UNSAID, YET SAID\nWhat isn’t said often says the most.\nPowered by HRTechify',
        'duration_seconds': round(duration,1),
        'privacy': 'private',
        'narration_word_count': wc,
        'target_duration_seconds': [420,600],
        'production_format': 'faceless_free',
        'voice': 'free_stock_tts_en-IN-PrabhatNeural',
        'visual_scene_count': len(scenes),
        'visual_style': 'editorial_motion_graphics_slideshow'
    }
    (OUT/'metadata.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False))
    print('Rendered',OUT/'video.mp4','duration',round(duration,1),'words',wc,'scenes',len(scenes))

if __name__ == '__main__':
    main()
