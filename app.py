from flask import Flask

UPLOAD_FOLDER = 'invoices'
MODEL_BEST = 'spacy_v2/output/model-best'
BASE_WORD = 'base_word.txt'
API_KEY = '9ZHt2gprBdGYe0kbFL7eb40DEFPEqQ8G'
RANGE = 0.8

app = Flask(__name__)
app.secret_key = "secret key"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['MODEL_BEST'] = MODEL_BEST
app.config['BASE_WORD'] = BASE_WORD
app.config['API_KEY'] = API_KEY
app.config['RANGE'] = RANGE