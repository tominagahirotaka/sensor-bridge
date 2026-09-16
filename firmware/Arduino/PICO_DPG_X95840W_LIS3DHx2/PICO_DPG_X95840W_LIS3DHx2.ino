// Raspberry Pi Pico / Pico W (X95840W digital potentiometer + 2x LIS3DH accelerometer, SPI)
// 2026/09/13
// H.Tominaga
//
// Combines the existing DPG_X95840W board (3 ADC channels, I2C-controlled
// potentiometer with amplitude calibration) with two SPI-connected LIS3DH
// accelerometers sharing one SPI bus (distinct CS pins). See utils.h for
// the full pin assignment.
//
// NOTE: the LIS3DH register map/mode/sensitivity table are from the public
// datasheet only -- not yet verified on real hardware. Check that
// who_am_i_1 / who_am_i_2 (sent to the PC, and printed over Serial) read
// back 0x33 before trusting any accelerometer data.
//
#include "utils.h"

char program_name[] = "DPG_X95840W_LIS3DHx2";

uint32_t baud = 115200; //  9600; 19200; 38400; 57600;
uint32_t time0micros, time0millis, one_data_byte, real_time_interval, serial_time_interval, waiting_time0;    // 4byte
usignal usig;  // Union member sig[] is uint16_t & member binary[] is uint8_t
int ok=0;
//
std::map<string, string> params;  //  parameters between this board and PC
vector<int> indx, i2c_pinno, i2c_addr;
vector<float> amp_max, tuning_width;
uint8_t  numCh, num_avg, time_unit, dpm_tmp;
uint16_t signal_max, calib_int_msec, calib_waiting;
uint8_t  calib_max_iters;
uint16_t calib_settle_tol;
uint32_t time_interval, calib_interval;
vector<int> dpm(3, 0x7F), dpm0(3, 0xFF); // !!Can not set initial value 127 (digital potentio-meter value 0--255)
vector<uint16_t> range={0,0,0}, range_max={0,0,0}, range_min={0,0,0};

// --- LIS3DH (x2, shared SPI0 bus) ---
uint8_t spi_sck_pin, spi_mosi_pin, spi_miso_pin;
uint8_t cs_pin1, cs_pin2;
uint8_t odr1, fs1, odr2, fs2;
float g_per_count1, g_per_count2;

#define LIS3DH_WHO_AM_I        0x0F
#define LIS3DH_CTRL_REG1       0x20
#define LIS3DH_CTRL_REG4       0x23
#define LIS3DH_OUT_X_L         0x28
#define LIS3DH_WHO_AM_I_VALUE  0x33
const float HR_MG_PER_DIGIT[4] = {1.0, 2.0, 4.0, 12.0};  // HR mode, indexed by fs (0=+-2g..3=+-16g)

void initialSetupParam(char ch, string str){
  //
  // <- PC (Read parameters from PC)
  //
  params   = split_dict(str, ";", "=");
  //
  int   ADCres   = get_int(params,      "ADCres",         12);  // Pico 12bit
  float volt     = get_float(params,    "volt",          5.0);
  time_unit      = get_int(params,      "time_unit",       6);  //Time Unit (millis=3 or micros=6)
  time_interval  = get_int(params,      "time_interval",   0);  //Time interval (micro sec)
  num_avg        = get_int(params,      "num_avg",         1);
  indx           = get_int_list(params, "port_num",  "0,1,2");
  i2c_pinno      = get_int_list(params, "i2c_pinno", "20,");  // i2c line0 pin 20,21
       // for Calibration
  dpm0           = get_int_list(params, "dpm",    "-1,-1,-1");
  i2c_addr       = get_int_list(params, "i2c_addr",  "0x50,");  // X95840W = 0x50
  amp_max        = get_float_list(params, "calib_amplitude_max", "10,20,30");
  tuning_width   = get_float_list(params, "calib_tuning_width",  "5,5,5");
  calib_waiting  = get_int(params,        "calib_waiting", 800);
  calib_int_msec = get_int(params,        "calib_int_msec", 4000);
  calib_interval = calib_int_msec * ((time_unit == 6) ? 1000 : 1);
  calib_max_iters = get_int(params,       "calib_max_iters", 10); // bisection steps per calibration run
  calib_settle_tol = get_int(params,      "calib_settle_tol", 30); // ADC counts: consecutive probes within this much count as "settled"
  // LIS3DH x2
  spi_sck_pin  = get_int(params, "spi_sck_pin",  18);   // SPI0 default, shared by both units
  spi_mosi_pin = get_int(params, "spi_mosi_pin", 19);   // SPI0 default, shared by both units
  spi_miso_pin = get_int(params, "spi_miso_pin", 16);   // SPI0 default, shared by both units
  cs_pin1      = get_int(params, "spi_cs_pin1",  22);   // LIS3DH #1 (GP17 is already used by X95840W)
  cs_pin2      = get_int(params, "spi_cs_pin2",   2);   // LIS3DH #2
  odr1         = get_int(params, "odr1",          5);   // CTRL_REG1 ODR field; 5 = 100Hz
  fs1          = get_int(params, "fs1",           0);   // 0=+-2g, 1=+-4g, 2=+-8g, 3=+-16g
  odr2         = get_int(params, "odr2",          5);
  fs2          = get_int(params, "fs2",           0);
  //
  // setting variables
  //
  analogReadResolution(ADCres);
  signal_max = std::pow(2.0, (float)ADCres)-1;
  numCh      = indx.size();
  for (uint16_t i=0; i<amp_max.size(); i++) {
    range_max[i] = (amp_max[i] + tuning_width[i]/2)*signal_max/100.0;
    range_min[i] = (amp_max[i] - tuning_width[i]/2)*signal_max/100.0;
  }
  // Measure the unit_time
    uint8_t u8t_dummy[] = "00001111222233334444555566667777";
    uint32_t t0, t1, time_dummy = 0x7777;
    t0 = (time_unit == 6)?micros():millis();
    for (auto i=0; i<32; i++) { analog_read(indx, usig.sig, numCh, num_avg); bin_write(time_dummy, u8t_dummy, 2*numCh);}
    t1 = (time_unit == 6)?micros():millis();
    Serial.println("");
    params["unit_time"] = to_string((t1-t0)/32);
  //
  // Make parameters
  //
  params["endian"]    = "little";
  if (ch == 'i') {
    i2c_begin(Wire,i2c_pinno[0]); // Initialize Wire (pin setup)
    spi_begin(spi_sck_pin, spi_mosi_pin, spi_miso_pin);
    spi_cs_setup(cs_pin1);
    spi_cs_setup(cs_pin2);
  }
  else if (ch == 'a') params["i2c_WRITE_ERROR"] = to_string(X95840W_write(i2c_addr, dpm0));
  params["i2c_READ_ERROR"] = to_string(X95840W_read(i2c_addr, dpm));
  params["dpm"]       = to_string(dpm[0]) + "," + to_string(dpm[1]) + "," + to_string(dpm[2]);

  // Deviceにモードの設定cmd送り check existence (LIS3DH x2)
  uint8_t who1 = spi_read_reg(cs_pin1, LIS3DH_WHO_AM_I);
  uint8_t who2 = spi_read_reg(cs_pin2, LIS3DH_WHO_AM_I);
  Serial.print("who_am_i_1=0x"); Serial.println(who1, HEX);  // expect 0x33
  Serial.print("who_am_i_2=0x"); Serial.println(who2, HEX);  // expect 0x33
  params["who_am_i_1"] = to_string(who1);
  params["who_am_i_2"] = to_string(who2);
  spi_write_reg(cs_pin1, LIS3DH_CTRL_REG1, (odr1 << 4) | 0x07);
  spi_write_reg(cs_pin1, LIS3DH_CTRL_REG4, 0x80 | ((fs1 & 0x03) << 4) | 0x08);
  spi_write_reg(cs_pin2, LIS3DH_CTRL_REG1, (odr2 << 4) | 0x07);
  spi_write_reg(cs_pin2, LIS3DH_CTRL_REG4, 0x80 | ((fs2 & 0x03) << 4) | 0x08);
  g_per_count1 = (HR_MG_PER_DIGIT[fs1 & 0x03] / 1000.0) / 16.0;   // raw 16bit is a left-justified 12bit value
  g_per_count2 = (HR_MG_PER_DIGIT[fs2 & 0x03] / 1000.0) / 16.0;

  params["struct"]    = "time(u4:func0), [(" + params["port_num"] + ")]port(u2:func1)"; // data structure
  float divisor = std::pow(10.0, float(time_unit));
  float coeff   = volt / signal_max;
  float dpm_coeff = 10.0 / (std::pow(2.0, 7.0)-1);
  //                   [ (lambda,                                     bit(max value),       'unit')]
  params["func"] = "[ (lambda tm:tm/" + to_string(divisor)   + "," + to_string(4*8)    + ", \'sec\'),"
                    + "  (lambda x:x*"   + to_string(coeff)     + "," + to_string(ADCres) + ", \'V\'),"
                    + "  (lambda x:x*"   + to_string(dpm_coeff) + "," + to_string(8)      + ", \'kOhm\'),"
                    + "  (lambda x:(x-65536 if x>=32768 else x)*" + to_string(g_per_count1) + "," + to_string(16) + ", \'g\'),"
                    + "  (lambda x:(x-65536 if x>=32768 else x)*" + to_string(g_per_count2) + "," + to_string(16) + ", \'g\')  ]";
  //
  // -> PC (Write parameters to PC)
  //
  string str_params = join_dict(params, ";", "=");
  serial_print_separate(str_params);
}

void changeParam(char ch){
  // Byte order: time, ADC ports, accel x2 (always), dpm (calibration only, kept
  // last so it lines up with the existing negative-index LCD readout below).
  params["dpm"]       = to_string(dpm[0]) + "," + to_string(dpm[1]) + "," + to_string(dpm[2]);
  params["struct"] = "time(u4:func0), [(" + params["port_num"] + ")]port(u2:func1)"
                    ", ax1(u2:func3), ay1(u2:func3), az1(u2:func3), ax2(u2:func4), ay2(u2:func4), az2(u2:func4)";
  one_data_byte       = 4 + indx.size()*2 + 3*2*2;   // time + ADC ports + 2 sensors x 3 axes x 2 bytes
  if (ch == 'c') { params["struct"] += ", [3]dpm(u1:func2)"; one_data_byte += 3*1; }
  //
  // Time intervals (serial...USB transfer limit, real...real transfer interval)
  //
  serial_time_interval  = int((one_data_byte * 8)  * 1000000.0 * 1.2/ baud);  // micro sec with a 20% margin added
  real_time_interval = std::max((uint32_t)time_interval, serial_time_interval);
  params["one_data_byte"]         = to_string(one_data_byte);
  params["serial_time_interval"]  = to_string(serial_time_interval);
  params["real_time_interval"]    = to_string(real_time_interval);
  //
  // -> PC (Write parameters to PC)
  serial_print_separate(join_dict(params, ";", "="));
}

// Reads both LIS3DH units and writes their 12 bytes right after the ADC
// channels, at a fixed offset regardless of mode; dpm (calibration only) is
// appended after accel, not between ADC and accel -- see changeParam().
#define ACCEL_OFFSET (numCh*2)
void accel_read() {
  spi_read_regs(cs_pin1, LIS3DH_OUT_X_L, usig.binary + ACCEL_OFFSET,     6);
  spi_read_regs(cs_pin2, LIS3DH_OUT_X_L, usig.binary + ACCEL_OFFSET + 6, 6);
}

// Blocks (streaming samples throughout, staying responsive to new serial
// commands) until two consecutive short probe windows agree on every
// not-yet-converged channel's signal range within calib_settle_tol ADC
// counts, or until calib_waiting has elapsed. Real hardware showed a
// nonzero, not precisely known lag between an I2C write to the
// potentiometer and its effect stabilizing in the measured signal, so
// this checks for stability directly instead of trusting one fixed
// guessed delay. Returns false only if a new serial command interrupted
// the wait (the caller should abort, same as everywhere else in this
// file); running out of time without stabilizing is not an error --
// calibration proceeds with whatever the last probe read.
bool wait_for_settle(uint32_t tm, bool done[3], uint16_t dpm_offset) {
  uint16_t prev_range[3];
  bool have_prev = false;
  uint32_t probe_len = calib_interval / 4;
  uint32_t probe_floor = (time_unit == 6) ? 200000UL : 200UL; // >= 0.2s/probe
  if (probe_len < probe_floor) probe_len = probe_floor;
  uint32_t elapsed = 0;

  while (elapsed < calib_waiting) {
    uint16_t pmax[3], pmin[3];
    for (uint8_t i=0; i<dpm.size(); i++) { pmax[i] = 0; pmin[i] = UINT16_MAX; }
    uint32_t p0 = (time_unit == 6)?micros():millis(), p1 = p0;
    while ((p1 - p0) < probe_len) {
      if (Serial.available() > 0) { Serial.flush(); return false; }
      exact_waiting(waiting_time0 + real_time_interval);
      waiting_time0 = micros();
      analog_read(indx, usig.sig, numCh, num_avg);
      for (uint8_t i=0; i<dpm.size(); i++) {
        usig.binary[dpm_offset + i] = dpm[i];
        if (pmax[i] < usig.sig[i]) pmax[i] = usig.sig[i];
        if (pmin[i] > usig.sig[i]) pmin[i] = usig.sig[i];
      }
      accel_read();
      bin_write(p1-tm, usig.binary, dpm_offset + dpm.size());
      p1 = (time_unit == 6)?micros():millis();
    }
    bool stable = have_prev;
    for (uint8_t i=0; i<dpm.size(); i++) {
      if (done[i]) continue;
      uint16_t r = pmax[i] - pmin[i];
      int32_t d = (int32_t)r - (int32_t)prev_range[i];
      if (have_prev && (d > (int32_t)calib_settle_tol || d < -(int32_t)calib_settle_tol)) stable = false;
      prev_range[i] = r;
    }
    have_prev = true;
    elapsed += probe_len;
    if (stable) return true;
  }
  return true; // timed out waiting for stability; proceed with a best-effort reading
}

// Runs a full bisection-search calibration to completion (up to
// calib_max_iters rounds) in a single 'c' command, instead of requiring
// the host to press caliBrate repeatedly for one +/-2 step at a time.
// Each round: wait_for_settle() after any dpm change, then measure each
// channel's signal range over calib_interval (long enough to span several
// pulse periods for a trustworthy peak-to-peak reading), then take one
// tuning_step() per not-yet-converged channel. Streams samples throughout
// every phase, so the host's live plot/LCD readouts keep updating for the
// whole run. Also tracks the closest-to-target reading ever seen per
// channel, and falls back to it if bisection exhausts its search range
// or calib_max_iters is reached without landing in the target band --
// so a single noisy/motion-artifact measurement can't strand the
// potentiometer somewhere worse than the best value actually observed.
void calibrating(uint32_t tm) {
  uint32_t t0, t1;
  uint16_t sigmax[3],sigmin[3];
  uint16_t dpm_offset = ACCEL_OFFSET + 12;
  int lo[3] = {0, 0, 0}, hi[3] = {255, 255, 255};
  bool done[3] = {false, false, false};
  bool have_best[3] = {false, false, false};
  int best_dpm[3], best_err[3];

  for (uint8_t iter=0; iter<calib_max_iters; iter++) {
    if (!wait_for_settle(tm, done, dpm_offset)) return;

    t1 = t0 = (time_unit == 6)?micros():millis();
    for (uint8_t i=0; i<dpm.size(); i++) { sigmax[i] = 0; sigmin[i] = UINT16_MAX; }
    while ((t1 - t0) < calib_interval) {
      if (Serial.available() > 0) { Serial.flush(); return; }

      exact_waiting(waiting_time0 + real_time_interval);
      waiting_time0 = micros();

      analog_read(indx, usig.sig, numCh, num_avg);
      for (uint8_t i=0; i<dpm.size(); i++) {
        usig.binary[dpm_offset + i] = dpm[i];
        if (sigmax[i] < usig.sig[i]) sigmax[i] = usig.sig[i];
        if (sigmin[i] > usig.sig[i]) sigmin[i] = usig.sig[i];
        range[i]  = sigmax[i] - sigmin[i];
      }
      accel_read();
      bin_write(t1-tm, usig.binary, dpm_offset + dpm.size());
      t1 = (time_unit == 6)?micros():millis();
    }

    bool all_done = true;
    for (uint8_t i=0; i<dpm.size(); i++) {
      if (done[i]) continue;
      int center = ((int)range_max[i] + (int)range_min[i]) / 2;
      int err = (int)range[i] - center; if (err < 0) err = -err;
      if (!have_best[i] || err < best_err[i]) { best_err[i] = err; best_dpm[i] = dpm[i]; have_best[i] = true; }
      done[i] = tuning_step(range[i], range_max[i], range_min[i], dpm[i], lo[i], hi[i]);
      if (done[i] && have_best[i]) dpm[i] = best_dpm[i]; // land on the best reading seen, not just the last guess
      if (!done[i]) all_done = false;
    }
    X95840W_write(i2c_addr, dpm);    // <- Don't Move out from this function

    if (all_done) break;
  }
}

void setup() {
  ok = 99; begin_serial(baud, 100, program_name);
  pinMode(17, OUTPUT);   // X95840W I2C transaction enable/latch
}

void loop() {
  check_serial_reconnect(program_name, ok);  // re-announce + auto-stop on host reconnect/disconnect
  string input;
  char ch;
  if (Serial.available() > 0) {
    ch = Serial.read();
    switch (ch) {
      case 'i': // Initialize
      case 'a': // Initialize Again
        ok = 0; input = (Serial.readStringUntil('\n')).c_str(); initialSetupParam(ch, input);
        delay(100);        // <- VERY IMPORTANT https://garchiving.com/high-speed-processing-of-serial-communication-in-arduino/
        break;
      case 's':
      case ';':  // Start
        ok = 1;
        changeParam(ch);
        delay(100);
        Serial.println("OK");   // written out as a Start marker
        waiting_time0 = micros();
        break;
      case 'c': // Calibration
        ok = 2;
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
    case 1: {
      exact_waiting(waiting_time0 + real_time_interval);
      waiting_time0 = micros();
      analog_read(indx, usig.sig, numCh, num_avg);
      accel_read();
      bin_write((time_unit==6)?(micros()-time0micros):(millis()-time0millis), usig.binary, ACCEL_OFFSET + 12);
      break;
    }
    case 2:
      calibrating((time_unit == 6) ? time0micros : time0millis); break;
  }
}
