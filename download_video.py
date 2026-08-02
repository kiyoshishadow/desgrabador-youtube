from yt_dlp import YoutubeDL
import glob
import os
import re
import tempfile


def seconds_from_time_stamp(timestamp):
    """Convierte un timestamp WebVTT (MM:SS o HH:MM:SS) a segundos."""
    parts = timestamp.strip().split(':')
    if len(parts) == 2:
        minutes, seconds = parts
        hours = 0
    else:
        hours, minutes, seconds = parts
    return int(hours) * 3600 + int(minutes) * 60 + int(float(seconds))


def is_timestamp(line):
    """Identifica una línea de tiempo WebVTT."""
    return bool(re.match(r'^\s*(?:\d{2}:)?\d{2}:\d{2}[.,]\d{3}\s+-->', line))


def has_letters(line):
    return re.search('[a-zA-Z]', line)


def has_no_text(line):
    line = line.strip()
    return not line or line.isdigit() or (line[0] == '(' and line[-1] == ')') or '[' in line or '{' in line or not has_letters(line)


def has_text(line):
    return not has_no_text(line)


def clean_up(lines):
    """Extrae cues de VTT sin asumir una posición fija para el texto."""
    text_with_stamps = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not is_timestamp(line):
            index += 1
            continue

        timestamp = seconds_from_time_stamp(line.split('-->', 1)[0])
        index += 1
        cue_lines = []
        while index < len(lines) and lines[index].strip():
            cleaned = re.sub(r'<[^>]*>', '', lines[index]).strip()
            if cleaned and has_text(cleaned):
                cue_lines.append(cleaned)
            index += 1

        text = ' '.join(cue_lines)
        if text:
            text_with_stamps.append({'text': text, 'timestamp': timestamp})
    return text_with_stamps


def extract_text_from_vtt(directory, title=''):
    subtitles = []
    for filename in glob.glob(os.path.join(directory, '*.vtt')):
        with open(filename, 'r', encoding='utf-8') as vtt_file:
            cues = clean_up(vtt_file.read().splitlines())
        if cues:
            subtitles.append({'text_with_stamps': cues, 'title': title})
    return subtitles


def get_subtitles(url, lang='es'):
    """Descarga únicamente los subtítulos WebVTT del video solicitado."""
    with tempfile.TemporaryDirectory(prefix='youtube-subs-') as directory:
        ydl_opts = {
            'skip_download': True,
            'subtitleslangs': [lang],
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitlesformat': 'vtt',
            'noplaylist': True,
            # curl_cffi (de requirements) permite a yt-dlp impersonar Chrome
            # y evita los HTTP 429 de los endpoints de subtítulos de YouTube.
            'impersonate': 'chrome',
            'outtmpl': os.path.join(directory, '%(title)s [%(id)s].%(ext)s'),
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        title = (info or {}).get('title', '')
        return extract_text_from_vtt(directory, title)
