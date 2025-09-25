# Naim Streamer Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![maintained](https://img.shields.io/maintenance/yes/2025.svg)](#)
[![maintainer](https://img.shields.io/badge/maintainer-%20%40petes--UK-blue.svg)](#)
[![version](https://img.shields.io/github/v/release/peteS-UK/naim_streamer)](#)

A simple media player to control Naim Streamers from Home Assistant.

It's initially tested with NDX.

The original NDX only provides a basic UpNP interface with play, pause, stop etc. support. Although the metadata is shown for all sources, the commands only work with the UPnP input. However, if you select a Broadlink remote during setup, all of the buttons from the remote are implemented and work across all inputs.

## Installation

The preferred installation approach is via Home Assistant Community Store - aka [HACS](https://hacs.xyz/). The [repo](https://github.com/peteS-UK/naim_streamer) is installable as a [Custom Repo](https://hacs.xyz/docs/faq/custom_repositories) via HACS.

If you want to download the integration manually, create a new folder called naim_streamer under your custom_components folder in your config folder. If the custom_components folder doesn't exist, create it first. Once created, download the files and folders from the [github repo](https://github.com/peteS-UK/naim_streamer/tree/main/custom_components/naim_streamer) into this new naim_streamer folder.

Once downloaded either via HACS or manually, restart your Home Assistant server.

## Configuration

The integration should discover your steamer automatically and list it in the Discovered list in the integration page. If it's not discovered automatically, for example if your network has multiple subnets, then you can manually add the integration. In either case, you're presented with a configuration page.

<img width="515" height="947" alt="image" src="https://github.com/user-attachments/assets/5a247b35-57ab-496a-b2a7-02bef2d67c6d" />

## Broadlink Entity

The Naim streamers have no published API, and early devices such as the NDX have no API to properly control the device, other than a SOAP interface required for UPnP control.  As such, this integration is in two parts.  Firstly, it implements the UPnP interface for playback controls and to receive metadata and status information from the streamer.  Secondly, if you have a Broadlink remote device and you select it in the Configuration page, it implements all of the buttons from the remote control as buttons in Home Assistant.

## Volume Control

The NDX doesn't actually have any digital volume control.  The volume buttons on the remote as designed to control the volume on a Naim pre-amp.  This is actually the preferred designed to maintain maximum sound quality.  So, the volume control buttons only affect the volume if you have a Naim pre-amp.


