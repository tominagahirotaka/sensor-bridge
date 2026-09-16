// Raspberry Pi Pico / Pico W pins
// Default SPI0: SCK=GP18, MOSI(TX)=GP19, MISO(RX)=GP16, CS=GP17 (CS is configurable per-device)
// Pico W reserves GP23/24/25/29 for the onboard wireless chip -- none of the above overlap.
//
#include <map>
#include <string>
#include <vector>
#include "Arduino.h"
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
// SPI (LIS3DH). Register map/mode taken from the public LIS3DH datasheet;
// not yet verified against real hardware.
//
void spi_begin(uint8_t cs_pin, uint8_t sck_pin, uint8_t mosi_pin, uint8_t miso_pin);
uint8_t spi_read_reg(uint8_t cs_pin, uint8_t reg);
void spi_write_reg(uint8_t cs_pin, uint8_t reg, uint8_t val);
void spi_read_regs(uint8_t cs_pin, uint8_t start_reg, uint8_t *buf, uint8_t len);
//
void bin_write(uint32_t, uint8_t *b_sig, uint16_t);
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
