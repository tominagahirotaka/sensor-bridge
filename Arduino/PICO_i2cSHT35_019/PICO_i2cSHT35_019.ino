// Raspberry Pi Pico / Pico W (Sensirion SHT-35; temperature & humidity)
// 2022/04/28
// H.Tominaga
//
//#define DEBUG
#include "utils.h"
char program_name[] = "SHT35";

#ifdef DEBUG
char strbuf[512];
#endif

uint32_t baud = 115200; //  9600; 19200; 38400; 57600;
uint32_t time0micros, time0millis, one_data_byte, real_time_interval, serial_time_interval, waiting_time0;    // 4byte
usignal usig;  // Union member sig[] is uint16_t & member binary[] is uint8_t 
uint16_t stop_cmd = 0x3093;
int ok=0;

//
std::map<string, string> params_from;  //  parameters from PC
std::map<string, string> params_to = { //  parameters to PC
    {"data_names", "temperature,humidity"}
};
vector<int> i2c_addr, i2c_pinno, mode_list, sleep_time; 
vector<string> data_names, sensor_id;
uint8_t sensors=0; //0b1010;sensor connection i2cWire(0|1), addr(A|B) 4pattern=(0B,0A,1B,1A)-> 0000--1111;0A,1A=>0101;0B,1B=>1010
uint8_t time_unit, modeno;

void initialSetupParam(char ch, string str){
  //
  // <- PC (Read parameters from PC)
  //
  params_from = split_dict(str, ";", "=");
  //
  time_unit   = get_int(params_from,      "time_unit",     6);        //Time Unit (millis=3 or micros=6)
  i2c_pinno   = get_int_list(params_from, "i2c_pinno",     "20,18");  // i2c line0 pin 20,21; line1 pin 18,19
  // Sensor information
  i2c_addr    = get_int_list(params_from, "i2c_addr",   "0x44,0x45"); // 4pin->GND expensive; 4pin->VDD(or OPEN) Akizuki Denshi
  modeno      = get_int(params_from,      "modeno",     1);           // default 1 (0x2737) (100)
  mode_list   = get_int_list(params_from, "mode_list",  "0x2334, 0x2737"); // 4, 100
  sleep_time  = get_int_list(params_from, "sleep_time", "250,100");        // msec
  if (ch == 'i') i2c_2lines_begin(i2c_pinno);
  else if (ch == 'a') 
        for (uint8_t i=0; i<i2c_addr.size(); ++i) 
        {i2c_write2(Wire, i2c_addr[i], stop_cmd); i2c_write2(Wire1, i2c_addr[i], stop_cmd); delay(20); sensors = 0;}
  // Send mode-setting cmd to device, check existence
  for (uint8_t i=0; i<i2c_addr.size(); ++i) {
    char s[32];
    if (!i2c_write2(Wire,  i2c_addr[i], mode_list[modeno])) 
    { sensors += (i + 1)*4; snprintf(s, 32, "wire%d_0x%X", 0, i2c_addr[i]); sensor_id.push_back(s);}
    if (!i2c_write2(Wire1, i2c_addr[i], mode_list[modeno])) 
    { sensors += i + 1;     snprintf(s, 32, "wire%d_0x%X", 1, i2c_addr[i]); sensor_id.push_back(s);}
  }
  // SHT35 data structure
  data_names = split(params_to["data_names"], ",", 0, 0);
  //
  // Make parameters
  //
  params_to["endian"] = "little"; 
  params_to["sensor_id"] = join(sensor_id, ",");  
  params_to["struct"] = "time(u4:func0), [(" + params_to["sensor_id"] +")]{temp(u2:func1),humid(u2:func2)}";
  if (sensor_id.size() == 1) params_to["sensor_id"] += ',';
  one_data_byte       = 4 + sensor_id.size()*2*2;    // Look at the line above and calculate
  float divisor = std::pow(10.0, float(time_unit));
  //                   [ (lambda,                                     bit(max value),       'unit')]
  params_to["func"] = "[ (lambda tm:tm/" + to_string(divisor)   + "," + to_string(4*8)    + ", \'sec\'),"  
                    + "  (lambda x:-45+x*175.0/65535.0," + to_string(16) + ", \'℃\'),"         
                    + "  (lambda x:100.0*x/65535.0,"     + to_string(16) + ", \'%\')  ]";    

  //    
  // -> PC (Write parameters to PC)
  //
  string str_params = join_dict(params_to, ";", "=") + ";" + join_dict(params_from, ";", "=");
  serial_print_separate(str_params);
}

void changeParam(char ch){
  if (ch == 'c') { params_to["struct"] += ", [2]dpm(u1:func2)"; one_data_byte += 2*1; }
  //
  // Time intervals (serial...USB transfer limit, real...real transfer interval)
  //
  serial_time_interval  = int((one_data_byte * 8)  * 1000000.0 * 1.2/ baud);  // micro sec with a 20% margin added
  real_time_interval = std::max((uint32_t)sleep_time[modeno] * 1000, serial_time_interval);
  params_to["one_data_byte"]         = to_string(one_data_byte);
  params_to["serial_time_interval"]  = to_string(serial_time_interval);
  params_to["real_time_interval"]    = to_string(real_time_interval);
  //
  // -> PC (Write parameters to PC)
  serial_print_separate(join_dict(params_to, ";", "=")); //Serial.flush();  delay(10); 
}

#ifdef DEBUG
void write_plotting_data(uint16_t num_data) {
  float temp, RH;
  for (uint8_t i=0; i<num_data; i++) {
    temp = -45 + usig.sig[2*i] * 175.0/65535.0; RH = 100.0 * usig.sig[2*i+1]/65535.0;
    Serial.print(temp); Serial.print(", "); Serial.print(RH);Serial.print(", "); 
  } Serial.println(); }
#endif
bool sensor_read(uint16_t *sig) {
  vector<uint16_t> tmp(data_names.size());
  for (uint8_t i=0,cnt=0; i<i2c_addr.size(); ++i) {
    if (sensors & ((i + 1)*4) ) { 
      if (i2c_read_crc8(Wire,  i2c_addr[i], tmp, data_names.size())) {
        for (uint8_t j=0; j<tmp.size(); ++j) sig[cnt+j] = tmp[j];
        cnt+=tmp.size();
      } else { return false; }
    }
    if (sensors & (i + 1)) {
      if (i2c_read_crc8(Wire1, i2c_addr[i], tmp, data_names.size())) {
        for (uint8_t j=0; j<tmp.size(); ++j) sig[cnt+j] = tmp[j]; 
        cnt+=tmp.size();
      } else { return false; }
    }
  }
  return true;
}

void setup() {ok = 0; begin_serial(baud, 100, program_name); }

void loop() {
  string input;
  char ch; 
  if (Serial.available() > 0) {
    ch = Serial.read();// Serial.print("ch=");Serial.println(ch);
    switch (ch) {
      case 'i': // Initialize
      case 'a': // Initialize Again
        ok = 0; 
#ifdef DEBUG
        input = "time_unit=6;i2c_addr=0x44,0x45;modeno=1;mode_list=0x2334, 0x2737;sleep_time=250,100";
#else        
        input = (Serial.readStringUntil('\n')).c_str(); //Serial.flush();
#endif
        initialSetupParam(ch, input); 
        delay(100);        // <- VERY IMPORTANT https://garchiving.com/high-speed-processing-of-serial-communication-in-arduino/
        break; 
      case 's':  // start
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
      while (!sensor_read(usig.sig));
#ifdef DEBUG
      write_plotting_data(sensor_id.size());
#else
      bin_write((time_unit==6)?(micros()-time0micros):(millis()-time0millis), usig.binary, 2*sensor_id.size()*data_names.size());
//      bin_write(millis()-time0millis, usig.binary, sensor_id.size()*data_names.size());
#endif
      break;
  }
}
