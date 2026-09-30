# MeshBot

![Meshbot](./img/meshbot.png)

MeshBot is an OpenSource Python program designed to run on computers with a connected Meshtastic device, allowing users to send and receive messages efficiently over a mesh network.

Our Mission: 
 - To provied low-bandwidth functionality to a low bandwidth mesh.  This has originated in the EU where we have 1x longfast channel, and 10% duty cycle, so we try hard to make this low bandwidth, efficent, purposeful and helpful.  
 - For those outside of the EU, knock yourselves out, its opensource, modify at will. Just please dont be offended if we reject high bandwidth pull-requests, but we have no issues with extending commands.
 - As we are open source and an open community, please publish and share your meshtastic work. 

## Features

- Broadcast messages: Send text broadcasts to all devices on the mesh network.
- Weather updates: Get real-time weather updates for a specified location.
- Tides information: Receive tidal information for coastal areas.
- Whois: Query one of two User databases: mpowered247 or liamcottle
- Simple BBS: Store and retrieve messages via the bot

## Requirements

- Python 3.x
- Meshtastic Python library
- Access to a Meshtastic device [Meshtastic](https://meshtastic.org)
- Serial drivers for your meshtastic device, See [Installing Serial Drivers](https://meshtastic.org/docs/getting-started/serial-drivers/)

## Installation

1. Clone this repository to your local machine:

```
git clone https://github.com/868meshbot/meshbot.git
```

2. Navigate into the folder and setup a virtual environment

```
cd meshbot
python3 -m venv .venv
. .venv/bin/activate
```

3. Install the required dependencies:

```
pip install -r requirements.txt
```

4. Connect your Meshtastic device to your computer via USB and run the program

```
python ./meshbot.py
```

## Configuration (NEW)

We have revamped the configuration, there is now a ''settings.yaml'' file, which we believe makes the program easier to manage

Example Content:

```
---
LOCATION: "Swansea"
TIDE_LOCATION: "Swansea"
MYNODE: "3663493700"
MYNODES:
  - "3663493700"
  - "1234567890"
DBFILENAME: "./db/nodes.db"
DM_MODE: True
FIREWALL: True
DUTYCYCLE: True
```

Description

- LOCATION and TIDE_LOCATION = These should be obvious
- TIDE_NOAA_STATION = (US only) NOAA tide station ID to use instead of TIDE_LOCATION, which only covers the UK. Find yours at https://tidesandcurrents.noaa.gov/map/ (e.g. 8418150 for Portland, ME)
- MYNODE = The hw address of the node connected in int/number form. This is so the bot only responds to DMs
- MYNODES = A list of nodes (in int/number form) that are permitted to interact with the bot. Only these nodes may use the admin commands #fw, #dm and #kill_all_robots, even with the firewall off
- DBFILENAME = Configure which user database file to use by default (overridden by --db)
- BBS_FILENAME = Where BBS messages are stored so they survive a restart (default ./db/bbs.db)
- KILL_STRING = Text sent by #kill_all_robots after confirmation; the command is disabled if unset
- MESSAGE_LOG = Text file that records every message the bot sees (public channels and DMs) plus the bot's own replies (default ./messages.log). Set to "" to disable
- MESSAGE_LOG_LIMIT = Maximum number of messages kept in MESSAGE_LOG; the oldest are dropped first (default 1000)

Each line of the message log looks like:

```
2026-09-30 11:40:49 | RX | PUBLIC | LongFast | !00000007 (BOB) -> all | hello mesh
```
- DM_MODE = True: Only respond to DMs; False: responds to all traffic
- FIREWALL = True: Only respond to MYNODES; False: responds to all traffic
- DUTYCYCLE: True: Respect 10% Dutycycle in EU, false to disable for countries without Dutycycle

## Usage

Run the MeshBot program:

```
python meshbot.py --help
```

Example on Linux:

```
python meshbot.py --port /dev/ttyUSB0
```

Example on OSX:

```
python meshbot.py --port /dev/cu.usbserial-0001
```

Example on Windows:

```
python meshbot.py --port COM7
```

Example using TCP client:

```
python meshbot.py --host meshtastic.local
or
python meshbot.py --host 192.168.0.100
```

### Run on boot (Linux / systemd)

`meshbot.service` runs the bot as a service that starts on boot and restarts if the radio drops. It assumes MeshBot is installed in `/opt/meshbot` with its virtual environment in `.venv`, running as a `meshbot` user:

```
sudo useradd --system --home /opt/meshbot --groups dialout meshbot
sudo chown -R meshbot:meshbot /opt/meshbot
```

Edit `meshbot.service` if your paths or user differ, and set `--port` (ideally a `/dev/serial/by-id/...` path, which stays the same across reboots) or `--host`. Then:

```
sudo cp meshbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now meshbot
journalctl -u meshbot -f
```

## Bot interaction

You bot will be accessible through the meshtastic mesh network through the node name. DM the bot/node and issue any of the following commands:

- #test : receive a test message
- #tst-detail : as #test above only more detail e.g snr,rssi, hop count (thanks to [rohanki](https://github.com/rohanki))
- #weather : local weather report
- #tides : tide info (dont forget to change the default town in the source)
- #whois #xxxx : retrieve name and node info for a node based on last 4 chars of address
- #bbs any : do I have any messages?
- #bbs post !address message : post a message on the bbs for a given user at !address
- #bbs get : retrieve your message(s) left by another user(s)

## Contributors

- [868meshbot](https://github.com/868meshbot)

## Acknowledgements

This project utilizes the Meshtastic Python library, which provides communication capabilities for Meshtastic devices. For more information about Meshtastic, visit [meshtastic.org](https://meshtastic.org/).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## References

Database of IDs, long_name and short_names obtained from the node list from the following URLs:

- [https://map.mpowered247.com/](https://map.mpowered247.com/)
- [https://meshtastic.liamcottle.net/](https://meshtastic.liamcottle.net/)
