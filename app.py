from flask import Flask, request, jsonify, send_from_directory, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from sqlalchemy import text
import os
import logging
from datetime import datetime
import uuid
from werkzeug.utils import secure_filename

# Initialize Flask
app = Flask(__name__)

# Enable CORS
CORS(app)

# Configure logging (shows up in Render logs)
logging.basicConfig(level=logging.INFO)

# Configure database
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    # Render sometimes gives "postgres://" instead of "postgresql://"
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL or 'sqlite:///uploads.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

db = SQLAlchemy(app)

# Upload folder
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Allowed extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Database model
class Upload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(500), nullable=False)
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

# NEW: An HTML gallery page to view all uploaded files
@app.route('/gallery')
def view_uploads_gallery():
    """Renders a beautiful gallery of all uploaded images."""
    try:
        uploads = Upload.query.order_by(Upload.uploaded_at.desc()).all()
    except Exception as e:
        app.logger.error(f"Database query failed: {e}")
        return "Error: Could not retrieve images from the database.", 500

    # Start building the HTML string
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Uploaded Files Gallery</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
        <style>
            body { font-family: 'Inter', sans-serif; }
        </style>
    </head>
    <body class="bg-gray-100">
        <div class="container mx-auto px-4 py-8">
            <h1 class="text-4xl font-bold text-center text-gray-800 mb-2">Image Gallery</h1>
            <p class="text-center text-gray-500 mb-8">All the images the monster has been fed.</p>
    """

    if not uploads:
        html += '<p class="text-center text-gray-600 mt-12">No images have been uploaded yet. Go feed the monster!</p>'
    else:
        html += '<div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">'
        for upload in uploads:
            try:
                # Construct the URL for the image
                image_url = url_for('uploaded_file', filename=upload.filename, _external=True)
                # Format file size to be readable
                if upload.file_size:
                    size_kb = upload.file_size / 1024
                    size_display = f"{size_kb:.1f} KB"
                else:
                    size_display = "N/A"

                card_html = f"""
                <div class="bg-white rounded-lg shadow-lg overflow-hidden transform hover:scale-105 transition-transform duration-300 group">
                    <a href="{image_url}" target="_blank">
                        <img src="{image_url}" alt="{upload.original_filename}" class="w-full h-56 object-cover" onerror="this.onerror=null;this.src='https://placehold.co/600x400/EEE/31343C?text=Image+Not+Found';">
                    </a>
                    <div class="p-4">
                        <p class="font-semibold text-gray-800 truncate" title="{upload.original_filename}">{upload.original_filename}</p>
                        <p class="text-sm text-gray-500">{upload.uploaded_at.strftime('%b %d, %Y %I:%M %p')}</p>
                        <p class="text-sm text-gray-500">{size_display}</p>
                    </div>
                </div>
                """
                html += card_html
            except Exception as e:
                app.logger.error(f"Error processing upload ID {upload.id}: {e}")
                continue # Skip this card if there's an error
        html += '</div>'

    html += """
        </div>
    </body>
    </html>
    """
    return html


# Serve static monster images
@app.route('/hungry.png')
def hungry_image():
    return send_from_directory('.', 'hungry.png')

@app.route('/yumm.png')
def yummy_image():
    return send_from_directory('.', 'yumm.png')

# API info
@app.route('/api')
def api_info():
    return jsonify({
        "message": "Monster Feed Backend API",
        "endpoints": {
            "upload": "/upload (POST)",
            "uploads": "/uploads (GET)",
            "files": "/files/<filename> (GET)",
            "gallery": "/gallery (GET)",
            "health": "/health (GET)"
        },
        "version": "1.1.0"
    })

# Serve uploaded files
@app.route('/files/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# Upload endpoint
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type"}), 400

    original_filename = secure_filename(file.filename)
    file_extension = original_filename.rsplit('.', 1)[1].lower()
    unique_filename = f"{uuid.uuid4().hex}.{file_extension}"

    filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
    file.save(filepath)

    file_size = os.path.getsize(filepath)
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()

    new_upload = Upload(
        filename=unique_filename,
        original_filename=original_filename,
        filepath=filepath,
        file_size=file_size,
        ip_address=client_ip
    )
    db.session.add(new_upload)
    db.session.commit()

    return jsonify({
        "message": f"{original_filename} uploaded successfully!",
        "filename": unique_filename,
        "size": file_size,
        "url": f"/files/{unique_filename}"
    }), 200

# Get uploads with pagination
@app.route('/uploads', methods=['GET'])
def get_uploads():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    uploads = Upload.query.order_by(Upload.uploaded_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    data = [{
        "id": u.id,
        "original_filename": u.original_filename,
        "filename": u.filename,
        "size": u.file_size,
        "uploaded_at": u.uploaded_at.isoformat(),
        "url": f"/files/{u.filename}",
        "ip": u.ip_address
    } for u in uploads.items]

    return jsonify({
        "uploads": data,
        "total": uploads.total,
        "pages": uploads.pages,
        "current_page": page,
        "per_page": per_page
    })

# Health check
@app.route('/health')
def health_check():
    try:
        db.session.execute(text('SELECT 1'))
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "database": "connected",
            "upload_count": Upload.query.count()
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }), 500

# Error handlers
@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "File too large. Max size is 16MB."}), 413

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(e):
    app.logger.error(f"Internal error: {str(e)}")
    return jsonify({"error": "Internal server error"}), 500

# Local dev entrypoint
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)

