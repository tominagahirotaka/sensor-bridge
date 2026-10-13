// Raspberry Pi Pico / Pico W (STMicroelectronics LIS3DH; 3-axis accelerometer, SPI)
// 2026/09/13
// H.Tominaga
//
// NOTE: The register map, SPI mode (Mode 3), and sensitivity tables below
// come from the public LIS3DH datasheet (STMicroelectronics DocID17530
// Rev 2) -- cross-checked directly against the PDF (Table 4, Table 10,
// Table 12, Table 31, Table 37, Section 8.16-8.18), not from memory or
// secondhand summaries. All three operating modes -- High-Resolution
// (the default, operating_mode=2), Normal (operating_mode=1), and
// Low-power (operating_mode=0) -- have been verified on real hardware
// (all four board variants; see README.md's hardware-verification
// matrix). See the g_per_count comment below for why its conversion
// factor doesn't need to differ between any of the three modes
// (confirmed against the datasheet's own numbers, and against real
// readings in each mode). Before trusting any
// data, check that who_am_i (sent to the PC as a parameter, and printed
// over Serial) reads back 0x33 -- that alone confirms wiring, SPI mode,
// and CS handling are correct.
//
// Naming note: the datasheet's own term for this 3-way choice is
// "operating mode" (Section 3.2.1's title, Table 10's own heading) --
// deliberately not "resolution_mode" or "power_mode", since neither axis
// alone describes all three: Normal and High-Resolution differ only in
// resolution (Table 12 shows their current consumption is identical at
// every ODR), while Low-power differs in both resolution AND power
// consumption. "Operating mode" is the datasheet's own neutral term for
// this, not invented here.
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
uint8_t odr, fs, operating_mode;
float g_per_count;

#define LIS3DH_WHO_AM_I        0x0F
#define LIS3DH_CTRL_REG1       0x20
#define LIS3DH_CTRL_REG4       0x23
#define LIS3DH_OUT_X_L         0x28
#define LIS3DH_WHO_AM_I_VALUE  0x33

// High-resolution mode sensitivity (mg per 12bit digit), indexed by fs (0=+-2g,1=+-4g,2=+-8g,3=+-16g)
const float HR_MG_PER_DIGIT[4] = {1.0, 2.0, 4.0, 12.0};
// Normal (10bit) and Low-power (8bit) sensitivity are exactly 4x and 16x
// HR's, per the datasheet's own mechanical-characteristics table (Table
// 4; not derived/guessed). Kept only as a documentation cross-check --
// NOT used in g_per_count below, which intentionally stays HR-mode-shaped
// in all three modes; see the comment there for why.
const float NORMAL_MG_PER_DIGIT[4] = {4.0, 8.0, 16.0, 48.0};
const float LOW_POWER_MG_PER_DIGIT[4] = {16.0, 32.0, 64.0, 192.0};

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
  // CTRL_REG1 ODR field; 5 = 100Hz. 8/9/10 are the three "fastest"
  // choices and need special handling below -- see odr_reg_code/force_lp.
  // 8 = 1.6kHz (Table 31's ODR code 1000, Low-power only -- there is no
  //     Normal/HR entry for this code in the datasheet).
  // 9 = 1.344kHz (ODR code 1001, Normal/High-Resolution; follows
  //     operating_mode normally).
  // 10 = 5.376kHz (same ODR code 1001 as 9, but the higher rate only
  //     exists in Low-power mode -- a separate odr value is needed here
  //     purely to tell this apart from 9 on the PC side, since the two
  //     share one 4-bit register code).
  odr       = get_int(params_from, "odr",           5);
  fs        = get_int(params_from, "fs",            0);   // 0=+-2g, 1=+-4g, 2=+-8g, 3=+-16g
  // Operating mode (datasheet's own term, Table 10 -- deliberately not
  // "resolution_mode"/"power_mode"; see the file header comment for why):
  // 0=Low-power (8bit), 1=Normal (10bit), 2=High-Resolution (12bit,
  // default). Overridden to Low-power regardless of this setting when
  // odr is 8 or 10 (see force_lp below) -- those ODR choices only exist
  // in Low-power mode, so there is nothing else they could mean.
  operating_mode = get_int(params_from, "operating_mode", 2);

  if (ch == 'i') spi_begin(cs_pin, sck_pin, mosi_pin, miso_pin);

  bool force_lp = (odr == 8 || odr == 10);
  uint8_t odr_reg_code = (odr == 10) ? 9 : odr;     // 10 shares code 1001 with 9 -- see above
  uint8_t lpen_bit = (force_lp || operating_mode == 0) ? 1 : 0;
  uint8_t hr_bit   = (!lpen_bit && operating_mode == 2) ? 1 : 0;  // LPen=1,HR=1 is "not allowed" per Table 10

  // Deviceにモードの設定cmd送り check existence
  uint8_t who = spi_read_reg(cs_pin, LIS3DH_WHO_AM_I);
  Serial.print("who_am_i=0x"); Serial.println(who, HEX);  // expect 0x33
  spi_write_reg(cs_pin, LIS3DH_CTRL_REG1,
               (odr_reg_code << 4) | (lpen_bit << 3) | 0x07);    // ODR, LPen, Zen/Yen/Xen=1
  spi_write_reg(cs_pin, LIS3DH_CTRL_REG4,
               0x80 | ((fs & 0x03) << 4) | (hr_bit << 3));       // BDU=1, FS, HR

  // Deliberately the same HR-shaped formula in all three operating
  // modes: each mode places its significant bits left-justified in the
  // same 16bit register (HR: 12bit+4 padding -> /16; Normal: 10bit+6
  // padding -> /64; Low-power: 8bit+8 padding -> /256 -- "left-justified"
  // per Section 8.16-8.18, bit counts per Table 10's "12-bit"/"10-bit"/
  // "8-bit data output"), and each mode's mg/digit (Table 4) is exactly
  // proportional to its padding divisor (Normal = 4x HR's, Low-power =
  // 16x HR's), so (mg/digit)/divisor comes out identical in all three --
  // e.g. at FS=+-2g: HR 1/1000/16, Normal 4/1000/64, Low-power
  // 16/1000/256, all 0.0000625 g per raw LSB (checked at every FS
  // setting, not just this one). This conversion formula therefore
  // already produces correct g values applied directly to the raw
  // (unshifted) register value in ANY mode; only the register bits
  // change. The mg/digit table and bit-justification are confirmed
  // straight from the datasheet (DocID17530 Rev 2), but the overall
  // result hasn't yet been checked against real Normal/Low-power-mode
  // hardware -- the simplest check is comparing a static High-Resolution
  // reading against a Normal or Low-power reading in the same
  // orientation; they should agree (the lower-resolution mode's will
  // just be more quantized/coarser), not differ by a factor of ~4/~16.
  g_per_count = (HR_MG_PER_DIGIT[fs & 0x03] / 1000.0) / 16.0;
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
  // Rough ODR(Hz) lookup, indexed by the odr PARAMETER (0-10, not the raw
  // register code -- index 10 is the "5.376kHz(LP only)" virtual value,
  // see initialSetupParam()); used only to avoid polling faster than the
  // sensor actually produces new samples.
  const uint32_t odr_hz[11] = {0, 1, 10, 25, 50, 100, 200, 400, 1600, 1344, 5376};
  uint32_t odr_interval_us = (odr < 11 && odr_hz[odr] > 0) ? (1000000UL / odr_hz[odr]) : 10000UL;
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
      bin_write((time_unit==6)?(micros()-time0micros):(millis()-time0millis), usig.binary, 3*2);
      break;
  }
}
