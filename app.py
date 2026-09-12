import os
from flask import Flask, request, redirect, url_for

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/')
def index():
    files = os.listdir(UPLOAD_FOLDER)
    files_list = "".join([f"<li>{file}</li>" for file in files])
    return f'''
    <h2>ETHBD Style Hosting</h2>
    <form action="/upload" method="post" enctype="multipart/form-data">
        <input type="file" name="file">
        <input type="submit" value="Upload">
    </form>
    <h3>Uploaded Files:</h3>
    <ul>{files_list}</ul>
    '''

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' in request.files:
        file = request.files['file']
        if file.filename != '':
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], file.filename))
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
