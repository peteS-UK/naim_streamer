"""Infrared codes for first-generation Naim streamers."""

from enum import IntEnum

from infrared_protocols.commands.rc5 import RC5Command

STREAMER_ADDRESS = 0x15


class NaimGen1StreamerCode(IntEnum):
    """Commands for first-generation Naim streamers."""

    PLAY = 0x35
    STOP = 0x36
    PREVIOUS = 0x21
    NEXT = 0x20
    REWIND = 0x32
    FAST_FORWARD = 0x34
    REPEAT = 0x1D
    SHUFFLE = 0x38
    UP = 0x50
    DOWN = 0x51
    LEFT = 0x55
    RIGHT = 0x56
    OK = 0x57
    EXIT = 0x53
    INFO = 0x0F
    SETUP = 0x54
    DISPLAY = 0x47
    PRESET = 0x0E
    STORE = 0x29
    ZERO = 0x00
    ONE = 0x01
    TWO = 0x02
    THREE = 0x03
    FOUR = 0x04
    FIVE = 0x05
    SIX = 0x06
    SEVEN = 0x07
    EIGHT = 0x08
    NINE = 0x09
    CD = 0x15
    RADIO = 0x14
    PC = 0x3D
    IPOD = 0x43
    TV = 0x44
    AV = 0x46
    HDD = 0x46
    AUX = 0x22

    def to_command(self, repeat_count: int = 0, *, toggle: int = 0) -> RC5Command:
        """Build the RC5 command for this code."""
        return RC5Command(
            address=STREAMER_ADDRESS,
            command=self.value,
            toggle=toggle,
            repeat_count=repeat_count,
        )
