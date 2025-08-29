from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import os
from datetime import datetime

app = Flask(__name__)

@app.route('/')
def home():
    return "Monster app running!"

# Configure database (SQLite)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///uploads.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Where to save uploaded files
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Database model
class Upload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(500), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

# Create the database
with app.app_context():
    db.create_all()

# Upload route
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    # Save file
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    # Save record in DB
    new_upload = Upload(filename=file.filename, filepath=filepath)
    db.session.add(new_upload)
    db.session.commit()

    return jsonify({"message": f"{file.filename} uploaded successfully!"}), 200

# API to view uploads (optional, for debugging)
@app.route('/uploads', methods=['GET'])
def get_uploads():
    uploads = Upload.query.all()
    data = [{"id": u.id, "filename": u.filename, "path": u.filepath, "uploaded_at": u.uploaded_at} for u in uploads]
    return jsonify(data)

if __name__ == '__main__':
    app.run(debug=True)
