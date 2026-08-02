# -*- coding: utf-8 -*-
import flask
import os
from flask import Flask, jsonify, request
from flask import abort
from flask import make_response
from flask import render_template
from flask_cors import cross_origin

import download_video

# GLOBALS
app = Flask(__name__)

@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify( { 'error': 'Not found' } ), 404)

@app.route("/")
def index():
    return render_template('index.html')
   
@app.route("/get_subs")
@cross_origin()
def get_subs():
    # Obtener el primero de los subtitlos
    url = request.args.get('url')
    if not url:
        return make_response(jsonify({'error': 'Falta la URL'}), 400)

    try:
        result = download_video.get_subtitles(url)
    except Exception:
        return make_response(jsonify({'error': 'El video no pudo ser procesado'}), 500)

    if not result:
        return make_response(jsonify({'error': 'El video no tiene subtítulos'}), 404)

    response = result[0]
    subtitles = response['text_with_stamps']
    # Pequeña modificación al título para mejor legibilidad
    title = response['title'].replace("_"," ")
    # Genero el json de respuesta
    return jsonify({'subtitles':subtitles,'title':title})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
