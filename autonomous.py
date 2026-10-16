"""Single-prompt autonomous motion-graphics video production.

Builds a scene-by-scene storyboard and streams graphic frames to FFmpeg. Optional
Gemini planning improves content; without an API key the safe offline planner
creates a visually varied, topic-based presentation without inventing facts.
Usage: python autonomous.py --prompt "Explain AI agents" --duration 300 --output output.mp4
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from motion_engine import LAYOUTS, PALETTES, render_scene

BEAT_NAMES = (
    "The opening idea", "Start with the question", "See the bigger picture",
    "The central concept", "Break it into pieces", "Explore the workflow",
    "Build the visual story", "Follow the sequence", "Connect the dots",
    "Spot the moving parts", "Organize the information", "Watch it in action",
    "Explore the interface", "Compare the approaches", "Find the pattern",
    "The step-by-step view", "What belongs together", "See the transformation",
    "Build from the basics", "Keep it clear", "Layer by layer",
    "Move to the next stage", "Understand the structure", "Focus on the details",
    "Visualize the process", "From first step to last", "Look at the complete picture",
    "The key takeaway", "Put the ideas together", "The final overview",
)
STEPS = [
    ("INTRODUCTION", "The idea", "The question", "What you'll discover", "Our direction", "Let's begin"),
    ("FOUNDATIONS", "The big picture", "The building blocks", "The moving parts", "The structure", "The connection"),
    ("BREAKDOWN", "The process", "The first stage", "What comes next", "How it fits", "The complete flow"),
    ("EXPLORATION", "Look closer", "The visual system", "What appears", "Inside the interface", "Motion in action"),
    ("PRACTICAL VIEW", "Make a plan", "Choose your elements", "Create each frame", "Review the sequence", "Put it together"),
    ("DESIGN", "Set the direction", "Use clear hierarchy", "Keep rhythm", "Make information readable", "Polish the transitions"),
    ("EXAMPLES", "Example workflow", "A simple sequence", "Another arrangement", "Compare the outputs", "The common thread"),
    ("REFINEMENT", "Test the result", "Find what matters", "Remove distractions", "Improve the pacing", "Keep improving"),
    ("RECAP", "What we covered", "The essential pieces", "Your next steps", "Final thoughts", "The story continues"),
]
STOP = {
    "about","for","the","and","with","this","that","from","your","make","create","build",
    "a","an","of","on","in","to","video","motion","graphics","explainer","please","five",
    "minutes","minute","using","how","why","what","into","like","professional",
}


def run(command, timeout=3600):
    p=subprocess.run(command,capture_output=True,text=True,timeout=timeout)
    if p.returncode:
        raise RuntimeError((p.stderr or "FFmpeg failed")[-1200:])


def _keywords(prompt):
    words=re.findall(r"[\w'-]+",prompt,flags=re.UNICODE)
    words=[w for w in words if w.lower() not in STOP and len(w)>2]
    output=[]
    for word in words:
        if word.casefold() not in {w.casefold() for w in output}:
            output.append(word)
    return output[:12] or ["Your idea", "Design", "Motion"]


def offline_storyboard(prompt, count, theme="midnight"):
    """Topic-aware planning, explicitly NOT a factual/research engine."""
    keywords=_keywords(prompt)
    subject=" ".join(keywords[:5]).strip()
    subject=subject[:65] or "Ideas into motion"
    scenes=[]
    for i in range(count):
        section=min(len(STEPS)-1, int(i*len(STEPS)/count))
        chapter=STEPS[section]
        beat=chapter[1:][i%5]
        focus=keywords[i%len(keywords)]
        next_focus=keywords[(i+1)%len(keywords)]
        pair=keywords[(i+2)%len(keywords)]
        if i==0:
            headline=subject.upper()
            subtitle="A visual journey through the idea"
        elif i==count-1:
            headline="THE STORY CONTINUES"
            subtitle="Create, explore, and keep refining"
        elif i%7==0:
            headline=chapter[0]
            subtitle=f"Exploring {subject.lower()}"
        else:
            headline=beat.upper() if i%3 else f"{focus.upper()} IN FOCUS"
            subtitle=f"{subject} · {chapter[0].title()}"
        layouts=("kinetic","steps","cards","dashboard","scroll","split","metrics","quote")
        scene={
            "layout": layouts[i%len(layouts)],
            "theme": theme if i%6 not in (4,5) else ("ocean" if theme!="ocean" else "midnight"),
            "title": headline[:100],
            "subtitle": subtitle[:130],
            "label": f"{section+1:02d} / {chapter[0]} / {i+1:02d}",
            "items": [beat[:52], focus[:52], next_focus[:52], pair[:52],
                      "Visualize and review"],
        }
        scenes.append(scene)
    return scenes


def gemini_storyboard(prompt, count, base_scenes):
    """Gemini returns original scene text/layout hints; renderer validates everything."""
    key=os.getenv("GEMINI_API_KEY")
    if not key:
        return None
    try:
        from google import genai
        client=genai.Client(api_key=key)
        scene_total=[]
        # Ten scenes per call keeps generated sections coherent and avoids truncation.
        for first in range(0,count,10):
            subset=base_scenes[first:first+10]
            indexes=list(range(first+1,first+1+len(subset)))
            response=client.models.generate_content(
                model=os.getenv("GEMINI_MODEL","gemini-2.5-flash"),
                contents=(
                    "Write ORIGINAL motion-graphic explainer storyboard content based on "
                    "the user's request. Return only a JSON object with 'scenes', EXACTLY "
                    f"{len(subset)} objects in order for scene numbers {indexes}. "
                    "Each object: title (<=9 words), subtitle (<=16 words), "
                    "items (array of 3 to 5 concise, distinct labels), "
                    "layout (one of: " + ", ".join(LAYOUTS) + "). "
                    "Make titles specific, concrete and connected across scenes, not generic. "
                    "NO statistics, quotes, citations or claims that you cannot verify. "
                    "If the prompt requests factual research, present a conceptual explainer "
                    "and do not pretend to have looked up sources. "
                    "Keep copyrighted/trademarked characters and logos out of the visual design. "
                    f"User prompt: {prompt}. "
                    f"Nearby context: {json.dumps(subset,ensure_ascii=False)}"
                ),
                config={"response_mime_type":"application/json"},
            )
            parsed=json.loads(response.text or "{}")
            chunk=parsed.get("scenes")
            if not isinstance(chunk,list) or len(chunk)!=len(subset):
                return None
            scene_total.extend(chunk)
        if len(scene_total)!=count:
            return None
        safe=[]
        for base,provided in zip(base_scenes,scene_total):
            if not isinstance(provided,dict):
                return None
            scene=dict(base)
            for field,limit in (("title",100),("subtitle",155)):
                value=provided.get(field)
                if isinstance(value,str) and value.strip():
                    scene[field]=value.strip()[:limit]
            items=provided.get("items",[])
            if isinstance(items,list):
                trimmed=[str(x).strip()[:58] for x in items[:6] if str(x).strip()]
                if trimmed:scene["items"]=trimmed
            if provided.get("layout") in LAYOUTS:
                scene["layout"]=provided["layout"]
            safe.append(scene)
        return safe
    except Exception as exc:
        print("Gemini storyboard unavailable; using offline plan:",str(exc)[:180],flush=True)
        return None


def make_storyboard(prompt, duration=300, ratio="16:9", theme="midnight", use_ai=False):
    prompt=str(prompt).strip()
    if not 5<=len(prompt)<=2000:
        raise ValueError("Describe your video in 5 to 2000 characters")
    duration=int(duration)
    if not 30<=duration<=300:
        raise ValueError("Choose a total duration from 30 to 300 seconds")
    if ratio not in ("9:16","16:9","1:1"):
        raise ValueError("Invalid aspect ratio")
    if theme not in PALETTES:
        raise ValueError("Unknown design palette")
    # Keep timings on integer frame boundaries, including the last segment.
    count=min(60,max(6,round(duration/6)))
    offline=offline_storyboard(prompt,count,theme)
    planned=gemini_storyboard(prompt,count,offline) if use_ai else None
    mode="gemini" if planned else "offline"
    scenes=planned or offline
    return {
        "prompt": prompt, "duration": duration, "ratio": ratio,
        "theme": theme, "planning_mode": mode,
        "fps": 20, "scenes": scenes,
        "notes": (
            "AI-written storyboard; no external research or downloaded footage was used."
            if planned else
            "Offline topic-based graphics; text is a generic visual outline, not researched narration."
        )
    }


def _audio_bed(path, seconds):
    """Synthesize a quiet original sound bed, not a licensed soundtrack."""
    expression="0.018*(sin(2*PI*110*t)+0.55*sin(2*PI*164.81*t)+0.35*sin(2*PI*220*t))"
    run(["ffmpeg","-hide_banner","-loglevel","error","-y",
         "-f","lavfi","-i",f"aevalsrc={expression}:s=16000:d={seconds}",
         "-af",f"afade=t=in:st=0:d=2,afade=t=out:st={max(0,seconds-3)}:d=3",
         "-c:a","aac","-b:a","96k",str(path)])


def render_storyboard(storyboard, output, *, quality="draft", ambience=False, progress=None):
    """Render all frames, concatenate scenes and mux optional generated ambience."""
    if quality not in ("draft","standard"):
        raise ValueError("Invalid render quality")
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg is required")
    seconds=int(storyboard["duration"])
    fps=int(storyboard.get("fps",20))
    scenes=storyboard["scenes"]
    if not 1<=len(scenes)<=60 or not 30<=seconds<=300:
        raise ValueError("Storyboard exceeds production limits")
    sizes={
        "16:9": (640,360) if quality=="standard" else (426,240),
        "9:16": (360,640) if quality=="standard" else (240,426),
        "1:1": (480,480) if quality=="standard" else (320,320),
    }
    w,h=sizes[storyboard["ratio"]]
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="motionforge_") as d:
        work=Path(d)
        count=len(scenes)
        # All shots are exact integer numbers of frames, totaling the requested duration.
        frames=int(seconds*fps)
        base,extra=divmod(frames,count)
        lengths=[base+(1 if i<extra else 0) for i in range(count)]
        if min(lengths)<fps or max(lengths)>16*fps:
            raise ValueError("Storyboard scene duration is outside renderer range")
        for i,scene in enumerate(scenes):
            if progress:progress(i/count*90, f"Animating shot {i+1}/{count}")
            render_scene(scene,work/f"shot_{i:03d}.mp4",width=w,height=h,
                         fps=fps,duration=lengths[i]/fps)
        if progress:progress(92,"Assembling the complete timeline")
        manifest=work/"timeline.txt"
        manifest.write_text("".join(f"file 'shot_{i:03d}.mp4'\n" for i in range(count)),encoding="utf-8")
        merged=work/"merged.mp4"
        run(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","concat",
             "-safe","0","-i",str(manifest),"-c","copy",str(merged)])
        if ambience:
            if progress:progress(95,"Creating original ambient audio")
            track=work/"ambient.m4a"
            _audio_bed(track,seconds)
            run(["ffmpeg","-hide_banner","-loglevel","error","-y",
                 "-i",str(merged),"-i",str(track),"-map","0:v:0",
                 "-map","1:a:0","-c:v","copy","-c:a","copy",
                 "-t",str(seconds),"-movflags","+faststart",str(output)])
        else:
            run(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(merged),
                 "-c","copy","-movflags","+faststart",str(output)])
    if progress:progress(100,"Full video is ready")
    return str(output)


def create_video(prompt, output, *, duration=300, ratio="16:9",
                 theme="midnight", quality="draft", use_ai=False,
                 ambience=False, progress=None):
    if progress:progress(1,"Planning the storyboard")
    storyboard=make_storyboard(prompt,duration=duration,ratio=ratio,theme=theme,use_ai=use_ai)
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    json_path=output.with_suffix(".storyboard.json")
    json_path.write_text(json.dumps(storyboard,ensure_ascii=False,indent=2),encoding="utf-8")
    if progress:progress(3,f"Prepared {len(storyboard['scenes'])} original motion scenes")
    render_storyboard(storyboard,output,quality=quality,ambience=ambience,
                      progress=progress)
    return {"video":str(output),"storyboard":str(json_path),
            "scene_count":len(storyboard["scenes"]),
            "planning_mode":storyboard["planning_mode"]}


def main():
    parser=argparse.ArgumentParser(description="MotionForge one-prompt graphics movie")
    parser.add_argument("--prompt",required=True)
    parser.add_argument("--duration",type=int,default=300,help="30-300 seconds")
    parser.add_argument("--ratio",choices=["16:9","9:16","1:1"],default="16:9")
    parser.add_argument("--theme",choices=list(PALETTES),default="midnight")
    parser.add_argument("--quality",choices=["draft","standard"],default="standard")
    parser.add_argument("--use-ai",action="store_true",help="Use optional Gemini storyboard key")
    parser.add_argument("--ambience",action="store_true",help="Add synthesized ambient audio")
    parser.add_argument("--output",default="motionforge-5min.mp4")
    args=parser.parse_args()
    def show(p,message):
        print(f"[{p:5.1f}%] {message}",flush=True)
    result=create_video(args.prompt,args.output,duration=args.duration,ratio=args.ratio,
                        theme=args.theme,quality=args.quality,use_ai=args.use_ai,
                        ambience=args.ambience,progress=show)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
