#!python3
# -*- coding: utf-8 -*-

"""
MeshBot
=======================

meshbot.py: A message bot designed for Meshtastic, providing information from modules upon request:
* weather information 
* tides information 
* whois search
* simple bbs

Author:
- Andy
- April 2024
- Ben Mason , Feb 2026

MIT License

Copyright (c) 2024 Andy

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


import argparse
import logging
import secrets
import string
import sys
import threading
import time
from pathlib import Path
import requests
import yaml

try:
    import meshtastic.serial_interface
    import meshtastic.tcp_interface
    from pubsub import pub
except ImportError:
    print(
        "ERROR: Missing meshtastic library!\nYou can install it via pip:\npip install meshtastic\n"
    )
    sys.exit(1)

import serial.tools.list_ports

from modules.bbs import BBS
from modules.msglog import MessageLog
from modules.tides import NoaaTides, TidesScraper
from modules.twin_cipher import TwinHexDecoder, TwinHexEncoder
from modules.whois import Whois
from modules.wttr import WeatherFetcher

# Meshtastic payloads top out around 230 bytes; leave headroom
MAX_TEXT_BYTES = 200
# Transmissions allowed before the bot goes quiet; one is forgiven every DECAY_SECONDS
DUTY_CYCLE_LIMIT = 10
DECAY_SECONDS = 180
REFRESH_SECONDS = 3 * 60 * 60
KILLBOT_CONFIRM_SECONDS = 120
BROADCAST_NUM = 0xFFFFFFFF

# Commands only nodes listed in MYNODES may use, even with the firewall off
ADMIN_COMMANDS = {"#fw", "#dm", "#kill_all_robots"}

HELP_TEXT = (
    "Commands:\n"
    "#help #test #tst-detail\n"
    "#weather #tides\n"
    "#flipcoin #random\n"
    "#twin e|d <text>\n"
    "#whois #<id|name>\n"
    "#bbs any|get|post <!id> <msg>"
)


def find_serial_ports():
    # Use the list_ports module to get a list of available serial ports
    ports = [port.device for port in serial.tools.list_ports.comports()]
    filtered_ports = [
        port for port in ports if "COM" in port.upper() or "USB" in port.upper()
    ]
    return filtered_ports


def truncate_text(text, limit=MAX_TEXT_BYTES):
    """Trim text to fit in `limit` UTF-8 bytes without splitting a character."""
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text
    return data[: limit - 3].decode("utf-8", "ignore") + "…"


def node_id(num):
    """Format a node number the way Meshtastic displays it, e.g. !0a1b2c3d."""
    return f"!{num:08x}"


def parse_on_off(args):
    return args.strip().lower() != "off"


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger()

class MeshBot:

    def __init__(self, ip_host = None, serial_port = None, db = None):
        self.serial_ports = serial_port
        self.ip_host = ip_host
        self.db = db
        self.interface = None
        self.connection_lost = threading.Event()
        self.weather_info = None
        self.tides_info = None

        # Guards transmission_count and cooldown, which the decay thread also touches
        self.lock = threading.Lock()
        self.transmission_count = 0
        self.cooldown = False
        self.kill_armed_by = None
        self.kill_armed_at = 0.0

        self.commands = {
            "#fw": self.command_fw,
            "#dm": self.command_dm,
            "#flipcoin": self.command_flipcoin,
            "#random": self.command_random,
            "#twin": self.command_twin,
            "#weather": self.command_weather,
            "#tides": self.command_tides,
            "#test": self.command_test,
            "#tst-detail": self.command_tst_detail,
            "#whois": self.command_whois,
            "#bbs": self.command_bbs,
            "#kill_all_robots": self.command_kill_all_robots,
            "#help": self.command_help,
        }

        self.load_setting()

    def load_setting(self):

        with open("settings.yaml", "r") as file:
            settings = yaml.safe_load(file) or {}

        self.location = settings.get("LOCATION")
        if not self.location:
            try:
                response = requests.get("https://ipinfo.io/city", timeout=10)
                response.raise_for_status()
                self.location = response.text.strip()
            except requests.RequestException as e:
                raise RuntimeError(
                    "Could not determine location; set LOCATION in settings.yaml"
                ) from e
            if not self.location:
                raise RuntimeError(
                    "Could not determine location; set LOCATION in settings.yaml"
                )
            logger.info(f"Setting location to {self.location}")

        self.tide_location = settings.get("TIDE_LOCATION", self.location)
        # YAML reads unquoted node numbers as ints; compare everything as strings
        mynode = settings.get("MYNODE")
        self.mynode = str(mynode) if mynode is not None else None
        self.mynodes = {str(node) for node in settings.get("MYNODES") or []}
        # --db on the command line overrides DBFILENAME
        self.db_filename = self.db or settings.get("DBFILENAME")
        self.dm_mode = settings.get("DM_MODE", True)
        self.firewall = settings.get("FIREWALL", True)
        self.dutycycle = settings.get("DUTYCYCLE", True)
        self.kill_string = settings.get("KILL_STRING")

        logger.info(f"DUTYCYCLE: {self.dutycycle}")
        logger.info(f"DM_MODE: {self.dm_mode}")
        logger.info(f"FIREWALL: {self.firewall}")
        logger.info(f"Whois DB: {self.db_filename}")
        if self.firewall and not self.mynodes:
            logger.warning("FIREWALL is on but MYNODES is empty; all messages will be ignored")

        self.weather_fetcher = WeatherFetcher(self.location)
        # tidetimes.org.uk only covers the UK; set TIDE_NOAA_STATION for US tides
        noaa_station = settings.get("TIDE_NOAA_STATION")
        if noaa_station:
            self.tides_scraper = NoaaTides(noaa_station)
            logger.info(f"Tides from NOAA station {noaa_station}")
        else:
            self.tides_scraper = TidesScraper(self.tide_location)
        self.bbs = BBS(settings.get("BBS_FILENAME", "./db/bbs.db"))

        # Set MESSAGE_LOG to an empty value to disable message logging
        log_filename = settings.get("MESSAGE_LOG", "./messages.log")
        log_limit = settings.get("MESSAGE_LOG_LIMIT", 1000)
        self.message_log = MessageLog(log_filename, log_limit) if log_filename else None
        if self.message_log:
            logger.info(f"Logging messages to {log_filename} (last {log_limit})")

    # Function to periodically refresh weather and tides data
    def refresh_data(self):
        while True:
            try:
                # Keep the last good value if a fetch fails
                weather = self.weather_fetcher.get_weather()
                if weather:
                    self.weather_info = weather
                tides = self.tides_scraper.get_tides()
                if tides:
                    self.tides_info = tides
            except Exception:
                logger.exception("Data refresh failed")
            time.sleep(REFRESH_SECONDS)

    def _background_resets(self):
        """Forgive one transmission every DECAY_SECONDS and lift cooldown once under the limit."""
        while True:
            time.sleep(DECAY_SECONDS)
            with self.lock:
                self.transmission_count = max(0, self.transmission_count - 1)
                logger.debug(f"Reducing transmission count {self.transmission_count}")
                if self.cooldown and self.transmission_count < DUTY_CYCLE_LIMIT:
                    self.cooldown = False
                    logger.info("Cooldown Disabled.")

    def _under_limit(self):
        with self.lock:
            return not self.dutycycle or self.transmission_count < DUTY_CYCLE_LIMIT

    def _check_duty_cycle(self, sender_id):
        """Return True if the bot may transmit; announces cooldown once when it starts."""
        if not self.dutycycle:
            return True
        with self.lock:
            if self.transmission_count < DUTY_CYCLE_LIMIT:
                return True
            announce = not self.cooldown
            self.cooldown = True
        logger.info("Duty cycle limit reached. Please wait before transmitting again.")
        if announce:
            logger.info("Cooldown enabled.")
            self._send("❌ Bot has reached duty cycle, entering cool down... ❄", sender_id)
        return False

    def _send(self, text, sender_id, wantAck=False):
        """Send a DM, counting it against the duty cycle. Returns True on success."""
        try:
            self.interface.sendText(
                truncate_text(text), wantAck=wantAck, destinationId=sender_id
            )
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False
        with self.lock:
            self.transmission_count += 1
        self._log_message("TX", 0, self.mynode, sender_id, truncate_text(text))
        return True

    def _node_label(self, num):
        """Node ID plus short name if the radio knows it, e.g. !0a1b2c3d (ABCD)."""
        if num is None:
            return "?"
        try:
            num = int(num)
        except (TypeError, ValueError):
            return str(num)
        if num == BROADCAST_NUM:
            return "all"
        label = node_id(num)
        try:
            short_name = self.interface.nodesByNum[num]["user"]["shortName"]
            label += f" ({short_name})"
        except (AttributeError, KeyError, TypeError):
            pass
        return label

    def _channel_name(self, index):
        """Channel name, using the modem preset (e.g. LongFast) for an unnamed primary."""
        try:
            local_node = self.interface.localNode
            name = local_node.channels[index].settings.name
            if name:
                return name
            if index == 0:
                lora = local_node.localConfig.lora
                preset = lora.DESCRIPTOR.fields_by_name["modem_preset"].enum_type \
                    .values_by_number[lora.modem_preset].name
                return "".join(word.capitalize() for word in preset.split("_"))
        except Exception:
            pass
        return f"ch{index}"

    def _log_message(self, direction, channel, from_num, to_num, text, rx_time=None):
        if not self.message_log:
            return
        try:
            to_int = int(to_num) if to_num is not None else None
        except (TypeError, ValueError):
            to_int = None
        kind = "PUBLIC" if to_int == BROADCAST_NUM else "DM"
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(rx_time or time.time()))
        try:
            self.message_log.log(
                f"{timestamp} | {direction} | {kind} | {self._channel_name(channel)} | "
                f"{self._node_label(from_num)} -> {self._node_label(to_num)} | {text}"
            )
        except Exception:
            logger.exception("Failed to log message")

    def command_fw(self, packet, sender_id, args):
        self.firewall = parse_on_off(args)
        logger.info(f"FIREWALL={self.firewall}")

    def command_dm(self, packet, sender_id, args):
        self.dm_mode = parse_on_off(args)
        logger.info(f"DM_MODE={self.dm_mode}")

    def command_flipcoin(self, packet, sender_id, args):
        self._send(secrets.choice(["Heads", "Tails"]), sender_id, wantAck=True)

    def command_random(self, packet, sender_id, args):
        self._send(str(secrets.randbelow(10) + 1), sender_id, wantAck=True)

    def command_twin(self, packet, sender_id, args):
        parts = args.split(maxsplit=1)
        if len(parts) < 2 or parts[0].lower() not in ("e", "d"):
            self._send("Usage: #twin e|d <text>", sender_id)
            return
        mode, content = parts
        try:
            if mode.lower() == "d":
                text = TwinHexDecoder().decrypt(content)
            else:
                text = TwinHexEncoder().encrypt(content)
        except ValueError as e:
            text = f"Error: {e}"
        self._send(text, sender_id, wantAck=True)

    def command_weather(self, packet, sender_id, args):
        self._send(self.weather_info or "Weather data not available.", sender_id, wantAck=True)

    def command_tides(self, packet, sender_id, args):
        self._send(self.tides_info or "Tide data not available.", sender_id, wantAck=True)

    def command_test(self, packet, sender_id, args):
        self._send("🟢 ACK", sender_id, wantAck=True)

    def command_tst_detail(self, packet, sender_id, args):
        details = []
        hop_start, hop_limit = packet.get("hopStart"), packet.get("hopLimit")
        if hop_start is not None and hop_limit is not None:
            hops = hop_start - hop_limit
            details.append("Received directly" if hops == 0 else f"Received {hops} hop(s) away")
        rssi, snr = packet.get("rxRssi"), packet.get("rxSnr")
        if rssi is not None:
            details.append(f"RSSI: {rssi}dBm")
        if snr is not None:
            quality = min(100, max(0, int((snr + 10) * 5)))
            details.append(f"SNR: {snr}dB ({quality}%)")
        reply = "🟢 ACK. " + ", ".join(details) if details else "🟢 ACK"
        self._send(reply, sender_id, wantAck=True)

    def command_whois(self, packet, sender_id, args):
        term = args.strip().lstrip("#").strip()
        if not term:
            self._send("Usage: #whois #<node id|short name>", sender_id)
            return
        if not self.db_filename:
            self._send("Whois database not configured.", sender_id)
            return

        logger.info(f"Querying whois DB {self.db_filename} for: {term}")
        # IDs are stored as 0x61d3c63 or !061d3c63, so search on the bare unpadded hex
        lowered = term.lower()
        hex_term = lowered.removeprefix("!").removeprefix("0x")
        # Short names are at most 4 chars and many are valid hex ("CAFE"), so only
        # treat the term as a node ID if it has a prefix or is too long to be a name
        is_id = all(c in string.hexdigits for c in hex_term) and (
            hex_term != lowered or len(hex_term) > 4
        )
        with Whois(self.db_filename) as whois_search:
            result = None
            if is_id:
                result = whois_search.search_nodes(hex_term.lstrip("0") or "0")
            if not result:
                result = whois_search.search_nodes_sn(term)

        if result:
            found_id, long_name, short_name = result
            whois_data = f"ID:{found_id}\n"
            whois_data += f"Long Name: {long_name}\n"
            whois_data += f"Short Name: {short_name}"
            logger.info(f"Data: {whois_data}")
            self._send(whois_data, sender_id)
        else:
            self._send("No matching record found.", sender_id)

    def _short_name(self, num):
        if self.db_filename:
            with Whois(self.db_filename) as whois_search:
                result = whois_search.search_nodes(f"{num:x}")
            if result:
                return result[2]
        return node_id(num)

    def command_bbs(self, packet, sender_id, args):
        parts = args.split(maxsplit=2)
        subcommand = parts[0].lower() if parts else ""
        mailbox = node_id(sender_id)

        if subcommand == "any":
            count = self.bbs.count_messages(mailbox)
            logger.info(f"{count} messages found")
            self._send(f"You have {count} messages.", sender_id, wantAck=True)

        elif subcommand == "get":
            messages = self.bbs.get_message(mailbox)
            if not messages:
                logger.info("No new messages")
                self._send("No new messages.", sender_id)
                return
            for row_id, content in messages:
                # Anything unsent stays queued for the next #bbs get
                if not self._under_limit() or not self._send(content, sender_id):
                    break
                self.bbs.delete_message(row_id)

        elif subcommand == "post" and len(parts) == 3:
            recipient_hex = parts[1].lower().removeprefix("!")
            if not recipient_hex or not all(c in string.hexdigits for c in recipient_hex):
                self._send("Invalid node ID, use !xxxxxxxx", sender_id)
                return
            recipient = node_id(int(recipient_hex, 16))
            suffix = f". From: {self._short_name(sender_id)}({mailbox})"
            content = truncate_text(parts[2], MAX_TEXT_BYTES - len(suffix.encode("utf-8"))) + suffix
            if self.bbs.post_message(recipient, content):
                self._send(f"Message posted to {recipient}.", sender_id)
            else:
                self._send("Mailbox full, try again later.", sender_id)

        else:
            self._send("Usage: #bbs any|get|post <!id> <msg>", sender_id)

    def command_kill_all_robots(self, packet, sender_id, args):
        if not self.kill_string:
            self._send("KILL_STRING not configured.", sender_id)
            return
        now = time.time()
        if self.kill_armed_by == sender_id and now - self.kill_armed_at < KILLBOT_CONFIRM_SECONDS:
            self.kill_armed_by = None
            self._send(f"💣 Deactivating all reachable bots... {self.kill_string}", sender_id)
        else:
            self.kill_armed_by = sender_id
            self.kill_armed_at = now
            self._send("Confirm", sender_id)

    def command_help(self, packet, sender_id, args):
        self._send(HELP_TEXT, sender_id)

    # Function to handle incoming messages
    def message_listener(self, packet, interface):

        if packet is None or "decoded" not in packet or \
                packet["decoded"].get("portnum") != "TEXT_MESSAGE_APP":
            return

        text = packet["decoded"].get("text", "").strip()
        self._log_message(
            "RX",
            packet.get("channel", 0),
            packet.get("from"),
            packet.get("to"),
            text,
            packet.get("rxTime"),
        )
        if not text.startswith("#"):
            return

        # Dispatch on the first word only, so "#whois #test" can't trigger #test
        parts = text.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        handler = self.commands.get(command)
        if handler is None:
            return

        sender_id = packet["from"]
        is_admin = str(sender_id) in self.mynodes
        logger.info(f"Message {text} from {sender_id}")

        if self.dm_mode and str(packet.get("to")) != self.mynode:
            return
        if (self.firewall or command in ADMIN_COMMANDS) and not is_admin:
            logger.info(f"Ignoring {command} from {sender_id}: not in MYNODES")
            return
        # #fw and #dm don't transmit, so they work during cooldown
        if command not in ("#fw", "#dm") and not self._check_duty_cycle(sender_id):
            return

        logger.info(f"{command} command received, transmission count {self.transmission_count}")
        try:
            handler(packet, sender_id, args)
        except Exception:
            logger.exception(f"Error handling {command}")


    def on_connection_lost(self, interface):
        self.connection_lost.set()

    # Main function
    def run(self):
        logger.info("Starting program.")

        reset_thread = threading.Thread(target=self._background_resets, daemon=True)
        reset_thread.start()

        # Fetch data before listening so early #weather/#tides have something to send
        refresh_thread = threading.Thread(target=self.refresh_data, daemon=True)
        refresh_thread.start()

        if self.ip_host:
            self.interface = meshtastic.tcp_interface.TCPInterface(hostname=self.ip_host, noProto=False)
        else:
            self.interface = meshtastic.serial_interface.SerialInterface(self.serial_ports[0])

        if self.mynode is None:
            my_info = getattr(self.interface, "myInfo", None)
            if my_info is not None:
                self.mynode = str(my_info.my_node_num)
                logger.info(f"MYNODE not set, using connected node {self.mynode}")

        # Receive Meshtastic Messages
        pub.subscribe(self.message_listener, "meshtastic.receive")
        pub.subscribe(self.on_connection_lost, "meshtastic.connection.lost")

        logger.info("Press CTRL-C to terminate the program")
        exit_code = 0
        try:
            # Exit if the radio goes away so a supervisor (e.g. systemd) can restart us
            while not self.connection_lost.wait(1):
                pass
            logger.critical("Lost connection to the radio, exiting.")
            exit_code = 1
        except KeyboardInterrupt:
            logger.info("Shutting down.")
        finally:
            try:
                self.interface.close()
            except Exception as e:
                logger.error(f"Error closing interface: {e}")
        sys.exit(exit_code)

def load_args():
    parser = argparse.ArgumentParser(description="Meshbot a bot for Meshtastic devices")
    parser.add_argument("--port", type=str, help="Specify the serial port to probe")
    parser.add_argument("--db", type=str, help="Specify DB: mpowered or liam")
    parser.add_argument("--host", type=str, help="Specify meshtastic host (IP address) if using API")

    return parser.parse_args()

def main(args):

    cwd = Path.cwd()
    ip_host = None
    serial_ports = None
    db_mode = None

    if args.port:
        serial_ports = [args.port]
        logger.info(f"Serial port {serial_ports}\n")
    elif args.host:
        ip_host = args.host
        logger.info(f"Meshtastic API host {ip_host}\n")
    else:
        serial_ports = find_serial_ports()
        if serial_ports:
            logger.info("Available serial ports:")
            for port in serial_ports:
                logger.info(port)
            logger.info(
                "Im not smart enough to work out the correct port, please use the --port argument with a relevent meshtastic port"
            )
        else:
            logger.critical("No serial ports found.")
        sys.exit(1)

    if args.db:
        if args.db.lower() == "mpowered":
            db_mode = str(cwd) + "/db/nodes.db"
            logger.info(f"Setting DB to mpowered data: {db_mode}")
        elif args.db.lower() == "liam":
            db_mode = str(cwd) + "/db/nodes2.db"
            logger.info(f"Setting DB to Liam Cottle data: {db_mode}")
        else:
            logger.critical(f"Unknown --db {args.db!r}, expected mpowered or liam")
            sys.exit(1)
    else:
        logger.info(f"Default DB")

    meshbot = MeshBot(
        ip_host = ip_host,
        serial_port = serial_ports,
        db = db_mode,
    )

    meshbot.run()

if __name__ == "__main__":
    args = load_args()
    main(args)
