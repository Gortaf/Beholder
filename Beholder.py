# -*- coding: utf-8 -*-
"""
Created on Thu May  1 12:01:01 2025

@author: nicol
"""

import os
import sys
import io
import requests
import pdfkit
import time
import enum
import json
import argparse
from pathvalidate import sanitize_filename
from datetime import datetime, timedelta, date
from dotenv import load_dotenv
from google import genai
from google.cloud import texttospeech
from pydantic import BaseModel
from pydub import AudioSegment
from tqdm import tqdm

# Semantic Scholar search constants
API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
API_FIELDS = "title,authors,url,year,publicationDate,externalIds,abstract,isOpenAccess,openAccessPdf"
# API_STUDY_FIELDS="Computer Science"
# API_STUDY_FIELDS="Psychology"

# Sound effect mp3s
SOUND_EFFECTS = [
    "intro.mp3",
    "transition.mp3",
    "click.mp3",
    "paper.mp3",
    "crumpled_paper.mp3",
    "amogus.mp3",
    "outro.mp3",
    ]

# Sound effects struct. Model can always choose one of them for the Sound_Effects fields of a Turn
class Sound_Effect(enum.Enum):
        NOTHING = "nothing"
        INTRO = "intro.mp3"
        TRANSITION = "transition.mp3"
        CLICK = "click.mp3"
        PAPER = "paper.mp3"
        RIPPED_PAPER = "crumpled_paper.mp3"
        AMOGUS = "amogus.mp3"
        OUTRO = "outro.mp3"

# Base struct of a speaker's turn to generate a structured output
class Turn(BaseModel):
    speaker: str
    text: str
    sound_effect_before: Sound_Effect
    sound_effect_after: Sound_Effect

# Making arg parser
parser_desc = """
Bot for Extracting & Highlighting Outstanding Literature, Evaluations & Reviews (BEHOLDER).\n
Requires the following files & directory:
    .env (containing a G_API_KEY variable with a valid google cloud API key for Gemini & TTS)
    watch_terms.txt (a list of terms to search through semantic scholar, one per line)
    script_prompt.txt (the Gemini prompt for script generation)
    sound_effects (a directory containing all available sound effects & bgm)
"""
parser = argparse.ArgumentParser(
    prog="Beholder",
    description=parser_desc,
    epilog="Written by Nicolas Jacquin (nicolas.jacquin@umontreal.ca)",
    formatter_class=argparse.RawTextHelpFormatter)

# Value args
parser.add_argument("-o", "--output", help = "folder where papers will be stored and the mp3 will be added",
                    default = ".")
parser.add_argument("-i", "--interests", help = "areas of interests for the script prompt. Defaults to watch terms",
                    nargs='+', default=[])
parser.add_argument("-d", "--days_back", 
                    help = "number of days to look back for papers. Default is 14",
                    default=14, type=int)
parser.add_argument("-c", "--search_chunk", 
                    help = "paper search limit for each watch term. Higher means more captured results, but can cause issues with Semantic Scholar API. Default is 75",
                    default=75, type=int)
parser.add_argument("-m", "--model", 
                    help = "gemini model to use. Consider API costs & context windows before changing from default. Default is gemini-1.5-pro",
                    default="gemini-1.5-pro")
parser.add_argument("-t", "--temperature", 
                    help = "script generation temperature (higher means more spicy outcomes). Default is 0.7",
                    default=0.7, type=float)
parser.add_argument("-s", "--max_tokens", 
                    help = "maximum token length of generated script (higher means potentially longer scripts, but higher google API cost). Default is 300000",
                    default=300000, type=int)
parser.add_argument("-l", "--language", 
                    help = "language of TTS model to use. Need to match the chosen --voice. Default is en-US",
                    default="en-US")
parser.add_argument("-v", "--voice", 
                    help = "voice for podcast. See README for a list of available voices (consider API costs per voice engine before making drastic changes). Default is en-US-Chirp3-HD-Algieba",
                    default="en-US-Chirp3-HD-Algieba")
parser.add_argument("-f", "--fields_of_study", 
                    help = "fields of study to search in Semantic Scholar. Check API for available fields of study (API paramater fieldsOfStudy). Default is Computer Science",
                    nargs='+', default=["Computer Science"])
parser.add_argument("-w", "--watch_terms", 
                    help = "sets watch_terms.txt path. Defaults to watch_terms.txt",
                    default="watch_terms.txt")
parser.add_argument("-p", "--script_prompt", 
                    help = "sets script_prompt.txt path. Defaults to script_prompt.txt",
                    default="script_prompt.txt")

# No shortcut value args
parser.add_argument("--from_papers", 
                    help = "skips paper retrievals, send the given folder of papers to podcast generation")


# Flags
parser.add_argument("--save_script",
                    help = "the podcast script's JSON will be saved in the output directory",
                    action='store_true')
parser.add_argument("--no_podcast", 
                    help = "the script will stop after retrieving the papers and will not attempt to generate an audio podcast", 
                    action='store_true')
parser.add_argument("--no_audio",
                    help = "the script will stop after generating the podcast script json. Couple with --save_script to save the script json",
                    action='store_true')

def search_papers(query, fields, days_back=14, limit=75):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    date_range = f"{start_date.date()}:{end_date.date()}"

    params = {
        'query': query,
        'limit': limit,
        'fields': API_FIELDS,
        'fieldsOfStudy': fields,
        'offset': 0,
        'year': start_date.year,  # Restrict by year, we'll filter by date on results

    }
    
    success = False
    while not success:
        response = requests.get(API_URL, params=params)
        if response.ok:
            success = True
        elif response.status_code == 429:
            tqdm.write("hit too many requests, sleeping for 2 seconds...")
            time.sleep(2)
        else:
            response.raise_for_status()
            
    data = response.json()

    # Filter further by exact publication dates & PDF availability
    recent_papers = []
    for paper in data.get('data', []):
        
        # Getting publication date & checking if it's within timeframe
        pub_date = paper.get('publicationDate', '')
        if pub_date:
            pub_datetime = datetime.strptime(pub_date, '%Y-%m-%d')
            if start_date <= pub_datetime <= end_date:

                # PDF is marked as available
                if paper.get('openAccessPdf'):
                    recent_papers.append({
                        'title': sanitize_filename(paper['title']),
                        'pdf_url': paper['openAccessPdf']['url'],
                        'DOI': paper["externalIds"]['DOI'],
                        'abstract': paper["abstract"]
                    })
                    
                # PDF not available but DOI still provided.
                elif "DOI" in paper["externalIds"].keys() and paper["externalIds"]["DOI"]:
                    recent_papers.append({
                        'title': sanitize_filename(paper['title']),
                        'pdf_url': None,  # PDF not directly available
                        'DOI': paper["externalIds"]['DOI'],
                        'abstract': paper["abstract"]
                    })
    return recent_papers

def get_pdf(url, doi, path):
    
    # Tries retrieving the pdf the "polite" way
    if ".pdf" in url:
        response = requests.get(url)
        with open(path+".pdf", 'wb') as f:
            f.write(response.content)
            return True
    
    # If the polite way fails because the provided link isn't a pdf, try turning the page from the link into a pdf
    try:
        pdfkit.from_url(url, path+".pdf")
        return True
    except:
        tqdm.write(f"pdfkit failed using provided pdf link for paper: {path}... deleting file...")
        if os.path.exists(path+".pdf"):
            os.remove(path+".pdf")

    # If the provided link won't be turned into a pdf, uses doi to retrieve paper page and turn it into pdf
    try:
        pdfkit.from_url(f"https://doi.org/{doi}", path+".pdf")
        return True
    except:
        tqdm.write(f"pdfkit failed using doi link for paper: {path}... deleting file...")
        if os.path.exists(path+".pdf"):
            os.remove(path+".pdf")
    
    # If all else fails, returns False so that we at least try to retrieve the abstract
    return False

def batch_get_pdf(watch_terms, folder, fields, days_back=14, limit=75):
    total_papers = 0
    for term in tqdm(watch_terms):
        papers = search_papers(term, fields, days_back=days_back, limit=limit)
        total_papers += len(papers)
        # tqdm.write(papers)
        for paper in papers:
            success = False
            if "Abstract" in paper["title"]: continue   # Skips sketch unreviewed pretqdm.writes
            
            # Main pathway for recovering pdf
            if paper['pdf_url'] != None or paper['DOI'] != None:
                tqdm.write(f"getting pdf for: {paper['title']}")
                success = get_pdf(paper['pdf_url'], paper['DOI'], f"{folder}/{paper['title']}")
            
            # No pdf available or recovery failed -> use abstract
            if (paper['pdf_url'] == None or not success) and paper["abstract"] != None:
                tqdm.write(f"abstract only for: {paper['title']}")
                with open(f"{folder}/{paper['title']}.txt", "w", encoding="utf-8") as f:
                    f.write("ABSTRACT ONLY:\n"+paper["abstract"])
                    
    return total_papers

def script_from_papers(gkey, folder, prompt, model="gemini-1.5-pro", max_tokens=300000, temperature=0.7):
    client = genai.Client(api_key = gkey)
    files = os.scandir(folder)
    pdfs = []
    abstracts = []
    
    for file in files:
        if not file.is_file():
            continue
        
        if os.path.splitext(file)[-1] == ".pdf":
            pdf_bytes = io.BytesIO(open(file, "rb").read())
            pdfs.append(client.files.upload(
               file=pdf_bytes,
               config=dict(mime_type='application/pdf')
             ))
        elif os.path.splitext(file)[-1] == ".txt":
            name = os.path.splitext(file)[-2]
            abstracts.append(f"{name}:\n"+open(file, "r", encoding="utf8").read())
        else:
            tqdm.write(f"Unsupported file:\n{file}\nSkipping...\n")
    
    content = []
    if len(pdfs) != 0: content.append(pdfs)
    if len(abstracts) != 0: content.append(abstracts)
    # tqdm.write([*pdfs, *abstracts, prompt])
    response = client.models.generate_content(
        model=model,
        contents=content,
      
      # This allows for generating a discussion formatted in turns
      # Since multi-speaker voices are currently whitelist only,
      # I only generate a single speaker for now.
      config=genai.types.GenerateContentConfig(
          response_mime_type= "application/json", 
          response_schema=list[Turn], 
          max_output_tokens=max_tokens, 
          temperature=temperature,
          system_instruction = prompt
          )
    )
    
    return json.loads(response.text)

def generate_voice_line(client, voice, audio_config, text):
    return client.synthesize_speech(
        input=texttospeech.SynthesisInput(text=text),
        voice=voice,
        audio_config=audio_config,
    )

def add_bgm(podcast_audio, intro_end, outro_start, bgm_mp3="sound_effects/bgm.mp3", volume_mod = -5):
    background_music = AudioSegment.from_mp3(bgm_mp3)
    duration = outro_start - intro_end
    looped_background = background_music * (duration // len(background_music) + 1)
    looped_background = looped_background[:duration]
    looped_background = looped_background + volume_mod
    pre = podcast_audio[:intro_end]
    mid = podcast_audio[intro_end:outro_start]
    post = podcast_audio[outro_start:]
    mid_with_music = looped_background.overlay(mid)
    combined = pre + mid_with_music + post
    return combined

def script_to_podcast(gkey, text, output, language = "en-US", voice="en-US-Chirp3-HD-Algieba"):
    loaded_effects = {file:AudioSegment.from_mp3(f"sound_effects/{file}") for file in SOUND_EFFECTS}
    client = texttospeech.TextToSpeechClient(client_options={"api_key":gkey})

    voice = texttospeech.VoiceSelectionParams(
        language_code=language,
        name=voice,
    )

    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3
    )
    
    final_audio = AudioSegment.silent(duration=0)
    intro_end = -1
    outro_start = -1
    
    for turn in tqdm(text):
        before = turn["sound_effect_before"]
        after = turn["sound_effect_after"]
        to_voice = turn["text"]
        
        if before != "nothing" and before in loaded_effects:
            final_audio += loaded_effects[before]
            
            if before == "intro.mp3":  # Getting end of intro to overlay bgm
                intro_end = len(final_audio)
            
        
        voice_line = generate_voice_line(client, voice, audio_config, to_voice)
        final_audio += AudioSegment.from_file(io.BytesIO(voice_line.audio_content), format="mp3")
        
        if after != "nothing" and after in loaded_effects:
            
            if after == "outro.mp3":  # Getting start of outro to overlay bgm
                outro_start = len(final_audio)
            
            final_audio += loaded_effects[after]
    
    final_audio = add_bgm(final_audio, intro_end, outro_start)
    final_audio.export(output, format="mp3")
    return final_audio

if __name__ == "__main__":
    try:
        load_dotenv()
        gkey = os.getenv("G_API_KEY")
    except Exception as e:
        raise Exception("Loading google API key from .env failed. Please check your .env file.") from e
        
    args = parser.parse_args()
    
    watch_terms = [l.strip() for l in open(args.watch_terms, "r").readlines()]
    if len(args.interests) == 0:
        args.interests = watch_terms
    
    # review_month = (date.today().replace(day=1) - timedelta(days=1)).strftime("%B")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days_back)
    date_range = f"{start_date.date()}_{end_date.date()}"
    folder = f"{args.output}/Papers_{date_range}".replace("//", "/")
    os.path.exists(folder) or os.mkdir(folder)
    
    tqdm.write(f"running {date_range} paper review")
    tqdm.write("search terms:\n" + '\n'.join(watch_terms))
    
    if args.from_papers == None:
        # print(",".join(args.fields_of_study))
        total_papers = batch_get_pdf(watch_terms, folder, ",".join(args.fields_of_study), args.days_back, args.search_chunk)
        tqdm.write(f"generating script for {total_papers} papers")
    else:
        tqdm.write(f"skipping paper retrieval, using {args.from_papers} as paper folder. Generating podcast.")
    args.no_podcast and sys.exit(0)
    
    prompt = open(args.script_prompt, "r", encoding="utf8").read()
    prompt = prompt.replace("{DAYS_BACK}", str(args.days_back))
    prompt = prompt.replace("{INTERESTS}", "\n-" + "\n-".join(args.interests))
    podcast_script = script_from_papers(gkey, folder, prompt, args.model, args.max_tokens, args.temperature)
    tqdm.write("script done")
    if args.save_script:
        with open(f"{args.output}/script.json".replace("//", "/"), 'w') as f:
            json.dump(podcast_script, f)
    args.no_audio and sys.exit(0)
    
    tqdm.write("generating podcast audio")
    podcast_audio = script_to_podcast(
        gkey, podcast_script, f"{args.output}/podcast.mp3".replace("//", "/"),
        args.language, args.voice)
    
    tqdm.write("all done! Enjoy :)")
