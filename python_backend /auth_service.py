"""
Authentication Service for Smart Doorbell System
Handles user authentication, session management, and security
"""

import hashlib
import secrets
import sqlite3
import jwt
import bcrypt
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, session, current_app
import logging
import re

class AuthService:
    def __init__(self, db_path='smart_doorbell.db'):
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
        self.secret_key = self._get_or_create_secret_key()
        
    def _get_or_create_secret_key(self):
        """Get or create a secret key for JWT tokens"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if secret key exists
            cursor.execute("SELECT value FROM system_config WHERE key = 'jwt_secret'")
            result = cursor.fetchone()
            
            if result:
                secret_key = result[0]
            else:
                # Generate new secret key
                secret_key = secrets.token_hex(32)
                cursor.execute(
                    "INSERT OR REPLACE INTO system_config (key, value) VALUES (?, ?)",
                    ('jwt_secret', secret_key)
                )
                conn.commit()
            
            conn.close()
            return secret_key
            
        except Exception as e:
            self.logger.error(f"Error managing secret key: {str(e)}")
            return secrets.token_hex(32)  # Fallback secret
    
    def hash_password(self, password):
        """Hash password using bcrypt"""
        try:
            # Generate salt and hash password
            salt = bcrypt.gensalt()
            hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
            return hashed.decode('utf-8')
        except Exception as e:
            self.logger.error(f"Password hashing error: {str(e)}")
            raise
    
    def verify_password(self, password, hashed_password):
        """Verify password against hash"""
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
        except Exception as e:
            self.logger.error(f"Password verification error: {str(e)}")
            return False
    
    def validate_password_strength(self, password):
        """Validate password strength"""
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"
        
        if not re.search(r"[A-Z]", password):
            return False, "Password must contain at least one uppercase letter"
        
        if not re.search(r"[a-z]", password):
            return False, "Password must contain at least one lowercase letter"
        
        if not re.search(r"[0-9]", password):
            return False, "Password must contain at least one number"
        
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            return False, "Password must contain at least one special character"
        
        return True, "Password is valid"
    
    def validate_email(self, email):
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    def register_user(self, username, password, email, phone_number=None, full_name=None):
        """Register a new user"""
        try:
            # Validate input
            if not username or not password or not email:
                return False, "Username, password, and email are required"
            
            if not self.validate_email(email):
                return False, "Invalid email format"
            
            is_valid, message = self.validate_password_strength(password)
            if not is_valid:
                return False, message
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if user already exists
            cursor.execute("SELECT id FROM users WHERE username = ? OR email = ?", (username, email))
            if cursor.fetchone():
                conn.close()
                return False, "Username or email already exists"
            
            # Hash password
            hashed_password = self.hash_password(password)
            
            # Insert new user
            cursor.execute("""
                INSERT INTO users (username, password_hash, email, phone_number, full_name, created_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (username, hashed_password, email, phone_number, full_name, datetime.now().isoformat(), True))
            
            user_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            self.logger.info(f"User registered successfully: {username}")
            return True, f"User registered successfully with ID: {user_id}"
            
        except Exception as e:
            self.logger.error(f"User registration error: {str(e)}")
            return False, "Registration failed due to system error"
    
    def authenticate_user(self, username, password):
        """Authenticate user credentials"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get user data
            cursor.execute("""
                SELECT id, username, password_hash, email, is_active, failed_login_attempts, locked_until
                FROM users WHERE username = ? OR email = ?
            """, (username, username))
            
            user_data = cursor.fetchone()
            conn.close()
            
            if not user_data:
                return False, None, "Invalid credentials"
            
            user_id, db_username, password_hash, email, is_active, failed_attempts, locked_until = user_data
            
            # Check if account is active
            if not is_active:
                return False, None, "Account is deactivated"
            
            # Check if account is locked
            if locked_until:
                lock_time = datetime.fromisoformat(locked_until)
                if datetime.now() < lock_time:
                    return False, None, f"Account locked until {lock_time.strftime('%Y-%m-%d %H:%M:%S')}"
            
            # Verify password
            if self.verify_password(password, password_hash):
                # Reset failed attempts on successful login
                self._reset_failed_attempts(user_id)
                
                user_info = {
                    'id': user_id,
                    'username': db_username,
                    'email': email
                }
                
                return True, user_info, "Authentication successful"
            else:
                # Increment failed attempts
                self._increment_failed_attempts(user_id)
                return False, None, "Invalid credentials"
                
        except Exception as e:
            self.logger.error(f"Authentication error: {str(e)}")
            return False, None, "Authentication failed due to system error"
    
    def _increment_failed_attempts(self, user_id):
        """Increment failed login attempts and lock account if necessary"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get current failed attempts
            cursor.execute("SELECT failed_login_attempts FROM users WHERE id = ?", (user_id,))
            result = cursor.fetchone()
            failed_attempts = (result[0] or 0) + 1
            
            # Lock account after 5 failed attempts for 30 minutes
            if failed_attempts >= 5:
                locked_until = (datetime.now() + timedelta(minutes=30)).isoformat()
                cursor.execute("""
                    UPDATE users 
                    SET failed_login_attempts = ?, locked_until = ?, last_failed_login = ?
                    WHERE id = ?
                """, (failed_attempts, locked_until, datetime.now().isoformat(), user_id))
            else:
                cursor.execute("""
                    UPDATE users 
                    SET failed_login_attempts = ?, last_failed_login = ?
                    WHERE id = ?
                """, (failed_attempts, datetime.now().isoformat(), user_id))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Error updating failed attempts: {str(e)}")
    
    def _reset_failed_attempts(self, user_id):
        """Reset failed login attempts after successful login"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE users 
                SET failed_login_attempts = 0, locked_until = NULL, last_login = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), user_id))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Error resetting failed attempts: {str(e)}")
    
    def generate_jwt_token(self, user_info, expires_in_hours=24):
        """Generate JWT token for authenticated user"""
        try:
            payload = {
                'user_id': user_info['id'],
                'username': user_info['username'],
                'email': user_info['email'],
                'exp': datetime.utcnow() + timedelta(hours=expires_in_hours),
                'iat': datetime.utcnow()
            }
            
            token = jwt.encode(payload, self.secret_key, algorithm='HS256')
            return token
            
        except Exception as e:
            self.logger.error(f"JWT generation error: {str(e)}")
            return None
    
    def verify_jwt_token(self, token):
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
            return True, payload
            
        except jwt.ExpiredSignatureError:
            return False, "Token has expired"
        except jwt.InvalidTokenError:
            return False, "Invalid token"
        except Exception as e:
            self.logger.error(f"JWT verification error: {str(e)}")
            return False, "Token verification failed"
    
    def get_user_by_id(self, user_id):
        """Get user information by ID"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, username, email, phone_number, full_name, created_at, last_login, is_active
                FROM users WHERE id = ?
            """, (user_id,))
            
            user_data = cursor.fetchone()
            conn.close()
            
            if user_data:
                return {
                    'id': user_data[0],
                    'username': user_data[1],
                    'email': user_data[2],
                    'phone_number': user_data[3],
                    'full_name': user_data[4],
                    'created_at': user_data[5],
                    'last_login': user_data[6],
                    'is_active': user_data[7]
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Get user error: {str(e)}")
            return None
    
    def update_user_profile(self, user_id, email=None, phone_number=None, full_name=None):
        """Update user profile information"""
        try:
            updates = []
            params = []
            
            if email:
                if not self.validate_email(email):
                    return False, "Invalid email format"
                updates.append("email = ?")
                params.append(email)
            
            if phone_number:
                updates.append("phone_number = ?")
                params.append(phone_number)
            
            if full_name:
                updates.append("full_name = ?")
                params.append(full_name)
            
            if not updates:
                return False, "No updates provided"
            
            updates.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            params.append(user_id)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            query = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)
            
            if cursor.rowcount == 0:
                conn.close()
                return False, "User not found"
            
            conn.commit()
            conn.close()
            
            return True, "Profile updated successfully"
            
        except Exception as e:
            self.logger.error(f"Profile update error: {str(e)}")
            return False, "Profile update failed"
    
    def change_password(self, user_id, current_password, new_password):
        """Change user password"""
        try:
            # Validate new password
            is_valid, message = self.validate_password_strength(new_password)
            if not is_valid:
                return False, message
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get current password hash
            cursor.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,))
            result = cursor.fetchone()
            
            if not result:
                conn.close()
                return False, "User not found"
            
            current_hash = result[0]
            
            # Verify current password
            if not self.verify_password(current_password, current_hash):
                conn.close()
                return False, "Current password is incorrect"
            
            # Hash new password
            new_hash = self.hash_password(new_password)
            
            # Update password
            cursor.execute("""
                UPDATE users 
                SET password_hash = ?, updated_at = ?
                WHERE id = ?
            """, (new_hash, datetime.now().isoformat(), user_id))
            
            conn.commit()
            conn.close()
            
            return True, "Password changed successfully"
            
        except Exception as e:
            self.logger.error(f"Password change error: {str(e)}")
            return False, "Password change failed"
    
    def create_session(self, user_id, device_info=None):
        """Create a user session"""
        try:
            session_id = secrets.token_urlsafe(32)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO user_sessions (session_id, user_id, device_info, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                session_id,
                user_id,
                device_info,
                datetime.now().isoformat(),
                (datetime.now() + timedelta(hours=24)).isoformat()
            ))
            
            conn.commit()
            conn.close()
            
            return session_id
            
        except Exception as e:
            self.logger.error(f"Session creation error: {str(e)}")
            return None
    
    def validate_session(self, session_id):
        """Validate user session"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT user_id, expires_at FROM user_sessions 
                WHERE session_id = ? AND is_active = 1
            """, (session_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if not result:
                return False, None
            
            user_id, expires_at = result
            expiry_time = datetime.fromisoformat(expires_at)
            
            if datetime.now() > expiry_time:
                self.invalidate_session(session_id)
                return False, None
            
            return True, user_id
            
        except Exception as e:
            self.logger.error(f"Session validation error: {str(e)}")
            return False, None
    
    def invalidate_session(self, session_id):
        """Invalidate a user session"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE user_sessions 
                SET is_active = 0, invalidated_at = ?
                WHERE session_id = ?
            """, (datetime.now().isoformat(), session_id))
            
            conn.commit()
            conn.close()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Session invalidation error: {str(e)}")
            return False


# Decorator functions for Flask routes
def require_auth(auth_service):
    """Decorator to require authentication for Flask routes"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check for JWT token in Authorization header
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
                is_valid, payload = auth_service.verify_jwt_token(token)
                
                if is_valid:
                    request.current_user = payload
                    return f(*args, **kwargs)
            
            # Check for session ID in cookies or session
            session_id = request.cookies.get('session_id') or session.get('session_id')
            if session_id:
                is_valid, user_id = auth_service.validate_session(session_id)
                if is_valid:
                    user_info = auth_service.get_user_by_id(user_id)
                    if user_info:
                        request.current_user = user_info
                        return f(*args, **kwargs)
            
            return jsonify({'error': 'Authentication required'}), 401
        
        return decorated_function
    return decorator

def require_admin(auth_service):
    """Decorator to require admin privileges"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # First check authentication
            auth_required = require_auth(auth_service)
            result = auth_required(f)(*args, **kwargs)
            
            # Check if user is admin (you might have an is_admin field)
            if hasattr(request, 'current_user'):
                # Add admin check logic here based on your requirements
                # For example: if not request.current_user.get('is_admin'):
                #     return jsonify({'error': 'Admin privileges required'}), 403
                pass
            
            return result
        
        return decorated_function
    return decorator


if __name__ == "__main__":
    # Test the authentication service
    auth_service = AuthService()
    
    # Example usage
    print("Testing Authentication Service...")
    
    # Register a test user
    success, message = auth_service.register_user(
        username="testuser",
        password="TestPass123!",
        email="test@example.com",
        phone_number="+1234567890",
        full_name="Test User"
    )
    print(f"Registration: {success} - {message}")
    
    # Authenticate the user
    success, user_info, message = auth_service.authenticate_user("testuser", "TestPass123!")
    print(f"Authentication: {success} - {message}")
    
    if success:
        # Generate JWT token
        token = auth_service.generate_jwt_token(user_info)
        print(f"JWT Token: {token}")
        
        # Verify JWT token
        is_valid, payload = auth_service.verify_jwt_token(token)
        print(f"Token verification: {is_valid} - {payload}")
