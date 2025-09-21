# Naim Streamer Integration for Home Assistant

A simple media player to control Naim Streamers from Home Assistant.

It's initially tested with NDX.

Since there's no direct control of the original NDX for some functions, this uses a Broadlink remote device to send the IR commands to the NDX if available for some functions and SOAP commands where possible.
