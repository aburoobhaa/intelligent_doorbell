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
            timestamp=
