from flask import Flask, request, jsonify, send_from_directory, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy import text
import os
import logging
from datetime import datetime
import uuid
from werkzeug.utils import secure_filename
import cloudinary
import cloudinary.uploader
from PIL import Image
import io
import time

# Initialize Flask
app = Flask(__name__)

# Enable CORS
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)

# Rate limiting
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# --- Configure Cloudinary ---
try:
    cloudinary.config(
      cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME'),
      api_key = os.environ.get('CLOUDINARY_API_KEY'),
      api_secret = os.environ.get('CLOUDINARY_API_SECRET')
    )
    app.logger.info("Cloudinary configured successfully.")
    
    # Test Cloudinary connection
    try:
        cloudinary.api.ping()
        app.logger.info("Cloudinary connection test successful.")
    except Exception as e:
        app.logger.warning(f"Cloudinary connection test failed: {e}")
        
except Exception as e:
    app.logger.error(f"FATAL: Cloudinary configuration failed. Check environment variables. Error: {e}")

# Configure database
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

db = SQLAlchemy(app)

# Database model
class Upload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    image_url = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer)
    image_width = db.Column(db.Integer)
    image_height = db.Column(db.Integer)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))

# Create tables at startup
with app.app_context():
    try:
        db.create_all()
        app.logger.info("Database tables created successfully.")
    except Exception as e:
        app.logger.error(f"Database initialization failed: {e}")

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'tiff', 'svg'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_type(filename):
    """Get file type from filename"""
    if '.' not in filename:
        return 'unknown'
    return filename.rsplit('.', 1)[1].lower()

def validate_image_file(file_data):
    """Validate and get image information"""
    try:
        image = Image.open(io.BytesIO(file_data))
        width, height = image.size
        
        # Check image dimensions (max 8000x8000 pixels)
        if width > 8000 or height > 8000:
            return None, "Image dimensions too large (max 8000x8000 pixels)"
        
        # Check if image is valid
        image.verify()
        
        return {"width": width, "height": height}, None
    except Exception as e:
        return None, f"Invalid image file: {str(e)}"

def optimize_image(file_data, max_size=(2048, 2048), quality=85):
    """Optimize image before upload"""
    try:
        image = Image.open(io.BytesIO(file_data))
        
        # Convert to RGB if necessary
        if image.mode in ('RGBA', 'LA', 'P'):
            image = image.convert('RGB')
        
        # Resize if too large
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Save optimized image
        output = io.BytesIO()
        image.save(output, format='JPEG', quality=quality, optimize=True)
        output.seek(0)
        
        return output.getvalue()
    except Exception as e:
        app.logger.warning(f"Image optimization failed: {e}")
        return file_data

# --- ROUTES ---

@app.route('/')
def index():
    if os.path.exists('index.html'):
        return send_from_directory('.', 'index.html')
    return jsonify({"error": "Frontend not found."}), 404

@app.route('/gallery')
def view_uploads_gallery():
    try:
        uploads = Upload.query.order_by(Upload.uploaded_at.desc()).limit(100).all()
        
        html = """
        <!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Monster's Gallery</title><script src="https://cdn.tailwindcss.com"></script><link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;700&display=swap" rel="stylesheet"><style>body{font-family:'Poppins',sans-serif;}.image-card{transition:all 0.3s ease;}.image-card:hover{transform:translateY(-5px);box-shadow:0 20px 40px rgba(0,0,0,0.1);}.loading{background:linear-gradient(90deg,#f0f0f0 25%,#e0e0e0 50%,#f0f0f0 75%);background-size:200% 100%;animation:loading 1.5s infinite;}@keyframes loading{0%{background-position:200% 0;}100%{background-position:-200% 0;}}.modal{display:none;position:fixed;z-index:1000;left:0;top:0;width:100%;height:100%;background-color:rgba(0,0,0,0.9);}.modal-content{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);max-width:90%;max-height:90%;}.modal img{max-width:100%;max-height:100%;object-fit:contain;}</style></head><body class="bg-gradient-to-br from-purple-400 to-pink-400 min-h-screen"><div class="container mx-auto px-4 py-8"><div class="text-center mb-8"><h1 class="text-5xl font-bold text-white mb-4">🍽️ Monster's Gallery</h1><p class="text-xl text-white/90 mb-4">All the delicious images our monster has devoured!</p><div class="inline-block bg-white/20 backdrop-blur-lg rounded-full px-6 py-2"><span class="text-white font-semibold">📊 Total Images: {total}</span></div></div>
        """.format(total=len(uploads))
        
        if not uploads:
            html += '''
            <div class="text-center py-20">
                <div class="text-8xl mb-4">😴</div>
                <h2 class="text-3xl font-bold text-white mb-4">Monster is still hungry!</h2>
                <p class="text-xl text-white/80 mb-8">No images have been uploaded yet.</p>
                <a href="/" class="inline-block bg-yellow-500 hover:bg-yellow-600 text-black font-bold px-8 py-4 rounded-full transition-all duration-300 transform hover:scale-105">Feed the Monster!</a>
            </div>
            '''
        else:
            html += '<div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-6 mb-8">'
            
            for upload in uploads:
                size_mb = (upload.file_size / (1024 * 1024)) if upload.file_size else 0
                size_display = f"{size_mb:.1f} MB" if size_mb >= 1 else f"{(upload.file_size / 1024):.1f} KB" if upload.file_size else "Unknown"
                
                dimensions = ""
                if upload.image_width and upload.image_height:
                    dimensions = f"{upload.image_width}×{upload.image_height}"
                
                card_html = f'''
                <div class="image-card bg-white/10 backdrop-blur-lg rounded-xl overflow-hidden shadow-lg">
                    <div class="aspect-square bg-gray-200 loading relative overflow-hidden cursor-pointer" onclick="openModal('{upload.image_url}', '{upload.original_filename}')">
                        <img src="{upload.image_url}" alt="{upload.original_filename}" 
                             class="w-full h-full object-cover transition-opacity duration-300" 
                             onload="this.parentElement.classList.remove('loading')"
                             onerror="this.onerror=null;this.src='data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgZmlsbD0iI2VlZSIvPjx0ZXh0IHg9IjEwMCIgeT0iMTAwIiBmb250LWZhbWlseT0ic2Fucy1zZXJpZiIgZm9udC1zaXplPSIxNCIgZmlsbD0iIzk5OSIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZHk9Ii4zZW0iPkltYWdlIE5vdCBGb3VuZDwvdGV4dD48L3N2Zz4=';this.parentElement.classList.remove('loading')">
                    </div>
                    <div class="p-4">
                        <p class="font-semibold text-white truncate text-sm" title="{upload.original_filename}">{upload.original_filename}</p>
                        <div class="text-xs text-white/70 mt-2 space-y-1">
                            <p>📅 {upload.uploaded_at.strftime('%b %d, %Y')}</p>
                            <p>📏 {dimensions}</p>
                            <p>💾 {size_display}</p>
                        </div>
                    </div>
                </div>
                '''
                html += card_html
                
            html += '</div>'
            
            # Back to home button
            html += '''
            <div class="text-center">
                <a href="/" class="inline-block bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white font-bold px-8 py-4 rounded-full transition-all duration-300 transform hover:scale-105 shadow-lg">
                    🍽️ Feed Monster More!
                </a>
            </div>
            '''
        
        # Modal for full-size images
        html += '''
        <div id="imageModal" class="modal" onclick="closeModal()">
            <div class="modal-content">
                <img id="modalImage" src="" alt="">
            </div>
        </div>
        
        <script>
        function openModal(src, alt) {
            document.getElementById('modalImage').src = src;
            document.getElementById('modalImage').alt = alt;
            document.getElementById('imageModal').style.display = 'block';
        }
        
        function closeModal() {
            document.getElementById('imageModal').style.display = 'none';
        }
        
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') closeModal();
        });
        </script>
        
        </div></body></html>
        '''
        
        return html
    except Exception as e:
        app.logger.error(f"Gallery error: {e}")
        return jsonify({"error": "Failed to load gallery"}), 500

# Static image routes
@app.route('/hungry.png')
def hungry_image():
    return send_from_directory('.', 'hungry.png')

@app.route('/yumm.png')
def yummy_image():
    return send_from_directory('.', 'yumm.png')

@app.route('/upload', methods=['POST'])
@limiter.limit("10 per minute")
def upload_file_route():
    start_time = time.time()
    
    # Enhanced validation
    if 'file' not in request.files:
        return jsonify({"error": "No file provided", "code": "NO_FILE"}), 400
        
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({"error": "No file selected", "code": "EMPTY_FILENAME"}), 400
    
    if not allowed_file(file.filename):
        supported_types = ", ".join(['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'tiff', 'svg'])
        return jsonify({
            "error": f"File type not supported. Supported types: {supported_types}", 
            "code": "UNSUPPORTED_TYPE"
        }), 400

    # Read file data
    try:
        file.seek(0)  # Reset file pointer
        file_data = file.read()
        file_size = len(file_data)
        
        # Check file size (16MB limit)
        if file_size > 16 * 1024 * 1024:
            return jsonify({
                "error": "File too large. Maximum size is 16MB", 
                "code": "FILE_TOO_LARGE"
            }), 400
            
        if file_size < 100:  # Minimum 100 bytes
            return jsonify({
                "error": "File too small. Minimum size is 100 bytes", 
                "code": "FILE_TOO_SMALL"
            }), 400
            
    except Exception as e:
        app.logger.error(f"File reading error: {e}")
        return jsonify({
            "error": "Failed to read file", 
            "code": "READ_ERROR"
        }), 400

    # Validate image
    image_info, validation_error = validate_image_file(file_data)
    if validation_error:
        return jsonify({
            "error": validation_error, 
            "code": "INVALID_IMAGE"
        }), 400

    try:
        app.logger.info(f"Processing upload: {file.filename} ({file_size} bytes)")
        
        # Optimize image if it's large
        if file_size > 1024 * 1024:  # 1MB threshold
            app.logger.info("Optimizing large image...")
            file_data = optimize_image(file_data)
            
        # Upload to Cloudinary with transformation
        upload_result = cloudinary.uploader.upload(
            file_data,
            transformation=[
                {"quality": "auto:good"},
                {"fetch_format": "auto"}
            ],
            resource_type="auto"
        )
        
        app.logger.info("File uploaded to Cloudinary successfully.")

        # Extract metadata
        secure_url = upload_result['secure_url']
        cloudinary_file_size = upload_result.get('bytes', file_size)
        original_filename = secure_filename(file.filename)
        public_id = upload_result['public_id']
        
        # Get client information
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
        user_agent = request.headers.get('User-Agent', '')[:500]  # Limit length
        
        # Create database record
        new_upload = Upload(
            filename=public_id,
            original_filename=original_filename,
            image_url=secure_url,
            file_size=cloudinary_file_size,
            image_width=image_info.get('width'),
            image_height=image_info.get('height'),
            ip_address=client_ip,
            user_agent=user_agent
        )
        
        db.session.add(new_upload)
        db.session.commit()
        
        processing_time = round((time.time() - start_time) * 1000, 2)  # in milliseconds
        app.logger.info(f"Upload completed in {processing_time}ms for {original_filename}")

        return jsonify({
            "message": "Monster enjoyed your image! Upload successful!",
            "url": secure_url,
            "file_size": cloudinary_file_size,
            "dimensions": f"{image_info.get('width')}x{image_info.get('height')}",
            "processing_time": f"{processing_time}ms",
            "code": "SUCCESS"
        }), 200

    except cloudinary.exceptions.Error as e:
        app.logger.error(f"Cloudinary error: {e}")
        db.session.rollback()
        return jsonify({
            "error": "Image processing failed. Please try a different image.",
            "code": "CLOUDINARY_ERROR"
        }), 500
        
    except Exception as e:
        app.logger.error(f"Upload error: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({
            "error": "An unexpected error occurred during upload.",
            "code": "INTERNAL_ERROR"
        }), 500

@app.route('/api')
def api_info():
    return jsonify({
        "message": "Monster Feed API v2.2.0",
        "endpoints": {
            "upload": "/upload (POST) - Feed the monster with images",
            "gallery": "/gallery (GET) - View monster's feast",
            "health": "/health (GET) - Check system health",
            "stats": "/stats (GET) - View upload statistics"
        },
        "limits": {
            "max_file_size": "16MB",
            "supported_formats": ["png", "jpg", "jpeg", "gif", "bmp", "webp", "tiff", "svg"],
            "rate_limit": "10 uploads per minute, 50 per hour, 200 per day"
        },
        "version": "2.2.0",
        "monster_status": "hungry" if Upload.query.count() == 0 else "satisfied"
    })

@app.route('/stats')
def stats():
    try:
        total_uploads = Upload.query.count()
        total_size = db.session.query(db.func.sum(Upload.file_size)).scalar() or 0
        recent_uploads = Upload.query.filter(Upload.uploaded_at >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)).count()
        
        # File type statistics
        file_types = db.session.query(
            db.func.substring(Upload.original_filename, db.func.length(Upload.original_filename) - db.func.position('.' in db.func.reverse(Upload.original_filename)) + 2),
            db.func.count()
        ).group_by(
            db.func.substring(Upload.original_filename, db.func.length(Upload.original_filename) - db.func.position('.' in db.func.reverse(Upload.original_filename)) + 2)
        ).all()
        
        return jsonify({
            "total_uploads": total_uploads,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "uploads_today": recent_uploads,
            "file_types": dict(file_types) if file_types else {},
            "monster_satisfaction": "very happy" if total_uploads > 100 else "happy" if total_uploads > 10 else "getting satisfied" if total_uploads > 0 else "hungry"
        })
    except Exception as e:
        app.logger.error(f"Stats error: {e}")
        return jsonify({"error": "Failed to load statistics"}), 500

@app.route('/health')
def health_check():
    db_status = "disconnected"
    cloudinary_status = "disconnected"
    
    try:
        db.session.execute(text('SELECT 1'))
        db_status = "connected"
    except Exception as e:
        app.logger.warning(f"Database health check failed: {e}")
    
    try:
        cloudinary.api.ping()
        cloudinary_status = "connected"
    except Exception as e:
        app.logger.warning(f"Cloudinary health check failed: {e}")
    
    upload_count = 0
    try:
        upload_count = Upload.query.count()
    except:
        pass
    
    health_status = "healthy" if db_status == "connected" and cloudinary_status == "connected" else "degraded"
    
    return jsonify({
        "status": health_status,
        "database": db_status,
        "cloudinary": cloudinary_status,
        "upload_count": upload_count,
        "version": "2.2.0",
        "timestamp": datetime.utcnow().isoformat()
    })

# Error handlers
@app.errorhandler(404)
def not_found(e):
    return jsonify({
        "error": "Page not found", 
        "code": "NOT_FOUND",
        "available_endpoints": ["/", "/upload", "/gallery", "/health", "/stats", "/api"]
    }), 404

@app.errorhandler(413)
def file_too_large(e):
    return jsonify({
        "error": "File too large. Maximum size is 16MB",
        "code": "FILE_TOO_LARGE"
    }), 413

@app.errorhandler(429)
def rate_limit_exceeded(e):
    return jsonify({
        "error": "Too many uploads. Please wait before trying again.",
        "code": "RATE_LIMIT_EXCEEDED",
        "retry_after": "60 seconds"
    }), 429

@app.errorhandler(500)
def internal_server_error(e):
    app.logger.error(f"Internal server error: {e}")
    return jsonify({
        "error": "Internal server error. Please try again later.",
        "code": "INTERNAL_ERROR"
    }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
