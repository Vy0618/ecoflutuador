#pragma once
#include <stdint.h>
#include <math.h>

// Hardware-independent logic, also compiled by the host tests.
struct UltrasonicConfig {
  float minCm, maxCm, activationCm, releaseCm, baselineAlpha;
  uint16_t calibrationSamples;
  uint8_t confirmations, clearSamples;
};
class UltrasonicSensor {
 public:
  explicit UltrasonicSensor(UltrasonicConfig c) : cfg(c) {}
  bool valid = false, calibrated = false, start = false;
  float distance = 0, baseline = 0, delta = 0;
  // Returns +1/-1 only at START edges. Invalid samples break consecutive runs.
  int update(float cm) {
    valid = isfinite(cm) && cm > 0 && cm >= cfg.minCm && cm <= cfg.maxCm;
    if (!valid) { activeRun = clearRun = 0; return 0; }
    history[index++ % 5] = cm;
    if (count < 5) ++count;
    float sorted[5];
    for (uint8_t i=0; i<count; ++i) sorted[i] = history[i];
    for (uint8_t i=1; i<count; ++i)
      for (uint8_t j=i; j>0 && sorted[j]<sorted[j-1]; --j) {
        float t=sorted[j]; sorted[j]=sorted[j-1]; sorted[j-1]=t;
      }
    distance = sorted[count/2];
    if (count < 5) return 0;
    if (!calibrated) {
      baseline += (distance-baseline) / ++calibrationCount;
      calibrated = calibrationCount >= cfg.calibrationSamples;
      delta = baseline-distance;
      return 0;
    }
    delta = baseline-distance;
    if (!start) {
      activeRun = delta >= cfg.activationCm ? activeRun+1 : 0;
      if (activeRun >= cfg.confirmations) { start=true; activeRun=0; return 1; }
      // Freeze even during pending object confirmation and hysteresis band.
      if (delta < cfg.releaseCm && baseline-cm < cfg.releaseCm)
        baseline += cfg.baselineAlpha*(distance-baseline);
    } else {
      clearRun = delta <= cfg.releaseCm ? clearRun+1 : 0;
      if (clearRun >= cfg.clearSamples) { start=false; clearRun=0; return -1; }
    }
    delta = baseline-distance;
    return 0;
  }
 private:
  UltrasonicConfig cfg;
  float history[5] = {};
  uint32_t index = 0;
  uint16_t calibrationCount = 0;
  uint8_t count = 0, activeRun = 0, clearRun = 0;
};

struct NetConfig { uint32_t debounceMs, fullMs, clearMs; };
class NetSensor {
 public:
  enum Event { BLOCKED=1, PASS=2, FULL=4, CLEAR=8 };
  explicit NetSensor(NetConfig c) : cfg(c) {}
  bool blocked=false, fullSuspected=false;
  uint32_t passageCount=0;
  uint32_t blockedMs(uint32_t now) const { return blocked ? now-blockedSince : 0; }
  unsigned update(bool raw, uint32_t now) {
    unsigned events=0;
    if (raw != previousRaw) { previousRaw=raw; rawSince=now; }
    if (raw != blocked && now-rawSince >= cfg.debounceMs) {
      if (raw) { blocked=true; blockedSince=now; events|=BLOCKED; }
      else {
        if (now-blockedSince < cfg.fullMs) { ++passageCount; events|=PASS; }
        else if (!fullSuspected) { fullSuspected=true; events|=FULL; }
        blocked=false; freeSince=now;
        if (!fullSuspected) events|=CLEAR;
      }
    }
    if (blocked && !fullSuspected && now-blockedSince >= cfg.fullMs) {
      fullSuspected=true; events|=FULL;
    }
    if (!blocked && !raw && fullSuspected && now-freeSince >= cfg.clearMs) {
      fullSuspected=false; events|=CLEAR;
    }
    // A raw interruption also restarts the continuous-free timer.
    if (raw) freeSince=now;
    return events;
  }
 private:
  NetConfig cfg;
  bool previousRaw=false;
  uint32_t rawSince=0, blockedSince=0, freeSince=0;
};

// A heartbeat renews only the already accepted command, never starts movement.
class ControlLease {
 public:
  explicit ControlLease(uint32_t timeout) : timeoutMs(timeout) {}
  void command(char value, uint32_t now) { current=value; since=now; }
  bool renew(char value, uint32_t now) {
    if (expired(now) || value != current) return false;
    since=now;
    return true;
  }
  bool expired(uint32_t now) const {
    return current != 's' && uint32_t(now-since) >= timeoutMs;
  }
  void stop() { current='s'; }
  char current='s';
 private:
  uint32_t timeoutMs, since=0;
};

// Drop the entire oversized record, including any valid-looking suffix.
class CommandFramer {
 public:
  enum Result { NONE, LINE, OVERFLOW };
  Result feed(char c) {
    if (c == '\r') return NONE;
    if (c == '\n') {
      if (discarding) { discarding=false; length=0; return NONE; }
      data[length]='\0'; length=0; return LINE;
    }
    if (discarding) return NONE;
    if (length == 32) { length=0; discarding=true; return OVERFLOW; }
    data[length++]=c;
    return NONE;
  }
  char data[33] = {};
 private:
  uint8_t length=0;
  bool discarding=false;
};
