# Naim Streamer Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![maintained](https://img.shields.io/maintenance/yes/2026.svg)](#)
[![maintainer](https://img.shields.io/badge/maintainer-%20%40petes--UK-blue.svg)](#)
[![version](https://img.shields.io/github/v/release/peteS-UK/naim_streamer)](#)

A simple media player to control Naim NDX Streamers from Home Assistant.

The original NDX only provides a basic UpNP interface with play, pause, stop etc. support. Although the metadata is shown for all sources, the commands only work with the UPnP input. However, if you select a remote emitter during setup, all of the buttons from the remote are implemented and work across all inputs.

This integration is for the original NDX.  It may also work with other first generation streamers, such as ND5, NDS etc. but this is untested.  It won't work with later streamers such as NDX2, NDS2 etc. which provide a much richer API and for which other integrations are available.

## Installation

The preferred installation approach is via Home Assistant Community Store - aka [HACS](https://hacs.xyz/). The [repo](https://github.com/peteS-UK/naim_streamer) is installable as a [Custom Repo](https://hacs.xyz/docs/faq/custom_repositories) via HACS.

If you want to download the integration manually, create a new folder called naim_streamer under your custom_components folder in your config folder. If the custom_components folder doesn't exist, create it first. Once created, download the files and folders from the [github repo](https://github.com/peteS-UK/naim_streamer/tree/main/custom_components/naim_streamer) into this new naim_streamer folder.

Once downloaded either via HACS or manually, restart your Home Assistant server.

## Configuration

The integration should discover your steamer automatically and list it in the Discovered list in the integration page. If it's not discovered automatically, for example if your network has multiple subnets, then you can manually add the integration.Go into your Integrations (under Settings, Devices & Services), select Add Integration, and choose the NAIM Streamer integration, or click the shortcut button below (requires My Homeassistant configured).

[![Add Integration to your Home Assistant
instance.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=naim_cdx)

This will display the configuration page

In either case, you're presented with a configuration page.

<img width="1166" height="1448" alt="image" src="https://github.com/user-attachments/assets/fdd373fe-e3aa-4ea1-965f-af04b806a7cd" />

## Remote Entity

The Naim streamers have no published API, and early devices such as the NDX have no API to properly control the device, other than a SOAP interface required for UPnP control. As such, this integration is in two parts. Firstly, it implements the UPnP interface for playback controls and to receive metadata and status information from the streamer. Secondly, if you have a remote ir blaster device which is supported by the [Home Assistant Infrared Integration](https://www.home-assistant.io/integrations/infrared/) as an emitter, and you select it in the Configuration page, it implements all of the buttons from the remote control as buttons in Home Assistant.  The Infrared integration acts as an abstraction layer between this integration and other integrations which actually provide infrared entities, such as [Broadlink](https://www.home-assistant.io/integrations/broadlink/) or [Tuya Local](https://github.com/make-all/tuya-local).

## Volume Control

The NDX doesn't actually have any digital volume control. The volume buttons on the remote as designed to control the volume on a Naim pre-amp. This is actually the preferred designed to maintain maximum sound quality. So, the volume control buttons only affect the volume if you have a Naim pre-amp. They are only available if you have a remote entity defined.

The streamer remote uses a combined Play/Pause button, rather than a separate Pause button.

## Audio format sensor

The audio format sensor uses the MIME type from the current track's DIDL-Lite
resource. It is unknown when the source does not supply a MIME type. The format
may describe a container rather than its codec; unrecognized MIME types are
displayed as reported.

## Temporary infrared diagnostic

The `naim_streamer.test_ir` action sends one Radio or Stop signal through the
selected streamer's configured infrared emitter. In Developer Tools > Actions,
select **Naim Streamer: Test infrared signal** and choose its media player.
Choose `generated` to specify the RC5 toggle (0 or 1), total frames (1-10), and
frame start-to-start interval (90-130 ms). The normal generated signal uses
114 ms; 110 ms is close to the tester's recording. Choose `learned` to send
timings reconstructed from that tester's Radio or Stop recording: both use
three frames, with toggle 0 for Radio and toggle 1 for Stop. The toggle, frames
and interval fields are ignored for `learned`.

The reconstructed signal goes through the same Infrared and emitter integrations
as the generated one. It is not necessarily byte-identical to the original
Broadlink packet, and the 36 kHz carrier is an assumption. For an exact learned
packet comparison, send the original using the Broadlink remote action.

For a fair comparison, keep the same emitter position, wait for the streamer to
settle between attempts, and record each outcome. Try both toggle values at 114
ms and 110 ms with the same frame count, interleaving conditions and repeating
each condition enough times to observe intermittent failures. Switch away from
Radio between trials and record that intervening command too: receiver toggle
state can depend on previous presses. Stop tests need playback restarted for
each trial. Enable INFO logging for `custom_components.naim_streamer.ir_diagnostics`
to record the test parameters and send completion. Completion means the emitter
accepted the request, not that the streamer received or acted on it.

```yaml
logger:
  logs:
    custom_components.naim_streamer.ir_diagnostics: info
```
