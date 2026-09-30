import defusedxml.ElementTree as ET
import json
from datetime import datetime
from urllib.parse import quote, urlencode
from urllib.error import HTTPError
from urllib.request import urlopen
import logging

logger = logging.getLogger(__name__)

NOAA_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"


class NoaaTides:
    """US tide predictions from NOAA CO-OPS, by station ID (e.g. 8418150 for Portland, ME)."""

    def __init__(self, station):
        self.station = str(station)

    def get_tides(self):
        """Return formatted tide text, or None if it could not be fetched."""
        params = {
            "product": "predictions",
            "datum": "MLLW",
            "station": self.station,
            "date": "today",
            "time_zone": "lst_ldt",
            "interval": "hilo",
            "units": "english",
            "format": "json",
            "application": "meshbot",
        }
        try:
            with urlopen(f"{NOAA_URL}?{urlencode(params)}", timeout=30) as Client:
                data = json.load(Client)
            if "error" in data:
                logger.error("Failed to fetch tide data: %s", data["error"].get("message", "").strip())
                return None
            predictions = data["predictions"]
            if not predictions:
                logger.error("Failed to fetch tide data: no predictions for station %s", self.station)
                return None
            date = datetime.strptime(predictions[0]["t"], "%Y-%m-%d %H:%M")
            formatted_output = f"{date:%a %d %B %Y}\n"
            for prediction in predictions:
                time = prediction["t"].split()[1]
                tide_type = "High" if prediction["type"] == "H" else "Low"
                formatted_output += f"{time} - {tide_type}\n"
            return formatted_output
        except HTTPError as e:
            e.close()
            logger.error("Failed to fetch tide data for station %s: %s", self.station, e)
        except Exception as e:
            logger.error("Failed to fetch tide data: %s", e)
        return None

class TidesScraper:
    def __init__(self, location):
        slug = "-".join(location.strip().lower().split())
        self.rss_url = "https://www.tidetimes.org.uk/" + quote(slug) + "-tide-times.rss"

    def get_tides(self):
        """Return formatted tide text, or None if it could not be fetched."""
        try:
            with urlopen(self.rss_url, timeout=30) as Client:
                xml_page = Client.read()
                root = ET.fromstring(xml_page)
                for item in root.iter("item"):
                    description = item.find("description").text
                    description = description.replace("&lt;br/&gt;", "\n").replace(
                        "&amp;amp;", "&"
                    )
                    lines = description.split("<br/>")
                    date = lines[0].split("on ")[1].strip()
                    tide_info = [line.split(" - ") for line in lines[2:] if line]
                    formatted_output = f"{date}\n"
                    for info in tide_info:
                        time = info[0].strip()
                        tide_type = "High" if "High" in info[1] else "Low"
                        formatted_output += f"{time} - {tide_type}\n"
                    return formatted_output
                logger.error("Failed to fetch tide data: no items in feed")

        except Exception as e:
            logger.error("Failed to fetch tide data: %s", e)
        return None



# # Example usage:
# rss_url = "https://www.tidetimes.org.uk/swansea-tide-times.rss"
# location="Swansea";
# scraper = TidesScraper(location)
# scraper.get_tides()
