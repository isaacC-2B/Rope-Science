#include <Wire.h>
#include <Adafruit_MotorShield.h>

Adafruit_MotorShield AFMS1(0x60);
Adafruit_MotorShield AFMS2(0x61);

Adafruit_StepperMotor *steppera1a = AFMS1.getStepper(200, 1);
Adafruit_StepperMotor *steppera1b = AFMS1.getStepper(200, 2);

Adafruit_StepperMotor *stepperb1a = AFMS2.getStepper(200, 1);
Adafruit_StepperMotor *stepperb1b = AFMS2.getStepper(200, 2);

void setup() {
  Serial.begin(9600);
  while (!Serial);

  Serial.println("Running 4 steppers safely for 10 seconds...");

  AFMS1.begin();
  AFMS2.begin();

  steppera1a->setSpeed(160);
  steppera1b->setSpeed(160);
  stepperb1a->setSpeed(160);
  stepperb1b->setSpeed(160);
}

void loop() {
  unsigned long startTime = millis();


  while (millis() - startTime < 150000) {
    steppera1a->onestep(BACKWARD, SINGLE);
    steppera1b->onestep(FORWARD, SINGLE);
    stepperb1a->onestep(BACKWARD, SINGLE);
    stepperb1b->onestep(FORWARD, SINGLE);

    delay(1);
  }

  Serial.println("All motors run complete. Releasing...");

  steppera1a->release();
  steppera1b->release();
  stepperb1a->release();
  stepperb1b->release();

  Serial.println("All motors released. Safe to power down motor supplies now.");

  while (1);
}
