"""
Notification Service Module
Handles push notifications, email alerts, and SMS notifications
"""

import requests
import json
import logging
import smtplib
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
from email.mime.image import MimeImage
from datetime import datetime
import os
from twilio.rest import Client  # pip install twilio

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
            
            # Send notifications
            if self.user_preferences['push_notifications']:
                self.send_push_notification(title, body, 'doorbell', notification_data)
            
            if self.user_
