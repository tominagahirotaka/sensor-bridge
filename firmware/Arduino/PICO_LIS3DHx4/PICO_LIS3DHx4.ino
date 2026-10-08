// Raspberry Pi Pico / Pico W (4x STMicroelectronics LIS3DH; 3-axis
// accelerometer, SPI, sharing one SPI0 bus with distinct CS pins)
// 2026/09/24
// H.Tominaga
//
// Same idea as PICO_LIS3DHx2/x3, one more unit. See utils.h for the pin
// assignment (GP17/GP20/GP21/GP22 for CS1/CS2/CS3/CS4).
//
// NOTE: not yet verified on real hardware -- needs four physical LIS3DH
// units and only one is currently on hand (see README.md's hardware-
// verification matrix); this applies to Normal/Low-power mode
// (operating_mode1-4) equally -- see the g_per_count comment below for
// why its conversion factor doesn't need to differ between any of the
// three modes despite being otherwise unverified (reasoning confirmed
// against the datasheet, STMicroelectronics DocID17530 Rev 2 -- Table 4,
// Table 10, Table 12, Table 31, Table 37, Section 8.16-8.18). Before
// trusting any data, check that who_am_i_1 through who_am_i_4 (sent to
// the PC as parameters, and printed over Serial) read back 0x33 -- that
// alone confirms wiring, SPI mode, and CS handling are correct for each
// unit.
//
// Naming note: the datasheet's own term for the 3-way HR/Normal/Low-power
// choice is "operating mode" (Section 3.2.1's title, Table 10's own
// heading) -- deliberately not "resolution_mode" or "power_mode", since
// neither axis alone describes all three: Normal and High-Resolution
// differ only in resolution (Table 12 shows identical current consumption
// at every ODR), while Low-power differs in both resolution AND power.
//
#include "utils.h"
char program_name[] = "LIS3DHx4";

uint32_t baud = 115200; //  9600; 19200; 38400; 57600;
uint32_t time0micros, time0millis, one_data_byte, real_time_interval, serial_time_interval, waiting_time0;    // 4byte
usignal usig;  // Union member sig[] is uint16_t & member binary[] is uint8_t
int ok=0;

//
std::map<string, string> params_from;  //  parameters from PC
std::map<string, string> params_to = { //  parameters to PC
    {"data_names", "x1,y1,z1,x2,y2,z2,x3,y3,z3,x4,y4,z4"}
};
uint8_t time_unit;
uint8_t spi_sck_pin, spi_mosi_pin, spi_miso_pin;
uint8_t cs_pin1, cs_pin2, cs_pin3, cs_pin4;
uint8_t odr1, fs1, odr2, fs2, odr3, fs3, odr4, fs4;
uint8_t operating_mode1, operating_mode2, operating_mode3, operating_mode4;
float g_per_count1, g_per_count2, g_per_count3, g_per_count4;

#define LIS3DH_WHO_AM_I        0x0F
#define LIS3DH_CTRL_REG1       0x20
#define LIS3DH_CTRL_REG4       0x23
#define LIS3DH_OUT_X_L         0x28
#define LIS3DH_WHO_AM_I_VALUE  0x33

// High-resolution mode sensitivity (mg per 12bit digit), indexed by fs (0=+-2g,1=+-4g,2=+-8g,3=+-16g)
const float HR_MG_PER_DIGIT[4] = {1.0, 2.0, 4.0, 12.0};
// Normal/Low-power sensitivity is exactly 4x/16x HR's (datasheet Table 4).
// Documentation cross-check only -- NOT used in g_per_count below.
const float NORMAL_MG_PER_DIGIT[4] = {4.0, 8.0, 16.0, 48.0};
const float LOW_POWER_MG_PER_DIGIT[4] = {16.0, 32.0, 64.0, 192.0};

void initialSetupParam(char ch, string str){
  //
  // <- PC (Read parameters from PC)
  //
  params_from = split_dict(str, ";", "=");
  //
  time_unit    = get_int(params_from, "time_unit",     6);   // Time Unit (millis=3 or micros=6)
  spi_sck_pin  = get_int(params_from, "spi_sck_pin",  18);   // SPI0 default, shared by all units
  spi_mosi_pin = get_int(params_from, "spi_mosi_pin", 19);   // SPI0 default, shared by all units
  spi_miso_pin = get_int(params_from, "spi_miso_pin", 16);   // SPI0 default, shared by all units
  cs_pin1      = get_int(params_from, "spi_cs_pin1",  17);   // LIS3DH #1 (single-LIS3DH default)
  cs_pin2      = get_int(params_from, "spi_cs_pin2",  20);   // LIS3DH #2 (closest free pin to the bus)
  cs_pin3      = get_int(params_from, "spi_cs_pin3",  21);   // LIS3DH #3 (next-closest free pin)
  cs_pin4      = get_int(params_from, "spi_cs_pin4",  22);   // LIS3DH #4 (next-closest free pin after that)
  // CTRL_REG1 ODR field; 5=100Hz. 8/9/10 are the three fastest choices --
  // see PICO_LIS3DH_SPI.ino's fuller comment on the 8/9/10 scheme.
  odr1         = get_int(params_from, "odr1",          5);
  fs1          = get_int(params_from, "fs1",           0);   // 0=+-2g, 1=+-4g, 2=+-8g, 3=+-16g
  odr2         = get_int(params_from, "odr2",          5);
  fs2          = get_int(params_from, "fs2",           0);
  odr3         = get_int(params_from, "odr3",          5);
  fs3          = get_int(params_from, "fs3",           0);
  odr4         = get_int(params_from, "odr4",          5);
  fs4          = get_int(params_from, "fs4",           0);
  // Operating mode (datasheet's own term, Table 10): 0=Low-power (8bit),
  // 1=Normal (10bit), 2=High-Resolution (12bit, default). Overridden to
  // Low-power regardless of this setting when the matching odr is 8 or 10.
  operating_mode1 = get_int(params_from, "operating_mode1", 2);
  operating_mode2 = get_int(params_from, "operating_mode2", 2);
  operating_mode3 = get_int(params_from, "operating_mode3", 2);
  operating_mode4 = get_int(params_from, "operating_mode4", 2);

  if (ch == 'i') {
    spi_begin(spi_sck_pin, spi_mosi_pin, spi_miso_pin);
    spi_cs_setup(cs_pin1);
    spi_cs_setup(cs_pin2);
    spi_cs_setup(cs_pin3);
    spi_cs_setup(cs_pin4);
  }

  bool force_lp1 = (odr1 == 8 || odr1 == 10);
  bool force_lp2 = (odr2 == 8 || odr2 == 10);
  bool force_lp3 = (odr3 == 8 || odr3 == 10);
  bool force_lp4 = (odr4 == 8 || odr4 == 10);
  uint8_t odr1_reg_code = (odr1 == 10) ? 9 : odr1;  // 10 shares code 1001 with 9
  uint8_t odr2_reg_code = (odr2 == 10) ? 9 : odr2;
  uint8_t odr3_reg_code = (odr3 == 10) ? 9 : odr3;
  uint8_t odr4_reg_code = (odr4 == 10) ? 9 : odr4;
  uint8_t lpen1_bit = (force_lp1 || operating_mode1 == 0) ? 1 : 0;
  uint8_t lpen2_bit = (force_lp2 || operating_mode2 == 0) ? 1 : 0;
  uint8_t lpen3_bit = (force_lp3 || operating_mode3 == 0) ? 1 : 0;
  uint8_t lpen4_bit = (force_lp4 || operating_mode4 == 0) ? 1 : 0;
  uint8_t hr1_bit   = (!lpen1_bit && operating_mode1 == 2) ? 1 : 0;  // LPen=1,HR=1 not allowed
  uint8_t hr2_bit   = (!lpen2_bit && operating_mode2 == 2) ? 1 : 0;
  uint8_t hr3_bit   = (!lpen3_bit && operating_mode3 == 2) ? 1 : 0;
  uint8_t hr4_bit   = (!lpen4_bit && operating_mode4 == 2) ? 1 : 0;

  // Deviceにモードの設定cmd送り check existence (LIS3DH x4)
  uint8_t who1 = spi_read_reg(cs_pin1, LIS3DH_WHO_AM_I);
  uint8_t who2 = spi_read_reg(cs_pin2, LIS3DH_WHO_AM_I);
  uint8_t who3 = spi_read_reg(cs_pin3, LIS3DH_WHO_AM_I);
  uint8_t who4 = spi_read_reg(cs_pin4, LIS3DH_WHO_AM_I);
  Serial.print("who_am_i_1=0x"); Serial.println(who1, HEX);  // expect 0x33
  Serial.print("who_am_i_2=0x"); Serial.println(who2, HEX);  // expect 0x33
  Serial.print("who_am_i_3=0x"); Serial.println(who3, HEX);  // expect 0x33
  Serial.print("who_am_i_4=0x"); Serial.println(who4, HEX);  // expect 0x33
  spi_write_reg(cs_pin1, LIS3DH_CTRL_REG1, (odr1_reg_code << 4) | (lpen1_bit << 3) | 0x07);
  spi_write_reg(cs_pin1, LIS3DH_CTRL_REG4, 0x80 | ((fs1 & 0x03) << 4) | (hr1_bit << 3));
  spi_write_reg(cs_pin2, LIS3DH_CTRL_REG1, (odr2_reg_code << 4) | (lpen2_bit << 3) | 0x07);
  spi_write_reg(cs_pin2, LIS3DH_CTRL_REG4, 0x80 | ((fs2 & 0x03) << 4) | (hr2_bit << 3));
  spi_write_reg(cs_pin3, LIS3DH_CTRL_REG1, (odr3_reg_code << 4) | (lpen3_bit << 3) | 0x07);
  spi_write_reg(cs_pin3, LIS3DH_CTRL_REG4, 0x80 | ((fs3 & 0x03) << 4) | (hr3_bit << 3));
  spi_write_reg(cs_pin4, LIS3DH_CTRL_REG1, (odr4_reg_code << 4) | (lpen4_bit << 3) | 0x07);
  spi_write_reg(cs_pin4, LIS3DH_CTRL_REG4, 0x80 | ((fs4 & 0x03) << 4) | (hr4_bit << 3));

  // g_per_count is intentionally the same formula regardless of
  // operating_mode -- see PICO_LIS3DH_SPI.ino's fuller comment on why
  // this is mode-invariant across all three modes.
  g_per_count1 = (HR_MG_PER_DIGIT[fs1 & 0x03] / 1000.0) / 16.0;
  g_per_count2 = (HR_MG_PER_DIGIT[fs2 & 0x03] / 1000.0) / 16.0;
  g_per_count3 = (HR_MG_PER_DIGIT[fs3 & 0x03] / 1000.0) / 16.0;
  g_per_count4 = (HR_MG_PER_DIGIT[fs4 & 0x03] / 1000.0) / 16.0;
  //
  // Make parameters
  //
  params_to["endian"]    = "little";
  params_to["who_am_i_1"] = to_string(who1);
  params_to["who_am_i_2"] = to_string(who2);
  params_to["who_am_i_3"] = to_string(who3);
  params_to["who_am_i_4"] = to_string(who4);
  params_to["struct"]    = "time(u4:func0), x1(u2:func1), y1(u2:func1), z1(u2:func1), x2(u2:func2), y2(u2:func2), z2(u2:func2), x3(u2:func3), y3(u2:func3), z3(u2:func3), x4(u2:func4), y4(u2:func4), z4(u2:func4)";
  one_data_byte           = 4 + 3*2 + 3*2 + 3*2 + 3*2;
  float divisor = std::pow(10.0, float(time_unit));
  //                    [ (lambda,                                                           bit(max value), 'unit')]
  params_to["func"] = "[ (lambda tm:tm/" + to_string(divisor) + "," + to_string(4*8) + ", \'sec\'),"
                    + "  (lambda x:(x-65536 if x>=32768 else x)*" + to_string(g_per_count1) + "," + to_string(16) + ", \'g\'),"
                    + "  (lambda x:(x-65536 if x>=32768 else x)*" + to_string(g_per_count2) + "," + to_string(16) + ", \'g\'),"
                    + "  (lambda x:(x-65536 if x>=32768 else x)*" + to_string(g_per_count3) + "," + to_string(16) + ", \'g\'),"
                    + "  (lambda x:(x-65536 if x>=32768 else x)*" + to_string(g_per_count4) + "," + to_string(16) + ", \'g\')  ]";

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
  // Rough ODR(Hz) lookup, indexed by the odr PARAMETER (0-10, not the raw
  // register code -- index 10 is the "5.376kHz(LP only)" virtual value);
  // used only to avoid polling faster than any of the four sensors
  // actually produces new samples (the slowest governs).
  const uint32_t odr_hz[11] = {0, 1, 10, 25, 50, 100, 200, 400, 1600, 1344, 5376};
  uint32_t odr1_interval_us = (odr1 < 11 && odr_hz[odr1] > 0) ? (1000000UL / odr_hz[odr1]) : 10000UL;
  uint32_t odr2_interval_us = (odr2 < 11 && odr_hz[odr2] > 0) ? (1000000UL / odr_hz[odr2]) : 10000UL;
  uint32_t odr3_interval_us = (odr3 < 11 && odr_hz[odr3] > 0) ? (1000000UL / odr_hz[odr3]) : 10000UL;
  uint32_t odr4_interval_us = (odr4 < 11 && odr_hz[odr4] > 0) ? (1000000UL / odr_hz[odr4]) : 10000UL;
  real_time_interval = std::max(std::max(std::max(odr1_interval_us, odr2_interval_us),
                                          std::max(odr3_interval_us, odr4_interval_us)),
                                 serial_time_interval);
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
  spi_read_regs(cs_pin3, LIS3DH_OUT_X_L, (uint8_t*)&sig[6], 6);
  spi_read_regs(cs_pin4, LIS3DH_OUT_X_L, (uint8_t*)&sig[9], 6);
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
      bin_write((time_unit==6)?(micros()-time0micros):(millis()-time0millis), usig.binary, 3*2*4);
      break;
  }
}
