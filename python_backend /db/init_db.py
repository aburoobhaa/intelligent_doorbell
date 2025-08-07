"""
Database Initialization Script for Smart Doorbell System
Creates all required tables and sets up initial data
"""

import sqlite3
import os
import json
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DatabaseInitializer:
    def __init__(self, db_path: str = 'smart_doorbell.db'):
        self.db_path = db_path
        self.logger = logger
    
    def create_database(self, force_recreate: bool = False):
        """Create database and all tables"""
        if force_recreate and os.path.exists(self.db_path):
            os.remove(self.db_path)
            self.logger.info(f"Existing database {self.db_path} removed")
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Enable foreign key constraints
            cursor.execute("PRAGMA foreign_keys = ON")
            
            # Create all tables
            self._create_users_table(cursor)
            self._create_events_table(cursor)
            self._create_user_sessions_table(cursor)
            self._create_device_tokens_table(cursor)
            self._create_system_config_table(cursor)
            self._create_notification_logs_table(cursor)
            self._create_arduino_data_table(cursor)
            
            # Create indexes for better performance
            self._create_indexes(cursor)
            
            # Insert initial configuration
            self._insert_initial_config(cursor)
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"Database {self.db_path} created successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Database creation failed: {str(e)}")
            return False
    
    def _create_users_table(self, cursor):
        """Create users table"""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone_number TEXT,
                full_name TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                last_login TEXT,
                is_active BOOLEAN DEFAULT 1,
                failed_login_attempts INTEGER DEFAULT 0,
                locked_until TEXT,
                last_failed_login TEXT,
                device_token TEXT,
                notification_preferences TEXT DEFAULT '{}',
                is_admin BOOLEAN DEFAULT 0
            )
        """)
        self.logger.info("Users table created")
    
    def _create_events_table(self, cursor):
        """Create events table"""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL CHECK(event_type IN ('doorbell', 'motion', 'system_alert', 'manual_trigger')),
                timestamp TEXT NOT NULL,
                location TEXT DEFAULT 'front_door',
                photo_filename TEXT,
                home_mode BOOLEAN DEFAULT 1,
                notification_sent BOOLEAN DEFAULT 0,
                user_id INTEGER,
                metadata TEXT DEFAULT '{}',
                processed BOOLEAN DEFAULT 0,
                confidence_score REAL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
            )
        """)
        self.logger.info("Events table created")
    
    def _create_user_sessions_table(self, cursor):
        """Create user sessions table"""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                device_info TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                invalidated_at TEXT,
                last_activity TEXT,
                ip_address TEXT,
                user_agent TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)
        self.logger.info("User sessions table created")
    
    def _create_device_tokens_table(self, cursor):
        """Create device tokens table for push notifications"""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS device_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                device_token TEXT UNIQUE NOT NULL,
                device_type TEXT CHECK(device_type IN ('android', 'ios', 'web', 'desktop')) DEFAULT 'unknown',
                device_name TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                is_active BOOLEAN DEFAULT 1,
                last_used TEXT,
                app_version TEXT,
                os_version TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)
        self.logger.info("Device tokens table created")
    
    def _create_system_config_table(self, cursor):
        """Create system configuration table"""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT,
                data_type TEXT DEFAULT 'string',
                description TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT
            )
        """)
        self.logger.info("System config table created")
    
    def _create_notification_logs_table(self, cursor):
        """Create notification logs table"""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notification_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER,
                user_id INTEGER,
                notification_type TEXT CHECK(notification_type IN ('push', 'email', 'sms', 'websocket')) NOT NULL,
                recipient TEXT NOT NULL,
                subject TEXT,
                message TEXT,
                sent_at TEXT NOT NULL,
                status TEXT CHECK(status IN ('pending', 'sent', 'failed', 'retrying')) DEFAULT 'pending',
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                delivery_confirmed_at TEXT,
                FOREIGN KEY (event_id) REFERENCES events (id) ON DELETE SET NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)
        self.logger.info("Notification logs table created")
    
    def _create_arduino_data_table(self, cursor):
        """Create table for Arduino sensor data"""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS arduino_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sensor_type TEXT NOT NULL,
                sensor_value TEXT NOT NULL,
                raw_data TEXT,
                timestamp TEXT NOT NULL,
                processed BOOLEAN DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.logger.info("Arduino data table created")
    
    def _create_indexes(self, cursor):
        """Create database indexes for better performance"""
        indexes = [
            # Users table indexes
            "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)",
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)",
            "CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active)",
            
            # Events table indexes
            "CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)",
            "CREATE INDEX IF NOT EXISTS idx_events_user_id ON events(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_events_processed ON events(processed)",
            "CREATE INDEX IF NOT EXISTS idx_events_notification_sent ON events(notification_sent)",
            
            # Sessions table indexes
            "CREATE INDEX IF NOT EXISTS idx_sessions_session_id ON user_sessions(session_id)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON user_sessions(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_active ON user_sessions(is_active)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_expires ON user_sessions(expires_at)",
            
            # Device tokens indexes
            "CREATE INDEX IF NOT EXISTS idx_tokens_user_id ON device_tokens(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_tokens_active ON device_tokens(is_active)",
            "CREATE INDEX IF NOT EXISTS idx_tokens_device_type ON device_tokens(device_type)",
            
            # System config indexes
            "CREATE INDEX IF NOT EXISTS idx_config_key ON system_config(key)",
            
            # Notification logs indexes
            "CREATE INDEX IF NOT EXISTS idx_notif_logs_event_id ON notification_logs(event_id)",
            "CREATE INDEX IF NOT EXISTS idx_notif_logs_user_id ON notification_logs(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_notif_logs_status ON notification_logs(status)",
            "CREATE INDEX IF NOT EXISTS idx_notif_logs_sent_at ON notification_logs(sent_at)",
            
            # Arduino data indexes
            "CREATE INDEX IF NOT EXISTS idx_arduino_timestamp ON arduino_data(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_arduino_sensor_type ON arduino_data(sensor_type)",
            "CREATE INDEX IF NOT EXISTS idx_arduino_processed ON arduino_data(processed)",
        ]
        
        for index_sql in indexes:
            cursor.execute(index_sql)
        
        self.logger.info("Database indexes created")
    
    def _insert_initial_config(self, cursor):
        """Insert initial system configuration"""
        initial_configs = [
            ('app_name', 'Smart Doorbell System', 'string', 'Application name'),
            ('app_version', '1.0.0', 'string', 'Application version'),
            ('max_failed_logins', '5', 'number', 'Maximum failed login attempts before lockout'),
            ('session_timeout_hours', '24', 'number', 'Session timeout in hours'),
            ('notification_retry_attempts', '3', 'number', 'Maximum notification retry attempts'),
            ('photo_retention_days', '30', 'number', 'Days to keep doorbell photos'),
            ('log_retention_days', '90', 'number', 'Days to keep system logs'),
            ('enable_motion_detection', 'true', 'boolean', 'Enable motion detection alerts'),
            ('enable_doorbell_notifications', 'true', 'boolean', 'Enable doorbell notifications'),
            ('quiet_hours_enabled', 'true', 'boolean', 'Enable quiet hours functionality'),
            ('default_quiet_hours', '{"start": "22:00", "end": "07:00"}', 'json', 'Default quiet hours'),
            ('camera_resolution', '{"width": 640, "height": 480}', 'json', 'Camera resolution settings'),
            ('notification_settings', '{"push_enabled": true, "email_enabled": true, "sms_enabled": false}', 'json', 'Default notification settings'),
            ('arduino_connection', '{"port": "/dev/ttyUSB0", "baud_rate": 9600, "timeout": 1}', 'json', 'Arduino connection settings'),
            ('photo_directory', './doorbell_photos', 'string', 'Directory to store photos'),
            ('log_level', 'INFO', 'string', 'System log level'),
        ]
        
        for config in initial_configs:
            cursor.execute("""
                INSERT OR IGNORE INTO system_config (key, value, data_type, description, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (*config, datetime.now().isoformat()))
        
        self.logger.info("Initial configuration inserted")
    
    def create_admin_user(self, username: str = 'admin', password: str = 'admin123', email: str = 'admin@doorbell.local'):
        """Create default admin user"""
        try:
            from auth_service import AuthService
            
            auth_service = AuthService(self.db_path)
            
            # Check if admin user already exists
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            if cursor.fetchone():
                conn.close()
                self.logger.info("Admin user already exists")
                return True
            conn.close()
            
            # Create admin user
            success, message = auth_service.register_user(
                username=username,
                password=password,
                email=email,
                full_name='System Administrator'
            )
            
            if success:
                # Set admin privileges
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET is_admin = 1 WHERE username = ?", (username,))
                conn.commit()
                conn.close()
                
                self.logger.info(f"Admin user '{username}' created successfully")
                return True
            else:
                self.logger.error(f"Failed to create admin user: {message}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error creating admin user: {str(e)}")
            return False
    
    def populate_sample_data(self):
        """Populate database with sample data for testing"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Sample events
            sample_events = [
                ('doorbell', 'front_door', 1, '{"visitor_detected": true, "confidence": 0.95}'),
                ('motion', 'front_door', 1, '{"motion_intensity": "medium", "duration": 5}'),
                ('doorbell', 'front_door', 0
