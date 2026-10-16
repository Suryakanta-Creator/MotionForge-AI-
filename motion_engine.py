"""Procedural 2D motion-graphics renderer: cards, kinetic text, scrolling UI and more.

No diffusion model or stock assets required. Every object is drawn with Pillow and
animated from parameterized JSON; streamed to ffmpeg without accumulating frames.
"""
from __future__ import annotations

import math
import subprocess
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

LAYOUTS = ("kinetic", "cards", "steps", "dashboard", "scroll", "split", "quote", "metrics")
PALETTES = {
    "midnight": ("#0B0F19", "#1D2541", "#BBA4FF", "#F8F6FF", "#9FA6BC"),
    "ocean": ("#081923", "#103C4C", "#6DE8DC", "#F5FCFF", "#A4C8D1"),
    "ember": ("#25130F", "#542C21", "#FBA167", "#FFF7ED", "#E3BCAE"),
    "paper": ("#F0EEE9", "#DFDED9", "#EB583F", "#1B2233", "#697488"),
    "berry": ("#201025", "#472342", "#FF89C9", "#FFF3FD", "#D2B2D4"),
}


def _rgb(value):
    return tuple(bytes.fromhex(value.lstrip("#")))


def _mix(a, b, t):
    t = min(1.0, max(0.0, t))
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


def _ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def _enter(t, start, length=.20):
    return _ease((t - start) / length)


@lru_cache(maxsize=90)
def _font(size, bold=True):
    fonts = [
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    path = next((p for p in fonts if Path(p).exists()), None)
    return ImageFont.truetype(path, max(10, int(size))) if path else ImageFont.load_default()


def _text_width(d, text, font):
    return d.textbbox((0, 0), text, font=font)[2]


def _lines(d, text, font, max_width, max_lines=5):
    output, line = [], ""
    for word in str(text).replace("\n", " \n ").split():
        if word == "\n":
            if line:
                output.append(line)
            line = ""
            continue
        check = (line + " " + word).strip()
        if line and _text_width(d, check, font) > max_width:
            output.append(line)
            line = word
        else:
            line = check
    if line:
        output.append(line)
    return output[:max_lines]


def _rect(d, box, r, color, outline=None, width=1):
    d.rounded_rectangle(tuple(round(v) for v in box), radius=max(1, round(r)),
                        fill=color, outline=outline, width=max(1, width))


@lru_cache(maxsize=16)
def _background(w, h, theme):
    colors = [_rgb(i) for i in PALETTES[theme]]
    bg, panel, accent, white, muted = colors
    im = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(im)
    for y in range(0, h, 4):
        d.rectangle((0, y, w, min(h, y + 4)), fill=_mix(bg, panel, .12 + .15 * y / h))
    # Ambient glow and quiet technical grid.
    cx, cy = int(w * .81), int(h * .15)
    rmax = max(20, int(min(w, h) * .48))
    for r in range(rmax, 0, -11):
        strength = .06 + .27 * (1 - r / rmax)
        d.ellipse((cx-r, cy-r, cx+r, cy+r), fill=_mix(bg, panel, strength))
    for x in range(0, w, max(38, w // 11)):
        d.line((x, 0, x, h), fill=_mix(bg, panel, .28))
    return im


def frame(scene, w, h, seconds, duration):
    """Render a fully composited frame at a precise moment, with animated layers."""
    layout = scene.get("layout", "kinetic")
    theme = scene.get("theme", "midnight")
    if layout not in LAYOUTS or theme not in PALETTES:
        raise ValueError("Invalid motion template or palette")
    im = _background(w, h, theme).copy()
    d = ImageDraw.Draw(im)
    bg, panel, accent, white, muted = [_rgb(x) for x in PALETTES[theme]]
    t = min(1.0, seconds / max(.1, duration))
    margin = int(w * .085)
    portrait = h > w
    title = str(scene.get("title", "IDEAS IN MOTION"))[:110]
    subtitle = str(scene.get("subtitle", "Make it move."))[:155]
    label = str(scene.get("label", "MOTIONFORGE / MOTION STUDY"))[:65]
    entries = [str(v)[:58] for v in scene.get("items", []) if str(v).strip()][:6]
    if not entries:
        entries = ["Discover", "Design", "Animate"]
    size = min(w*.067 if portrait else w*.048, h*.066)
    heading = _font(max(16, size), True)
    body = _font(max(12, w * (.037 if portrait else .023)), False)
    note = _font(max(10, w * (.024 if portrait else .016)), True)
    # Timer, eyebrow and ornamental halo.
    d.line((margin, h*.047, w-margin, h*.047), fill=_mix(panel, white, .32), width=2)
    d.line((margin, h*.047, margin+(w-2*margin)*t, h*.047), fill=accent, width=3)
    d.text((margin, h*.062), label.upper(), font=note, fill=muted)
    halo_r = min(w,h)*(.15+ .015*math.sin(seconds*.9))
    d.ellipse((w*.79-halo_r,h*.18-halo_r,w*.79+halo_r,h*.18+halo_r),
              outline=_mix(panel,accent,.42),width=2)

    if layout in ("kinetic", "quote"):
        size_factor = 1.12 if layout == "kinetic" else .93
        font = _font(heading.size*size_factor, True)
        lines = _lines(d, title, font, w-2*margin, 6)
        line_h = font.size*1.23
        yy = h*(.32 if portrait else .22)
        for i, line in enumerate(lines):
            a = _enter(t,.06+i*.11,.23)
            x = margin+(1-a)*w*.20
            color=_mix(bg,white,a)
            d.text((x, yy+i*line_h), line, font=font, fill=color)
        ysub = min(h*.81, yy+len(lines)*line_h+h*.052)
        a = _enter(t,.45,.20)
        for i,line in enumerate(_lines(d,subtitle,body,w-2*margin,3)):
            d.text((margin, ysub+i*body.size*1.35+(1-a)*20), line,
                   font=body, fill=_mix(bg, muted, a))
        _rect(d,(margin,h*.89,w-margin,h*.9),3,panel)
        _rect(d,(margin,h*.89,margin+(w-2*margin)*_ease(t),h*.9),3,accent)

    elif layout in ("cards","steps"):
        a = _enter(t,.02,.23)
        y_head = h*(.17 if portrait else .18)
        for i,line in enumerate(_lines(d,title,heading,w-2*margin,2)):
            d.text((margin,y_head+i*heading.size*1.18+(1-a)*30),line,
                   font=heading,fill=_mix(bg,white,a))
        d.text((margin,y_head+heading.size*2.42),subtitle[:80],font=body,fill=muted)
        if layout == "cards":
            cols = 1 if portrait else 3
            rows = math.ceil(len(entries)/cols)
            gap = max(6,int(w*.018))
            start = h * (.40 if portrait else .43)
            available = h*.88-start
            cw=(w-2*margin-gap*(cols-1))/cols
            ch=min(h*.15,(available-gap*(rows-1))/rows)
            for i,entry in enumerate(entries):
                a=_enter(t,.13+i*.07,.20)
                x=margin+(i%cols)*(cw+gap)
                y=start+(i//cols)*(ch+gap)+(1-a)*h*.040
                _rect(d,(x,y,x+cw,y+ch),max(7,w*.02),_mix(bg,panel,a),_mix(bg,accent,a*.75),2)
                dot=max(8,int(min(ch,cw)*.16))
                d.ellipse((x+13,y+ch*.20,x+13+dot,y+ch*.20+dot),fill=_mix(bg,accent,a))
                f=_font(min(body.size*1.1,ch*.22),True)
                d.text((x+13,y+ch*.57),entry,font=f,fill=_mix(bg,white,a))
        else:
            start=h*(.38 if portrait else .44)
            row_height=min(h*.108,(h*.90-start)/len(entries))
            for i,entry in enumerate(entries):
                a=_enter(t,.10+i*.10,.17)
                y=start+i*row_height
                x=margin+(1-a)*w*.16
                _rect(d,(x,y,w-margin,y+row_height*.83),w*.017,
                      _mix(bg,panel,a),None)
                d.text((x+12,y+row_height*.18),f"{i+1:02d}",font=body,fill=_mix(bg,accent,a))
                d.text((x+max(43,w*.11),y+row_height*.18),entry,font=body,fill=_mix(bg,white,a))

    elif layout in ("dashboard","scroll"):
        a=_enter(t,.04,.23)
        y_head=h*.16
        for i,line in enumerate(_lines(d,title,heading,w-2*margin,2)):
            d.text((margin,y_head+i*heading.size*1.2+(1-a)*25),line,font=heading,fill=_mix(bg,white,a))
        d.text((margin,y_head+heading.size*2.5),subtitle[:84],font=body,fill=muted)
        x=margin;y=h*.39;dw=w-2*margin;dh=h*.47
        _rect(d,(x,y,x+dw,y+dh),w*.025,panel,_mix(panel,accent,.57),2)
        _rect(d,(x+7,y+7,x+dw-7,y+min(43,dh*.14)),w*.01,_mix(bg,panel,.48))
        for j,c in enumerate(("#FF7777","#FFC57C","#80DDA7")):
            r=max(3,w*.007)
            d.ellipse((x+15+j*20,y+19,x+15+j*20+r*2,y+19+r*2),fill=_rgb(c))
        top=y+max(54,dh*.16)
        area=dh-max(54,dh*.16)-12
        rh=area/max(1, len(entries))
        # Scroll entries through a viewport, showing actual moving content.
        scroll_shift = _ease(t)*rh*max(0,len(entries)-3) if layout=="scroll" else 0
        viewport=(int(x+10),int(top),int(x+dw-10),int(y+dh-10))
        layer=Image.new("RGB",(max(1,viewport[2]-viewport[0]),max(1,viewport[3]-viewport[1])),panel)
        ld=ImageDraw.Draw(layer)
        lw,lh=layer.size
        for j,entry in enumerate(entries):
            a=_enter(t,.12+j*.075,.2)
            yy=j*rh-scroll_shift
            if yy+rh<0 or yy>lh:continue
            _rect(ld,(4,yy+3,lw-4,yy+rh*.82),8,
                  _mix(panel,white,.09*a))
            _rect(ld,(13,yy+rh*.26,31,yy+rh*.56),4,_mix(panel,accent,a))
            font=_font(min(body.size,rh*.29),True)
            ld.text((40,yy+rh*.18),entry,font=font,fill=_mix(panel,white,a))
        im.paste(layer,(viewport[0],viewport[1]))
        d=ImageDraw.Draw(im)
        if layout=="scroll":
            _rect(d,(x+dw-7,top+8,x+dw-4,y+dh-9),2,_mix(panel,muted,.5))
            thumby=top+9+_ease(t)*(area*.71)
            _rect(d,(x+dw-9,thumby,x+dw-2,thumby+area*.25),3,accent)

    elif layout in ("split","metrics"):
        y_head=h*.15
        for i,line in enumerate(_lines(d,title,heading,w-2*margin,2)):
            a=_enter(t,.05+i*.1,.24)
            d.text((margin+(1-a)*30,y_head+i*heading.size*1.20),line,font=heading,fill=_mix(bg,white,a))
        d.text((margin,y_head+heading.size*2.4),subtitle[:90],font=body,fill=muted)
        cols=2 if layout=="split" else (2 if portrait else 3)
        gap=max(9,w*.019)
        cw=(w-2*margin-gap*(cols-1))/cols
        start=h*.40
        rows=math.ceil(min(len(entries),6)/cols)
        ch=min(h*.20,(h*.87-start-gap*(rows-1))/max(1,rows))
        for i,entry in enumerate(entries):
            a=_enter(t,.15+i*.085,.21)
            x=margin+(i%cols)*(cw+gap)
            y=start+(i//cols)*(ch+gap)+(1-a)*h*.04
            _rect(d,(x,y,x+cw,y+ch),w*.02,_mix(bg,panel,a),_mix(bg,accent,a*.8),2)
            _rect(d,(x+11,y+12,x+cw-11,y+ch*.61),8,_mix(panel,accent,a*(.19+.10*(i%2))))
            fnum=_font(min(cw*.20,ch*.24),True)
            d.text((x+17,y+ch*.24),f"{i+1:02d}",font=fnum,fill=_mix(bg,white,a))
            f=_font(min(cw*.085,body.size),True)
            for k,line in enumerate(_lines(d,entry,f,cw-23,2)):
                d.text((x+11,y+ch*.72+k*f.size*1.04),line,font=f,fill=_mix(bg,white,a))

    d=ImageDraw.Draw(im)
    d.text((margin,h*.945),"MOTIONFORGE  /  "+layout.upper(),font=note,fill=muted)
    r=max(4,w*.008)
    d.ellipse((w-margin-2*r,h*.948,w-margin,h*.948+2*r),fill=accent)
    # Scene-to-scene fade so hard cuts do not flash aggressively.
    edge=min(1,seconds/.22,(duration-seconds)/.22)
    if edge<1:
        return Image.blend(Image.new("RGB",(w,h),bg),im,max(0.0,edge))
    return im


def render_scene(scene, path, width=360, height=640, fps=20, duration=6.0):
    """Low-memory pipe: one RGB frame at a time to H264 video."""
    if not (1<=duration<=16 and 10<=fps<=30):
        raise ValueError("Invalid scene timing or frame rate")
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    count=round(duration*fps)
    args=["ffmpeg","-hide_banner","-loglevel","error","-y","-threads","1",
          "-f","rawvideo","-pix_fmt","rgb24","-s",f"{width}x{height}",
          "-r",str(fps),"-i","pipe:0","-an","-c:v","libx264",
          "-threads","1","-preset","ultrafast","-crf","23",
          "-pix_fmt","yuv420p","-movflags","+faststart",str(path)]
    proc=subprocess.Popen(args,stdin=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        for i in range(count):
            proc.stdin.write(frame(scene,width,height,i/fps,duration).tobytes())
        proc.stdin.close()
        error=proc.stderr.read().decode("utf-8",errors="replace")
        if proc.wait()!=0:
            raise RuntimeError(error[-700:])
    except BaseException:
        if proc.poll() is None:proc.kill()
        path.unlink(missing_ok=True)
        raise
    return count/fps
