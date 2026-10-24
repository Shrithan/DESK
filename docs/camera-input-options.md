# Multiple-iPhone input alternatives — researched 2026-10-24

The Mac exposed only one iPhone camera during native enumeration: the iPhone 14
Pro Max, plus MacBook and Desk View devices. Desk View is not another phone.
The second connected iPhone has not been verified as an independent live source.

## Camera for OBS Studio — preferred USB trial

The vendor documents two or three iPhones as independent OBS sources over USB:
https://obs.camera/articles/multi-camera-iphone-obs/

Install the iPhone app on each device, OBS Studio and the matching iOS Camera
plugin on the Mac. Open each phone app in the foreground, choose USB, connect data
cables, and add one iOS Camera source per device in OBS. Start with 1080p30 and
verify both live images. This uses the app/plugin transport instead of depending
on Apple Continuity exposing every phone as a webcam.

The app supports autofocus, tap-to-focus and locked focus:
https://obs.camera/docs/camera-controls/

These are separate OBS sources, not automatically two browser camera devices.
Our tracker still needs a source adapter. A fixed uncropped side-by-side OBS
virtual-camera frame could be split into two images, or a supported per-source
transport can preserve independent streams. Neither adapter has been implemented
or tested here. Do not assume the normal OBS virtual camera exposes one camera
per input. The app offers a trial; verify current App Store terms/device limits
before buying. USB feeds are not hardware-genlocked; measure timing differences.

## Camo Studio + Camo Camera

Camo documents multi-camera layers as a core macOS feature and USB-connected phones:
https://camo.com/blog/camo-flyout-feedback
https://camo.com/support/camo/camo-getting-started

Focus-control availability and paid-plan features vary:
https://camo.com/pricing

Good alternative for capture controls and viewing both inputs. Independent live
export to our tracker still needs verification, rather than assuming a two-camera
composite is two webcam devices.

## VDO.Ninja — browser/network alternative

No phone app installation; each phone publishes its own WebRTC feed/view link:
https://docs.vdo.ninja/getting-started/vdo.ninja-basics

Useful when phones cannot use the same Apple camera workflow. It requires network
transport and a WebRTC/frame adapter for the local tracker. It is not USB video
just because a charging cable is attached. No streaming session was started.
