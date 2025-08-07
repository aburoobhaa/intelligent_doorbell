"""
Camera Controller Module
Handles photo capture, video recording, and camera operations
"""

import cv2
import os
import logging
from datetime import datetime
from threading import Lock
import numpy as np

class CameraController:
    def __init__(self, upload_folder):
        self.upload_folder = upload_folder
        self.camera = None
        self.camera_lock = Lock()
        self.logger = logging.getLogger(__name__)
        self.is_initialized = False
        
        # Camera settings
        self.photo_width = 1920
        self.photo_height = 1080
        self.photo_quality = 95
        
        self.initialize_camera()
    
    def initialize_camera(self):
        """Initialize the camera"""
        try:
            # Try different camera indices
            for camera_index in range(3):
                self.camera = cv2.VideoCapture(camera_index)
                if self.camera.isOpened():
                    # Set camera properties
                    self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.photo_width)
                    self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.photo_height)
                    self.camera.set(cv2.CAP_PROP_FPS, 30)
                    
                    self.is_initialized = True
                    self.logger.info(f"Camera initialized successfully on index {camera_index}")
                    break
                else:
                    if self.camera:
                        self.camera.release()
            
            if not self.is_initialized:
                self.logger.warning("No camera found. Photo capture will be simulated.")
                
        except Exception as e:
            self.logger.error(f"Camera initialization failed: {str(e)}")
            self.is_initialized = False
    
    def capture_photo(self, trigger_source="manual", location="front_door"):
        """Capture a photo and return the filename"""
        with self.camera_lock:
            try:
                timestamp = datetime.now()
                filename = f"{trigger_source}_{timestamp.strftime('%Y%m%d_%H%M%S')}.jpg"
                filepath = os.path.join(self.upload_folder, filename)
                
                if self.is_initialized and self.camera.isOpened():
                    # Capture frame
                    ret, frame = self.camera.read()
                    
                    if ret:
                        # Apply image enhancements
                        enhanced_frame = self.enhance_image(frame)
                        
                        # Save the photo
                        success = cv2.imwrite(filepath, enhanced_frame, 
                                            [cv2.IMWRITE_JPEG_QUALITY, self.photo_quality])
                        
                        if success:
                            self.logger.info(f"Photo captured successfully: {filename}")
                            return filename
                        else:
                            self.logger.error("Failed to save photo")
                            return None
                    else:
                        self.logger.error("Failed to capture frame from camera")
                        return None
                else:
                    # Simulate photo capture for testing
                    self.create_test_image(filepath, trigger_source, timestamp)
                    self.logger.info(f"Test photo created: {filename}")
                    return filename
                    
            except Exception as e:
                self.logger.error(f"Photo capture error: {str(e)}")
                return None
    
    def enhance_image(self, image):
        """Apply image enhancements for better quality"""
        try:
            # Convert to LAB color space for better processing
            lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            
            # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            l = clahe.apply(l)
            
            # Merge channels back
            enhanced_lab = cv2.merge([l, a, b])
            enhanced_image = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
            
            # Apply slight sharpening
            kernel = np.array([[-1,-1,-1],
                             [-1, 9,-1],
                             [-1,-1,-1]])
            enhanced_image = cv2.filter2D(enhanced_image, -1, kernel * 0.1)
            
            return enhanced_image
            
        except Exception as e:
            self.logger.error(f"Image enhancement error: {str(e)}")
            return image
    
    def create_test_image(self, filepath, trigger_source, timestamp):
        """Create a test image when no camera is available"""
        try:
            # Create a blank image
            img = np.zeros((self.photo_height, self.photo_width, 3), dtype=np.uint8)
            
            # Add background color
            img[:] = (50, 50, 50)  # Dark gray
            
            # Add text information
            font = cv2.FONT_HERSHEY_SIMPLEX
            text_color = (255, 255, 255)
            
            # Title
            cv2.putText(img, "Smart Doorbell System", (50, 100), 
                       font, 2, text_color, 3, cv2.LINE_AA)
            
            # Trigger source
            cv2.putText(img, f"Trigger: {trigger_source.upper()}", (50, 200), 
                       font, 1, text_color, 2, cv2.LINE_AA)
            
            # Timestamp
            timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
            cv2.putText(img, f"Time: {timestamp_str}", (50, 250), 
                       font, 1, text_color, 2, cv2.LINE_AA)
            
            # Location
            cv2.putText(img, "Location: Front Door", (50, 300), 
                       font, 1, text_color, 2, cv2.LINE_AA)
            
            # Camera status
            cv2.putText(img, "Status: TEST MODE", (50, 400), 
                       font, 1, (0, 255, 255), 2, cv2.LINE_AA)
            
            # Add a border
            cv2.rectangle(img, (20, 20), (self.photo_width-20, self.photo_height-20), 
                         (255, 255, 255), 3)
            
            # Save the test image
            cv2.imwrite(filepath, img, [cv2.IMWRITE_JPEG_QUALITY, self.photo_quality])
            
        except Exception as e:
            self.logger.error(f"Test image creation error: {str(e)}")
    
    def start_video_stream(self):
        """Start video streaming (for live monitoring)"""
        if not self.is_initialized:
            return None
        
        try:
            def generate_frames():
                while True:
                    with self.camera_lock:
                        if self.camera.isOpened():
                            ret, frame = self.camera.read()
                            if ret:
                                # Resize for streaming
                                frame = cv2.resize(frame, (640, 480))
                                
                                # Encode frame
                                ret, buffer = cv2.imencode('.jpg', frame,
                                                         [cv2.IMWRITE_JPEG_QUALITY, 70])
                                if ret:
                                    yield (b'--frame\r\n'
                                          b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            
            return generate_frames()
            
        except Exception as e:
            self.logger.error(f"Video streaming error: {str(e)}")
            return None
    
    def get_camera_info(self):
        """Get camera information and status"""
        try:
            info = {
                'initialized': self.is_initialized,
                'resolution': f"{self.photo_width}x{self.photo_height}",
                'quality': self.photo_quality,
                'status': 'ready' if self.is_initialized else 'not_available'
            }
            
            if self.is_initialized and self.camera.isOpened():
                info['fps'] = self.camera.get(cv2.CAP_PROP_FPS)
                info['brightness'] = self.camera.get(cv2.CAP_PROP_BRIGHTNESS)
                info['contrast'] = self.camera.get(cv2.CAP_PROP_CONTRAST)
            
            return info
            
        except Exception as e:
            self.logger.error(f"Camera info error: {str(e)}")
            return {'status': 'error', 'message': str(e)}
    
    def adjust_camera_settings(self, settings):
        """Adjust camera settings"""
        try:
            if not self.is_initialized:
                return False
            
            with self.camera_lock:
                if 'brightness' in settings:
                    self.camera.set(cv2.CAP_PROP_BRIGHTNESS, settings['brightness'])
                
                if 'contrast' in settings:
                    self.camera.set(cv2.CAP_PROP_CONTRAST, settings['contrast'])
                
                if 'saturation' in settings:
                    self.camera.set(cv2.CAP_PROP_SATURATION, settings['saturation'])
                
                if 'resolution' in settings:
                    width, height = settings['resolution'].split('x')
                    self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, int(width))
                    self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, int(height))
                    self.photo_width = int(width)
                    self.photo_height = int(height)
                
                if 'quality' in settings:
                    self.photo_quality = settings['quality']
            
            self.logger.info("Camera settings updated successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Camera settings adjustment error: {str(e)}")
            return False
    
    def test_camera(self):
        """Test camera functionality"""
        try:
            if not self.is_initialized:
                return {'status': 'error', 'message': 'Camera not initialized'}
            
            # Capture a test photo
            filename = self.capture_photo(trigger_source="test")
            
            if filename:
                return {
                    'status': 'success',
                    'message': 'Camera test successful',
                    'test_photo': filename
                }
            else:
                return {
                    'status': 'error',
                    'message': 'Failed to capture test photo'
                }
                
        except Exception as e:
            self.logger.error(f"Camera test error: {str(e)}")
            return {'status': 'error', 'message': str(e)}
    
    def cleanup(self):
        """Clean up camera resources"""
        try:
            if self.camera:
                self.camera.release()
            cv2.destroyAllWindows()
            self.logger.info("Camera resources cleaned up")
            
        except Exception as e:
            self.logger.error(f"Camera cleanup error: {str(e)}")
    
    def __del__(self):
        """Destructor to ensure camera is released"""
        self.cleanup()
