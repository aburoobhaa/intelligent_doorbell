/*
 * IoT-Based Smart Doorbell System
 * Main Arduino Code
 * 
 * Features:
 * - PIR Motion Detection
 * - Doorbell Button Monitoring
 * - WiFi Communication
 * - LED Status Indicators
 * - Buzzer Alerts
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "config.h"

// Pin Definitions
#define PIR_PIN 2
#define DOORBELL_PIN 3
#define LED_STATUS_PIN 13
#define LED_MOTION_PIN 12
#define BUZZER_PIN 11
#define CAMERA_TRIGGER_PIN 10

// WiFi Credentials
const char* ssid = WIFI_SSID;
const char* password = WIFI_PASSWORD;
const char* server_url = SERVER_URL;

// System Variables
bool motionDetected = false;
bool doorbellPressed = false;
bool systemActive = true;
bool homeMode = true;
unsigned long lastMotionTime = 0;
unsigned long lastDoorbellTime = 0;
unsigned long lastStatusUpdate = 0;

// Timing Constants
const unsigned long MOTION_COOLDOWN = 5000;      // 5 seconds
const unsigned long DOORBELL_COOLDOWN = 3000;    // 3 seconds
const unsigned long STATUS_UPDATE_INTERVAL = 30000; // 30 seconds

void setup() {
  Serial.begin(115200);
  Serial.println("Smart Doorbell System Starting...");
  
  // Initialize pins
  pinMode(PIR_PIN, INPUT);
  pinMode(DOORBELL_PIN, INPUT_PULLUP);
  pinMode(LED_STATUS_PIN, OUTPUT);
  pinMode(LED_MOTION_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(CAMERA_TRIGGER_PIN, OUTPUT);
  
  // Initial LED states
  digitalWrite(LED_STATUS_PIN, LOW);
  digitalWrite(LED_MOTION_PIN, LOW);
  digitalWrite(CAMERA_TRIGGER_PIN, LOW);
  
  // Connect to WiFi
  connectToWiFi();
  
  // System ready
  digitalWrite(LED_STATUS_PIN, HIGH);
  playStartupTone();
  
  Serial.println("Smart Doorbell System Ready!");
}

void loop() {
  // Check WiFi connection
  if (WiFi.status() != WL_CONNECTED) {
    reconnectWiFi();
  }
  
  // Read sensors
  readMotionSensor();
  readDoorbellButton();
  
  // Send periodic status updates
  if (millis() - lastStatusUpdate > STATUS_UPDATE_INTERVAL) {
    sendStatusUpdate();
    lastStatusUpdate = millis();
  }
  
  // Update LED indicators
  updateLEDs();
  
  // Small delay to prevent overwhelming the system
  delay(100);
}

void connectToWiFi() {
  Serial.print("Connecting to WiFi: ");
  Serial.println(ssid);
  
  WiFi.begin(ssid, password);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
    
    // Blink status LED during connection
    digitalWrite(LED_STATUS_PIN, !digitalRead(LED_STATUS_PIN));
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi Connected!");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());
    digitalWrite(LED_STATUS_PIN, HIGH);
  } else {
    Serial.println("\nWiFi Connection Failed!");
    digitalWrite(LED_STATUS_PIN, LOW);
  }
}

void reconnectWiFi() {
  Serial.println("WiFi disconnected. Reconnecting...");
  WiFi.disconnect();
  WiFi.reconnect();
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 10) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("Reconnected to WiFi!");
  }
}

void readMotionSensor() {
  int motionState = digitalRead(PIR_PIN);
  
  if (motionState == HIGH && !motionDetected) {
    // Motion detected
    if (millis() - lastMotionTime > MOTION_COOLDOWN) {
      motionDetected = true;
      lastMotionTime = millis();
      
      Serial.println("Motion Detected!");
      digitalWrite(LED_MOTION_PIN, HIGH);
      
      // Send motion alert
      sendMotionAlert();
      
      // If not in home mode, trigger camera
      if (!homeMode) {
        triggerCamera();
      }
    }
  } else if (motionState == LOW && motionDetected) {
    // Motion stopped
    motionDetected = false;
    digitalWrite(LED_MOTION_PIN, LOW);
    Serial.println("Motion Stopped");
  }
}

void readDoorbellButton() {
  int buttonState = digitalRead(DOORBELL_PIN);
  
  if (buttonState == LOW && !doorbellPressed) {
    // Doorbell pressed (button is LOW when pressed due to INPUT_PULLUP)
    if (millis() - lastDoorbellTime > DOORBELL_COOLDOWN) {
      doorbellPressed = true;
      lastDoorbellTime = millis();
      
      Serial.println("Doorbell Pressed!");
      
      // Play doorbell sound
      playDoorbellTone();
      
      // Always capture photo when doorbell is pressed
      triggerCamera();
      
      // Send doorbell notification
      sendDoorbellAlert();
    }
  } else if (buttonState == HIGH && doorbellPressed) {
    doorbellPressed = false;
  }
}

void sendMotionAlert() {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(String(server_url) + "/api/motion/detected");
    http.addHeader("Content-Type", "application/json");
    
    // Create JSON payload
    DynamicJsonDocument doc(1024);
    doc["timestamp"] = millis();
    doc["sensor_id"] = "PIR_001";
    doc["location"] = "front_door";
    doc["home_mode"] = homeMode;
    
    String jsonString;
    serializeJson(doc, jsonString);
    
    int httpResponseCode = http.POST(jsonString);
    
    if (httpResponseCode > 0) {
      String response = http.getString();
      Serial.println("Motion alert sent: " + response);
    } else {
      Serial.println("Error sending motion alert: " + String(httpResponseCode));
    }
    
    http.end();
  }
}

void sendDoorbellAlert() {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(String(server_url) + "/api/doorbell/pressed");
    http.addHeader("Content-Type", "application/json");
    
    // Create JSON payload
    DynamicJsonDocument doc(1024);
    doc["timestamp"] = millis();
    doc["button_id"] = "DOORBELL_001";
    doc["location"] = "front_door";
    doc["home_mode"] = homeMode;
    doc["photo_captured"] = true;
    
    String jsonString;
    serializeJson(doc, jsonString);
    
    int httpResponseCode = http.POST(jsonString);
    
    if (httpResponseCode > 0) {
      String response = http.getString();
      Serial.println("Doorbell alert sent: " + response);
    } else {
      Serial.println("Error sending doorbell alert: " + String(httpResponseCode));
    }
    
    http.end();
  }
}

void triggerCamera() {
  Serial.println("Triggering camera capture...");
  
  // Send trigger pulse to camera
  digitalWrite(CAMERA_TRIGGER_PIN, HIGH);
  delay(200);
  digitalWrite(CAMERA_TRIGGER_PIN, LOW);
  
  // Send HTTP request to capture photo
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(String(server_url) + "/api/camera/capture");
    http.addHeader("Content-Type", "application/json");
    
    DynamicJsonDocument doc(1024);
    doc["timestamp"] = millis();
    doc["trigger_source"] = doorbellPressed ? "doorbell" : "motion";
    doc["location"] = "front_door";
    
    String jsonString;
    serializeJson(doc, jsonString);
    
    int httpResponseCode = http.POST(jsonString);
    
    if (httpResponseCode > 0) {
      Serial.println("Camera capture requested successfully");
    } else {
      Serial.println("Error requesting camera capture");
    }
    
    http.end();
  }
}

void sendStatusUpdate() {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(String(server_url) + "/api/system/status");
    http.addHeader("Content-Type", "application/json");
    
    // Create status JSON
    DynamicJsonDocument doc(1024);
    doc["device_id"] = "SMART_DOORBELL_001";
    doc["timestamp"] = millis();
    doc["wifi_connected"] = true;
    doc["wifi_strength"] = WiFi.RSSI();
    doc["system_active"] = systemActive;
    doc["home_mode"] = homeMode;
    doc["motion_detected"] = motionDetected;
    doc["doorbell_pressed"] = doorbellPressed;
    doc["uptime"] = millis();
    
    String jsonString;
    serializeJson(doc, jsonString);
    
    int httpResponseCode = http.POST(jsonString);
    
    if (httpResponseCode > 0) {
      String response = http.getString();
      
      // Parse response to check for home mode updates
      DynamicJsonDocument responseDoc(1024);
      deserializeJson(responseDoc, response);
      
      if (responseDoc.containsKey("home_mode")) {
        homeMode = responseDoc["home_mode"];
        Serial.println("Home mode updated: " + String(homeMode ? "HOME" : "AWAY"));
      }
    }
    
    http.end();
  }
}

void playDoorbellTone() {
  // Play doorbell melody
  tone(BUZZER_PIN, 523, 200); // C5
  delay(250);
  tone(BUZZER_PIN, 659, 200); // E5
  delay(250);
  tone(BUZZER_PIN, 784, 400); // G5
  delay(450);
}

void playStartupTone() {
  // Play startup melody
  tone(BUZZER_PIN, 262, 150); // C4
  delay(200);
  tone(BUZZER_PIN, 330, 150); // E4
  delay(200);
  tone(BUZZER_PIN, 392, 150); // G4
  delay(200);
}

void updateLEDs() {
  // Status LED: Solid when connected, blinking when disconnected
  if (WiFi.status() != WL_CONNECTED) {
    digitalWrite(LED_STATUS_PIN, (millis() / 500) % 2);
  } else {
    digitalWrite(LED_STATUS_PIN, HIGH);
  }
  
  // Motion LED: On when motion detected
  digitalWrite(LED_MOTION_PIN, motionDetected ? HIGH : LOW);
}

// Function to handle HTTP GET requests (for configuration updates)
void handleConfigUpdate() {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(String(server_url) + "/api/config/get");
    
    int httpResponseCode = http.GET();
    
    if (httpResponseCode > 0) {
      String response = http.getString();
      
      DynamicJsonDocument doc(1024);
      deserializeJson(doc, response);
      
      // Update configuration based on server response
      if (doc.containsKey("system_active")) {
        systemActive = doc["system_active"];
      }
      
      if (doc.containsKey("home_mode")) {
        homeMode = doc["home_mode"];
      }
    }
    
    http.end();
  }
}
