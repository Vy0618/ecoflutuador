#ifdef ECO_FREESTANDING_TEST
#include <math.h>
#undef isfinite
#define isfinite(value) __builtin_isfinite(value)
#endif
#include "../../sensors_v4.h"
#include <assert.h>
#include <stdio.h>

// Optional minimal Windows host harness: avoids building an entire C runtime
// when Zig is used on a machine without a native compiler installation.
#ifdef ECO_FREESTANDING_TEST
extern "C" __declspec(dllimport) void __stdcall ExitProcess(unsigned int);
#undef assert
#define assert(condition) ((condition) ? (void)0 : ExitProcess(__LINE__))
#define puts(message) ((void)0)
#define main runTests
#endif

UltrasonicSensor calibrated() {
  UltrasonicSensor u({2,400,15,10,0.005f,30,3,5});
  for (int i=0;i<34;i++) assert(u.update(60)==0);
  assert(u.calibrated && u.baseline==60);
  return u;
}
int main() {
  ControlLease lease(1500);
  lease.command('w',100);
  assert(!lease.expired(1599) && lease.expired(1600));
  assert(!lease.renew('w',1600)); // late heartbeat cannot resume
  lease.stop(); assert(!lease.renew('w',1601));
  lease.command('a',2000); assert(!lease.renew('d',2100));
  assert(lease.renew('a',2500) && !lease.expired(3999));
  lease.command('w',UINT32_MAX-100);
  assert(!lease.expired(100) && lease.expired(1400));
  CommandFramer framer;
  for(int i=0;i<32;i++) assert(framer.feed('x')==CommandFramer::NONE);
  assert(framer.feed('x')==CommandFramer::OVERFLOW);
  assert(framer.feed('w')==CommandFramer::NONE);
  assert(framer.feed('\n')==CommandFramer::NONE);
  assert(framer.feed('s')==CommandFramer::NONE);
  assert(framer.feed('\r')==CommandFramer::NONE);
  assert(framer.feed('\n')==CommandFramer::LINE && framer.data[0]=='s' && framer.data[1]==0);
  auto u=calibrated();
  for (int i=0;i<100;i++) assert(u.update(60+(i%3-1)*0.5f)==0);
  assert(!u.start && fabs(u.baseline-60)<0.1);
  assert(u.update(40)==0); // isolated dip rejected by median
  for (int i=0;i<5;i++) assert(u.update(60)==0);
  float baseline=u.baseline;
  assert(u.update(40)==0); assert(u.update(40)==0); // median still water
  assert(u.update(40)==0); assert(u.update(40)==0); // confirmations 1,2
  assert(u.update(40)==1); // confirmation 3
  for (int i=0;i<100;i++) assert(u.update(40)==0);
  assert(u.start && u.baseline==baseline);
  assert(u.update(0)==0 && !u.valid && u.start);
  assert(u.update(NAN)==0 && !u.valid);
  assert(u.update(401)==0 && !u.valid);
  assert(u.update(1)==0 && !u.valid);
  for (int i=0;i<6;i++) assert(u.update(60)==0); // 2 median fill + 4 free
  assert(u.update(60)==-1 && !u.start); // fifth filtered free
  for (int i=0;i<10;i++) assert(u.update(60)==0);
  auto v=calibrated();
  for(int i=0;i<4;i++) v.update(40);
  v.update(0); // invalid breaks confirmations
  assert(v.update(40)==0 && v.update(40)==0 && v.update(40)==1);
  const float frozen=v.baseline;
  for(int i=0;i<10;i++) assert(v.update(48)==0); // hysteresis band
  assert(v.start && v.baseline==frozen);
  auto drift=calibrated();
  for(int i=0;i<100;i++) drift.update(62);
  assert(drift.baseline>60 && drift.baseline<62);

  NetSensor n({50,8000,5000});
  assert(n.update(true,100)==0);
  assert(n.update(false,120)==0); // bounce
  assert(n.update(true,200)==0);
  assert(n.update(true,250)==NetSensor::BLOCKED);
  assert(n.update(true,500)==0);
  assert(n.update(false,600)==0);
  assert(n.update(false,650)==(NetSensor::PASS|NetSensor::CLEAR));
  assert(n.passageCount==1 && !n.blocked);
  assert(n.update(false,1000)==0 && n.passageCount==1);
  n.update(true,2000);
  assert(n.update(true,2050)==NetSensor::BLOCKED);
  assert(n.update(true,10049)==0);
  assert(n.update(true,10050)==NetSensor::FULL && n.fullSuspected);
  assert(n.update(true,12000)==0 && n.passageCount==1);
  n.update(false,12100); n.update(false,12150);
  assert(n.update(false,17149)==0);
  assert(n.update(false,17150)==NetSensor::CLEAR && !n.fullSuspected);
  assert(n.update(false,18000)==0);
  puts("Sensor V4 C++ assertions passed (no hardware)");
  return 0;
}

#ifdef ECO_FREESTANDING_TEST
#undef main
extern "C" void mainCRTStartup() { ExitProcess(runTests()); }
#endif
