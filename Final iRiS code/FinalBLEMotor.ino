#include <ArduinoBLE.h>
#include <Wire.h>
#include <Adafruit_MotorShield.h>

// only 2 steppers for now but more can be added easily
Adafruit_MotorShield AFMS1(0x60); 
Adafruit_MotorShield AFMS2(0x61); 

Adafruit_StepperMotor *steppera1a = AFMS1.getStepper(200, 1);
Adafruit_StepperMotor *steppera1b = AFMS1.getStepper(200, 2);
Adafruit_StepperMotor *stepperb1a = AFMS2.getStepper(200, 1);
Adafruit_StepperMotor *stepperb1b = AFMS2.getStepper(200, 2);

// UUIDs to match in jetson python script
BLEService MotorService("19B10000-E8F2-537E-4F6C-D104768A1214");
BLEByteCharacteristic onoff("19B10001-E8F2-537E-4F6C-D104768A1214", BLERead | BLEWrite | BLENotify);

int motorState = -1; 

void setup() {
  Serial.begin(115200);

  if (!BLE.begin()) {
    while (1);
  }

  BLE.setLocalName("MotorController");
  BLE.setAdvertisedService(MotorService);
  MotorService.addCharacteristic(onoff);
  BLE.addService(MotorService);
  onoff.writeValue(0); 
  BLE.advertise();

  AFMS1.begin();
  AFMS2.begin();

  steppera1a->setSpeed(160);
  steppera1b->setSpeed(160);
  stepperb1a->setSpeed(160);
  stepperb1b->setSpeed(160);
}

void loop() {
  BLEDevice central = BLE.central();
  if (central && central.connected()) {
    while (central.connected()) {
      if (onoff.written()) {
        motorState = onoff.value();
      }

      if (motorState == 1) {
        steppera1a->onestep(BACKWARD, SINGLE);
        steppera1b->onestep(FORWARD, SINGLE);
        stepperb1a->onestep(BACKWARD, SINGLE);
        stepperb1b->onestep(FORWARD, SINGLE);
      } 
      else if (motorState == 0) {
        steppera1a->release();
        steppera1b->release();
        stepperb1a->release();
        stepperb1b->release();
        motorState = -1; 
      }
    }

    motorState = 0;
    steppera1a->release();
    steppera1b->release();
    stepperb1a->release();
    stepperb1b->release();
  }
}
/* motor state 1 = run
   motor state 0 = stop */