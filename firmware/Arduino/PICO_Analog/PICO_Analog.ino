// Raspberry Pi Pico / Pico W (analog sensor)
// 2022/04/05
// H.Tominaga
//
#include "utils.h"

char program_name[] = "Analog";

uint32_t baud = 115200; //  9600; 19200; 38400; 57600;
uint32_t time0micros, time0millis, one_data_byte, time_interval, real_time_interval, serial_time_interval, waiting_time0;    // 4byte
usignal usig;  // Union member sig[] is uint16_t & member binary[] is uint8_t
int ok=0;
//
std::map<string, string> params_from;  //  parameters from PC
std::map<string, string> params_to;    //  parameters to PC
vector<int> indx;
uint8_t  numCh, num_avg, time_unit;
uint16_t signal_max;

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
  // setting variables
  //
  analogReadResolution(ADCres);
  signal_max = std::pow(2.0, (float)ADCres)-1;
  numCh      = indx.size();
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
  params_to["endian"]    = "little";
  params_to["struct"]    = "time(u4:func0), [(" + params_from["port_num"] + ")]port(u2:func1)"; // data structure
  float divisor = std::pow(10.0, float(time_unit));
  float coeff   = volt / signal_max;
  params_to["func"] = "[ (lambda tm:tm/" + to_string(divisor)   + "," + to_string(4*8)    + ", \'sec\'),"
                    + "  (lambda x:x*"   + to_string(coeff)     + "," + to_string(ADCres) + ", \'V\')]";
  //
  // -> PC (Write parameters to PC)
  //
  string str_params = join_dict(params_to, ";", "=") + ";" + join_dict(params_from, ";", "=");
  serial_print_separate(str_params); //Serial.flush();  delay(10);
}

void changeParam(char ch){
  params_to["struct"] = "time(u4:func0), [(" + params_from["port_num"] + ")]port(u2:func1)";
  one_data_byte       = 4 + indx.size()*2;
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

void setup() {
  ok = 99; begin_serial(baud, 100, program_name);
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
      exact_waiting(waiting_time0 + real_time_interval); // Wait Until (now_time - waiting_time0 > real_time_interval)
      waiting_time0 = micros();
      analog_read(indx, usig.sig, numCh, num_avg);
      bin_write((time_unit==6)?(micros()-time0micros):(millis()-time0millis), usig.binary, 2*numCh);
      break;
  }
}
