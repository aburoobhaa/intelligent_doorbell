"""
IoT-Based Smart Doorbell System - Main Backend Application
Flask-based backend server for handling doorbell events, motion detection,
and photo capture with real-time notifications.
"""

from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import os
import json
import logging
from datetime import datetime, timedelta
import threading
import time

# Import custom modules
from motion_detector import MotionDetector
from camera_controller import CameraController
from notification_service import NotificationService
from auth_service import AuthService
from database.models import db, User, MotionEvent, DoorbellEvent, Photo

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this'
app.config['JWT_SECRET_KEY'] = 'jwt-secret-string-change-this'
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///smart_doorbell.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = './photos'

# Initialize extensions
CORS(app)
jwt = JWTManager(app)
db.init_app(app)

# Initialize services
motion_detector = MotionDetector()
camera_controller = CameraController(app.config['UPLOAD_FOLDER'])
notification_service = NotificationService()
auth_service = AuthService()

# Global system state
system_state = {
    'home_mode': True,
    'system_active': True,
    'motion_sensitivity': 7,
    'connected_devices': [],
    'last_activity': datetime.now()
}

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('./logs/system.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@app.before_first_request
def create_tables():
    """Create database tables and ensure upload directory exists"""
    db.create_all()
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs('./logs', exist_ok=True)
    logger.info("Smart Doorbell System initialized")

# Authentication Routes
@app.route('/api/auth/register', methods=['POST'])
def register():
    """Register a new user"""
    try:
        data = request.get_json()
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        
        if User.query.filter_by(username=username).first():
            return jsonify({'message': 'Username already exists'}), 400
        
        if User.query.filter_by(email=email).first():
            return jsonify({'message': 'Email already registered'}), 400
        
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        access_token = create_access_token(identity=user.id)
        
        logger.info(f"New user registered: {username}")
        return jsonify({
            'message': 'User registered successfully',
            'access_token': access_token
        }), 201
        
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return jsonify({'error': 'Registration failed'}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    """User login"""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            access_token = create_access_token(identity=user.id)
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            logger.info(f"User logged in: {username}")
            return jsonify({
                'message': 'Login successful',
                'access_token': access_token,
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email
                }
            }), 200
        else:
            return jsonify({'message': 'Invalid credentials'}), 401
            
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({'error': 'Login failed'}), 500

# Motion Detection Routes
@app.route('/api/motion/detected', methods=['POST'])
def motion_detected():
    """Handle motion detection from Arduino"""
    try:
        data = request.get_json()
        timestamp = datetime.now()
        
        # Log motion event
        motion_event = MotionEvent(
            timestamp=timestamp,
            sensor_id=data.get('sensor_id', 'PIR_001'),
            location=data.get('location', 'front_door'),
            home_mode=system_state['home_mode']
        )
        db.session.add(motion_event)
        db.session.commit()
        
        # Send notification if not in home mode
        if not system_state['home_mode']:
            notification_service.send_motion_alert(data)
        
        # Analyze motion pattern
        motion_analysis = motion_detector.analyze_motion(data)
        
        logger.info(f"Motion detected: {data}")
        
        return jsonify({
            'status': 'success',
            'message': 'Motion event recorded',
            'analysis': motion_analysis,
            'home_mode': system_state['home_mode']
        }), 200
        
    except Exception as e:
        logger.error(f"Motion detection error: {str(e)}")
        return jsonify({'error': 'Failed to process motion event'}), 500

@app.route('/api/motion/history', methods=['GET'])
@jwt_required()
def get_motion_history():
    """Get motion detection history"""
    try:
        # Get query parameters
        hours = request.args.get('hours', 24, type=int)
        limit = request.args.get('limit', 100, type=int)
        
        # Calculate time range
        start_time = datetime.now() - timedelta(hours=hours)
        
        # Query motion events
        events = MotionEvent.query.filter(
            MotionEvent.timestamp >= start_time
        ).order_by(MotionEvent.timestamp.desc()).limit(limit).all()
        
        # Format response
        motion_history = []
        for event in events:
            motion_history.append({
                'id': event.id,
                'timestamp': event.timestamp.isoformat(),
                'sensor_id': event.sensor_id,
                'location': event.location,
                'home_mode': event.home_mode
            })
        
        return jsonify({
            'motion_events': motion_history,
            'total_count': len(motion_history)
        }), 200
        
    except Exception as e:
        logger.error(f"Motion history error: {str(e)}")
        return jsonify({'error': 'Failed to retrieve motion history'}), 500

# Doorbell Routes
@app.route('/api/doorbell/pressed', methods=['POST'])
def doorbell_pressed():
    """Handle doorbell button press"""
    try:
        data = request.get_json()
        timestamp = datetime.now()
        
        # Capture photo immediately
        photo_filename = camera_controller.capture_photo(
            trigger_source='doorbell'
        )
        
        # Log doorbell event
        doorbell_event = DoorbellEvent(
            timestamp=timestamp,
            button_id=data.get('button_id', 'DOORBELL_001'),
            location=data.get('location', 'front_door'),
            home_mode=system_state['home_mode'],
            photo_captured=photo_filename is not None
        )
        db.session.add(doorbell_event)
        
        # Save photo record
        if photo_filename:
            photo = Photo(
                filename=photo_filename,
                timestamp=timestamp,
                trigger_source='doorbell',
                location=data.get('location', 'front_door'),
                event_id=doorbell_event.id
            )
            db.session.add(photo)
        
        db.session.commit()
        
        # Send notification
        notification_data = {
            'type': 'doorbell',
            'timestamp': timestamp.isoformat(),
            'location': data.get('location', 'front_door'),
            'photo_filename': photo_filename,
            'home_mode': system_state['home_mode']
        }
        notification_service.send_doorbell_alert(notification_data)
        
        logger.info(f"Doorbell pressed: {data}, Photo: {photo_filename}")
        
        return jsonify({
            'status': 'success',
            'message': 'Doorbell event recorded',
            'photo_captured': photo_filename is not None,
            'photo_filename': photo_filename,
            'home_mode': system_state['home_mode']
        }), 200
        
    except Exception as e:
        logger.error(f"Doorbell event error: {str(e)}")
        return jsonify({'error': 'Failed to process doorbell event'}), 500

@app.route('/api/doorbell/history', methods=['GET'])
@jwt_required()
def get_doorbell_history():
    """Get doorbell press history"""
    try:
        hours = request.args.get('hours', 24, type=int)
        limit = request.args.get('limit', 50, type=int)
        
        start_time = datetime.now() - timedelta(hours=hours)
        
        events = DoorbellEvent.query.filter(
            DoorbellEvent.timestamp >= start_time
        ).order_by(DoorbellEvent.timestamp.desc()).limit(limit).all()
        
        doorbell_history = []
        for event in events:
            # Get associated photo
            photo = Photo.query.filter_by(event_id=event.id).first()
            
            doorbell_history.append({
                'id': event.id,
                'timestamp': event.timestamp.isoformat(),
                'button_id': event.button_id,
                'location': event.location,
                'home_mode': event.home_mode,
                'photo_captured': event.photo_captured,
                'photo_filename': photo.filename if photo else None
            })
        
        return jsonify({
            'doorbell_events': doorbell_history,
            'total_count': len(doorbell_history)
        }), 200
        
    except Exception as e:
        logger.error(f"Doorbell history error: {str(e)}")
        return jsonify({'error': 'Failed to retrieve doorbell history'}), 500

# Camera Routes
@app.route('/api/camera/capture', methods=['POST'])
def capture_photo():
    """Manual photo capture"""
    try:
        data = request.get_json()
        
        photo_filename = camera_controller.capture_photo(
            trigger_source=data.get('trigger_source', 'manual')
        )
        
        if photo_filename:
            # Save photo record
            photo = Photo(
                filename=photo_filename,
                timestamp=datetime.now(),
                trigger_source=data.get('trigger_source', 'manual'),
                location=data.get('location', 'front_door')
            )
            db.session.add(photo)
            db.session.commit()
            
            logger.info(f"Photo captured: {photo_filename}")
            
            return jsonify({
                'status': 'success',
                'message': 'Photo captured successfully',
                'filename': photo_filename
            }), 200
        else:
            return jsonify({'error': 'Failed to capture photo'}), 500
            
    except Exception as e:
        logger.error(f"Photo capture error: {str(e)}")
        return jsonify({'error': 'Camera capture failed'}), 500

@app.route('/api/photos/<filename>')
@jwt_required()
def get_photo(filename):
    """Retrieve a specific photo"""
    try:
        photo_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        if os.path.exists(photo_path):
            return send_file(photo_path, as_attachment=False)
        else:
            return jsonify({'error': 'Photo not found'}), 404
            
    except Exception as e:
        logger.error(f"Photo retrieval error: {str(e)}")
        return jsonify({'error': 'Failed to retrieve photo'}), 500

@app.route('/api/photos/list', methods=['GET'])
@jwt_required()
def list_photos():
    """List all photos with pagination"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        photos = Photo.query.order_by(
            Photo.timestamp.desc()
        ).paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        photo_list = []
        for photo in photos.items:
            photo_list.append({
                'id': photo.id,
                'filename': photo.filename,
                'timestamp': photo.timestamp.isoformat(),
                'trigger_source': photo.trigger_source,
                'location': photo.location,
                'event_id': photo.event_id
            })
        
        return jsonify({
            'photos': photo_list,
            'total': photos.total,
            'pages': photos.pages,
            'current_page': page
        }), 200
        
    except Exception as e:
        logger.error(f"Photo list error: {str(e)}")
        return jsonify({'error': 'Failed to retrieve photo list'}), 500

# System Control Routes
@app.route('/api/system/status', methods=['POST', 'GET'])
def system_status():
    """Handle system status updates from Arduino and provide status to clients"""
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            # Update system state
            system_state['last_activity'] = datetime.now()
            
            # Log system status
            logger.info(f"System status update: {data}")
            
            # Determine home mode based on various factors
            home_mode = determine_home_mode(data)
            system_state['home_mode'] = home_mode
            
            return jsonify({
                'status': 'success',
                'home_mode': home_mode,
                'system_active': system_state['system_active'],
                'timestamp': datetime.now().isoformat()
            }), 200
            
        except Exception as e:
            logger.error(f"System status error: {str(e)}")
            return jsonify({'error': 'Failed to update system status'}), 500
    
    else:  # GET request
        try:
            return jsonify({
                'system_state': system_state,
                'timestamp': datetime.now().isoformat()
            }), 200
        except Exception as e:
            logger.error(f"System status retrieval error: {str(e)}")
            return jsonify({'error': 'Failed to get system status'}), 500

@app.route('/api/system/home-mode', methods=['POST'])
@jwt_required()
def set_home_mode():
    """Manually set home/away mode"""
    try:
        data = request.get_json()
        home_mode = data.get('home_mode', True)
        
        system_state['home_mode'] = home_mode
        
        logger.info(f"Home mode manually set to: {'HOME' if home_mode else 'AWAY'}")
        
        return jsonify({
            'status': 'success',
            'home_mode': home_mode,
            'message': f"Mode set to {'HOME' if home_mode else 'AWAY'}"
        }), 200
        
    except Exception as e:
        logger.error(f"Home mode setting error: {str(e)}")
        return jsonify({'error': 'Failed to set home mode'}), 500

@app.route('/api/config/get', methods=['GET'])
def get_config():
    """Get current configuration for Arduino"""
    try:
        config = {
            'system_active': system_state['system_active'],
            'home_mode': system_state['home_mode'],
            'motion_sensitivity': system_state['motion_sensitivity'],
            'timestamp': datetime.now().isoformat()
        }
        
        return jsonify(config), 200
        
    except Exception as e:
        logger.error(f"Config retrieval error: {str(e)}")
        return jsonify({'error': 'Failed to get configuration'}), 500

# Notification Routes
@app.route('/api/notifications/send', methods=['POST'])
@jwt_required()
def send_notification():
    """Send manual notification"""
    try:
        data = request.get_json()
        
        result = notification_service.send_custom_notification(data)
        
        return jsonify({
            'status': 'success' if result else 'failed',
            'message': 'Notification sent' if result else 'Failed to send notification'
        }), 200 if result else 500
        
    except Exception as e:
        logger.error(f"Notification sending error: {str(e)}")
        return jsonify({'error': 'Failed to send notification'}), 500

@app.route('/api/notifications/settings', methods=['GET', 'POST'])
@jwt_required()
def notification_settings():
    """Get or update notification settings"""
    user_id = get_jwt_identity()
    
    if request.method == 'POST':
        try:
            settings = request.get_json()
            
            # Update user notification preferences
            user = User.query.get(user_id)
            user.notification_settings = json.dumps(settings)
            db.session.commit()
            
            return jsonify({
                'status': 'success',
                'message': 'Notification settings updated'
            }), 200
            
        except Exception as e:
            logger.error(f"Notification settings update error: {str(e)}")
            return jsonify({'error': 'Failed to update settings'}), 500
    
    else:  # GET request
        try:
            user = User.query.get(user_id)
            settings = json.loads(user.notification_settings) if user.notification_settings else {}
            
            return jsonify({'settings': settings}), 200
            
        except Exception as e:
            logger.error(f"Notification settings retrieval error: {str(e)}")
            return jsonify({'error': 'Failed to get settings'}), 500

# Web Interface Routes
@app.route('/')
def index():
    """Main dashboard"""
    return render_template('dashboard.html')

@app.route('/dashboard')
@jwt_required(optional=True)
def dashboard():
    """System dashboard"""
    return render_template('dashboard.html', system_state=system_state)

# Utility Functions
def determine_home_mode(device_data):
    """Determine if user is home based on various factors"""
    try:
        # Method 1: WiFi device detection
        wifi_strength = device_data.get('wifi_strength', 0)
        
        # Method 2: Manual override check
        # This could be enhanced with GPS, device presence, etc.
        
        # Simple logic: if WiFi signal is strong, likely at home
        if wifi_strength > -60:  # Strong signal
            return True
        elif wifi_strength < -80:  # Weak signal, likely away
            return False
        else:
            # Maintain current state if signal is moderate
            return system_state.get('home_mode', True)
            
    except Exception as e:
        logger.error(f"Home mode determination error: {str(e)}")
        return system_state.get('home_mode', True)

def cleanup_old_photos():
    """Clean up old photos to save storage space"""
    try:
        # Delete photos older than 30 days
        cutoff_date = datetime.now() - timedelta(days=30)
        
        old_photos = Photo.query.filter(Photo.timestamp < cutoff_date).all()
        
        for photo in old_photos:
            photo_path = os.path.join(app.config['UPLOAD_FOLDER'], photo.filename)
            if os.path.exists(photo_path):
                os.remove(photo_path)
            db.session.delete(photo)
        
        db.session.commit()
        logger.info(f"Cleaned up {len(old_photos)} old photos")
        
    except Exception as e:
        logger.error(f"Photo cleanup error: {str(e)}")

# Background Tasks
def background_tasks():
    """Run background maintenance tasks"""
    while True:
        try:
            # Clean up old photos every 24 hours
            cleanup_old_photos()
            
            # Update system health metrics
            # Add more background tasks as needed
            
            time.sleep(86400)  # 24 hours
            
        except Exception as e:
            logger.error(f"Background task error: {str(e)}")
            time.sleep(300)  # Wait 5 minutes before retry

# Error Handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(401)
def unauthorized(error):
    return jsonify({'error': 'Unauthorized access'}), 401

if __name__ == '__main__':
    # Start background tasks in separate thread
    background_thread = threading.Thread(target=background_tasks, daemon=True)
    background_thread.start()
    
    # Run Flask app
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,  # Set to False in production
        threaded=True
    )
