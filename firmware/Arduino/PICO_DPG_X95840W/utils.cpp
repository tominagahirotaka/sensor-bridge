#include "utils.h"
#define ANALOGPIN0 26
// void software_reset() { asm volatile ("  jmp 0");  }  // Arduino Uno
void software_reset() { rp2040.reboot(); } // RP2040 Arduino core reboot (works across arduino-pico versions)
//
void exact_waiting(uint32_t t0_plus_thre) { uint32_t t1 = micros(); while (t1 < t0_plus_thre) t1 = micros(); }
//
//
// Serial
//
void begin_serial(uint32_t baud, uint16_t delay_time, char st[]) {
  char strbuf[64];
  Serial.begin(baud); while(!Serial){;} delay(delay_time);
  sprintf(strbuf, ":%s:@@", st); Serial.println(strbuf);
}
//
// i2c
//
void i2c_begin(TwoWire& wire, uint8_t SDA)
{ wire.setSDA(SDA); wire.setSCL(SDA + 1); wire.begin(); }
void i2c_read(TwoWire wire, uint8_t Addr, uint8_t dat[], uint8_t num)
{ wire.requestFrom(Addr, (uint8_t)num);          //while (wire.available() != num);
  for (int i = 0; i < num; i++) dat[i] = wire.read();}
int i2c_write1(TwoWire wire, uint8_t Addr, uint8_t dat)      // Success return 0, Error return 1-4
{ wire.beginTransmission(Addr); wire.write(dat); return wire.endTransmission();}
int i2c_write2(TwoWire wire, uint8_t Addr, uint16_t data)    // Success return 0, Error return 1-4
{ wire.beginTransmission(Addr); wire.write(data >> 8); wire.write(data & 0xFF); return wire.endTransmission();}

bool i2c_read_crc8(TwoWire wire, uint8_t addr, vector<uint16_t>& vec, uint16_t num_data) {
  uint8_t data[32];
  uint8_t get_data_size = (sizeof(uint16_t) + 1) * num_data ;
  i2c_read(wire, addr, data, get_data_size);  // 0,1 temperature & 2.CRC &  3,4 humidity & 5.CRC
  for (uint8_t i=0; i < num_data; ++i) if (data[2 + 3*i] != crc8(data + 3*i) ) return false;  // crc check
  for (uint8_t i=0; i < num_data; ++i) vec[i] = (data[3*i]<<8) + data[3*i+1];                 // load data
  return true;
}
//
// For Calibrating
//
// Bisection-search calibration step for one channel. `val` is adjusted
// toward the [range_min, range_max] target band based on the just-measured
// `range`, and the caller's [lo, hi] search interval narrows every call
// (the same monotonic assumption the old fixed-step version made: too-big
// range -> lower val; too-small range -> raise val). This converges in at
// most 8 calls across the full 0-255 range, versus the fixed +/-2 step it
// replaces, which could take over 100 calls to reach a distant target.
// Returns true once `range` is within the target band, or once the search
// interval has collapsed (lo > hi: no reachable value hits the target, so
// calibration stops adjusting this channel rather than looping forever).
bool tuning_step(uint16_t range, uint16_t range_max, uint16_t range_min,
                  int& val, int& lo, int& hi) {
  if (range >= range_min && range <= range_max) return true;
  if (range > range_max) hi = val - 1; else lo = val + 1;
  if (lo > hi) return true;
  val = (lo + hi) / 2;
  return false;
}

void analog_read(vector<int>& indx, uint16_t *sig, uint8_t ch, uint8_t avg) {
  for (auto i=0; i<ch; i++) sig[i] = 0;
  for (auto k=0; k<avg ; k++) for (auto i=0; i<ch; i++) sig[i] += analogRead(indx[i] + ANALOGPIN0);
  for (auto i=0; i<ch; i++) sig[i] /= avg;
}
//
void bin_write(uint32_t tm, uint8_t *b_sig, uint16_t len)
{ utime utm = { tm }; Serial.write(utm.binary, 4); Serial.write(b_sig, len); }
//
// X95840W digital potentiometer
//
uint8_t X95840W_read(vector<int> i2c_addr, vector<int>& dpm)
{ uint8_t Addr = (uint8_t)i2c_addr[0], num=(uint8_t)dpm.size(), error;
digitalWrite(17, HIGH);
  Wire.beginTransmission(Addr);
  Wire.write(0);
  error = Wire.endTransmission(false);  //(IMPORTANT) 'false' <- repeated start
  Wire.requestFrom(Addr, num);
  //while (Wire.available() != num);
  for (uint8_t i=0; i<num ; i++) dpm[i] = (int)Wire.read();
  digitalWrite(17, LOW);
  return error;}
uint8_t X95840W_write(vector<int> i2c_addr, vector<int>& dpm) {
  uint8_t Addr = (uint8_t)i2c_addr[0], error = 0;
  digitalWrite(17, HIGH);
  for (uint8_t i=0; i<dpm.size() ; i++) {
    Wire.beginTransmission(Addr);
    Wire.write(i); Wire.write((uint8_t)dpm[i]);
    error += Wire.endTransmission();
    delay(20);}
  digitalWrite(17, LOW);
  return error;}
//
// MCP4018 digital potentiometer
//
void i2c_2lines_begin(vector<int> i2c_pinno){i2c_begin(Wire,i2c_pinno[0]); i2c_begin(Wire1,i2c_pinno[1]);} // Wireの初期化(Pin設定)
void MCP4018_read(vector<int> i2c_addr, vector<uint8_t>& dpm)
{ uint8_t d0[2], d1[2]; i2c_read(Wire, i2c_addr[0], d0, 1); i2c_read(Wire1, i2c_addr[0], d1, 1);
  dpm[0] = d0[0]; dpm[1] = d1[0];}
void MCP4018_write(vector<int> i2c_addr, vector<uint8_t>& dpm)
{i2c_write1(Wire, i2c_addr[0], dpm[0]); i2c_write1(Wire1,i2c_addr[0], dpm[1]); }
//
int get_int(std::map<string, string>& mp, string key, int def_val)
{ return (mp.count(key))? std::stoi(mp[key]) : def_val; }

float get_float(std::map<string, string>& mp, string key, float def_val)
{ return (mp.count(key))? std::stof(mp[key]) : def_val; }

vector<int> get_int_list(std::map<string, string>& mp, string key, string def_val) {
  vector<int> tmp;
  vector<string> v = split((mp.count(key))? mp[key] : def_val, ",", 1, 0);
  for (auto itr = v.begin(); itr != v.end(); ++itr) tmp.push_back(std::stoi(*itr, nullptr, 0));
  return tmp;
}

vector<float> get_float_list(std::map<string, string>& mp, string key, string def_val) {
  vector<float> tmp;
  vector<string> v = split((mp.count(key))? mp[key] : def_val, ",", 1, 0);
  for (auto itr = v.begin(); itr != v.end(); ++itr) tmp.push_back(std::stof(*itr)); //, nullptr, 0.0));
  return tmp;
}
//
// reference https://progsennin.com/c_arduino_strcpy/1111/
// from https://marycore.jp/prog/cpp/std-string-split/
//template<class T> std::vector<std::string> split(const std::string& s, const T& separator, bool ignore_empty = 0, bool split_empty = 0) {
//
vector<string> split(const string& s, const string& separator, bool ignore_empty = 0, bool split_empty = 0) {
  struct {
    auto len(const std::string&             s) { return s.length(); }
    auto len(const std::string::value_type* p) { return p ? std::char_traits<std::string::value_type>::length(p) : 0; }
    auto len(const std::string::value_type  c) { return c == std::string::value_type() ? 0 : 1; /*return 1;*/ }
  } util;

  if (s.empty()) { /// empty string ///
    if (!split_empty || util.len(separator)) return {""};
    return {};
  }

  auto v = std::vector<std::string>();
  auto n = static_cast<std::string::size_type>(util.len(separator));
  if (n == 0) {    /// empty separator ///
    if (!split_empty) return {s};
    for (auto&& c : s) v.emplace_back(1, c);
    return v;
  }

  auto p = std::string::size_type(0);
  while (1) {      /// split with separator ///
    auto pos = s.find(separator, p);
    if (pos == std::string::npos) {
      if (ignore_empty && p - n + 1 == s.size()) break;
      v.emplace_back(s.begin() + p, s.end());
      break;
    }
    if (!ignore_empty || p != pos)
      v.emplace_back(s.begin() + p, s.begin() + pos);
    p = pos + n;
  }
  return v;
}

std::map<string, string> split_dict(const string& s, const string& sep1, const string& sep2) {
  std::map<string,string> dict;
  //Serial.print(s.size());
  //Serial.println(s.c_str());
  if (!s.size()) return dict;
  vector<string> v = split(s, sep1, 1, 0);

  for (auto itr = v.begin(); itr != v.end(); ++itr) {
    std::vector<std::string> tmp = split((*itr), sep2, 0 ,0);
    dict[tmp[0]] = tmp[1];
  }
  return dict;
}

// https://marycore.jp/prog/cpp/vector-join/
//
string join(const vector<string>& v, const string& delim) {
  std::string s;
  if (!v.empty()) {
    s += v[0];
    for (decltype(v.size()) i = 1, c = v.size(); i < c; ++i) {
      if (!delim.empty()) s += delim;
      s += v[i];
    }
  }
  return s;
}

string join_dict(const std::map<string, string>& mp, const string& delim1, const string& delim2) {
  vector<string> v;
 // Serial.print("mp.size()=");  Serial.println(mp.size());
  for (auto itr = mp.begin(); itr != mp.end(); ++itr) {
    string tmp = itr->first + delim2 + itr->second;
    v.push_back(tmp);
  }
  return join(v, delim1);
}
//
// Because Serial_Buffer_Size = 64
//
void serial_print_separate(const string& s) {
  uint8_t len = 56;
  uint8_t count= s.size()/len;
  for (uint16_t i = 0; i < count; ++i) {
    Serial.println((s.substr(i*len, len) + "@").c_str());
    delay(10);   // wait 10msec
  }
  Serial.println((s.substr(count*len) + "@@").c_str());  delay(10);
}
//
// crc
//
unsigned char table[256] = {
  0, 94, 188, 226, 97, 63, 221, 131, 194, 156, 126, 32, 163, 253, 31, 65, 157, 195, 33,
  127, 252, 162, 64, 30, 95, 1, 227, 189, 62, 96, 130, 220, 35, 125, 159, 193, 66, 28,
  254, 160, 225, 191, 93, 3, 128, 222, 60, 98, 190, 224, 2, 92, 223, 129, 99, 61, 124,
  34, 192, 158, 29, 67, 161, 255, 70, 24, 250, 164, 39, 121, 155, 197, 132, 218, 56,
  102, 229, 187, 89, 7, 219, 133, 103, 57, 186, 228, 6, 88, 25, 71, 165, 251, 120, 38,
  196, 154, 101, 59, 217, 135, 4, 90, 184, 230, 167, 249, 27, 69, 198, 152, 122, 36, 248,
  166, 68, 26, 153, 199, 37, 123, 58, 100, 134, 216, 91, 5, 231, 185, 140, 210, 48, 110,
  237, 179, 81, 15, 78, 16, 242, 172, 47, 113, 147, 205, 17, 79, 173, 243, 112, 46, 204,
  146, 211, 141, 111, 49, 178, 236, 14, 80, 175, 241, 19, 77, 206, 144, 114, 44, 109, 51,
  209, 143, 12, 82, 176, 238, 50, 108, 142, 208, 83, 13, 239, 177, 240, 174, 76, 18, 145,
  207, 45, 115, 202, 148, 118, 40, 171, 245, 23, 73, 8, 86, 180, 234, 105, 55, 213, 139,
  87, 9, 235, 181, 54, 104, 138, 212, 149, 203, 41, 119, 244, 170, 72, 22, 233, 183, 85,
  11, 136, 214, 52, 106, 43, 117, 151, 201, 74, 20, 246, 168, 116, 42, 200, 150, 21, 75,
  169, 247, 182, 232, 10, 84, 215, 137, 107, 53};
unsigned char crc8(const unsigned char * data) {
    unsigned char crc = 0xff;
    crc = table[reflect(data[0]) ^ crc]; crc = table[reflect(data[1]) ^ crc];
    return reflect(crc);
}
unsigned char reflect(unsigned char c) {
  unsigned char r = 0;
  for (int i = 0; i < 8; i++) { if (c & (1 << i)) { r = r | (1 << (7 - i)); }}
  return r;
}
