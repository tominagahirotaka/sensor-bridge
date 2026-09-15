// Raspberry Pi Pico / Pico W (analog sensor)
// 2022/04/21
// H.Tominaga
//
#include "utils.h"

char program_name[] = "DPG_X95840W";

uint32_t baud = 115200; //  9600; 19200; 38400; 57600;
uint32_t time0micros, time0millis, one_data_byte, real_time_interval, serial_time_interval, waiting_time0;    // 4byte
usignal usig;  // Union member sig[] is uint16_t & member binary[] is uint8_t
int ok=0;
//
std::map<string, string> params;  //  parameters between this board and PC
vector<int> indx, i2c_pinno, i2c_addr;
//vector<int> indx, i2c_pinno={20, 18}, i2c_addr={0x2F};
vector<float> amp_max, tuning_width;
uint8_t  numCh, num_avg, time_unit, dpm_tmp;
uint16_t signal_max, calib_int_msec, calib_waiting;
uint8_t  calib_max_iters;
uint16_t calib_settle_tol;
uint32_t time_interval, calib_interval;
vector<int> dpm(3, 0x7F), dpm0(3, 0xFF); // !!Can not set initial value 127 (digital potentio-meter value 0--255)
vector<uint16_t> range={0,0,0}, range_max={0,0,0}, range_min={0,0,0};

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
  i2c_pinno      = get_int_list(params, "i2c_pinno", "20,");  // i2c line0 pin 20,21; line1 pin 18,19
       // for Calibration
  dpm0           = get_int_list(params, "dpm",    "-1,-1,-1");
  i2c_addr       = get_int_list(params, "i2c_addr",  "0x50,");  // addr of MCP4018 = 0x2F; X95840W = 0x50
  amp_max        = get_float_list(params, "calib_amplitude_max", "10,20,30");
  tuning_width   = get_float_list(params, "calib_tuning_width",  "5,5,5");
  calib_waiting  = get_int(params,        "calib_waiting", 800);  //delay time:                   default 800msec
  calib_int_msec = get_int(params,        "calib_int_msec", 4000); //max&min search time interval: default 4000msec
  calib_interval = calib_int_msec * ((time_unit == 6) ? 1000 : 1);
  calib_max_iters = get_int(params,       "calib_max_iters", 10); // bisection steps per calibration run
  calib_settle_tol = get_int(params,      "calib_settle_tol", 30); // ADC counts: consecutive probes within this much count as "settled"
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
    Serial.println(""); //Serial.flush();  delay(10);
    params["unit_time"] = to_string((t1-t0)/32);   //params["unit_time0"] = to_string(t0);  params["unit_time1"] = to_string(t1);
  //
  // Make parameters
  //X95840W
  params["endian"]    = "little";
  if (ch == 'i') i2c_begin(Wire,i2c_pinno[0]); // Initialize Wire (pin setup)
  else if (ch == 'a') params["i2c_WRITE_ERROR"] = to_string(X95840W_write(i2c_addr, dpm0));
  params["i2c_READ_ERROR"] = to_string(X95840W_read(i2c_addr, dpm));
  params["dpm"]       = to_string(dpm[0]) + "," + to_string(dpm[1]) + "," + to_string(dpm[2]); // Digital potentio meter
  // params["dpm_size"]  = to_string(dpm.size());

  params["struct"]    = "time(u4:func0), [(" + params["port_num"] + ")]port(u2:func1)"; // data structure
  float divisor = std::pow(10.0, float(time_unit));
  float coeff   = volt / signal_max;
  float dpm_coeff = 10.0 / (std::pow(2.0, 7.0)-1);
  //                   [ (lambda,                                     bit(max value),       'unit')]
  params["func"] = "[ (lambda tm:tm/" + to_string(divisor)   + "," + to_string(4*8)    + ", \'sec\'),"
                    + "  (lambda x:x*"   + to_string(coeff)     + "," + to_string(ADCres) + ", \'V\'),"
                    + "  (lambda x:x*"   + to_string(dpm_coeff) + "," + to_string(8)      + ", \'kOhm\')  ]";
  //
  // -> PC (Write parameters to PC)
  //
  string str_params = join_dict(params, ";", "="); // + ";" + join_dict(params, ";", "=");
  serial_print_separate(str_params); //Serial.flush();  delay(10);
}

void changeParam(char ch){
  params["dpm"]       = to_string(dpm[0]) + "," + to_string(dpm[1]) + "," + to_string(dpm[2]);  // Digital potentio meter
  params["struct"] = "time(u4:func0), [(" + params["port_num"] + ")]port(u2:func1)";
  one_data_byte       = 4 + indx.size()*2;
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
  serial_print_separate(join_dict(params, ";", "=")); //Serial.flush();  delay(10);
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
bool wait_for_settle(uint32_t tm, bool done[3]) {
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
        usig.binary[numCh*2 + i] = dpm[i];
        if (pmax[i] < usig.sig[i]) pmax[i] = usig.sig[i];
        if (pmin[i] > usig.sig[i]) pmin[i] = usig.sig[i];
      }
      bin_write(p1-tm, usig.binary, 2*numCh + dpm.size());
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
  int lo[3] = {0, 0, 0}, hi[3] = {255, 255, 255};
  bool done[3] = {false, false, false};
  bool have_best[3] = {false, false, false};
  int best_dpm[3], best_err[3];

  for (uint8_t iter=0; iter<calib_max_iters; iter++) {
    if (!wait_for_settle(tm, done)) return;

    t1 = t0 = (time_unit == 6)?micros():millis();
    for (uint8_t i=0; i<dpm.size(); i++) { sigmax[i] = 0; sigmin[i] = UINT16_MAX; }
    while ((t1 - t0) < calib_interval) {
      if (Serial.available() > 0) { Serial.flush(); return; }

      exact_waiting(waiting_time0 + real_time_interval); // Wait Until (now_time - waiting_time0 > real_time_interval)
      waiting_time0 = micros();

      analog_read(indx, usig.sig, numCh, num_avg);
      for (uint8_t i=0; i<dpm.size(); i++) {
        usig.binary[numCh*2 + i] = dpm[i];
        if (sigmax[i] < usig.sig[i]) sigmax[i] = usig.sig[i];
        if (sigmin[i] > usig.sig[i]) sigmin[i] = usig.sig[i];
        range[i]  = sigmax[i] - sigmin[i];
      }
      bin_write(t1-tm, usig.binary, 2*numCh + dpm.size());
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
  pinMode(17, OUTPUT);
}

void loop() {
  string input;
  char ch;
  if (Serial.available() > 0) {
    ch = Serial.read(); Serial.print("ch=");Serial.println(ch);
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
    case 1:
      exact_waiting(waiting_time0 + real_time_interval); // Wait Until (now_time - waiting_time0 > real_time_interval)
      waiting_time0 = micros();
      analog_read(indx, usig.sig, numCh, num_avg);
      bin_write((time_unit==6)?(micros()-time0micros):(millis()-time0millis), usig.binary, 2*numCh);
      break;
    case 2:
      calibrating((time_unit == 6) ? time0micros : time0millis); break;
  }
}
