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
        'po_token_provider': download_video.po_token_available(),
        'deno': download_video._find_deno(),
        'provider_scripts': download_video._provider_candidates(),
        'cookies_configuradas': bool(os.environ.get('YT_COOKIES')),
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
        try:
            result = download_video.get_subtitles(url)
            info['subtitles_ok'] = bool(result)
            info['subtitles_frases'] = len(result[0]['text_with_stamps']) if result else 0
        except Exception as exc:
            info['subtitles_error'] = type(exc).__name__ + ': ' + str(exc)[:300]
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