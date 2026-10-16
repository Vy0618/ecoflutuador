#pragma once
#include <cstdint>
#include <iomanip>
#include <sstream>
#include <string>
#include "Wire.h"

inline constexpr uint8_t SSD1306_WHITE = 1;
inline constexpr uint8_t SSD1306_SWITCHCAPVCC = 2;

class Adafruit_SSD1306 {
 public:
  int width;
  int height;
  uint8_t address = 0;
  bool reinitializeWire = true;
  bool initialize = true;
  std::string buffer;
  std::string shown;
  Adafruit_SSD1306(int w, int h, FakeWire*, int) : width(w), height(h) {}
  bool begin(uint8_t, uint8_t target, bool, bool periphBegin) {
    address = target;
    reinitializeWire = periphBegin;
    return initialize;
  }
  void clearDisplay() { buffer.clear(); }
  void setTextColor(uint8_t) {}
  void setTextSize(uint8_t) {}
  void setCursor(int, int) {}
  void setTextWrap(bool) {}
  void display() { shown = buffer; }
  template <typename T> void print(const T& value) {
    std::ostringstream stream;
    stream << value;
    buffer += stream.str();
  }
  template <typename T> void println(const T& value) {
    print(value);
    buffer += '\n';
  }
  void print(float value, int decimals) {
    std::ostringstream stream;
    stream << std::fixed << std::setprecision(decimals) << value;
    buffer += stream.str();
  }
};
