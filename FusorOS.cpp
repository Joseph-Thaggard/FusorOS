#include <Arduino.h>

// === CONFIGURATION ===
const int BAUD_RATE = 9600; // Update to 115200 if allowed
const unsigned long LOOP_INTERVAL_MS = 30; // 30Hz

// === Pin Assignments ===
const int VALVE1_PIN = 2;
const int VALVE2_PIN = 3;

const int MFC_PWM_PIN = 5;
const int HV_PWM_PIN = 6;
const int SP_RELAY_PIN = 7;  // Optional: digital input
const int DEMO_MODE_PIN = 8;
const int STATUS_LED_PIN = LED_BUILTIN;

const int MFC_READ_PIN = A0;
const int HV_VOLT_READ_PIN = A1;
const int HV_CURR_READ_PIN = A2;
const int PRESSURE_READ_PIN = A3;

const int FUEL_PIN = 11;
const int VACUUM_PIN = 10;

// === System State ===
bool valve1_open = false;
bool valve2_open = false;
bool safeOn = false;
float mfc_set_sccm = 0.0;
float hv_set_kv = 0.0;
bool demo_mode = false;
bool safe_state = true;
bool ledBlinking = false;

unsigned long last_loop_time = 0;
unsigned long ledOnTime = 0;
const unsigned long LED_DURATION_MS = 500;

// === Safety Limits ===
const float MAX_HV_KV = 25.0;
const float DEMO_LIMIT_KV = 15.0;
const float PRESSURE_LIMIT_MTorr = 900.0; // Interlock threshold

void handleCommand(String cmd);
void enterSafeState();


void setup() {
  Serial.begin(BAUD_RATE);

  pinMode(MFC_PWM_PIN, OUTPUT);
  pinMode(HV_PWM_PIN, OUTPUT);
  pinMode(STATUS_LED_PIN, OUTPUT);
  pinMode(SP_RELAY_PIN, INPUT_PULLUP);
  pinMode(DEMO_MODE_PIN, INPUT_PULLUP);
  pinMode(STATUS_LED_PIN, OUTPUT);
  pinMode(FUEL_PIN, OUTPUT);
  pinMode(VACUUM_PIN, OUTPUT);
  digitalWrite(STATUS_LED_PIN, LOW);  // Start off
  digitalWrite(2, HIGH);   // Keep fuel pressurized
  digitalWrite(3, HIGH);   // Keep vacuum pressurized
  digitalWrite(11, LOW);    // Do not force close initially
  digitalWrite(10, LOW);   // Do not force close initially

  enterSafeState();
}

String serialBuffer = "";

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      handleCommand(serialBuffer);
      serialBuffer = "";
    } else {
      serialBuffer += c;
    }
  }
  unsigned long now = millis();
  if (now - last_loop_time >= LOOP_INTERVAL_MS) {
    last_loop_time = now;

    // === Read Inputs ===
    float mfc_feedback = analogRead(MFC_READ_PIN) * (5 / 1023.0) * 20.0;   // 0–5V → 0–100 sccm
    float hv_voltage = analogRead(HV_VOLT_READ_PIN) * (1 / 1023.0) * 5.0;  // → 0–25 kV
    float hv_current = analogRead(HV_CURR_READ_PIN) * (1 / 1023.0);        // Placeholder scaling
    float pressure = analogRead(PRESSURE_READ_PIN) * (1 / 1023.0) * 1999.0; // → 0–1999 mTorr

    // === Safety Interlock ===
    if (safeOn == true) {
      if (pressure > PRESSURE_LIMIT_MTorr) {
        enterSafeState();
        Serial.println("WARN:PRESSURE_SPIKE");
      }
    }

    // === Control Outputs ===
    float mfc_voltage = constrain(mfc_set_sccm / 100.0 * 255.0, 0, 255);
    float hv_voltage_cmd = constrain(hv_set_kv / MAX_HV_KV * 255.0, 0, 255);

    analogWrite(MFC_PWM_PIN, (int)mfc_voltage);
    analogWrite(HV_PWM_PIN, (int)hv_voltage_cmd);

    digitalWrite(VALVE1_PIN, valve1_open ? HIGH : LOW);
    digitalWrite(VALVE2_PIN, valve2_open ? HIGH : LOW);

    digitalWrite(STATUS_LED_PIN, safe_state ? LOW : HIGH);

    // === Handle Demo Mode ===
    demo_mode = (digitalRead(DEMO_MODE_PIN) == LOW);
    if (demo_mode && hv_set_kv > DEMO_LIMIT_KV) {
      hv_set_kv = DEMO_LIMIT_KV;
    }

    // === Send Telemetry ===
    Serial.print("DATA:T=");
    Serial.print(now);
    Serial.print(",P=");
    Serial.print(pressure, 4);
    Serial.print(",HVS=");
    Serial.print(hv_voltage_cmd, 4);
    Serial.print(",VHV=");
    Serial.print(hv_voltage, 4);
    Serial.print(",IHV=");
    Serial.print(hv_current, 4);
    Serial.print(",MFC_SET="); 
    Serial.print(mfc_set_sccm, 4);
    Serial.print(",MFCV=");
    Serial.print((int)mfc_voltage);
    Serial.print(",FMFC=");
    Serial.print(mfc_feedback, 4);
    Serial.print(",V1=");
    Serial.print(valve1_open);
    Serial.print(",V2=");
    Serial.print(valve2_open);
    Serial.print(",DEMO=");
    Serial.println(demo_mode);
  }

  // === Blink Upon Recieving ===
  if (ledBlinking && (millis() - ledOnTime >= LED_DURATION_MS)) {
  digitalWrite(STATUS_LED_PIN, LOW);
  ledBlinking = false;
  }

}


void enterSafeState() {
  valve1_open = false;
  valve2_open = false;
  mfc_set_sccm = 0.0;
  hv_set_kv = 0.0;
  safe_state = true;
}

void handleCommand(String cmd) {
  if (cmd.startsWith("ECHO:")) {
    String payload = cmd.substring(5);
    Serial.println("ECHO:" + payload);
    return;  // Skip the rest of the handler
  }

  Serial.println("CMD RECEIVED: " + cmd);
  digitalWrite(STATUS_LED_PIN, HIGH);
  ledBlinking = true;
  ledOnTime = millis();
  Serial.println("CMD:" + cmd);
  cmd.trim();

  if (cmd.startsWith("SET_MFC:")) {
    mfc_set_sccm = cmd.substring(8).toFloat();
    float debug_voltage = constrain(mfc_set_sccm / 100.0 * 255.0, 0, 255);
    Serial.print("DEBUG: MFC set to ");
    Serial.print(mfc_set_sccm);
    Serial.print(", PWM value: ");
    Serial.println((int)debug_voltage);
    
  } else if (cmd.startsWith("SET_HV:")) {
    hv_set_kv = cmd.substring(7).toFloat();

  } else if (cmd == "SAFE_STATE") {
    enterSafeState();

  } else if (cmd == "DEMO_MODE_ON") {
    demo_mode = true;

  } else if (cmd == "DEMO_MODE_OFF") {
    demo_mode = false;

  } else if (cmd == "FUEL_CLOSE") {
    digitalWrite(FUEL_PIN, HIGH);

  } else if (cmd == "FUEL_OPEN") {
    digitalWrite(FUEL_PIN, LOW);

  } else if (cmd == "VACUUM_CLOSE") {
    digitalWrite(VACUUM_PIN, HIGH);

  } else if (cmd == "VACUUM_OPEN") {
    digitalWrite(VACUUM_PIN, LOW);

  } else {
    Serial.println("ERR:UNKNOWN_CMD");
  }
}