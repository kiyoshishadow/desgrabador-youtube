from yt_dlp import YoutubeDL
from yt_dlp.networking.impersonate import ImpersonateTarget
import base64
import glob
import importlib.util
import json
import logging
import os
import re
import tempfile
import urllib.request

logger = logging.getLogger(__name__)

_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36',
    'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
}


def extract_video_id(url):
    match = re.search(r'(?:v=|youtu\.be/|shorts/|embed/|live/)([\w-]{11})', url)
    return match.group(1) if match else None


def fetch_page(video_id):
    req = urllib.request.Request(
        'https://www.youtube.com/watch?v=' + video_id, headers=_HEADERS)
    return urllib.request.urlopen(req, timeout=30).read().decode('utf-8', 'replace')


def fetch_title(url):
    """Obtiene el titulo del video desde la pagina, sin pasar por la API de player."""
    video_id = extract_video_id(url)
    if not video_id:
        return ''
    try:
        page = fetch_page(video_id)
        match = re.search(r'<title>([^<]*)</title>', page)
        if match:
            title = re.sub(r'\s*[-|]\s*YouTube.*$', '', match.group(1)).strip()
            if title:
                return title
        player_match = re.search(r'ytInitialPlayerResponse\s*=\s*({.*?});', page, re.DOTALL)
        if player_match:
            title = ((json.loads(player_match.group(1)).get('videoDetails') or {}).get('title') or '').strip()
            if title:
                return title
    except Exception:
        pass
    return ''


def get_transcript_api(url, lang='es'):
    """Metodo principal: usa el endpoint de transcripciones de YouTube.
    Es liviano y no pasa por la API de player, que es la que YouTube
    bloquea en IPs de datacenter como las de Render."""
    video_id = extract_video_id(url)
    if not video_id:
        return None
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        transcript = YouTubeTranscriptApi().fetch(video_id, [lang])
        cues = [{'text': s.text, 'timestamp': int(s.start)} for s in transcript.snippets]
        if not cues:
            return None
        return {'text_with_stamps': cues, 'title': fetch_title(url)}
    except Exception as exc:
        logger.warning('youtube-transcript-api fallo: %s', exc)
        return None


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


def _write_cookies_file(directory):
    """Si la variable de entorno YT_COOKIES trae un cookies.txt en base64,
    lo guarda en disco y devuelve la ruta. Nunca se expone a los clientes."""
    encoded = os.environ.get('YT_COOKIES') or ''
    if not encoded:
        return None
    try:
        content = base64.b64decode(encoded).decode('utf-8')
    except Exception:
        logger.warning('YT_COOKIES no es base64 valido')
        return None
    path = os.path.join(directory, 'cookies.txt')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return path


def get_subtitles_ytdlp(url, lang='es', directory=None):
    """Respaldo: extrae subtitulos con yt-dlp probando varios clientes."""
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

    close_directory = directory is None
    if directory is None:
        directory = tempfile.mkdtemp(prefix='youtube-subs-')

    cookies = _write_cookies_file(directory)
    if cookies:
        ydl_opts['cookiefile'] = cookies

    try:
        ydl_opts['outtmpl'] = os.path.join(directory, '%(title)s [%(id)s].%(ext)s')
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        title = (info or {}).get('title', '')
        return extract_text_from_vtt(directory, title)
    finally:
        if close_directory:
            import shutil
            shutil.rmtree(directory, ignore_errors=True)


def get_subtitles(url, lang='es'):
    """Descarga la transcripcion del video. Si hay cookies configuradas
    (cuenta descartable), las usa primero; si no, prueba el endpoint de
    transcripciones y cae en yt-dlp."""
    has_cookies = bool(os.environ.get('YT_COOKIES'))

    if has_cookies:
        try:
            result = get_subtitles_ytdlp(url, lang)
            if result:
                return result
        except Exception as exc:
            logger.warning('yt-dlp con cookies fallo: %s', exc)

    transcript = get_transcript_api(url, lang)
    if transcript:
        return [transcript]

    if not has_cookies:
        try:
            result = get_subtitles_ytdlp(url, lang)
            if result:
                return result
        except Exception as exc:
            logger.warning('yt-dlp fallo: %s', exc)

    return []
