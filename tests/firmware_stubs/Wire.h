#pragma once
#include <cstdint>

class FakeWire {
 public:
  int sda = -1;
  int scl = -1;
  void begin(int first, int second) { sda = first; scl = second; }
};
inline FakeWire Wire;
