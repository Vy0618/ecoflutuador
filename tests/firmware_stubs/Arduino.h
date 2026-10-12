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

inline uint32_t millis() { return testClock; }
inline void delay(uint32_t amount) { testClock += amount; }
template <typename T> T constrain(T value, T low, T high) {
  return min(max(value, low), high);
}
inline long map(long value, long low, long high, long outLow, long outHigh) {
  return (value - low) * (outHigh - outLow) / (high - low) + outLow;
}
inline bool ledcAttach(uint8_t, uint32_t, uint8_t) { return true; }
inline double ledcSetup(uint8_t, uint32_t frequency, uint8_t) { return frequency; }
inline void ledcAttachPin(uint8_t, uint8_t) {}
inline bool ledcWrite(uint8_t output, uint32_t duty) {
  testDuty[output] = duty;
  return true;
}

class FakeSerial {
 public:
  std::deque<char> input;
  std::string output;
  void begin(uint32_t) {}
  int available() { return input.size(); }
  int read() {
    char byte = input.front();
    input.pop_front();
    ++testClock;
    return byte;
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
