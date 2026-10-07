// Raspberry Pi Pico / Pico W (2x STMicroelectronics LIS3DH; 3-axis
// accelerometer, SPI, sharing one SPI0 bus with distinct CS pins)
// 2026/09/24
// H.Tominaga
//
// Two independent LIS3DH units, no other front end -- extracted from the
// LIS3DH-handling half of PICO_DPG_X95840W_LIS3DHx2.ino (which combines
// this with an unrelated X95840W PPG front end) for setups that just want
// two accelerometers and nothing else. See utils.h for the pin
// assignment.
//
// NOTE: The register map, SPI mode (Mode 3), and sensitivity tables below
// come from the public LIS3DH datasheet (STMicroelectronics DocID17530
// Rev 2) -- cross-checked directly against the PDF (Table 4, Table 10,
// Table 37, Section 8.16-8.18). This sketch has NOT been verified on real
// hardware (the combined circuit it was extracted from hasn't either --
// see README.md's hardware-verification matrix); this applies to Normal
// mode (hr_mode1/hr_mode2) equally -- see the g_per_count comment below
// for why its conversion factor doesn't need to differ from High-
// Resolution's despite being otherwise unverified. Before trusting any
// data, check that who_am_i_1 / who_am_i_2 (sent to the PC as parameters,
// and printed over Serial) read back 0x33 -- that alone confirms wiring,
// SPI mode, and CS handling are correct for each unit.
//
#include "utils.h"
char program_name[] = "LIS3DHx2";

uint32_t baud = 115200; //  9600; 19200; 38400; 57600;
uint32_t time0micros, time0millis, one_data_byte, real_time_interval, serial_time_interval, waiting_time0;    // 4byte
usignal usig;  // Union member sig[] is uint16_t & member binary[] is uint8_t
int ok=0;

//
std::map<string, string> params_from;  //  parameters from PC
std::map<string, string> params_to = { //  parameters to PC
    {"data_names", "x1,y1,z1,x2,y2,z2"}
};
uint8_t time_unit;
uint8_t spi_sck_pin, spi_mosi_pin, spi_miso_pin;
uint8_t cs_pin1, cs_pin2;
uint8_t odr1, fs1, odr2, fs2, hr_mode1, hr_mode2;
float g_per_count1, g_per_count2;

#define LIS3DH_WHO_AM_I        0x0F
#define LIS3DH_CTRL_REG1       0x20
#define LIS3DH_CTRL_REG4       0x23
#define LIS3DH_OUT_X_L         0x28
#define LIS3DH_WHO_AM_I_VALUE  0x33

// High-resolution mode sensitivity (mg per 12bit digit), indexed by fs (0=+-2g,1=+-4g,2=+-8g,3=+-16g)
const float HR_MG_PER_DIGIT[4] = {1.0, 2.0, 4.0, 12.0};
// Normal mode (10bit) sensitivity is exactly 4x HR's (datasheet Table 4).
// Documentation cross-check only -- NOT used in g_per_count below.
const float NORMAL_MG_PER_DIGIT[4] = {4.0, 8.0, 16.0, 48.0};

void initialSetupParam(char ch, string str){
  //
  // <- PC (Read parameters from PC)
  //
  params_from = split_dict(str, ";", "=");
  //
  time_unit    = get_int(params_from, "time_unit",     6);   // Time Unit (millis=3 or micros=6)
  spi_sck_pin  = get_int(params_from, "spi_sck_pin",  18);   // SPI0 default, shared by both units
  spi_mosi_pin = get_int(params_from, "spi_mosi_pin", 19);   // SPI0 default, shared by both units
  spi_miso_pin = get_int(params_from, "spi_miso_pin", 16);   // SPI0 default, shared by both units
  cs_pin1      = get_int(params_from, "spi_cs_pin1",  17);   // LIS3DH #1 (single-LIS3DH default -- free here, no X95840W using it)
  cs_pin2      = get_int(params_from, "spi_cs_pin2",  20);   // LIS3DH #2 (closest free pin to the GP16/17/18/19 cluster)
  odr1         = get_int(params_from, "odr1",          5);   // CTRL_REG1 ODR field; 5 = 100Hz
  fs1          = get_int(params_from, "fs1",           0);   // 0=+-2g, 1=+-4g, 2=+-8g, 3=+-16g
  odr2         = get_int(params_from, "odr2",          5);
  fs2          = get_int(params_from, "fs2",           0);
  // CTRL_REG4's HR bit: 1=High-Resolution (12bit, default), 0=Normal
  // (10bit, coarser but usable at a higher bandwidth -- ~149Hz HR vs
  // ~672Hz Normal at the same ODR, per the datasheet).
  hr_mode1     = get_int(params_from, "hr_mode1",       1);
  hr_mode2     = get_int(params_from, "hr_mode2",       1);

  if (ch == 'i') {
    spi_begin(spi_sck_pin, spi_mosi_pin, spi_miso_pin);
    spi_cs_setup(cs_pin1);
    spi_cs_setup(cs_pin2);
  }

  // Deviceにモードの設定cmd送り check existence (LIS3DH x2)
  uint8_t who1 = spi_read_reg(cs_pin1, LIS3DH_WHO_AM_I);
  uint8_t who2 = spi_read_reg(cs_pin2, LIS3DH_WHO_AM_I);
  Serial.print("who_am_i_1=0x"); Serial.println(who1, HEX);  // expect 0x33
  Serial.print("who_am_i_2=0x"); Serial.println(who2, HEX);  // expect 0x33
  spi_write_reg(cs_pin1, LIS3DH_CTRL_REG1, (odr1 << 4) | 0x07);                          // ODR, Zen/Yen/Xen=1
  spi_write_reg(cs_pin1, LIS3DH_CTRL_REG4,
               0x80 | ((fs1 & 0x03) << 4) | ((hr_mode1 & 0x01) << 3));                  // BDU=1, FS, HR
  spi_write_reg(cs_pin2, LIS3DH_CTRL_REG1, (odr2 << 4) | 0x07);
  spi_write_reg(cs_pin2, LIS3DH_CTRL_REG4,
               0x80 | ((fs2 & 0x03) << 4) | ((hr_mode2 & 0x01) << 3));

  // g_per_count is intentionally the same formula regardless of hr_mode:
  // HR/Normal both place their significant bits left-justified in the
  // same 16bit register (12bit+4 padding vs 10bit+6 padding), and
  // Normal's mg/digit is exactly 4x HR's at every FS setting, so
  // (mg/digit)/divisor is mode-invariant -- see PICO_LIS3DH_SPI.ino's
  // fuller comment on this (same reasoning, confirmed against the
  // datasheet, not yet against real Normal-mode hardware).
  g_per_count1 = (HR_MG_PER_DIGIT[fs1 & 0x03] / 1000.0) / 16.0;
  g_per_count2 = (HR_MG_PER_DIGIT[fs2 & 0x03] / 1000.0) / 16.0;
  //
  // Make parameters
  //
  params_to["endian"]    = "little";
  params_to["who_am_i_1"] = to_string(who1);
  params_to["who_am_i_2"] = to_string(who2);
  params_to["struct"]    = "time(u4:func0), x1(u2:func1), y1(u2:func1), z1(u2:func1), x2(u2:func2), y2(u2:func2), z2(u2:func2)";
  one_data_byte           = 4 + 3*2 + 3*2;
  float divisor = std::pow(10.0, float(time_unit));
  //                    [ (lambda,                                                           bit(max value), 'unit')]
  params_to["func"] = "[ (lambda tm:tm/" + to_string(divisor) + "," + to_string(4*8) + ", \'sec\'),"
                    + "  (lambda x:(x-65536 if x>=32768 else x)*" + to_string(g_per_count1) + "," + to_string(16) + ", \'g\'),"
                    + "  (lambda x:(x-65536 if x>=32768 else x)*" + to_string(g_per_count2) + "," + to_string(16) + ", \'g\')  ]";

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
  // faster than either sensor actually produces new samples (the slower of the two governs).
  const uint32_t odr_hz[10] = {0, 1, 10, 25, 50, 100, 200, 400, 1600, 1344};
  uint32_t odr1_interval_us = (odr1 < 10 && odr_hz[odr1] > 0) ? (1000000UL / odr_hz[odr1]) : 10000UL;
  uint32_t odr2_interval_us = (odr2 < 10 && odr_hz[odr2] > 0) ? (1000000UL / odr_hz[odr2]) : 10000UL;
  real_time_interval = std::max(std::max(odr1_interval_us, odr2_interval_us), serial_time_interval);
  params_to["one_data_byte"]         = to_string(one_data_byte);
  params_to["serial_time_interval"]  = to_string(serial_time_interval);
  params_to["real_time_interval"]    = to_string(real_time_interval);
  //
  // -> PC (Write parameters to PC)
  serial_print_separate(join_dict(params_to, ";", "="));
}

void sensor_read(uint16_t *sig) {
  spi_read_regs(cs_pin1, LIS3DH_OUT_X_L, (uint8_t*)&sig[0], 6);
  spi_read_regs(cs_pin2, LIS3DH_OUT_X_L, (uint8_t*)&sig[3], 6);
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
      case 'T':  // report on-chip temperature (die temp -- not the same as
                 // the crystal's own temperature; PC side only sends this
                 // while idle, between recordings, so it never perturbs a
                 // recording's sampling cadence)
        Serial.print("temp_c="); Serial.println(analogReadTemp(), 2); break;
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
      bin_write((time_unit==6)?(micros()-time0micros):(millis()-time0millis), usig.binary, 3*2*2);
      break;
  }
}
