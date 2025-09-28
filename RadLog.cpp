//RadLog.ino

#include <Arduino.h>

const int analogPin = A0;
const int printPin = 6;
const unsigned long baudRate = 115200; // High speed serial

void setup() {
  Serial.begin(baudRate);
}

void loop() {
  int sensorValue = analogRead(analogPin);
  Serial.println(sensorValue);  // Send as plain integer
  analogWrite(printPin,sensorValue); // Output value to pin
  //delay(1); // ~1 kHz sampling, adjust if needed
}
