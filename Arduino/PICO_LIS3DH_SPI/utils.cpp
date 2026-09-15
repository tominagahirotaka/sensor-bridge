#include "utils.h"

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
// SPI (LIS3DH)
// Control byte: bit7=R/W(1=read), bit6=MS(1=multi-byte/auto-increment), bits5-0=register address.
// LIS3DH SPI is Mode 3 (CPOL=1, CPHA=1) per the datasheet -- not yet confirmed on real hardware.
//
static SPISettings lis3dh_spi_settings(1000000, MSBFIRST, SPI_MODE3);  // 1MHz, conservative

void spi_begin(uint8_t cs_pin, uint8_t sck_pin, uint8_t mosi_pin, uint8_t miso_pin) {
  pinMode(cs_pin, OUTPUT);
  digitalWrite(cs_pin, HIGH);
  SPI.setSCK(sck_pin);
  SPI.setTX(mosi_pin);
  SPI.setRX(miso_pin);
  SPI.begin();
}

uint8_t spi_read_reg(uint8_t cs_pin, uint8_t reg) {
  uint8_t val;
  SPI.beginTransaction(lis3dh_spi_settings);
  digitalWrite(cs_pin, LOW);
  SPI.transfer(0x80 | (reg & 0x3F));
  val = SPI.transfer(0x00);
  digitalWrite(cs_pin, HIGH);
  SPI.endTransaction();
  return val;
}

void spi_write_reg(uint8_t cs_pin, uint8_t reg, uint8_t val) {
  SPI.beginTransaction(lis3dh_spi_settings);
  digitalWrite(cs_pin, LOW);
  SPI.transfer(reg & 0x3F);
  SPI.transfer(val);
  digitalWrite(cs_pin, HIGH);
  SPI.endTransaction();
}

void spi_read_regs(uint8_t cs_pin, uint8_t start_reg, uint8_t *buf, uint8_t len) {
  SPI.beginTransaction(lis3dh_spi_settings);
  digitalWrite(cs_pin, LOW);
  SPI.transfer(0xC0 | (start_reg & 0x3F));
  for (uint8_t i = 0; i < len; i++) buf[i] = SPI.transfer(0x00);
  digitalWrite(cs_pin, HIGH);
  SPI.endTransaction();
}
//
//
void bin_write(uint32_t tm, uint8_t *b_sig, uint16_t len)
{ utime utm = { tm }; Serial.write(utm.binary, 4); Serial.write(b_sig, len); }
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
  for (auto itr = v.begin(); itr != v.end(); ++itr) tmp.push_back(std::stof(*itr));
  return tmp;
}
//
// reference https://progsennin.com/c_arduino_strcpy/1111/
// from https://marycore.jp/prog/cpp/std-string-split/
//
vector<string> split(const string& s, const string& separator, bool ignore_empty = 0, bool split_empty = 0) {
  struct {
    auto len(const std::string&             s) { return s.length(); }
    auto len(const std::string::value_type* p) { return p ? std::char_traits<std::string::value_type>::length(p) : 0; }
    auto len(const std::string::value_type  c) { return c == std::string::value_type() ? 0 : 1; }
  } util;

  if (s.empty()) {
    if (!split_empty || util.len(separator)) return {""};
    return {};
  }

  auto v = std::vector<std::string>();
  auto n = static_cast<std::string::size_type>(util.len(separator));
  if (n == 0) {
    if (!split_empty) return {s};
    for (auto&& c : s) v.emplace_back(1, c);
    return v;
  }

  auto p = std::string::size_type(0);
  while (1) {
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
    delay(10);
  }
  Serial.println((s.substr(count*len) + "@@").c_str());  delay(10);
}
