# -*- coding: utf-8 -*-
import os
import sys
from flask import Flask, jsonify, make_response, render_template, request
from flask_cors import cross_origin

import download_video

app = Flask(__name__)


@app.route('/diagnostico')
def diagnostico():
    info = {
        'commit': os.environ.get('RENDER_GIT_COMMIT', 'local'),
        'python': sys.version.split()[0],
        'youtube_transcript_api': False,
        'curl_cffi': False,
        'yt_dlp': False,
    }
    try:
        import youtube_transcript_api
        info['youtube_transcript_api'] = True
    except ImportError:
        pass
    try:
        import curl_cffi
        info['curl_cffi'] = True
    except ImportError:
        pass
    try:
        import yt_dlp
        info['yt_dlp'] = True
    except ImportError:
        pass

    url = request.args.get('url')
    if url:
        transcript = download_video.get_transcript_api(url)
        info['transcript_api_ok'] = bool(transcript)
        info['transcript_frases'] = len(transcript['text_with_stamps']) if transcript else 0
        if not transcript:
            try:
                download_video.get_subtitles_ytdlp(url)
                info['ytdlp_ok'] = True
            except Exception as exc:
                info['ytdlp_error'] = type(exc).__name__ + ': ' + str(exc)[:200]
    return jsonify(info)


@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/get_subs')
@cross_origin()
def get_subs():
    url = request.args.get('url')
    if not url:
        return make_response(jsonify({'error': 'Falta la URL'}), 400)

    try:
        result = download_video.get_subtitles(url)
    except Exception:
        app.logger.exception('No se pudieron extraer subtítulos para la URL solicitada')
        return make_response(jsonify({'error': 'El video no pudo ser procesado'}), 500)

    if not result:
        return make_response(jsonify({'error': 'El video no tiene subtítulos'}), 404)

    response = result[0]
    return jsonify({
        'subtitles': response['text_with_stamps'],
        'title': response['title'].replace('_', ' '),
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)