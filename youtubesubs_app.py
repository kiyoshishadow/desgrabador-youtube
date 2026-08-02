# -*- coding: utf-8 -*-
import os
from flask import Flask, jsonify, make_response, render_template, request
from flask_cors import cross_origin

import download_video

app = Flask(__name__)


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