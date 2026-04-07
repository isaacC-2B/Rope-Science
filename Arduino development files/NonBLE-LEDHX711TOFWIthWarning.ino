#include <Wire.h>
#include "Adafruit_VL6180X.h"
#include "Adafruit_HX711.h"
#include <Adafruit_NeoPixel.h>
#ifdef __AVR__
  #include <avr/power.h>
#endif

#define PIN        6
#define NUMPIXELS 29

Adafruit_NeoPixel pixels(NUMPIXELS, PIN, NEO_GRB + NEO_KHZ800);
#define DELAYVAL 500

const uint8_t DATA_PIN = 9;
const uint8_t CLOCK_PIN = 8;

const int windowSize = 4;
static int i = 0;
long long arr[windowSize];
long long cumSqSum = 0;

Adafruit_HX711 hx711(DATA_PIN, CLOCK_PIN);
Adafruit_VL6180X vl = Adafruit_VL6180X();

void setup() {
  Serial.begin(115200);
  
  pixels.setBrightness(255);
  #if defined(__AVR_ATtiny85__) && (F_CPU == 16000000)
    clock_prescale_set(clock_div_1);
  #endif
    pixels.begin();
  
  while (!Serial) {
    delay(1);
  }

  Serial.println("Adafruit HX711 & VL6180x starting");
  if (! vl.begin()) {
    Serial.println("Failed to find ToF sensor");
    while (1);
  }
  Serial.println("ToF sensor found!");

  hx711.begin();

  Serial.println("Tareing....");
  for (uint8_t t=0; t<5; t++) {
    hx711.tareA(hx711.readChannelRaw(CHAN_A_GAIN_128));
  }
} 

void loop() {
  uint8_t range = vl.readRange();
  uint8_t status = vl.readRangeStatus();

  uint32_t white = pixels.Color(255, 255, 255, 255);
  pixels.fill(white);
  pixels.show();

  if (status == VL6180X_ERROR_NONE) {
    if (range > 15) {
      Serial.print("Alert No rope detected! Range: "); Serial.println(range);
    }
    else {
      Serial.print("Range: "); Serial.println(range);
    }
  }
  
  if  ((status >= VL6180X_ERROR_SYSERR_1) && (status <= VL6180X_ERROR_SYSERR_5)) {
    Serial.println("System error");
  }
  else if (status == VL6180X_ERROR_ECEFAIL) {
    Serial.println("ECE failure");
  }
  else if (status == VL6180X_ERROR_NOCONVERGE) {
    Serial.println("No convergence");
  }
  else if (status == VL6180X_ERROR_RANGEIGNORE) {
    Serial.println("Ignoring range");
  }
  else if (status == VL6180X_ERROR_SNR) {
    Serial.println("Signal/Noise error");
  }
  else if (status == VL6180X_ERROR_RAWUFLOW) {
    Serial.println("Raw reading underflow");
  }
  else if (status == VL6180X_ERROR_RAWOFLOW) {
    Serial.println("Raw reading overflow");
  }
  else if (status == VL6180X_ERROR_RANGEUFLOW) {
    Serial.println("Range reading underflow");
  }
  else if (status == VL6180X_ERROR_RANGEOFLOW) {
    Serial.println("Range reading overflow");
  }

  int64_t weightA128 = hx711.readChannelBlocking(CHAN_A_GAIN_128);
  long long envelope = (long long)weightA128 * weightA128;
  arr[i] = envelope;
  cumSqSum += arr[i];
  
  float rms = 0;
  static float lastRMS = 0;
  
  if (i == windowSize - 1) {
    rms = sqrt((float)cumSqSum / windowSize);
    
    if (lastRMS > 0) { 
      float diff = abs(rms - lastRMS);
      float percentChange = diff / lastRMS;
      if (percentChange >= 0.50) {
        Serial.println("Alert! 30% diff found");
      }
    }
    
    lastRMS = rms;
    i = 0;
    cumSqSum = 0;
    Serial.print("Load: ");
    Serial.println(rms);
  }
  else {
    i++;
  }
  delay(10);
}