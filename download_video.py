from yt_dlp import YoutubeDL
import glob
import re
import os
import tempfile

def seconds_from_time_stamp(timestamp):
  # Convierte un timestamp a segundos
  minutes = int(timestamp[3:5])
  seconds = int(timestamp[6:8])
  return minutes*60 + seconds

def is_timestamp(l):
  # Verifica que un string sea un timestamp
  return l[:2].isdigit() and l[2] == ':'

def has_letters(line):
  # Verifica si un string tiene letras
  return re.search('[a-zA-Z]', line)

def has_no_text(line):
  # Verifica si un string no tiene texto
  l = line.strip()
  return not len(l) or l.isdigit() or is_timestamp(l) or (l[0] == '(' and l[-1] == ')') or '[' in l or '{' in l or not has_letters(line)

def has_text(line):
  # Verifica si un string tiene textos
  return not has_no_text(line)

def clean_up(lines):
  # Esta función limpia el contenido del archivo .srt
  text_with_stamps = []
  for i in range(0,len(lines)-2):
    line = lines[i]
    next_line = lines[i+1]
    next_next_line = lines[i+2]
    if is_timestamp(line) and has_text(next_next_line):
      text_with_stamps.append({'text':next_next_line,'timestamp':seconds_from_time_stamp(line)})

  return text_with_stamps

def convertContent(fileContents):
  # Convierte el texto de un archivo vtt 
  replacement = re.sub(r'([\d]+)\.([\d]+)', r'\1,\2', fileContents)
  replacement = re.sub(r'<[^>]*>', '', replacement)
  replacement = re.sub(r'WEBVTT\n\n', '', replacement)
  replacement = re.sub(r'^\d+\n', '', replacement)
  replacement = re.sub(r'\n\d+\n', '\n', replacement)

  return replacement

def extract_text_from_vtt(directory, title=""):
    VTT_FILES = glob.glob(os.path.join(directory, "*.vtt"))
    
    text = []
     # Para cada archivo de subtitulos descargado
    for filename in VTT_FILES:
        with open(filename, 'r', encoding='utf-8') as vtt_file:
            print("Tagging elements in file " + filename)
            # Extraigo texto
            content = convertContent(vtt_file.read())
            lines = content.split("\n")
            # Lo limpio y guardo cada frase con su timestamp
            text_with_stamps = clean_up(lines)
            #Guardo los subtitulos
            text.append({'text_with_stamps':text_with_stamps,'title':title})
            vtt_file.close()
            # Borro el archivo
            os.remove(filename)

    return text

def get_subtitles(url, lang="es"):
    # Cada solicitud usa un directorio temporal propio. En un servidor web pueden
    # llegar varias solicitudes a la vez, por lo que usar el directorio actual
    # haría que un usuario pudiera leer o borrar los subtítulos de otro.
    with tempfile.TemporaryDirectory(prefix='youtube-subs-') as directory:
        ydl_opts = {
            'skip_download': True,
            'subtitleslangs': [lang],
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitlesformat': 'vtt',
            'playliststart': 1,
            'playlistend': 3,
            'outtmpl': os.path.join(directory, '%(title)s [%(id)s].%(ext)s'),
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        title = (info or {}).get('title', '')
        return extract_text_from_vtt(directory, title)



if __name__=="__main__":
    text = get_subtitles('https://www.youtube.com/watch?v=tmG4jwwhHTQ')
    import pdb; pdb.set_trace()
