from yt_dlp import YoutubeDL
from yt_dlp.networking.impersonate import ImpersonateTarget
import base64
import glob
import importlib.util
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request

logger = logging.getLogger(__name__)

_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36',
    'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
}

_po_available = None


def _provider_candidates():
    """Rutas donde puede estar el proveedor de PO Tokens (bgutil).
    En Render se instala en build dentro del repo (bgutil_server);
    en local se puede apuntar con la ruta por defecto de ~/."""
    repo_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(repo_dir, 'bgutil_server'),
        os.path.join(os.path.expanduser('~'), 'bgutil-ytdlp-pot-provider', 'server'),
    ]
    return [p for p in candidates
            if os.path.isfile(os.path.join(p, 'src', 'generate_once.ts'))]


def _find_deno():
    found = shutil.which('deno')
    if found:
        return found
    for candidate in (
        '/opt/render/project/src/.deno/bin/deno',
        os.path.join(os.path.expanduser('~'), '.deno', 'bin', 'deno'),
        os.path.join(os.path.expanduser('~'), '.deno', 'bin', 'deno.exe'),
    ):
        if os.path.isfile(candidate):
            return candidate
    return None


def po_token_available():
    """True si el proveedor de PO Tokens (bgutil + Deno) esta instalado.
    Es lo que permite esquivar el 'Sign in to confirm you're not a bot'
    que YouTube aplica a IPs de datacenter como las de Render."""
    global _po_available
    if _po_available is None:
        _po_available = bool(_find_deno()) and bool(_provider_candidates())
        logger.debug('PO token provider disponible: %s', _po_available)
    return _po_available


def test_po_token(url):
    """Genera un PO Token directamente con el proveedor bgutil (debug).
    Devuelve un dict con el resultado para exponerlo en /diagnostico."""
    video_id = extract_video_id(url)
    providers = _provider_candidates()
    deno = _find_deno()
    if not video_id:
        return {'ok': False, 'motivo': 'url sin video id'}
    if not providers or not deno:
        return {'ok': False, 'motivo': 'proveedor o deno no disponible'}
    provider = providers[0]
    script = os.path.join(provider, 'src', 'generate_once.ts')
    cmd = [
        deno, 'run', '--allow-env', '--allow-net',
        '--allow-ffi', '--allow-write', '--allow-read',
        script, '-c', video_id,
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=90)
        output = (proc.stdout or '') + (proc.stderr or '')
    except Exception as exc:
        return {'ok': False, 'error': str(exc)[:400]}
    if 'poToken' in output:
        return {'ok': True, 'salida': output.strip()[-400:]}
    return {'ok': False, 'salida': output.strip()[-800:]}


def _generate_po_token(video_id):
    """Genera un PO Token via el script de bgutil y devuelve el token.
    Retorna None si falla."""
    providers = _provider_candidates()
    deno = _find_deno()
    if not providers or not deno:
        return None
    provider = providers[0]
    script = os.path.join(provider, 'src', 'generate_once.ts')
    cmd = [
        deno, 'run', '--allow-env', '--allow-net',
        '--allow-ffi', '--allow-write', '--allow-read',
        script, '-c', video_id,
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=90)
        output = (proc.stdout or '') + (proc.stderr or '')
        for line in reversed(output.strip().splitlines()):
            try:
                data = json.loads(line)
                if 'poToken' in data:
                    logger.info('PO Token generado para %s', video_id)
                    return data['poToken']
            except json.JSONDecodeError:
                continue
    except Exception as exc:
        logger.warning('Fallo al generar PO Token: %s', exc)
    return None


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


def get_subtitles_ytdlp(url, lang='es', directory=None, verbose=False):
    """Respaldo: extrae subtitulos con yt-dlp probando varios clientes."""
    ydl_opts = {
        'skip_download': True,
        'subtitleslangs': [lang],
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitlesformat': 'vtt',
        'noplaylist': True,
        'extractor_args': {'youtube': {'player_client': [
            'web', 'web_safari', 'mweb', 'web_embedded',
            'tv', 'android_vr', 'ios',
        ]}},
    }
    if po_token_available():
        video_id = extract_video_id(url)
        if video_id:
            po = _generate_po_token(video_id)
            if po:
                ydl_opts['extractor_args']['youtube']['po_token'] = [
                    f'web.gvs+{po}',
                    f'web.player+{po}',
                    f'web.subs+{po}',
                    f'web_safari.gvs+{po}',
                    f'web_safari.player+{po}',
                    f'web_safari.subs+{po}',
                    f'mweb.gvs+{po}',
                    f'mweb.player+{po}',
                    f'mweb.subs+{po}',
                    f'web_embedded.gvs+{po}',
                    f'web_embedded.player+{po}',
                    f'web_embedded.subs+{po}',
                ]
    if importlib.util.find_spec('curl_cffi') is not None:
        ydl_opts['impersonate'] = ImpersonateTarget(client='chrome')
    if verbose:
        ydl_opts['verbose'] = True
        log_buffer = []
        class _LogCapture(logging.Handler):
            def emit(self, record):
                log_buffer.append(self.format(record))
        cap = _LogCapture()
        cap.setFormatter(logging.Formatter('%(message)s'))
        logging.getLogger('yt_dlp').addHandler(cap)
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
        result = extract_text_from_vtt(directory, title)
        if verbose:
            return result, '\n'.join(log_buffer[-50:])
        return result
    finally:
        if verbose:
            logging.getLogger('yt_dlp').removeHandler(cap)
        if close_directory:
            import shutil
            shutil.rmtree(directory, ignore_errors=True)


def get_subtitles(url, lang='es'):
    """Descarga la transcripcion del video. Orden de intentos:
    1. Si hay cookies (cuenta descartable), yt-dlp con cookies.
    2. Si el proveedor de PO Tokens esta disponible, yt-dlp (lo que
       esquiva el bloqueo de IPs de datacenter como las de Render).
    3. Endpoint de transcripciones (ligero, sin API de player).
    4. yt-dlp sin PO (ultimo recurso)."""
    has_cookies = bool(os.environ.get('YT_COOKIES'))

    if has_cookies:
        try:
            result = get_subtitles_ytdlp(url, lang)
            if result:
                return result
        except Exception as exc:
            logger.warning('yt-dlp con cookies fallo: %s', exc)

    if po_token_available():
        try:
            result = get_subtitles_ytdlp(url, lang)
            if result:
                return result
        except Exception as exc:
            logger.warning('yt-dlp con PO token fallo: %s', exc)

    transcript = get_transcript_api(url, lang)
    if transcript:
        return [transcript]

    if not has_cookies and not po_token_available():
        try:
            result = get_subtitles_ytdlp(url, lang)
            if result:
                return result
        except Exception as exc:
            logger.warning('yt-dlp fallo: %s', exc)

    return []
