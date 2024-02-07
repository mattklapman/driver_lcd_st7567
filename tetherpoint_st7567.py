# Micropython ST7567 128x64 display driver
# inherits from framebuf with overriding

"""
BSD 3-Clause License

Copyright (c) 2024, mattklapman and tetherpoint

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

from micropython import const
import framebuf
import time # needed for reset delay

# Constants: display registers
ST7567_DISPLAY_OFF = const(0xAE)
ST7567_DISPLAY_ON = const(0xAF)
ST7567_SET_START_LINE = const(0x40) # lower 6-bits: S5, S4, S3, S2, S1, S0
ST7567_SET_PAGE_ADDRESS = const(0xB0) # lower 4-bits: Y3, Y2, Y1, Y0
ST7567_SET_COL_ADDRESS_MSB = const(0x10) # lower 4-bits: X7, X6, X5, X4
ST7567_SET_COL_ADDRESS_LSB = const(0x00) # lower 4-bits: X3, X2, X1, X0
ST7567_READ_STATUS = const(0x00) # read-only
ST7567_SEG_DIRECTION_NORMAL = const(0xA0)
ST7567_SEG_DIRECTION_REVERSE = const(0xA1)
ST7567_DISPLAY_NORMAL = const(0xA6)
ST7567_DISPLAY_INVERSE = const(0xA7)
ST7567_DISPLAY_ALL_PIXELS_NORMAL = const(0xA4)
ST7567_DISPLAY_ALL_PIXELS_ON = const(0xA5)
ST7567_BIAS_SELECT_1DIV9 = const(0xA2) 
ST7567_BIAS_SELECT_1DIV7 = const(0xA3)
ST7567_READ_MODIFY_WRITE = const(0xE0) # write causes column address autoincrement
ST7567_READ_MODIFY_WRITE_END = const(0xEE)
ST7567_RESET = const(0xE2)
ST7567_COM_DIRECTION_NORMAL = const(0xC0)
ST7567_COM_DIRECTION_REVERSE = const(0xC8)
ST7567_POWER_CONTROL = const(0x28) # lower 3-bits: VB, VR, VF
ST7567_REGULATION_RATIO = const(0x20) # lower 3-bits: RR2, RR1, RR0 corresponding to volts: 3, 3.5, 4, 4.5, 5, 5.5, 6, 6.5
ST7567_SET_EV_START = const(0x81) # immediately follow this command with byte: 0, 0, EV5, EV4, EV3, EV2, EV1, EV0
ST7567_SET_BOOSTER_START = const(0xF8) # immediately follow this command with one of the following bytes:
ST7567_SET_BOOSTER_4X = const(0x00)
ST7567_SET_BOOSTER_5X = const(0x01)
#ST7567_NOP = const(0xE3)
#ST7567_TEST1 = const(0xFE) # do not use
#ST7567_TEST2 = const(0xFF) # do not use

class ST7567(framebuf.FrameBuffer):
    def __init__(self, spi, dc, cs=None, rs=None, rotation=0, inverse: boolean=False, contrast=0x1F, regulation_ratio=0x03) -> None:
        # override framebuf parent
        self._xoffset = (0x00 if rotation == 0 else 0x04) # rotation by 180 needs a column offset
        self.spi = spi
        self.dc = dc
        if cs != None:
            self.cs = cs
            cs.init(cs.OUT, value=1)
        if rs != None:
            self.rs = rs
            rs.init(rs.OUT, value=0)

        self.buffer=bytearray(128*64//8)
        super().__init__(self.buffer, 128, 64, framebuf.MONO_VLSB)
        self.fill(0) # clear buffer
        self.reset()
        self.show() # clear DDRAM pages 0~8
        self.init(rotation, inverse, contrast, regulation_ratio)
        self.rotate(rotation)
        self.invert(inverse)

    def reset(self) -> None:
        # hardware reset if available
        if self.rs != None:
            self.rs.value(0)
            time.sleep_us(5+1) # >5us
            self.rs.value(1)
            time.sleep_us(5+1) # >5us
        # software reset
        self._write_command(ST7567_RESET)

    def init(self, rotation=0, inverse=False, contrast=0x1F, regulation_ratio=0x03) -> None:
        # required after a reset
        init_commands = [
            ST7567_SET_BOOSTER_START, ST7567_SET_BOOSTER_4X,
            ST7567_BIAS_SELECT_1DIV7,
            (ST7567_SEG_DIRECTION_REVERSE if rotation == 180 else ST7567_SEG_DIRECTION_NORMAL), # SEG direction
            (ST7567_COM_DIRECTION_NORMAL if rotation == 180 else ST7567_COM_DIRECTION_REVERSE), # COM direction
            (ST7567_DISPLAY_INVERSE if inverse else ST7567_DISPLAY_NORMAL), # invert display
            ST7567_REGULATION_RATIO | (regulation_ratio & 0x07), # V0 = RR X [ 1 – (63 – EV) / 162 ] X 2.1
            ST7567_SET_EV_START, contrast & 0x3F, # see above
            ST7567_POWER_CONTROL | 0x04, # turn on booster
            ST7567_POWER_CONTROL | 0x06, # turn on regulator
            ST7567_POWER_CONTROL | 0x07, # turn on follower
            ST7567_SET_START_LINE | 0x00,
            ST7567_DISPLAY_ALL_PIXELS_NORMAL,
            ST7567_DISPLAY_ON
        ]
        #print('[{}]'.format(', '.join(hex(x) for x in init_commands)))
        self._write_command(init_commands)

    def contrast(self, contrast=0x1F) -> None:
        self._write_command(ST7567_SET_EV_START)
        self._write_command(contrast & 0x3F)
        
    def invert(self, inverse: boolean=False) -> None:
        if inverse == False:
            self._write_command(ST7567_DISPLAY_NORMAL)
        else:
            self._write_command(ST7567_DISPLAY_INVERSE)

    def rotate(self, rotation=0) -> None:
        # orientation can be 0 or 180
        if rotation == 0:
            self._write_command(ST7567_SEG_DIRECTION_NORMAL) 
            self._write_command(ST7567_COM_DIRECTION_NORMAL)
            self._xoffset = 0x00
        elif rotation == 180:
            self._write_command(ST7567_SEG_DIRECTION_REVERSE)
            self._write_command(ST7567_COM_DIRECTION_REVERSE)
            self._xoffset = 0x04 # quirk of the ST7567

    def sleep(self, on: boolean=True) -> None:
        # enable/disable low power mode (turns off visible display)
        # keeps display RAM & register settings
        # From datasheet:
        #   stops internal oscillation circuit;
        #   stops the built-in power circuits;
        #   stops the LCD driving circuits and keeps the common and segment outputs at VSS.
        #   After exiting Power Save mode, the settings will return to be as they were before.
        if on:
            self._write_command(ST7567_DISPLAY_OFF)
            self._write_command(ST7567_DISPLAY_ALL_PIXELS_ON)
            #time.sleep_ms(250) # can physically remove power after 250ms to POWER OFF
        else:
            self._write_command(ST7567_DISPLAY_ALL_PIXELS_NORMAL)
            self._write_command(ST7567_DISPLAY_ON)       

    def show(self) -> None:
        # override framebuf parent
        self._write_command([ST7567_SET_START_LINE | 0x00])
        for page_count in range(8): # 64 / 8
            self._write_command([ST7567_SET_PAGE_ADDRESS | page_count, ST7567_SET_COL_ADDRESS_MSB | 0x00, ST7567_SET_COL_ADDRESS_LSB | self._xoffset])
            self._write_data(self.buffer[(128 * page_count):(128 * page_count + 128)])

    def _write_data(self, data: bytearray) -> None:
        self.cs.value(0)
        self.dc.value(1)
        self.spi.write(data)
        self.cs.value(1)

    def _write_command(self, cmd: int) -> None:
        self.cs.value(0)
        self.dc.value(0)
        self.spi.write(bytearray(cmd))
        self.cs.value(1)
