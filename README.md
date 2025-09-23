# Naim Streamer Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
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
