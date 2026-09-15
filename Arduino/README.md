# Why "Arduino/"

The boards this code runs on are Raspberry Pi Pico / Pico W (RP2040), not
Arduino-brand hardware. This directory is named `Arduino/` because the
firmware is written using the **Arduino programming framework**
(`.ino` sketches, `setup()`/`loop()`, the `Serial`/`Wire`/`SPI` APIs,
`#include "Arduino.h"`), built via the community
[earlephilhower/arduino-pico](https://github.com/earlephilhower/arduino-pico)
core (`rp2040:rp2040:rpipico` board in Arduino IDE / `arduino-cli`) --
not the native Raspberry Pi Pico C/C++ SDK.

This is the same relationship many other non-Arduino-brand boards have to
"Arduino": ESP32, ESP8266, STM32, and Teensy boards are all commonly
programmed the same way, using an Arduino-compatible core on non-Arduino
silicon.

One sketch (`.ino` + `utils.h` + `utils.cpp`) per supported sensor board;
see [`../docs/adding-a-board.md`](../docs/adding-a-board.md) for how a
sketch pairs with a `.ini` file under the repository root.
