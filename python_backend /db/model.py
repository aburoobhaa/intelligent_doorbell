"""
Database Models for Smart Doorbell System
Defines the database schema and provides ORM-like functionality
"""

import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
import logging

class DatabaseManager:
    """Database connection and transaction manager"""
    
    def __init__(self, db_path: str = 'smart_doorbell.db'):
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
    
    def get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)
    
    def execute_query(self, query: str, params: tuple = (), fetch_one: bool = False, fetch_all: bool = False):
        """Execute a query with error handling"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            
            if fetch_one:
                result = cursor.fetchone()
            elif fetch_all:
                result = cursor.fetchall()
            else:
                result = cursor.rowcount
            
            conn.commit()
            conn.close()
            return result
            
        except Exception as e:
            self.logger.error(f"Database query error: {str(e)}")
            raise


class BaseModel:
    """Base model class with common functionality"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.logger = logging.getLogger(__name__)
    
    def to_dict(self, data: tuple, fields: List[str]) -> Dict:
        """Convert tuple to dictionary"""
        if not data:
            return None
        return dict(zip(fields, data))
    
    def format_datetime(self, dt_string: str) -> str:
        """Format datetime string for display"""
        if not dt_string:
            return None
        try:
            dt = datetime.fromisoformat(dt_string)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            return dt_string


class User(BaseModel):
    """User model for authentication and user management"""
    
    FIELDS = ['id', 'username', 'password_hash', 'email', 'phone_number', 'full_name', 
              'created_at', 'updated_at', 'last_login', 'is_active', 'failed_login_attempts', 
              'locked_until', 'last_failed_login', 'device_token', 'notification_preferences']
    
    def create(self, user_data: Dict) -> int:
        """Create a new user"""
        query = """
            INSERT INTO users (username, password_hash, email, phone_number, full_name, 
                             created_at, is_active, notification_preferences)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        preferences = json.dumps(user_data.get('notification_preferences', {
            'push_notifications': True,
            'email_notifications': True,
            'sms_notifications': False,
            'quiet_hours': {'start': '22:00', 'end': '07:00'}
        }))
        
        params = (
            user_data['username'],
            user_data['password_hash'],
            user_data['email'],
            user_data.get('phone_number'),
            user_data.get('full_name'),
            datetime.now().isoformat(),
            True,
            preferences
        )
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return user_id
    
    def get_by_id(self, user_id: int) -> Optional[Dict]:
        """Get user by ID"""
        query = f"SELECT {', '.join(self.FIELDS)} FROM users WHERE id = ?"
        result = self.db.execute_query(query, (user_id,), fetch_one=True)
        user_dict = self.to_dict(result, self.FIELDS)
        
        if user_dict and user_dict['notification_preferences']:
            try:
                user_dict['notification_preferences'] = json.loads(user_dict['notification_preferences'])
            except:
                user_dict['notification_preferences'] = {}
        
        return user_dict
    
    def get_by_username(self, username: str) -> Optional[Dict]:
        """Get user by username or email"""
        query = f"SELECT {', '.join(self.FIELDS)} FROM users WHERE username = ? OR email = ?"
        result = self.db.execute_query(query, (username, username), fetch_one=True)
        return self.to_dict(result, self.FIELDS)
    
    def update(self, user_id: int, user_data: Dict) -> bool:
        """Update user information"""
        update_fields = []
        params = []
        
        for field, value in user_data.items():
            if field in self.FIELDS and field not in ['id', 'created_at']:
                if field == 'notification_preferences' and isinstance(value, dict):
                    value = json.dumps(value)
                update_fields.append(f"{field} = ?")
                params.append(value)
        
        if not update_fields:
            return False
        
        update_fields.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(user_id)
        
        query = f"UPDATE users SET {', '.join(update_fields)} WHERE id = ?"
        result = self.db.execute_query(query, params)
        
        return result > 0
    
    def delete(self, user_id: int) -> bool:
        """Soft delete user (deactivate)"""
        query = "UPDATE users SET is_active = 0, updated_at = ? WHERE id = ?"
        result = self.db.execute_query(query, (datetime.now().isoformat(), user_id))
        return result > 0
    
    def get_all_active(self) -> List[Dict]:
        """Get all active users"""
        query = f"SELECT {', '.join(self.FIELDS)} FROM users WHERE is_active = 1 ORDER BY username"
        results = self.db.execute_query(query, fetch_all=True)
        return [self.to_dict(row, self.FIELDS) for row in results]


class Event(BaseModel):
    """Event model for doorbell and motion detection events"""
    
    FIELDS = ['id', 'event_type', 'timestamp', 'location', 'photo_filename', 
              'home_mode', 'notification_sent', 'user_id', 'metadata', 'processed']
    
    EVENT_TYPES = ['doorbell', 'motion', 'system_alert', 'manual_trigger']
    
    def create(self, event_data: Dict) -> int:
        """Create a new event"""
        query = """
            INSERT INTO events (event_type, timestamp, location, photo_filename, 
                               home_mode, notification_sent, user_id, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        metadata = json.dumps(event_data.get('metadata', {}))
        
        params = (
            event_data['event_type'],
            event_data.get('timestamp', datetime.now().isoformat()),
            event_data.get('location', 'front_door'),
            event_data.get('photo_filename'),
            event_data.get('home_mode', True),
            event_data.get('notification_sent', False),
            event_data.get('user_id'),
            metadata
        )
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        event_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return event_id
    
    def get_by_id(self, event_id: int) -> Optional[Dict]:
        """Get event by ID"""
        query = f"SELECT {', '.join(self.FIELDS)} FROM events WHERE id = ?"
        result = self.db.execute_query(query, (event_id,), fetch_one=True)
        event_dict = self.to_dict(result, self.FIELDS)
        
        if event_dict and event_dict['metadata']:
            try:
                event_dict['metadata'] = json.loads(event_dict['metadata'])
            except:
                event_dict['metadata'] = {}
        
        return event_dict
    
    def get_recent(self, limit: int = 50, event_type: Optional[str] = None, user_id: Optional[int] = None) -> List[Dict]:
        """Get recent events"""
        query = f"SELECT {', '.join(self.FIELDS)} FROM events WHERE 1=1"
        params = []
        
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        results = self.db.execute_query(query, params, fetch_all=True)
        events = []
        
        for row in results:
            event_dict = self.to_dict(row, self.FIELDS)
            if event_dict['metadata']:
                try:
                    event_dict['metadata'] = json.loads(event_dict['metadata'])
                except:
                    event_dict['metadata'] = {}
            events.append(event_dict)
        
        return events
    
    def get_by_date_range(self, start_date: str, end_date: str, user_id: Optional[int] = None) -> List[Dict]:
        """Get events within date range"""
        query = f"SELECT {', '.join(self.FIELDS)} FROM events WHERE timestamp BETWEEN ? AND ?"
        params = [start_date, end_date]
        
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        
        query += " ORDER BY timestamp DESC"
        
        results = self.db.execute_query(query, params, fetch_all=True)
        return [self.to_dict(row, self.FIELDS) for row in results]
    
    def update_notification_status(self, event_id: int, sent: bool = True) -> bool:
        """Update notification sent status"""
        query = "UPDATE events SET notification_sent = ?, processed = 1 WHERE id = ?"
        result = self.db.execute_query(query, (sent, event_id))
        return result > 0
    
    def get_unprocessed(self, limit: int = 100) -> List[Dict]:
        """Get unprocessed events for background processing"""
        query = f"SELECT {', '.join(self.FIELDS)} FROM events WHERE processed = 0 ORDER BY timestamp ASC LIMIT ?"
        results = self.db.execute_query(query, (limit,), fetch_all=True)
        return [self.to_dict(row, self.FIELDS) for row in results]
    
    def get_statistics(self, user_id: Optional[int] = None, days: int = 30) -> Dict:
        """Get event statistics"""
        base_query = "SELECT event_type, COUNT(*) as count FROM events WHERE timestamp >= date('now', '-{} days')"
        
        if user_id:
            base_query += " AND user_id = ?"
            params = (user_id,)
        else:
            params = ()
        
        base_query += " GROUP BY event_type"
        query = base_query.format(days)
        
        results = self.db.execute_query(query, params, fetch_all=True)
        
        stats = {
            'total_events': 0,
            'by_type': {},
            'period_days': days
        }
        
        for row in results:
            event_type, count = row
            stats['by_type'][event_type] = count
            stats['total_events'] += count
        
        return stats


class UserSession(BaseModel):
    """User session model for session management"""
    
    FIELDS = ['id', 'session_id', 'user_id', 'device_info', 'created_at', 
              'expires_at', 'is_active', 'invalidated_at', 'last_activity']
    
    def create(self, session_data: Dict) -> int:
        """Create a new session"""
        query = """
            INSERT INTO user_sessions (session_id, user_id, device_info, created_at, 
                                     expires_at, is_active, last_activity)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        
        now = datetime.now().isoformat()
        params = (
            session_data['session_id'],
            session_data['user_id'],
            session_data.get('device_info'),
            now,
            session_data['expires_at'],
            True,
            now
        )
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        session_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return session_id
    
    def get_by_session_id(self, session_id: str) -> Optional[Dict]:
        """Get session by session ID"""
        query = f"SELECT {', '.join(self.FIELDS)} FROM user_sessions WHERE session_id = ?"
        result = self.db.execute_query(query, (session_id,), fetch_one=True)
        return self.to_dict(result, self.FIELDS)
    
    def update_activity(self, session_id: str) -> bool:
        """Update session last activity"""
        query = "UPDATE user_sessions SET last_activity = ? WHERE session_id = ?"
        result = self.db.execute_query(query, (datetime.now().isoformat(), session_id))
        return result > 0
    
    def invalidate(self, session_id: str) -> bool:
        """Invalidate a session"""
        query = "UPDATE user_sessions SET is_active = 0, invalidated_at = ? WHERE session_id = ?"
        result = self.db.execute_query(query, (datetime.now().isoformat(), session_id))
        return result > 0
    
    def cleanup_expired(self) -> int:
        """Clean up expired sessions"""
        query = "UPDATE user_sessions SET is_active = 0 WHERE expires_at < ? AND is_active = 1"
        result = self.db.execute_query(query, (datetime.now().isoformat(),))
        return result
    
    def get_user_sessions(self, user_id: int) -> List[Dict]:
        """Get all active sessions for a user"""
        query = f"SELECT {', '.join(self.FIELDS)} FROM user_sessions WHERE user_id = ? AND is_active = 1 ORDER BY last_activity DESC"
        results = self.db.execute_query(query, (user_id,), fetch_all=True)
        return [self.to_dict(row, self.FIELDS) for row in results]


class DeviceToken(BaseModel):
    """Device token model for push notifications"""
    
    FIELDS = ['id', 'user_id', 'device_token', 'device_type', 'device_name', 
              'created_at', 'updated_at', 'is_active', 'last_used']
    
    DEVICE_TYPES = ['android', 'ios', 'web', 'desktop']
    
    def create(self, token_data: Dict) -> int:
        """Create or update device token"""
        # Check if token already exists
        existing = self.get_by_token(token_data['device_token'])
        if existing:
            return self.update(existing['id'], token_data)
        
        query = """
            INSERT INTO device_tokens (user_id, device_token, device_type, device_name, 
                                     created_at, is_active, last_used)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        
        now = datetime.now().isoformat()
        params = (
            token_data['user_id'],
            token_data['device_token'],
            token_data.get('device_type', 'unknown'),
            token_data.get('device_name', 'Unknown Device'),
            now,
            True,
            now
        )
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        token_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return token_id
    
    def get_by_token(self, device_token: str) -> Optional[Dict]:
        """Get device token record by token string"""
        query = f"SELECT {', '.join(self.FIELDS)} FROM device_tokens WHERE device_token = ?"
        result = self.db.execute_query(query, (device_token,), fetch_one=True)
        return self.to_dict(result, self.FIELDS)
    
    def get_user_tokens(self, user_id: int) -> List[Dict]:
        """Get all active tokens for a user"""
        query = f"SELECT {', '.join(self.FIELDS)} FROM device_tokens WHERE user_id = ? AND is_active = 1"
        results = self.db.execute_query(query, (user_id,), fetch_all=True)
        return [self.to_dict(row, self.FIELDS) for row in results]
    
    def update_last_used(self, token_id: int) -> bool:
        """Update token last used timestamp"""
        query = "UPDATE device_tokens SET last_used = ? WHERE id = ?"
        result = self.db.execute_query(query, (datetime.now().isoformat(), token_id))
        return result > 0
    
    def deactivate(self, token_id: int) -> bool:
        """Deactivate a device token"""
        query = "UPDATE device_tokens SET is_active = 0, updated_at = ? WHERE id = ?"
        result = self.db.execute_query(query, (datetime.now().isoformat(), token_id))
        return result > 0


class SystemConfig(BaseModel):
    """System configuration model"""
    
    FIELDS = ['id', 'key', 'value', 'data_type', 'description', 'created_at', 'updated_at']
    
    def set(self, key: str, value: Any, data_type: str = 'string', description: str = '') -> bool:
        """Set configuration value"""
        # Convert value to string for storage
        if isinstance(value, (dict, list)):
            str_value = json.dumps(value)
            data_type = 'json'
        elif isinstance(value, bool):
            str_value = str(value).lower()
            data_type = 'boolean'
        elif isinstance(value, (int, float)):
            str_value = str(value)
            data_type = 'number'
        else:
            str_value = str(value)
        
        query = """
            INSERT OR REPLACE INTO system_config (key, value, data_type, description, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """
        
        params = (key, str_value, data_type, description, datetime.now().isoformat())
        result = self.db.execute_query(query, params)
        
        return result > 0
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        query = "SELECT value, data_type FROM system_config WHERE key = ?"
        result = self.db.execute_query(query, (key,), fetch_one=True)
        
        if not result:
            return default
        
        value, data_type = result
        
        # Convert value back to appropriate type
        try:
            if data_type == 'json':
                return json.loads(value)
            elif data_type == 'boolean':
                return value.lower() in ('true', '1', 'yes')
            elif data_type == 'number':
                return float(value) if '.' in value else int(value)
            else:
                return value
        except:
            return default
    
    def get_all(self) -> Dict[str, Any]:
        """Get all configuration values"""
        query = f"SELECT {', '.join(self.FIELDS)} FROM system_config ORDER BY key"
        results = self.db.execute_query(query, fetch_all=True)
        
        config = {}
        for row in results:
            config_dict = self.to_dict(row, self.FIELDS)
            key = config_dict['key']
            value = config_dict['value']
            data_type = config_dict['data_type']
            
            try:
                if data_type == 'json':
                    config[key] = json.loads(value)
                elif data_type == 'boolean':
                    config[key] = value.lower() in ('true', '1', 'yes')
                elif data_type == 'number':
                    config[key] = float(value) if '.' in value else int(value)
                else:
                    config[key] = value
            except:
                config[key] = value
        
        return config
    
    def delete(self, key: str) -> bool:
        """Delete configuration value"""
        query = "DELETE FROM system_config WHERE key = ?"
        result = self.db.execute_query(query, (key,))
        return result > 0


class NotificationLog(BaseModel):
    """Notification log model to track sent notifications"""
    
    FIELDS = ['id', 'event_id', 'user_id', 'notification_type', 'recipient', 
              'subject', 'message', 'sent_at', 'status', 'error_message', 'retry_count']
    
    NOTIFICATION_TYPES = ['push', 'email', 'sms', 'websocket']
    STATUSES = ['pending', 'sent', 'failed', 'retrying']
    
    def create(self, log_data: Dict) -> int:
        """Create notification log entry"""
        query = """
            INSERT INTO notification_logs (event_id, user_id, notification_type, recipient, 
                                         subject, message, sent_at, status, error_message, retry_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        params = (
            log_data.get('event_id'),
            log_data.get('user_id'),
            log_data['notification_type'],
            log_data['recipient'],
            log_data.get('subject', ''),
            log_data.get('message', ''),
            datetime.now().isoformat(),
            log_data.get('status', 'pending'),
            log_data.get('error_message'),
            log_data.get('retry_count', 0)
        )
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        log_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return log_id
    
    def update_status(self, log_id: int, status: str, error_message: str = None) -> bool:
        """Update notification status"""
        query = "UPDATE notification_logs SET status = ?, error_message = ? WHERE id = ?"
        result = self.db.execute_query(query, (status, error_message, log_id))
        return result > 0
    
    def get_failed_notifications(self, max_retries: int = 3) -> List[Dict]:
        """Get failed notifications that can be retried"""
        query = f"""
            SELECT {', '.join(self.FIELDS)} 
            FROM notification_logs 
            WHERE status = 'failed' AND retry_count < ? 
            ORDER BY sent_at ASC
        """
        results = self.db.execute_query(query, (max_retries,), fetch_all=True)
        return [self.to_dict(row, self.FIELDS) for row in results]
    
    def increment_retry_count(self, log_id: int) -> bool:
        """Increment retry count for a notification"""
        query = "UPDATE notification_logs SET retry_count = retry_count + 1 WHERE id = ?"
        result = self.db.execute_query(query, (log_id,))
        return result > 0


class ModelFactory:
    """Factory class to create model instances"""
    
    def __init__(self, db_path: str = 'smart_doorbell.db'):
        self.db_manager = DatabaseManager(db_path)
        self._models = {}
    
    def get_model(self, model_name: str):
        """Get model instance (singleton pattern)"""
        if model_name not in self._models:
            model_classes = {
                'user': User,
                'event': Event,
                'session': UserSession,
                'device_token': DeviceToken,
                'system_config': SystemConfig,
                'notification_log': NotificationLog
            }
            
            if model_name in model_classes:
                self._models[model_name] = model_classes[model_name](self.db_manager)
            else:
                raise ValueError(f"Unknown model: {model_name}")
        
        return self._models[model_name]
    
    @property
    def user(self) -> User:
        return self.get_model('user')
    
    @property
    def event(self) -> Event:
        return self.get_model('event')
    
    @property
    def session(self) -> UserSession:
        return self.get_model('session')
    
    @property
    def device_token(self) -> DeviceToken:
        return self.get_model('device_token')
    
    @property
    def system_config(self) -> SystemConfig:
        return self.get_model('system_config')
    
    @property
    def notification_log(self) -> NotificationLog:
        return self.get_model('notification_log')


# Example usage and testing
if __name__ == "__main__":
    # Initialize model factory
    models = ModelFactory()
    
    print("Testing Database Models...")
    
    # Test user creation
    user_data = {
        'username': 'testuser',
        'password_hash': 'hashed_password',
        'email': 'test@example.com',
        'phone_number': '+1234567890',
        'full_name': 'Test User'
    }
    
    try:
        user_id = models.user.create(user_data)
        print(f"User created with ID: {user_id}")
        
        # Test user retrieval
        user = models.user.get_by_id(user_id)
        print(f"Retrieved user: {user['username']}")
        
        # Test event creation
        event_data = {
            'event_type': 'doorbell',
            'location': 'front_door',
            'user_id': user_id,
            'metadata': {'visitor_count': 1, 'weather': 'sunny'}
        }
        
        event_id = models.event.create(event_data)
        print(f"Event created with ID: {event_id}")
        
        # Test event retrieval
        events = models.event.get_recent(limit=10)
        print(f"Retrieved {len(events)} recent events")
        
        # Test system configuration
        models.system_config.set('doorbell_volume', 75, 'number', 'Doorbell notification volume')
        volume = models.system_config.get('doorbell_volume')
        print(f"Doorbell volume setting: {volume}")
        
    except Exception as e:
        print(f"Error testing models: {str(e)}")
