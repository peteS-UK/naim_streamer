"""Naim RC5 infrared codes."""

from dataclasses import dataclass

from infrared_protocols.commands.rc5 import RC5Command

from .codes.naim.gen1_preamp import NaimGen1PreampCode
from .codes.naim.gen1_streamer import NaimGen1StreamerCode


class NaimIRCodes:
    """Naim streamer (address 0x15) and preamp (address 0x10) RC5 codes."""

    # Transport
    PLAY = NaimGen1StreamerCode.PLAY.to_command()
    STOP = NaimGen1StreamerCode.STOP.to_command()
    PREVIOUS = NaimGen1StreamerCode.PREVIOUS.to_command()
    NEXT = NaimGen1StreamerCode.NEXT.to_command()
    REWIND = NaimGen1StreamerCode.REWIND.to_command()
    FASTFORWARD = NaimGen1StreamerCode.FAST_FORWARD.to_command()
    REPEAT = NaimGen1StreamerCode.REPEAT.to_command()
    SHUFFLE = NaimGen1StreamerCode.SHUFFLE.to_command()

    # Navigation
    UP = NaimGen1StreamerCode.UP.to_command()
    DOWN = NaimGen1StreamerCode.DOWN.to_command()
    LEFT = NaimGen1StreamerCode.LEFT.to_command()
    RIGHT = NaimGen1StreamerCode.RIGHT.to_command()
    OK = NaimGen1StreamerCode.OK.to_command()
    EXIT = NaimGen1StreamerCode.EXIT.to_command()
    INFO = NaimGen1StreamerCode.INFO.to_command()
    SETUP = NaimGen1StreamerCode.SETUP.to_command()
    DISPLAY = NaimGen1StreamerCode.DISPLAY.to_command()
    PRESET = NaimGen1StreamerCode.PRESET.to_command()
    STORE = NaimGen1StreamerCode.STORE.to_command()

    # Keypad
    ZERO = NaimGen1StreamerCode.ZERO.to_command()
    ONE = NaimGen1StreamerCode.ONE.to_command()
    TWO = NaimGen1StreamerCode.TWO.to_command()
    THREE = NaimGen1StreamerCode.THREE.to_command()
    FOUR = NaimGen1StreamerCode.FOUR.to_command()
    FIVE = NaimGen1StreamerCode.FIVE.to_command()
    SIX = NaimGen1StreamerCode.SIX.to_command()
    SEVEN = NaimGen1StreamerCode.SEVEN.to_command()
    EIGHT = NaimGen1StreamerCode.EIGHT.to_command()
    NINE = NaimGen1StreamerCode.NINE.to_command()

    # Inputs
    CD = NaimGen1StreamerCode.CD.to_command()
    RADIO = NaimGen1StreamerCode.RADIO.to_command()
    PC = NaimGen1StreamerCode.PC.to_command()
    IPOD = NaimGen1StreamerCode.IPOD.to_command()
    TV = NaimGen1StreamerCode.TV.to_command()
    AV = NaimGen1StreamerCode.AV.to_command()
    HDD = NaimGen1StreamerCode.HDD.to_command()
    AUX = NaimGen1StreamerCode.AUX.to_command()

    # Volume (preamp)
    VOL_UP = NaimGen1PreampCode.VOLUME_UP.to_command()
    VOL_DOWN = NaimGen1PreampCode.VOLUME_DOWN.to_command()
    MUTE = NaimGen1PreampCode.MUTE.to_command()


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
