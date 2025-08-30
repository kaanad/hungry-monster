from flask import Flask, request, jsonify, send_from_directory, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from sqlalchemy import text
import os
import logging
from datetime import datetime
import uuid
from werkzeug.utils import secure_filename
import cloudinary
import cloudinary.uploader

# Initialize Flask
app = Flask(__name__)

# Enable CORS
CORS(app)

# --- NEW: Configure Cloudinary ---
# This uses the environment variables you set on Render
cloudinary.config(
  cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME'),
  api_key = os.environ.get('CLOUDINARY_API_KEY'),
  api_secret = os.environ.get('CLOUDINARY_API_SECRET')
)
app.logger.info("Cloudinary configured.")

# Configure logging (shows up in Render logs)
logging.basicConfig(level=logging.INFO)

# Configure database
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL or 'sqlite:///uploads.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

db = SQLAlchemy(app)

# The 'uploads' folder is no longer used for permanent storage
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Allowed extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- EDITED: Database model ---
# We no longer store the local filepath. We store the permanent URL from Cloudinary.
class Upload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    image_url = db.Column(db.String(500), nullable=False) # Changed from 'filepath'
    file_size = db.Column(db.Integer)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45))

# Create tables at startup
with app.app_context():
    db.create_all()

# Serve index.html
@app.route('/')
def index():
    if os.path.exists('index.html'):
        return send_from_directory('.', 'index.html')
    return jsonify({"error": "Frontend not found. Ensure index.html is in the project root."}), 404

# --- EDITED: Gallery page now uses the image_url from the database ---
@app.route('/gallery')
def view_uploads_gallery():
    uploads = Upload.query.order_by(Upload.uploaded_at.desc()).all()
    html = """
    <!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Uploaded Files Gallery</title><script src="https://cdn.tailwindcss.com"></script><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap" rel="stylesheet"><style>body{font-family:'Inter',sans-serif;}</style></head><body class="bg-gray-100"><div class="container mx-auto px-4 py-8"><h1 class="text-4xl font-bold text-center text-gray-800 mb-2">Image Gallery</h1><p class="text-center text-gray-500 mb-8">All the images the monster has been fed.</p>
    """
    if not uploads:
        html += '<p class="text-center text-gray-600 mt-12">No images have been uploaded yet!</p>'
    else:
        html += '<div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">'
        for upload in uploads:
            size_kb = (upload.file_size / 1024) if upload.file_size else 0
            size_display = f"{size_kb:.1f} KB"
            card_html = f"""
            <div class="bg-white rounded-lg shadow-lg overflow-hidden transform hover:scale-105 transition-transform duration-300"><a href="{upload.image_url}" target="_blank"><img src="{upload.image_url}" alt="{upload.original_filename}" class="w-full h-56 object-cover"></a><div class="p-4"><p class="font-semibold text-gray-800 truncate" title="{upload.original_filename}">{upload.original_filename}</p><p class="text-sm text-gray-500">{upload.uploaded_at.strftime('%b %d, %Y %I:%M %p')}</p><p class="text-sm text-gray-500">{size_display}</p></div></div>
            """
            html += card_html
        html += '</div>'
    html += "</div></body></html>"
    return html

# --- EDITED: Upload endpoint now sends files to Cloudinary ---
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type"}), 400

    try:
        # This is the main change: upload to Cloudinary instead of saving locally
        upload_result = cloudinary.uploader.upload(file)
        app.logger.info("File uploaded to Cloudinary successfully.")
        
        # The permanent URL is in the result
        secure_url = upload_result['secure_url']
        file_size = upload_result['bytes']
        original_filename = secure_filename(file.filename)
        unique_filename = upload_result['public_id'] # Cloudinary's unique ID
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()

        # Save the Cloudinary URL to our database
        new_upload = Upload(
            filename=unique_filename,
            original_filename=original_filename,
            image_url=secure_url,
            file_size=file_size,
            ip_address=client_ip
        )
        db.session.add(new_upload)
        db.session.commit()

        return jsonify({
            "message": f"{original_filename} uploaded successfully!",
            "url": secure_url
        }), 200

    except Exception as e:
        app.logger.error(f"Upload failed: {e}")
        return jsonify({"error": "File upload failed"}), 500

# Other routes (health, api info, etc.) remain largely the same...
# [The rest of the file is omitted for brevity, but should be the same as your previous version]
@app.route('/api')
def api_info(): return jsonify({"message":"Monster Feed API","endpoints":{"upload":"/upload (POST)","gallery":"/gallery (GET)","health":"/health (GET)"},"version":"2.0.0"})
@app.route('/health')
def health_check():
    try:
        db.session.execute(text('SELECT 1'))
        return jsonify({"status":"healthy","database":"connected","upload_count":Upload.query.count()})
    except Exception as e: return jsonify({"status":"unhealthy","error":str(e)}),500
@app.errorhandler(404)
def not_found(e): return jsonify({"error": "Endpoint not found"}), 404
if __name__ == '__main__': app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)))


