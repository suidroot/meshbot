import defusedxml.ElementTree as ET
from urllib.parse import quote
from urllib.request import urlopen
import logging

logger = logging.getLogger(__name__)

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
