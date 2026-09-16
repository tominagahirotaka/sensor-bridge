// Raspberry Pi Pico / Pico W (STMicroelectronics LIS3DH; 3-axis accelerometer, SPI)
// 2026/09/13
// H.Tominaga
//
// NOTE: The register map, SPI mode (Mode 3), and high-resolution-mode
// sensitivity table below come from the public LIS3DH datasheet. This
// sketch has NOT been verified on real hardware. Before trusting any data,
// check that who_am_i (sent to the PC as a parameter, and printed over
// Serial) reads back 0x33 -- that alone confirms wiring, SPI mode, and CS
// handling are correct.
//
#include "utils.h"
char program_name[] = "LIS3DH";

uint32_t baud = 115200; //  9600; 19200; 38400; 57600;
uint32_t time0micros, time0millis, one_data_byte, real_time_interval, serial_time_interval, waiting_time0;    // 4byte
usignal usig;  // Union member sig[] is uint16_t & member binary[] is uint8_t
int ok=0;

//
std::map<string, string> params_from;  //  parameters from PC
std::map<string, string> params_to = { //  parameters to PC
    {"data_names", "x,y,z"}
};
uint8_t time_unit;
uint8_t cs_pin, sck_pin, mosi_pin, miso_pin;
uint8_t odr, fs;
float g_per_count;

#define LIS3DH_WHO_AM_I        0x0F
#define LIS3DH_CTRL_REG1       0x20
#define LIS3DH_CTRL_REG4       0x23
#define LIS3DH_OUT_X_L         0x28
#define LIS3DH_WHO_AM_I_VALUE  0x33

// High-resolution mode sensitivity (mg per 12bit digit), indexed by fs (0=+-2g,1=+-4g,2=+-8g,3=+-16g)
const float HR_MG_PER_DIGIT[4] = {1.0, 2.0, 4.0, 12.0};

void initialSetupParam(char ch, string str){
  //
  // <- PC (Read parameters from PC)
  //
  params_from = split_dict(str, ";", "=");
  //
  time_unit = get_int(params_from, "time_unit",     6);   // Time Unit (millis=3 or micros=6)
  cs_pin    = get_int(params_from, "spi_cs_pin",   17);   // chip select (active low)
  sck_pin   = get_int(params_from, "spi_sck_pin",  18);   // SPI0 default
  mosi_pin  = get_int(params_from, "spi_mosi_pin", 19);   // SPI0 default (TX)
  miso_pin  = get_int(params_from, "spi_miso_pin", 16);   // SPI0 default (RX)
  odr       = get_int(params_from, "odr",           5);   // CTRL_REG1 ODR field; 5 = 100Hz
  fs        = get_int(params_from, "fs",            0);   // 0=+-2g, 1=+-4g, 2=+-8g, 3=+-16g

  if (ch == 'i') spi_begin(cs_pin, sck_pin, mosi_pin, miso_pin);

  // Deviceにモードの設定cmd送り check existence
  uint8_t who = spi_read_reg(cs_pin, LIS3DH_WHO_AM_I);
  Serial.print("who_am_i=0x"); Serial.println(who, HEX);  // expect 0x33
  spi_write_reg(cs_pin, LIS3DH_CTRL_REG1, (odr << 4) | 0x07);                  // ODR, Zen/Yen/Xen=1
  spi_write_reg(cs_pin, LIS3DH_CTRL_REG4, 0x80 | ((fs & 0x03) << 4) | 0x08);   // BDU=1, FS, HR=1

  g_per_count = (HR_MG_PER_DIGIT[fs & 0x03] / 1000.0) / 16.0;   // raw 16bit is a left-justified 12bit value
  //
  // Make parameters
  //
  params_to["endian"]   = "little";
  params_to["who_am_i"] = to_string(who);
  params_to["struct"]   = "time(u4:func0), x(u2:func1), y(u2:func1), z(u2:func1)";
  one_data_byte         = 4 + 3*2;
  float divisor = std::pow(10.0, float(time_unit));
  //                   [ (lambda,                                                          bit(max value), 'unit')]
  params_to["func"] = "[ (lambda tm:tm/" + to_string(divisor) + "," + to_string(4*8) + ", \'sec\'),"
                    + "  (lambda x:(x-65536 if x>=32768 else x)*" + to_string(g_per_count) + "," + to_string(16) + ", \'g\')  ]";

  //
  // -> PC (Write parameters to PC)
  //
  string str_params = join_dict(params_to, ";", "=") + ";" + join_dict(params_from, ";", "=");
  serial_print_separate(str_params);
}

void changeParam(char ch){
  //
  // Time intervals (serial...USB transfer limit, real...real transfer interval)
  //
  serial_time_interval  = int((one_data_byte * 8)  * 1000000.0 * 1.2/ baud);  // micro sec with a 20% margin added
  // Rough ODR(Hz) lookup for CTRL_REG1's ODR field (index 0-9); used only to avoid polling
  // faster than the sensor actually produces new samples.
  const uint32_t odr_hz[10] = {0, 1, 10, 25, 50, 100, 200, 400, 1600, 1344};
  uint32_t odr_interval_us = (odr < 10 && odr_hz[odr] > 0) ? (1000000UL / odr_hz[odr]) : 10000UL;
  real_time_interval = std::max(odr_interval_us, serial_time_interval);
  params_to["one_data_byte"]         = to_string(one_data_byte);
  params_to["serial_time_interval"]  = to_string(serial_time_interval);
  params_to["real_time_interval"]    = to_string(real_time_interval);
  //
  // -> PC (Write parameters to PC)
  serial_print_separate(join_dict(params_to, ";", "="));
}

void sensor_read(uint16_t *sig) {
  uint8_t buf[6];
  spi_read_regs(cs_pin, LIS3DH_OUT_X_L, buf, 6);
  sig[0] = (uint16_t)((buf[1] << 8) | buf[0]);   // x
  sig[1] = (uint16_t)((buf[3] << 8) | buf[2]);   // y
  sig[2] = (uint16_t)((buf[5] << 8) | buf[4]);   // z
}

void setup() { ok = 0; begin_serial(baud, 100, program_name); }

void loop() {
  check_serial_reconnect(program_name, ok);  // re-announce + auto-stop on host reconnect/disconnect
  string input;
  char ch;
  if (Serial.available() > 0) {
    delay(100);
    ch = Serial.read();
    switch (ch) {
      case 'i': // Initialize
      case 'a': // Initialize Again
        ok = 0;
        input = (Serial.readStringUntil('\n')).c_str();
        initialSetupParam(ch, input);
        delay(100);        // <- VERY IMPORTANT https://garchiving.com/high-speed-processing-of-serial-communication-in-arduino/
        break;
      case 's':  // Start
      case ';':
        ok = 1;
        changeParam(ch);
        delay(100);
        Serial.println("OK");   // written out as a Start marker
        waiting_time0 = micros();
        break;
      case 'r':  // stop(reset) -> 'r'
        ok = 0; break;
      case 'q':  // quit  -> 'q'
        ok = 0; software_reset(); break;
      default:
        ;
    }
    time0micros = micros(); time0millis = millis();
  }
  switch (ok) {
    case 0: break;
    case 1:
      exact_waiting(waiting_time0 + real_time_interval);
      waiting_time0 = micros();
      sensor_read(usig.sig);
      bin_write((time_unit==6)?(micros()-time0micros):(millis()-time0millis), usig.binary, 3*2);
      break;
  }
}
