## Bot for Extracting & Highlighting Outstanding Literature, Evaluations & Reviews (BEHOLDER).
A python script to automatically retrieve Computer Science papers with predetermined watch terms using Semantic Scholar API, then generating an AI podcast using google cloud API.
This python package requires the following packages to be importable (yes I should have exported a conda env, maybe later :p):
```
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
from pydub import AudioSegment   # Requires ffmpeg!
from tqdm import tqdm
```

The following needs to be done for installation (outside of installing python packages):
- make a .env file containing a value for G_API_KEY. The value should be a Google Cloud API key that's autorised for the following APIs: Generative Language API, Cloud Text-to-Speech API
- install [FFPMEG](https://www.ffmpeg.org/download.html) if not already done

You can customize your paper search & podcast by doing the following:
- Change watch_terms.txt to your search terms (more search terms = more papers)
- Change script_prompt.txt to your liking. I recommend not editing it too drastically, but you can have fun with it. The {DAYS_BACK} and {INTERESTS} tags will be automatically replaced when running the program. You can place them wherever you want.


#### Paper Searching
Paper searching is done with the Semantic Scholar API based on your watch terms in watch_terms.txt. It is hard coded to be constrained to Computer Science papers (I'll allow it to be changed soon). Papers are retrieved within the last X days (see --days_back) per watch term. For each paper, the following is done:
- if the paper is flagged as having an available pdf, attempt to retrieve the full pdf
- if pdf retrieval fails, attempt to convert the webpage linked to the paper's DOI into a pdf
- if all else fails, attempt to retrieve the paper abstract and add that as a txt file

#### Podcast Generation
The script is generated with Gemini in a JSON format. Each "block" of script can be flanked by sound effects provided in the sound effect folder (code and prompt need to be updated to add new sound effects). Script generation doesn't do good when there are too many papers. I'd recommend limiting your papers so you around 25 at most (and even then it will sort them by interest to avoid generating too long answer). The audio is generated from the JSON format using the google cloud TTS API. Voice can be changed (see the list of [voice](https://cloud.google.com/text-to-speech/docs/voices?hl=fr)). Intro and Outro are automatically detected to overlay bgm.mp3 over the text in between those two sound effects. 

#### Example Podcast
Here's a podcast generated in May 2025 using the default parameters
[mp3](https://drive.google.com/file/d/1S17f52nqJMUGILWfaUJHt5SNwHSMNJdQ/view?usp=sharing)

python Beholder --help:
```
usage: Beholder [-h] [-o OUTPUT] [-i INTERESTS [INTERESTS ...]] [-d DAYS_BACK] [-c SEARCH_CHUNK] [-m MODEL]
                [-t TEMPERATURE] [-s MAX_TOKENS] [-l LANGUAGE] [-v VOICE] [-f FROM_PAPERS] [--save_script]
                [--no_podcast] [--no_audio]

Bot for Extracting & Highlighting Outstanding Literature, Evaluations & Reviews (BEHOLDER).

Requires the following files & directory:
    .env (containing a G_API_KEY variable with a valid google cloud API key for Gemini & TTS)
    watch_terms.txt (a list of terms to search through semantic scholar, one per line)
    script_prompt.txt (the Gemini prompt for script generation)
    sound_effects (a directory containing all available sound effects & bgm)

options:
  -h, --help            show this help message and exit
  -o, --output OUTPUT   folder where papers will be stored and the mp3 will be added
  -i, --interests INTERESTS [INTERESTS ...]
                        areas of interests for the script prompt. Defaults to watch terms
  -d, --days_back DAYS_BACK
                        number of days to look back for papers. Default is 14
  -c, --search_chunk SEARCH_CHUNK
                        paper search limit for each watch term. Higher means more captured results, but can cause issues with Semantic Scholar API. Default is 75
  -m, --model MODEL     gemini model to use. Consider API costs & context windows before changing from default. Default is gemini-1.5-pro
  -t, --temperature TEMPERATURE
                        script generation temperature (higher means more spicy outcomes). Default is 0.7
  -s, --max_tokens MAX_TOKENS
                        maximum token length of generated script (higher means potentially longer scripts, but higher google API cost). Default is 300000
  -l, --language LANGUAGE
                        language of TTS model to use. Need to match the chosen --voice. Default is en-US
  -v, --voice VOICE     voice for podcast. See for a list of available voices (consider API costs per voice engine before making drastic changes). Default is en-US-Chirp3-HD-Algieba
  -f, --from_papers FROM_PAPERS
                        skips paper retrievals, send the given folder of papers to podcast generation
  --save_script         the podcast script's JSON will be saved in the output directory
  --no_podcast          the script will stop after retrieving the papers and will not attempt to generate an audio podcast
  --no_audio            the script will stop after generating the podcast script json. Couple with --save_script to save the script json

Written by Nicolas Jacquin (nicolas.jacquin@umontreal.ca)
```