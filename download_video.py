from yt_dlp import YoutubeDL
from yt_dlp.networking.impersonate import ImpersonateTarget
import glob
import importlib.util
import json
import os
import re
import tempfile
import urllib.request


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


def fetch_timedtext(url, lang='es'):
    """Fallback: baja los subtítulos directo desde la página del video,
    sin pasar por la API de player que YouTube bloquea en IPs de datacenter."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36',
        'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }

    match = re.search(r'(?:v=|youtu\.be/|shorts/|embed/|live/)([\w-]{11})', url)
    if not match:
        return None
    video_id = match.group(1)

    try:
        req = urllib.request.Request(
            'https://www.youtube.com/watch?v=' + video_id, headers=headers)
        page = urllib.request.urlopen(req, timeout=30).read().decode('utf-8', 'replace')

        player_match = re.search(r'ytInitialPlayerResponse\s*=\s*({.*?});', page, re.DOTALL)
        if not player_match:
            return None
        player = json.loads(player_match.group(1))
    except Exception:
        return None

    tracks = (((player.get('captions') or {}).get('playerCaptionsTracklistRenderer') or {})
              .get('captionTracks') or [])
    if not tracks:
        return None

    track = next((t for t in tracks if t.get('languageCode') == lang), tracks[0])
    base_url = track.get('baseUrl')
    if not base_url:
        return None

    try:
        vtt_url = base_url + ('&' if '?' in base_url else '?') + 'fmt=vtt'
        vtt_req = urllib.request.Request(vtt_url, headers=headers)
        vtt_content = urllib.request.urlopen(vtt_req, timeout=30).read().decode('utf-8', 'replace')
    except Exception:
        return None

    cues = clean_up(vtt_content.splitlines())
    if not cues:
        return None

    title = ((player.get('videoDetails') or {}).get('title') or '').strip()
    return {'text_with_stamps': cues, 'title': title}


def get_subtitles(url, lang='es'):
    """Descarga únicamente los subtítulos WebVTT del video solicitado."""
    ydl_opts = {
        'skip_download': True,
        'subtitleslangs': [lang],
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitlesformat': 'vtt',
        'noplaylist': True,
        # Prueba varios "clientes" de YouTube en orden hasta que uno funcione.
        'extractor_args': {'youtube': {'player_client': [
            'tv', 'web_safari', 'android_vr', 'mweb', 'ios', 'web_embedded',
        ]}},
    }
    # Si curl_cffi esta instalado, imita a Chrome para evitar HTTP 429.
    # Si no esta instalado, funciona igual con la extraccion normal.
    if importlib.util.find_spec('curl_cffi') is not None:
        ydl_opts['impersonate'] = ImpersonateTarget(client='chrome')

    try:
        with tempfile.TemporaryDirectory(prefix='youtube-subs-') as directory:
            ydl_opts['outtmpl'] = os.path.join(directory, '%(title)s [%(id)s].%(ext)s')
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)

            title = (info or {}).get('title', '')
            result = extract_text_from_vtt(directory, title)
            if result:
                return result
    except Exception:
        # Si yt-dlp falla (bloqueo de YouTube, etc.), intentamos el fallback directo.
        pass

    timedtext = fetch_timedtext(url, lang)
    if timedtext:
        return [timedtext]

    return []
