#!/usr/bin/env python
# encoding: utf-8
import os
import urllib.request
from app import app
import pandas as pd
import numpy as np
import requests
import re
import uuid
import spacy
import pdfplumber
from paddleocr import PaddleOCR,draw_ocr
from flask import Flask, request, redirect, jsonify
from werkzeug.utils import secure_filename
import easyocr

ALLOWED_EXTENSIONS = set(['pdf', 'png', 'jpg', 'jpeg', 'gif'])

def allowed_file(filename):
	return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def recognize_text(img_path):
    reader = easyocr.Reader(['ja'])
    return reader.readtext(img_path, detail = 0, paragraph=True)

def overlay_easyocr_text(img_path):
	info = '' 
	result = recognize_text(img_path)
    # if OCR prob is over 0.5, overlay bounding box and text
	for text in result:
		info = info  + text + ' '
	return info

def overlay_paddleocr_text(img_path):
	# Paddleocr supports Chinese, English, French, German, Korean and Japanese.
	# You can set the parameter `lang` as `ch`, `en`, `french`, `german`, `korean`, `japan`
	# to switch the language model in order.
	ocr = PaddleOCR(use_angle_cls=True, lang='japan', use_gpu=False) # need to run only once to download and load model into memory
	info = ''
	result = ocr.ocr(img_path, cls=True)
	for idx in range(len(result)):
		res = result[idx]
		for line in res:
			info = info  + line[1][0] + ' '

	return info

def overlay_pdf_text(pdf_path):
	with pdfplumber.open(pdf_path) as pdf:
		page = pdf.pages[0]
		info = page.extract_text()
		return info.replace("\n", "")
		 
def record_log(str):
	with open('tmp/data.txt', 'r') as f:
		f.write(str)

def format_string(str):
	old_chars = ['半']
	new_chars = ['￥']

	for old, new in zip(old_chars, new_chars):
		str = str.replace(old, new)

	return str		

def create_folder():
	unique_folder_name = str(uuid.uuid4())
	if not os.path.exists(app.config['UPLOAD_FOLDER'] + '/' + unique_folder_name):
		os.makedirs(app.config['UPLOAD_FOLDER'] + '/' + unique_folder_name)
		return app.config['UPLOAD_FOLDER'] + '/' + unique_folder_name
	else:
		return create_folder()
	

@app.route('/invoices', methods=['POST'])
def invoices():
	param_key = request.args.get('API_KEY')
	if param_key is None or param_key != app.config['API_KEY']:
		resp = jsonify({'message' : 'Unauthorized'})
		resp.status_code = 401
		return resp
	
	# return data
	data = []

    # check if the post request has the file part
	if 'file' not in request.files:
		resp = jsonify({'message' : 'No file part in the request'})
		resp.status_code = 400
		return resp
	files = request.files.getlist("file")
	for file in files:
		if file.filename == '':
			resp = jsonify({'message' : 'No file selected for uploading'})
			resp.status_code = 400
			return resp
		if file is None or not allowed_file(file.filename):
			resp = jsonify({'message' : 'Allowed file types are pdf, png, jpg, jpeg, gif'})
			resp.status_code = 400
			return resp
	#create unique folder name	
	unique_folder_name = create_folder()
	for file in files:	
		filename = secure_filename(file.filename)
		file.save(os.path.join(unique_folder_name, filename))

	# Load the model
	ner_categories = ["MONEY"]
	nlp = spacy.load(app.config['MODEL_BEST'])
	directory_files = os.listdir(unique_folder_name)
	for file in directory_files:
		detected = False
		invoice_file = os.path.join(unique_folder_name, file)
		if file.rsplit('.', 1)[1].lower() == 'pdf':
			info = overlay_pdf_text(invoice_file)
		else:
			info = overlay_paddleocr_text(invoice_file)
		doc = nlp(format_string(info))
		amt_re = re.compile(r'(\d+([,.]?\d)*)')
		with open (app.config['BASE_WORD'],'r') as fid:
			for line in fid:
				for ent in doc.ents:
					if ent.label_ in ner_categories:
						token = ent.text.replace(' ', '')
						word = line.replace("\n", "")
						
						if amt_re.search(token) and (word in token):
							value = amt_re.search(token).group(1)
							i = {'name': file.split('.')[0], 'value': value}
							data.append(i)
							detected = True
							break
					else:
						i = {'name': file.split('.')[0], 'value': 'Not detect'}
						data.append(i)
						#record_log(invoice_file)
				if detected:
					break

		if not detected:
			i = {'name': file.split('.')[0], 'value': 'Not detect'}
			data.append(i)
			#record_log(invoice_file)
	resp = jsonify({'message' : 'Success', 'data': data})
	resp.status_code = 201
	return resp
app.run(debug=False)