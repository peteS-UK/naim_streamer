"""Naim RC5 infrared codes."""

from dataclasses import dataclass

from infrared_protocols.commands.rc5 import RC5Command

STREAMER_ADDRESS = 0x15
PREAMP_ADDRESS = 0x10


def _streamer(command: int) -> RC5Command:
    return RC5Command(address=STREAMER_ADDRESS, command=command)


def _preamp(command: int) -> RC5Command:
    return RC5Command(address=PREAMP_ADDRESS, command=command, repeat_count=1)


class NaimIRCodes:
    """Naim streamer (address 0x15) and preamp (address 0x10) RC5 codes."""

    # Transport
    PLAY = _streamer(0x35)
    STOP = _streamer(0x36)
    PREVIOUS = _streamer(0x21)
    NEXT = _streamer(0x20)
    REWIND = _streamer(0x32)
    FASTFORWARD = _streamer(0x34)
    REPEAT = _streamer(0x1D)
    SHUFFLE = _streamer(0x38)

    # Navigation
    UP = _streamer(0x50)
    DOWN = _streamer(0x51)
    LEFT = _streamer(0x55)
    RIGHT = _streamer(0x56)
    OK = _streamer(0x57)
    EXIT = _streamer(0x53)
    INFO = _streamer(0x0F)
    SETUP = _streamer(0x54)
    DISPLAY = _streamer(0x47)
    PRESET = _streamer(0x0E)
    STORE = _streamer(0x29)

    # Keypad
    ZERO = _streamer(0x00)
    ONE = _streamer(0x01)
    TWO = _streamer(0x02)
    THREE = _streamer(0x03)
    FOUR = _streamer(0x04)
    FIVE = _streamer(0x05)
    SIX = _streamer(0x06)
    SEVEN = _streamer(0x07)
    EIGHT = _streamer(0x08)
    NINE = _streamer(0x09)

    # Inputs
    CD = _streamer(0x15)
    RADIO = _streamer(0x14)
    PC = _streamer(0x3D)
    IPOD = _streamer(0x43)
    TV = _streamer(0x44)
    AV = _streamer(0x46)
    HDD = _streamer(0x46)
    AUX = _streamer(0x22)

    # Volume (preamp)
    VOL_UP = _preamp(0x10)
    VOL_DOWN = _preamp(0x11)
    MUTE = _preamp(0x0D)


@dataclass(frozen=True)
class NaimButton:
    """A remote button: its command key, display details and RC5 code."""

    key: str
    name: str
    code: RC5Command
    icon: str | None = None
    # Name shown in the media player source list; None if not a source.
    source: str | None = None
    # False for commands that are only sent (e.g. as a source), with no entity.
    has_button: bool = True

C = NaimIRCodes

# Single source of truth: button.py builds its entities from this list and
# COMMANDS is derived from it.
BUTTONS: tuple[NaimButton, ...] = (
    NaimButton("play", "Play/Pause", C.PLAY, "mdi:play-pause"),
    NaimButton("stop", "Stop", C.STOP, "mdi:stop"),
    NaimButton("next", "Next", C.NEXT, "mdi:skip-next"),
    NaimButton("previous", "Previous", C.PREVIOUS, "mdi:skip-previous"),
    NaimButton("mute", "Mute", C.MUTE, "mdi:volume-off"),
    NaimButton("vol+", "Volume Up", C.VOL_UP, "mdi:volume-plus"),
    NaimButton("vol-", "Volume Down", C.VOL_DOWN, "mdi:volume-minus"),
    NaimButton("disp", "Display", C.DISPLAY),
    NaimButton("one", "One", C.ONE, "mdi:numeric-1"),
    NaimButton("two", "Two", C.TWO, "mdi:numeric-2"),
    NaimButton("three", "Three", C.THREE, "mdi:numeric-3"),
    NaimButton("four", "Four", C.FOUR, "mdi:numeric-4"),
    NaimButton("five", "Five", C.FIVE, "mdi:numeric-5"),
    NaimButton("six", "Six", C.SIX, "mdi:numeric-6"),
    NaimButton("seven", "Seven", C.SEVEN, "mdi:numeric-7"),
    NaimButton("eight", "Eight", C.EIGHT, "mdi:numeric-8"),
    NaimButton("nine", "Nine", C.NINE, "mdi:numeric-9"),
    NaimButton("zero", "Zero", C.ZERO, "mdi:numeric-0"),
    NaimButton("preset", "Preset", C.PRESET),
    NaimButton("store", "Store", C.STORE, "mdi:bookmark"),
    NaimButton("ok", "OK", C.OK),
    NaimButton("up", "Up", C.UP, "mdi:arrow-up"),
    NaimButton("down", "Down", C.DOWN, "mdi:arrow-down"),
    NaimButton("left", "Left", C.LEFT, "mdi:arrow-left"),
    NaimButton("right", "Right", C.RIGHT, "mdi:arrow-right"),
    NaimButton("shuffle", "Shuffle", C.SHUFFLE, "mdi:shuffle"),
    NaimButton("repeat", "Repeat", C.REPEAT, "mdi:repeat"),
    NaimButton("info", "Info", C.INFO, "mdi:information-box"),
    NaimButton("setup", "Setup", C.SETUP),
    NaimButton("rewind", "Rewind", C.REWIND, "mdi:rewind"),
    NaimButton("fastforward", "Fast Forward", C.FASTFORWARD, "mdi:fast-forward"),
    # Sources, in the order they appear in the source list.
    NaimButton("cd", "CD", C.CD, "mdi:disc", source="CD"),
    NaimButton("radio", "Radio", C.RADIO, "mdi:radio", source="Radio"),
    NaimButton("pc", "PC", C.PC, "mdi:laptop", source="PC"),
    NaimButton("ipod", "iPod", C.IPOD, "mdi:ipod", source="iPod"),
    NaimButton("tv", "TV", C.TV, "mdi:television", source="TV"),
    NaimButton("av", "AV", C.AV, source="AV", has_button=False),
    NaimButton("hdd", "HDD", C.HDD, "mdi:harddisk", source="HDD"),
    NaimButton("aux", "AUX", C.AUX, source="Aux"),
    NaimButton("exit", "Exit", C.EXIT, "mdi:keyboard-return"),
)

COMMANDS: dict[str, RC5Command] = {button.key: button.code for button in BUTTONS}

SOURCES: tuple[str, ...] = tuple(b.source for b in BUTTONS if b.source)
SOURCE_TO_KEY: dict[str, str] = {b.source: b.key for b in BUTTONS if b.source}