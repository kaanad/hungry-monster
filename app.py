from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import os
from datetime import datetime
import uuid
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Enable CORS
CORS(app)

# Configure database
DATABASE_URL = os.environ.get('postgresql://usere:shNSbLvCkgbC9YEtD2xBpf1S2JaUoxEA@dpg-d2oue4vfte5s738p9kvg-a.singapore-postgres.render.com/monster_56un')
if DATABASE_URL:
    # For production (Render PostgreSQL)
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
else:
    # For local development (SQLite)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///uploads.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

db = SQLAlchemy(app)

# Create uploads directory
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Database model
class Upload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45))

# Create tables
with app.app_context():
    db.create_all()

# Serve the main HTML page
@app.route('/')
def index():
    try:
        with open('index.html', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return jsonify({"error": "Frontend not found. Make sure index.html is in the project root."}), 404

# Serve monster images
@app.route('/hungry.png')
def hungry_image():
    return send_from_directory('.', 'hungry.png')

@app.route('/yumm.png')
def yummy_image():
    return send_from_directory('.', 'yumm.png')

# API info endpoint
@app.route('/api')
def api_info():
    return jsonify({
        "message": "Monster Feed Backend API",
        "endpoints": {
            "upload": "/upload (POST)",
            "uploads": "/uploads (GET)",
            "files": "/files/<filename> (GET)",
            "health": "/health (GET)"
        },
        "version": "1.0.0"
    })

# Serve uploaded files
@app.route('/files/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# Upload route
@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        # Check if file is in request
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        # Check file type
        if not allowed_file(file.filename):
            return jsonify({"error": "File type not allowed. Please upload an image."}), 400
        
        # Generate unique filename to prevent conflicts
        original_filename = secure_filename(file.filename)
        file_extension = original_filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4().hex}.{file_extension}"
        
        # Save file
        filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
        file.save(filepath)
        
        # Get file size
        file_size = os.path.getsize(filepath)
        
        # Get client IP (Render provides real IP in X-Forwarded-For)
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if client_ip:
            client_ip = client_ip.split(',')[0].strip()
        
        # Save record in database
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
            "message": f"'{original_filename}' uploaded successfully!",
            "filename": unique_filename,
            "size": file_size,
            "url": f"/files/{unique_filename}"
        }), 200
        
    except Exception as e:
        app.logger.error(f"Upload error: {str(e)}")
        return jsonify({"error": f"Upload failed: {str(e)}"}), 500

# API to view uploads (for debugging/admin)
@app.route('/uploads', methods=['GET'])
def get_uploads():
    try:
        # Add pagination for large numbers of uploads
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
        
    except Exception as e:
        app.logger.error(f"Get uploads error: {str(e)}")
        return jsonify({"error": f"Failed to fetch uploads: {str(e)}"}), 500

# Health check endpoint (important for Render)
@app.route('/health')
def health_check():
    try:
        # Test database connection
        db.session.execute('SELECT 1')
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
    return jsonify({"error": "File too large. Maximum size is 16MB."}), 413

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(e):
    app.logger.error(f"Internal error: {str(e)}")
    return jsonify({"error": "Internal server error"}), 500

# For local development
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

