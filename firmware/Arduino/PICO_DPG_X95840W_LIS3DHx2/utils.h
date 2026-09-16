// Raspberry Pi Pico / Pico W pins used by this combined sketch:
//   GP17        X95840W I2C transaction enable/latch (digitalWrite HIGH/LOW; see X95840W_read/write)
//   GP20/21     I2C (Wire): SDA/SCL for the X95840W digital potentiometer
//   GP26/27/28  ADC (analog_read): 3 analog channels
//   GP16/18/19  SPI0 bus (shared): MISO/SCK/MOSI for both LIS3DH units
//   GP22, GP2   SPI CS: LIS3DH #1, LIS3DH #2 (each configurable via .ini)
// None of the above overlap with GP23/24/25/29, which Pico W reserves for its wireless chip.
//
#include <map>
#include <string>
#include <vector>
#include "Arduino.h"
#include <Wire.h>
#include <SPI.h>
using namespace std;
typedef union { uint32_t time;    uint8_t binary[4];  } utime;
typedef union { uint16_t sig[16]; uint8_t binary[32]; } usignal;

void software_reset();
//
void exact_waiting(uint32_t);
//
void begin_serial(uint32_t, uint16_t, char st[]);
// Re-announces the board (same message as begin_serial's initial one) on
// every new host connection detected in loop(), not just the very first one
// at boot -- so a host reconnecting to an already-running, un-rebooted board
// (e.g. after a previous get.py process was killed instead of cleanly quit,
// which is the only path that calls software_reset()) still gets a handshake
// response instead of waiting forever.
void check_serial_reconnect(char st[], int &ok);
//
void i2c_begin(TwoWire&, uint8_t);
void i2c_read(TwoWire, uint8_t, uint8_t dat[], uint8_t);
int i2c_write1(TwoWire, uint8_t, uint8_t);
int i2c_write2(TwoWire, uint8_t, uint16_t);
bool i2c_read_crc8(TwoWire, uint8_t, vector<uint16_t>& , uint16_t);
//
void analog_read(vector<int>&, uint16_t *sig, uint8_t, uint8_t);
void bin_write(uint32_t, uint8_t *b_sig, uint16_t);
//
uint8_t X95840W_read(vector<int>, vector<int>&);
uint8_t X95840W_write(vector<int>, vector<int>&);
//
void i2c_2lines_begin(vector<int>);
void MCP4018_read(vector<int>, vector<uint8_t>&);
void MCP4018_write(vector<int>, vector<uint8_t>&);
//
bool tuning_step(uint16_t, uint16_t, uint16_t, int&, int&, int&);
//
// SPI (LIS3DH). Register map/mode taken from the public LIS3DH datasheet;
// not yet verified against real hardware. SCK/MOSI/MISO are a single shared
// bus (spi_begin() sets them once); CS is passed per-call so multiple
// LIS3DH units can share the bus with distinct CS pins.
//
void spi_begin(uint8_t sck_pin, uint8_t mosi_pin, uint8_t miso_pin);
void spi_cs_setup(uint8_t cs_pin);
uint8_t spi_read_reg(uint8_t cs_pin, uint8_t reg);
void spi_write_reg(uint8_t cs_pin, uint8_t reg, uint8_t val);
void spi_read_regs(uint8_t cs_pin, uint8_t start_reg, uint8_t *buf, uint8_t len);
//
int   get_int(std::map<string, string>&, string, int);
float get_float(std::map<string, string>& , string, float);
vector<int> get_int_list(std::map<string, string>&, string, string);
vector<float> get_float_list(std::map<string, string>&, string, string);
//
vector<string> split(const string&, const string&, bool, bool);
std::map<string, string> split_dict(const string&, const string&, const string&);

string join(const vector<string>&, const string&);
string join_dict(const std::map<string, string>&, const string&, const string&);
void serial_print_separate(const string&);

unsigned char crc8(const unsigned char *);
unsigned char reflect(unsigned char);
