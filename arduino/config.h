/*
 * Configuration file for Smart Doorbell System
 * Update these values according to your setup
 */

#ifndef CONFIG_H
#define CONFIG_H

// WiFi Configuration
#define WIFI_SSID "Your_WiFi_Name"
#define WIFI_PASSWORD "Your_WiFi_Password"

// Server Configuration
#define SERVER_URL "http://192.168.1.100:5000"  // Replace with your server IP
#define API_KEY "your_api_key_here"

// Hardware Pin Configurations
#define PIR_SENSOR_PIN 2
#define DOORBELL_BUTTON_PIN 3
#define STATUS_LED_PIN 13
#define MOTION_LED_PIN 12
#define BUZZER_PIN 11
#define CAMERA_TRIGGER_PIN 10

// Sensor Sensitivity Settings
#define PIR_SENSITIVITY 7           // 1-10 scale
#define MOTION_TIMEOUT 5000         // milliseconds
#define DOORBELL_DEBOUNCE 300       // milliseconds

// System Settings
#define DEVICE_ID "DOORBELL_001"
#define LOCATION "front_door"
#define DEBUG_MODE true

// Network Settings
#define MAX_WIFI_RETRY 20
#define HTTP_TIMEOUT 5000
#define STATUS_UPDATE_INTERVAL 30000

// Camera Settings
#define CAMERA_TRIGGER_DURATION 200  // milliseconds
#define PHOTO_QUALITY "high"         // low, medium, high

// Power Management
#define DEEP_SLEEP_ENABLE false
#define BATTERY_CHECK_INTERVAL 60000 // milliseconds

#endif
