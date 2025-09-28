// Arduino square wave generator
// Pin 9 outputs a square wave at ~1 kHz
#include <Arduino.h>

const int wavePin = 9;

void setup() {
  pinMode(wavePin, OUTPUT);
}

void loop() {
  digitalWrite(wavePin, HIGH);
  delayMicroseconds(500);   // 1 kHz, 50% duty cycle
  digitalWrite(wavePin, LOW);
  delayMicroseconds(500);
}
