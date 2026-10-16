#pragma once
#include <algorithm>
#include <cstdint>
#include <deque>
#include <sstream>
#include <string>

using std::max;
using std::min;
inline uint32_t testClock = 0;
inline uint32_t testDuty[64] = {};
inline uint32_t testPwmCalls = 0;
inline uint32_t testDetachCalls = 0;
inline bool testPwmFailures[64] = {};
inline bool testPwmAttached[64] = {};
inline constexpr uint32_t SERIAL_8N1 = 1;
inline constexpr uint8_t INPUT = 0;
inline constexpr uint8_t OUTPUT = 1;
inline constexpr uint8_t LOW = 0;
inline constexpr uint8_t HIGH = 1;
inline uint8_t testPinModes[64] = {};
inline uint32_t testPinModeCalls[64] = {};
inline uint8_t testDigitalValues[64] = {};
inline unsigned long testEchoDuration = 0;
inline uint32_t testPulseCalls = 0;
inline uint32_t testPulseDelayMs = 0;
inline uint8_t testPulsePin = 0;
inline uint8_t testPulseState = LOW;
inline unsigned long testPulseTimeout = 0;

inline uint32_t millis() { return testClock; }
inline void delay(uint32_t amount) { testClock += amount; }
inline void delayMicroseconds(uint32_t) {}
inline void pinMode(uint8_t pin, uint8_t mode) {
  testPinModes[pin] = mode;
  ++testPinModeCalls[pin];
}
inline void digitalWrite(uint8_t pin, uint8_t value) { testDigitalValues[pin] = value; }
inline unsigned long pulseIn(uint8_t pin, uint8_t state, unsigned long timeout) {
  ++testPulseCalls;
  testPulsePin = pin;
  testPulseState = state;
  testPulseTimeout = timeout;
  testClock += testPulseDelayMs;
  return testEchoDuration;
}
template <typename T> T constrain(T value, T low, T high) {
  return min(max(value, low), high);
}
inline long map(long value, long low, long high, long outLow, long outHigh) {
  return (value - low) * (outHigh - outLow) / (high - low) + outLow;
}
inline bool ledcAttach(uint8_t pin, uint32_t, uint8_t) {
  ++testPwmCalls;
  if (testPwmFailures[pin]) return false;
  testPwmAttached[pin] = true;
  return true;
}
inline double ledcSetup(uint8_t channel, uint32_t frequency, uint8_t) {
  ++testPwmCalls;
  return testPwmFailures[channel] ? 0 : frequency;
}
inline void ledcAttachPin(uint8_t pin, uint8_t) {
  ++testPwmCalls;
  testPwmAttached[pin] = true;
}
inline bool ledcDetach(uint8_t pin) {
  ++testDetachCalls;
  testPwmAttached[pin] = false;
  return true;
}
inline void ledcDetachPin(uint8_t pin) {
  ++testDetachCalls;
  testPwmAttached[pin] = false;
}
inline bool ledcWrite(uint8_t output, uint32_t duty) {
  ++testPwmCalls;
  testDuty[output] = duty;
  return true;
}

class FakeSerial {
 public:
  std::deque<char> input;
  std::string output;
  uint32_t baud = 0;
  uint32_t config = SERIAL_8N1;
  int8_t rxPin = -1;
  int8_t txPin = -1;
  void begin(uint32_t speed, uint32_t format = SERIAL_8N1,
             int8_t rx = -1, int8_t tx = -1) {
    baud = speed;
    config = format;
    rxPin = rx;
    txPin = tx;
  }
  int available() { return input.size(); }
  int read() {
    char byte = input.front();
    input.pop_front();
    ++testClock;
    return byte;
  }
  size_t write(const char* message) {
    output += message;
    return std::string(message).size();
  }
  template <typename T> void print(const T& value) {
    std::ostringstream stream;
    stream << value;
    output += stream.str();
  }
  template <typename T> void println(const T& value) {
    print(value);
    output += '\n';
  }
};
inline FakeSerial Serial;
inline FakeSerial Serial2;
