"""
IoT-Based Smart Doorbell System - Notification Service Module
Handles push notifications, email alerts, SMS notifications, and real-time monitoring
"""

import requests
import json
import logging
import smtplib
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
from email.mime.image import MimeImage
from datetime import datetime, time
import os
import cv2
import base64
import threading
import time as time_module
from twilio.rest import Client  # pip install twilio
import sqlite3
import hashlib
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO, emit
import serial  # pip install pyserial

class NotificationService:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Firebase configuration
        self.firebase_server_key = os.getenv('FIREBASE_SERVER_KEY', '')
        self.firebase_url = "https://fcm.googleapis.com/fcm/send"
        
        # Email configuration
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.email_address = os.getenv('EMAIL_ADDRESS', '')
        self.email_password = os.getenv('EMAIL_PASSWORD', '')
        
        # Twilio configuration for SMS
        self.twilio_account_sid = os.getenv('TWILIO_ACCOUNT_SID', '')
        self.twilio_auth_token = os.getenv('TWILIO_AUTH_TOKEN', '')
        self.twilio_phone_number = os.getenv('TWILIO_PHONE_NUMBER', '')
        
        # Initialize Twilio client
        if self.twilio_account_sid and self.twilio_auth_token:
            self.twilio_client = Client(self.twilio_account_sid, self.twilio_auth_token)
        
        # User notification preferences (in production, this would come from database)
        self.user_preferences = {
            'push_notifications': True,
            'email_notifications': True,
            'sms_notifications': False,
            'notification_quiet_hours': {'start': '22:00', 'end': '07:00'},
            'notification_types': {
                'motion': True,
                'doorbell': True,
                'system_alerts': True
            }
        }
        
        # Device tokens (in production, stored in database)
        self.device_tokens = []
        
        # Initialize database
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database for storing events and user data"""
        try:
            conn = sqlite3.connect('smart_doorbell.db')
            cursor = conn.cursor()
            
            # Create events table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    location TEXT,
                    photo_filename TEXT,
                    home_mode BOOLEAN,
                    notification_sent BOOLEAN DEFAULT FALSE
                )
            ''')
            
            # Create users table for authentication
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    device_token TEXT,
                    phone_number TEXT,
                    email TEXT
                )
            ''')
            
            conn.commit()
            conn.close()
            self.logger.info("Database initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Database initialization error: {str(e)}")
    
    def send_doorbell_alert(self, doorbell_data):
        """Send doorbell press alert"""
        try:
            if not self.user_preferences['notification_types']['doorbell']:
                return
            
            timestamp = datetime.now().strftime("%H:%M:%S")
            location = doorbell_data.get('location', 'front door')
            photo_filename = doorbell_data.get('photo_filename')
            home_mode = doorbell_data.get('home_mode', True)
            
            # Prepare notification content
            if home_mode:
                title = "🔔 Someone's at the Door"
                body = f"Doorbell pressed at {location} at {timestamp}"
            else:
                title = "🔔 Visitor While Away"
                body = f"Someone rang the doorbell at {location} while you're away ({timestamp})"
            
            if photo_filename:
                body += " - Photo captured"
            
            # Prepare additional data
            notification_data = {
                'type': 'doorbell',
                'timestamp': doorbell_data.get('timestamp'),
                'location': location,
                'photo_filename': photo_filename,
                'home_mode': home_mode
            }
            
            # Store event in database
            self.store_event('doorbell', location, photo_filename, home_mode)
            
            # Send notifications
            if self.user_preferences['push_notifications']:
                self.send_push_notification(title, body, 'doorbell', notification_data)
            
            if self.user_preferences['email_notifications']:
                self.send_email_notification(title, body, 'doorbell', photo_filename)
            
            if self.user_preferences['sms_notifications']:
                self.send_sms_notification(f"{title}: {body}")
            
            self.logger.info(f"Doorbell alert sent for location: {location}")
            
        except Exception as e:
            self.logger.error(f"Doorbell alert error: {str(e)}")
    
    def send_motion_alert(self, motion_data):
        """Send motion detection alert"""
        try:
            if not self.user_preferences['notification_types']['motion']:
                return
            
            if self.is_quiet_hours():
                self.logger.info("Skipping motion notification due to quiet hours")
                return
            
            timestamp = datetime.now().strftime("%H:%M:%S")
            location = motion_data.get('location', 'front door')
            
            # Prepare notification content
            title = "🚨 Motion Detected"
            body = f"Motion detected at {location} at {timestamp}"
            
            # Store event in database
            self.store_event('motion', location, None, motion_data.get('home_mode', True))
            
            # Send notifications
            if self.user_preferences['push_notifications']:
                self.send_push_notification(title, body, 'motion', motion_data)
            
            if self.user_preferences['email_notifications']:
                self.send_email_notification(title, body, 'motion')
            
            if self.user_preferences['sms_notifications']:
                self.send_sms_notification(f"{title}: {body}")
            
            self.logger.info(f"Motion alert sent for location: {location}")
            
        except Exception as e:
            self.logger.error(f"Motion alert error: {str(e)}")
    
    def send_push_notification(self, title, body, notification_type, data=None):
        """Send push notification via Firebase"""
        try:
            if not self.firebase_server_key or not self.device_tokens:
                self.logger.warning("Firebase not configured or no device tokens available")
                return
            
            headers = {
                'Authorization': f'key={self.firebase_server_key}',
                'Content-Type': 'application/json',
            }
            
            for token in self.device_tokens:
                payload = {
                    'to': token,
                    'notification': {
                        'title': title,
                        'body': body,
                        'sound': 'default',
                        'priority': 'high'
                    },
                    'data': data or {}
                }
                
                response = requests.post(self.firebase_url, headers=headers, json=payload)
                if response.status_code == 200:
                    self.logger.info(f"Push notification sent successfully")
                else:
                    self.logger.error(f"Push notification failed: {response.text}")
                    
        except Exception as e:
            self.logger.error(f"Push notification error: {str(e)}")
    
    def send_email_notification(self, title, body, notification_type, photo_filename=None):
        """Send email notification with optional photo attachment"""
        try:
            if not self.email_address or not self.email_password:
                self.logger.warning("Email not configured")
                return
            
            msg = MimeMultipart()
            msg['From'] = self.email_address
            msg['To'] = self.email_address  # In production, get from user preferences
            msg['Subject'] = f"Smart Doorbell Alert - {title}"
            
            # Email body
            html_body = f"""
            <html>
                <body>
                    <h2>{title}</h2>
                    <p>{body}</p>
                    <p><strong>Time:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
                    <p><strong>System:</strong> Smart Doorbell IoT</p>
                </body>
            </html>
            """
            
            msg.attach(MimeText(html_body, 'html'))
            
            # Attach photo if available
            if photo_filename and os.path.exists(photo_filename):
                with open(photo_filename, 'rb') as f:
                    img = MimeImage(f.read())
                    img.add_header('Content-Disposition', 'attachment', filename=os.path.basename(photo_filename))
                    msg.attach(img)
            
            # Send email
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.email_address, self.email_password)
            server.send_message(msg)
            server.quit()
            
            self.logger.info("Email notification sent successfully")
            
        except Exception as e:
            self.logger.error(f"Email notification error: {str(e)}")
    
    def send_sms_notification(self, message):
        """Send SMS notification via Twilio"""
        try:
            if not hasattr(self, 'twilio_client'):
                self.logger.warning("Twilio not configured")
                return
            
            # In production, get phone numbers from user preferences
            phone_numbers = ['+1234567890']  # Replace with actual phone numbers
            
            for phone_number in phone_numbers:
                message = self.twilio_client.messages.create(
                    body=message,
                    from_=self.twilio_phone_number,
                    to=phone_number
                )
                self.logger.info(f"SMS sent successfully: {message.sid}")
                
        except Exception as e:
            self.logger.error(f"SMS notification error: {str(e)}")
    
    def is_quiet_hours(self):
        """Check if current time is within quiet hours"""
        try:
            current_time = datetime.now().time()
            start_time = time.fromisoformat(self.user_preferences['notification_quiet_hours']['start'])
            end_time = time.fromisoformat(self.user_preferences['notification_quiet_hours']['end'])
            
            if start_time <= end_time:
                return start_time <= current_time <= end_time
            else:  # Quiet hours span midnight
                return current_time >= start_time or current_time <= end_time
                
        except Exception as e:
            self.logger.error(f"Quiet hours check error: {str(e)}")
            return False
    
    def store_event(self, event_type, location, photo_filename, home_mode):
        """Store event in database"""
        try:
            conn = sqlite3.connect('smart_doorbell.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO events (event_type, location, photo_filename, home_mode, notification_sent)
                VALUES (?, ?, ?, ?, ?)
            ''', (event_type, location, photo_filename, home_mode, True))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Database storage error: {str(e)}")
    
    def get_recent_events(self, limit=50):
        """Get recent events from database"""
        try:
            conn = sqlite3.connect('smart_doorbell.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM events 
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (limit,))
            
            events = cursor.fetchall()
            conn.close()
            
            return events
            
        except Exception as e:
            self.logger.error(f"Database query error: {str(e)}")
            return []


class CameraModule:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.camera = None
        self.photo_directory = "doorbell_photos"
        
        # Create photo directory if it doesn't exist
        if not os.path.exists(self.photo_directory):
            os.makedirs(self.photo_directory)
    
    def initialize_camera(self, camera_index=0):
        """Initialize camera for photo capture"""
        try:
            self.camera = cv2.VideoCapture(camera_index)
            if not self.camera.isOpened():
                self.logger.error("Failed to open camera")
                return False
            
            # Set camera properties
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            
            self.logger.info("Camera initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Camera initialization error: {str(e)}")
            return False
    
    def capture_photo(self):
        """Capture photo when doorbell is pressed"""
        try:
            if not self.camera or not self.camera.isOpened():
                self.logger.error("Camera not initialized")
                return None
            
            ret, frame = self.camera.read()
            if not ret:
                self.logger.error("Failed to capture frame")
                return None
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(self.photo_directory, f"visitor_{timestamp}.jpg")
            
            # Save photo
            cv2.imwrite(filename, frame)
            self.logger.info(f"Photo captured: {filename}")
            
            return filename
            
        except Exception as e:
            self.logger.error(f"Photo capture error: {str(e)}")
            return None
    
    def release_camera(self):
        """Release camera resources"""
        if self.camera:
            self.camera.release()
            self.logger.info("Camera released")


class ArduinoInterface:
    def __init__(self, port='/dev/ttyUSB0', baud_rate=9600):
        self.logger = logging.getLogger(__name__)
        self.port = port
        self.baud_rate = baud_rate
        self.serial_connection = None
        self.is_connected = False
    
    def connect(self):
        """Connect to Arduino"""
        try:
            self.serial_connection = serial.Serial(self.port, self.baud_rate, timeout=1)
            self.is_connected = True
            self.logger.info(f"Connected to Arduino on {self.port}")
            return True
            
        except Exception as e:
            self.logger.error(f"Arduino connection error: {str(e)}")
            return False
    
    def read_sensor_data(self):
        """Read data from Arduino sensors"""
        try:
            if not self.is_connected:
                return None
            
            if self.serial_connection.in_waiting > 0:
                data = self.serial_connection.readline().decode('utf-8').strip()
                return data
            
            return None
            
        except Exception as e:
            self.logger.error(f"Arduino read error: {str(e)}")
            return None
    
    def send_command(self, command):
        """Send command to Arduino"""
        try:
            if not self.is_connected:
                return False
            
            self.serial_connection.write(f"{command}\n".encode('utf-8'))
            return True
            
        except Exception as e:
            self.logger.error(f"Arduino send error: {str(e)}")
            return False
    
    def disconnect(self):
        """Disconnect from Arduino"""
        if self.serial_connection:
            self.serial_connection.close()
            self.is_connected = False
            self.logger.info("Arduino disconnected")


class SmartDoorbellSystem:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.notification_service = NotificationService()
        self.camera_module = CameraModule()
        self.arduino_interface = ArduinoInterface()
        self.home_mode = True  # True = user is home, False = user is away
        self.running = False
    
    def initialize_system(self):
        """Initialize all system components"""
        try:
            # Initialize camera
            if not self.camera_module.initialize_camera():
                self.logger.error("Failed to initialize camera")
                return False
            
            # Connect to Arduino
            if not self.arduino_interface.connect():
                self.logger.error("Failed to connect to Arduino")
                return False
            
            self.logger.info("Smart Doorbell System initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"System initialization error: {str(e)}")
            return False
    
    def set_home_mode(self, is_home):
        """Set home mode (True = home, False = away)"""
        self.home_mode = is_home
        mode_text = "Home" if is_home else "Away"
        self.logger.info(f"Home mode set to: {mode_text}")
    
    def process_doorbell_event(self):
        """Process doorbell press event"""
        try:
            self.logger.info("Doorbell pressed!")
            
            # Capture photo
            photo_filename = self.camera_module.capture_photo()
            
            # Prepare doorbell data
            doorbell_data = {
                'timestamp': datetime.now().isoformat(),
                'location': 'front door',
                'photo_filename': photo_filename,
                'home_mode': self.home_mode
            }
            
            # Send alert
            self.notification_service.send_doorbell_alert(doorbell_data)
            
            # If user is not home, send immediate notification to app
            if not self.home_mode:
                self.send_real_time_notification(doorbell_data)
            
        except Exception as e:
            self.logger.error(f"Doorbell event error: {str(e)}")
    
    def process_motion_event(self):
        """Process motion detection event"""
        try:
            self.logger.info("Motion detected!")
            
            motion_data = {
                'timestamp': datetime.now().isoformat(),
                'location': 'front door',
                'home_mode': self.home_mode
            }
            
            # Send motion alert
            self.notification_service.send_motion_alert(motion_data)
            
        except Exception as e:
            self.logger.error(f"Motion event error: {str(e)}")
    
    def send_real_time_notification(self, data):
        """Send real-time notification to mobile app via WebSocket"""
        try:
            # In a real implementation, this would use WebSocket or push notifications
            # to immediately notify the mobile app
            self.logger.info("Sending real-time notification to mobile app")
            
            notification_data = {
                'type': 'real_time_doorbell',
                'timestamp': data['timestamp'],
                'message': 'Someone is at your door while you\'re away!',
                'photo_available': data['photo_filename'] is not None
            }
            
            # This would typically emit to connected WebSocket clients
            # socketio.emit('doorbell_alert', notification_data)
            
        except Exception as e:
            self.logger.error(f"Real-time notification error: {str(e)}")
    
    def run_monitoring_loop(self):
        """Main monitoring loop"""
        self.running = True
        self.logger.info("Starting monitoring loop...")
        
        while self.running:
            try:
                # Read data from Arduino
                sensor_data = self.arduino_interface.read_sensor_data()
                
                if sensor_data:
                    # Parse sensor data
                    if "DOORBELL_PRESSED" in sensor_data:
                        self.process_doorbell_event()
                    
                    elif "MOTION_DETECTED" in sensor_data:
                        self.process_motion_event()
                    
                    elif "HOME_MODE" in sensor_data:
                        # Update home mode based on Arduino input
                        self.set_home_mode("ON" in sensor_data)
                
                time_module.sleep(0.1)  # Small delay to prevent excessive CPU usage
                
            except KeyboardInterrupt:
                self.logger.info("Monitoring loop interrupted by user")
                break
            except Exception as e:
                self.logger.error(f"Monitoring loop error: {str(e)}")
                time_module.sleep(1)  # Wait before retrying
        
        self.cleanup()
    
    def cleanup(self):
        """Clean up system resources"""
        self.running = False
        self.camera_module.release_camera()
        self.arduino_interface.disconnect()
        self.logger.info("System cleanup completed")


# Authentication helper functions
def hash_password(password):
    """Hash password for storage"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, password_hash):
    """Verify password against hash"""
    return hashlib.sha256(password.encode()).hexdigest() == password_hash


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create and initialize smart doorbell system
    doorbell_system = SmartDoorbellSystem()
    
    if doorbell_system.initialize_system():
        try:
            # Start monitoring loop
            doorbell_system.run_monitoring_loop()
        except KeyboardInterrupt:
            print("\nShutting down Smart Doorbell System...")
    else:
        print("Failed to initialize Smart Doorbell System")
