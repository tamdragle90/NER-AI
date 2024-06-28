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
from paddleocr import PaddleOCR
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from gevent.pywsgi import WSGIServer
from flask_cors import CORS, cross_origin
cors = CORS(app)
app.config['CORS_HEADERS'] = 'Content-Type'
amt_re = re.compile(r'(\d+([,.]?\d)*)')
cur_re = re.compile(r'[円￥半]')

ALLOWED_EXTENSIONS = set(['pdf', 'png', 'jpg', 'jpeg', 'gif'])

def allowed_file(filename):
	return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def overlay_paddleocr_text(img_path):
	# Paddleocr supports Chinese, English, French, German, Korean and Japanese.
	# You can set the parameter `lang` as `ch`, `en`, `french`, `german`, `korean`, `japan`
	# to switch the language model in order.
	ocr = PaddleOCR(use_angle_cls=True, lang='japan', use_gpu=False) # need to run only once to download and load model into memory
	info = ''
	result = ocr.ocr(img_path, cls=True)
	m_result = []
	max_size_box = 0
	max_size_value = 0
	for idx in range(len(result)):
		res = result[idx]
		for line in res:
			info = info  + line[1][0] + ' '
			x1, _, x2, _ = line[0]
			m_result.append([x2[1] - x1[1], line[1][0]])
			if (x2[1] - x1[1])  >  max_size_box and amt_re.search(line[1][0]) and cur_re.search(line[1][0]):
				max_size_value = line[1][0]
				max_size_box = x2[1] - x1[1]

	m_result.sort(reverse=True)
	return m_result, max_size_box, max_size_value, info

def overlay_pdf_text(pdf_path):
	info = ''
	m_result = []
	max_size_box = 0
	max_size_value = 0
	with pdfplumber.open(pdf_path) as pdf:
		for page in pdf.pages:
			text_elements = page.extract_words()
			for element in text_elements:
				m_result.append([element['height'], str(element['text'])])
				info = info  + str(element['text']) + ' '
				if element['height']  >  max_size_box and amt_re.search(element['text']) and cur_re.search(element['text']):
					max_size_value = element['text']
					max_size_box = element['height']
	
	m_result.sort(reverse=True)
	return m_result, max_size_box, max_size_value, info

def verify_result(m_result, max_size_box, max_size_value, result):
	print(result)
	print(max_size_value)
	if str(result) in str(max_size_value):
		return result
	else:
		for i in range(len(m_result)):
			if ((str(result) in str(m_result[i][1])) and amt_re.search(m_result[i][1])):
				if (m_result[i][0] / max_size_box > app.config['RANGE']):
					return result
				else: 
					return amt_re.search(max_size_value).group(1)
		return result
		 
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
@cross_origin()
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
	m_result = []
	max_size_box = 0
	max_size_value = 0
	directory_files = os.listdir(unique_folder_name)
	for file in directory_files:
		detected = False
		invoice_file = os.path.join(unique_folder_name, file)
		if file.rsplit('.', 1)[1].lower() == 'pdf':
			m_result, max_size_box, max_size_value, info = overlay_pdf_text(invoice_file)
			if info == '':
				m_result, max_size_box, max_size_value, info = overlay_paddleocr_text(invoice_file)
		else:
			m_result, max_size_box, max_size_value, info = overlay_paddleocr_text(invoice_file)
		doc = nlp(format_string(info))
		
		with open (app.config['BASE_WORD'],'r', encoding="shift_jis") as fid:
			for line in fid:
				for ent in doc.ents:
					if ent.label_ in ner_categories:
						token = ent.text.replace(' ', '')
						word = line.replace("\n", "")
						if amt_re.search(token) and (word in token):
							value = amt_re.search(token).group(1)
							if (max_size_value != 0):
								value = verify_result(m_result, max_size_box, max_size_value, value)
							i = {'name': file.split('.')[0], 'value': value, 'currency': '円'}
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
if __name__ == "__main__":
    app.run()