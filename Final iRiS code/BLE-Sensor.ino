#include <ArduinoBLE.h>
#include <Wire.h>
#include "Adafruit_VL6180X.h"
#include "Adafruit_HX711.h"
#include <Adafruit_NeoPixel.h>

#define PIN        6
#define NUMPIXELS 29
Adafruit_NeoPixel pixels(NUMPIXELS, PIN, NEO_GRB + NEO_KHZ800);

const char* serviceUUID = "11111111-E8F2-537E-4F6C-D104768A1214";
const char* charUUID    = "19B10001-E8F2-537E-4F6C-D104768A1214";

const int ROPE_THRESHOLD = 25;      
const int BUFFER_SIZE = 600; // 5 seconds ish

enum State { WAITING_FOR_ROPE, STABILIZING, MONITORING, ALERT_VERIFY, ALERT_HOLD, ROPE_COMPLETE };
State currentState = WAITING_FOR_ROPE;

float weightBuffer[BUFFER_SIZE];
int bufferIndex = 0;
unsigned long stateStartTime = 0;
unsigned long lastRetryTime = 0;
int exitCounter = 0; 
const int REQUIRED_EXIT_READINGS = 3; 

float smoothedRMS = 0;
const float alpha = 0.7; 

Adafruit_HX711 hx711(9, 8); 
Adafruit_VL6180X vl = Adafruit_VL6180X();
BLEService sensorService(serviceUUID);

BLEStringCharacteristic alertChar(charUUID, BLERead | BLEWrite | BLENotify, 20);

void setup() {
  pixels.begin();
  pixels.setBrightness(255);
  Serial.begin(115200);
  while (!Serial && millis() < 3000); 
  
  vl.begin();
  hx711.begin();
  for (uint8_t t=0; t<10; t++) hx711.tareA(hx711.readChannelRaw(CHAN_A_GAIN_128));
  
  if (!BLE.begin()) while (1);
  BLE.setLocalName("SensorHub");
  BLE.setAdvertisedService(sensorService);
  sensorService.addCharacteristic(alertChar);
  BLE.addService(sensorService);
  
  alertChar.writeValue("0,0.0"); 
  BLE.advertise();
  Serial.println("system ready");
}

void loop() {
  pixels.fill(pixels.Color(255, 255, 255));
  pixels.show();

  BLEDevice central = BLE.central();
  if (central && central.connected()) {
    uint8_t range = vl.readRange();
    int64_t raw = hx711.readChannelBlocking(CHAN_A_GAIN_128);
    float currentRMS = sqrt((float)raw * raw); 

    smoothedRMS = (alpha * currentRMS) + ((1.0 - alpha) * smoothedRMS);

    switch (currentState) {
      case WAITING_FOR_ROPE:
        if (range > 0 && range <= ROPE_THRESHOLD) {
          stateStartTime = millis();
          currentState = STABILIZING;
          smoothedRMS = currentRMS; 

          alertChar.writeValue("4," + String(smoothedRMS, 1)); 
          
          for(int i=0; i<BUFFER_SIZE; i++) weightBuffer[i] = currentRMS;
          Serial.println("Rope Detected.");
        }
        break;

      case STABILIZING:
        weightBuffer[bufferIndex] = smoothedRMS;
        bufferIndex = (bufferIndex + 1) % BUFFER_SIZE;
        if (millis() - stateStartTime >= 5000) { 
          currentState = MONITORING;
          alertChar.writeValue("6," + String(smoothedRMS, 1)); 
          Serial.println("Monitoring Active.");
        }
        break;

      case MONITORING:
        if (range > ROPE_THRESHOLD || range == 255 || range == 0) {
          currentState = ROPE_COMPLETE;
          alertChar.writeValue("5," + String(smoothedRMS, 1)); 
          Serial.println("Complete");
        } else {
          float oldReading = weightBuffer[bufferIndex];
          if (oldReading > 5.0) { 
            if (smoothedRMS > (oldReading * 1.40) || smoothedRMS < (oldReading * 0.85)) { // custom calibrated sensitivity values
              Serial.print("Spike detected: "); Serial.println(smoothedRMS);
              stateStartTime = millis();
              currentState = ALERT_VERIFY;
            }
          }
          weightBuffer[bufferIndex] = smoothedRMS;
          bufferIndex = (bufferIndex + 1) % BUFFER_SIZE;
        }
        break;

      case ALERT_VERIFY:
        if (range > ROPE_THRESHOLD || range == 255 || range == 0) {
          currentState = ROPE_COMPLETE;
          alertChar.writeValue("5," + String(smoothedRMS, 1));
        } else if (millis() - stateStartTime >= 5000) {
          currentState = ALERT_HOLD;
          stateStartTime = millis(); 
          alertChar.writeValue("3," + String(smoothedRMS, 1));
          Serial.println("alerted to jetson");
        }
        break;

      case ALERT_HOLD:
        if (millis() - lastRetryTime > 500) {
           alertChar.writeValue("3," + String(smoothedRMS, 1)); 
           lastRetryTime = millis();
        }
        if (millis() - stateStartTime >= 4000) {
          currentState = MONITORING;
          alertChar.writeValue("6," + String(smoothedRMS, 1));
          for(int i=0; i<BUFFER_SIZE; i++) weightBuffer[i] = smoothedRMS;
          Serial.println("alert window ended");
        }
        break;

      case ROPE_COMPLETE:
        if (range > ROPE_THRESHOLD || range == 255 || range == 0) {
          exitCounter++;
          if (exitCounter >= REQUIRED_EXIT_READINGS) {
            currentState = WAITING_FOR_ROPE;
            alertChar.writeValue("0," + String(smoothedRMS, 1)); 
            exitCounter = 0; 
            Serial.println("Resetted and waiting for next rope");
          }
        } else {
          exitCounter = 0; 
        }
        break;
    }
  }
  delay(5); 
}