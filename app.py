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

# Configure logging
logging.basicConfig(level=logging.INFO)

# --- Configure Cloudinary ---
# This uses the environment variables you set on Render
try:
    cloudinary.config(
      cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME'),
      api_key = os.environ.get('CLOUDINARY_API_KEY'),
      api_secret = os.environ.get('CLOUDINARY_API_SECRET')
    )
    app.logger.info("Cloudinary configured successfully.")
except Exception as e:
    app.logger.error(f"FATAL: Cloudinary configuration failed. Check environment variables. Error: {e}")


# Configure database
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

db = SQLAlchemy(app)

# Database model (stores the permanent URL from Cloudinary)
class Upload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False) # Cloudinary public_id
    original_filename = db.Column(db.String(255), nullable=False)
    image_url = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45))

# Create tables at startup
with app.app_context():
    db.create_all()

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- ROUTES ---

@app.route('/')
def index():
    if os.path.exists('index.html'):
        return send_from_directory('.', 'index.html')
    return jsonify({"error": "Frontend not found."}), 404

@app.route('/gallery')
def view_uploads_gallery():
    # (The gallery code remains the same as before)
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
            <div class="bg-white rounded-lg shadow-lg overflow-hidden transform hover:scale-105 transition-transform duration-300"><a href="{upload.image_url}" target="_blank"><img src="{upload.image_url}" alt="{upload.original_filename}" class="w-full h-56 object-cover" onerror="this.onerror=null;this.src='https://placehold.co/600x400/EEE/31343C?text=Image+Not+Found';"></a><div class="p-4"><p class="font-semibold text-gray-800 truncate" title="{upload.original_filename}">{upload.original_filename}</p><p class="text-sm text-gray-500">{upload.uploaded_at.strftime('%b %d, %Y %I:%M %p')}</p><p class="text-sm text-gray-500">{size_display}</p></div></div>
            """
            html += card_html
        html += '</div>'
    html += "</div></body></html>"
    return html

# --- FIX: Re-adding the static image routes ---
@app.route('/hungry.png')
def hungry_image():
    return send_from_directory('.', 'hungry.png')

@app.route('/yumm.png')
def yummy_image():
    return send_from_directory('.', 'yumm.png')

@app.route('/upload', methods=['POST'])
def upload_file_route():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({"error": "Invalid file or file type"}), 400

    try:
        app.logger.info("Attempting to upload to Cloudinary...")
        upload_result = cloudinary.uploader.upload(file)
        app.logger.info("File uploaded to Cloudinary successfully.")

        secure_url = upload_result['secure_url']
        file_size = upload_result.get('bytes', 0)
        original_filename = secure_filename(file.filename)
        public_id = upload_result['public_id']
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()

        new_upload = Upload(
            filename=public_id,
            original_filename=original_filename,
            image_url=secure_url,
            file_size=file_size,
            ip_address=client_ip
        )
        db.session.add(new_upload)
        db.session.commit()
        app.logger.info(f"Database record created for {original_filename}")

        return jsonify({"message": "Upload successful!", "url": secure_url}), 200

    except Exception as e:
        app.logger.error(f"An error occurred during upload: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({"error": "An internal error occurred during upload."}), 500


@app.route('/api')
def api_info():
    return jsonify({"message":"Monster Feed API","endpoints":{"upload":"/upload (POST)","gallery":"/gallery (GET)","health":"/health (GET)"},"version":"2.1.0"})

@app.route('/health')
def health_check():
    db_status = "disconnected"
    try:
        db.session.execute(text('SELECT 1'))
        db_status = "connected"
    except Exception:
        pass
    return jsonify({"status":"healthy", "database": db_status, "upload_count": Upload.query.count()})

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not Found"}), 404

@app.errorhandler(500)
def internal_server_error(e):
    return jsonify({"error": "Internal Server Error"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)

