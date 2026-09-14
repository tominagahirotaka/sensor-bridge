// Raspberry Pi Pico / Pico W (analog sensor)
// 2022/02/24
// H.Tominaga
//
#include "utils.h"

char dpm_chip[] = "MCP4018";

uint32_t baud = 115200; //  9600; 19200; 38400; 57600;
uint32_t time0micros, time0millis, one_data_byte, real_time_interval, serial_time_interval, waiting_time0;    // 4byte
usignal usig;  // Union member sig[] is uint16_t & member binary[] is uint8_t 
int ok=0;
//
std::map<string, string> params_from;  //  parameters from PC
std::map<string, string> params_to;    //  parameters to PC 
vector<int> indx, i2c_pinno, i2c_addr;
//vector<int> indx, i2c_pinno={20, 18}, i2c_addr={0x2F};
vector<float> amp_max, tuning_width;
uint8_t  numCh, num_avg, time_unit, dpm_tmp;
uint16_t signal_max, calib_int_msec, calib_waiting;
uint32_t time_interval, calib_interval;
vector<uint8_t> dpm = {63,63}; // !!Can not set initial value 63 (digital potentio-meter value 0--127)
vector<uint16_t> range={0,0}, range_max={0,0}, range_min={0,0};

void initialSetupParam(char ch, string str){
  //
  // <- PC (Read parameters from PC)
  //
  params_from   = split_dict(str, ";", "=");
  //
  int   ADCres   = get_int(params_from,      "ADCres",         12);  // Pico 12bit
  float volt     = get_float(params_from,    "volt",          5.0);
  time_unit      = get_int(params_from,      "time_unit",       6);  //Time Unit (millis=3 or micros=6)
  time_interval  = get_int(params_from,      "time_interval",   0);  //Time interval (micro sec)
  num_avg        = get_int(params_from,      "num_avg",         1);
  indx           = get_int_list(params_from, "port_num",  "0,1,2");
  i2c_pinno      = get_int_list(params_from, "i2c_pinno", "20,18");  // i2c line0 pin 20,21; line1 pin 18,19
       // for Calibration
  i2c_addr       = get_int_list(params_from, dpm_chip,                "0x2F,");  // addr of MCP4018 = 0x2F
  amp_max        = get_float_list(params_from, "calib_amplitude_max", "20,30");
  tuning_width   = get_float_list(params_from, "calib_tuning_width",  "5,5");
  calib_waiting  = get_int(params_from,        "calib_waiting", 800);  //delay time:                   default 800msec
  calib_int_msec = get_int(params_from,        "calib_int_msec", 4000); //max&min search time interval: default 4000msec
  calib_interval = calib_int_msec * ((time_unit == 6) ? 1000 : 1);
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
    params_to["unit_time"] = to_string((t1-t0)/32);   //params_to["unit_time0"] = to_string(t0);  params_to["unit_time1"] = to_string(t1);
  //
  // Make parameters
  //
  params_to["endian"]    = "little"; 
  
  if (ch == 'i') i2c_2lines_begin(i2c_pinno);  
  MCP4018_read(i2c_addr, dpm);
  params_to["dpm"]       = to_string(dpm[0]) + "," + to_string(dpm[1]);                // Digital potentio meter
  params_to["dpm_size"]  = to_string(dpm.size());
  
  params_to["struct"]    = "time(u4:func0), [(" + params_from["port_num"] + ")]port(u2:func1)"; // data structure
  float divisor = std::pow(10.0, float(time_unit));
  float coeff   = volt / signal_max;
  float dpm_coeff = 10.0 / (std::pow(2.0, 7.0)-1);
  //                   [ (lambda,                                     bit(max value),       'unit')]
  params_to["func"] = "[ (lambda tm:tm/" + to_string(divisor)   + "," + to_string(4*8)    + ", \'sec\'),"  
                    + "  (lambda x:x*"   + to_string(coeff)     + "," + to_string(ADCres) + ", \'V\'),"         
                    + "  (lambda x:x*"   + to_string(dpm_coeff) + "," + to_string(7)      + ", \'kOhm\')  ]";           
  //    
  // -> PC (Write parameters to PC)
  //
  string str_params = join_dict(params_to, ";", "=") + ";" + join_dict(params_from, ";", "=");
  serial_print_separate(str_params); //Serial.flush();  delay(10); 
}

void changeParam(char ch){
  params_to["dpm"]       = to_string(dpm[0]) + "," + to_string(dpm[1]);                // Digital potentio meter
  params_to["struct"] = "time(u4:func0), [(" + params_from["port_num"] + ")]port(u2:func1)"; 
  one_data_byte       = 4 + indx.size()*2;
  if (ch == 'c') { params_to["struct"] += ", [2]dpm(u1:func2)"; one_data_byte += 2*1; }
  //
  // Time intervals (serial...USB transfer limit, real...real transfer interval)
  //
  serial_time_interval  = int((one_data_byte * 8)  * 1000000.0 * 1.2/ baud);  // micro sec with a 20% margin added
  real_time_interval = std::max((uint32_t)time_interval, serial_time_interval);
  params_to["one_data_byte"]         = to_string(one_data_byte);
  params_to["serial_time_interval"]  = to_string(serial_time_interval);
  params_to["real_time_interval"]    = to_string(real_time_interval);
  //
  // -> PC (Write parameters to PC)
  serial_print_separate(join_dict(params_to, ";", "=")); //Serial.flush();  delay(10); 
}
  
void calibrating(uint32_t tm) {
  uint32_t t0, t1;
  uint16_t sigmax[3],sigmin[3];

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
   // delay(1);
    bin_write(t1-tm, usig.binary, 2*numCh + dpm.size());
    t1 = (time_unit == 6)?micros():millis();
  }
  tuning(range, range_max, range_min, dpm); 
  MCP4018_write(i2c_addr, dpm);    // <- Don't Move out from this function
  delay(calib_waiting);            // <- Don't Move out from this function
}

void setup() {
  ok = 99; begin_serial(baud, 100, dpm_chip);
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
