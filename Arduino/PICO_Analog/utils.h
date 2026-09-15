// Raspberry PICO pins
//         [SCL,SDA]
// i2c0    [GP1,GP0],[GP5,GP4],[GP9,GP8],  [GP13,GP12],[GP17,GP16],[GP21,GP20]
// i2c1    [GP3,GP2],[GP7,GP6],[GP11,GP10],[GP15,GP14],[GP19,GP18],[GP27,GP26]
// analog0 26
//
#include <map>
#include <string>
#include <vector>
#include "Arduino.h"
#include <Wire.h>
using namespace std;
typedef union { uint32_t time;    uint8_t binary[4];  } utime;
typedef union { uint16_t sig[16]; uint8_t binary[32]; } usignal;

void software_reset();
//
void exact_waiting(uint32_t);
//
void begin_serial(uint32_t, uint16_t, char st[]);
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
void X95840W_read(vector<int>, vector<uint8_t>&);
void X95840W_write(vector<int>, vector<uint8_t>&);
//
void i2c_2lines_begin(vector<int>);
void MCP4018_read(vector<int>, vector<uint8_t>&);
void MCP4018_write(vector<int>, vector<uint8_t>&);
//
void tuning(vector<uint16_t>, vector<uint16_t>, vector<uint16_t>, vector<uint8_t>&);
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
