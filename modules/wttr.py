import requests
import logging
from urllib.parse import quote

logger = logging.getLogger(__name__)

# Checked in order; the first keyword found in the condition wins
EMOJIS = [
    ("🌩️", ["thunder"]),
    ("🌨️", ["snow shower", "shower snow", "blizzard"]),
    ("❄", ["snow", "sleet", "ice"]),
    ("🌧️", ["rain", "drizzle", "shower"]),
    ("🌫️", ["mist", "fog", "haze"]),
    ("🌤️", ["partly"]),
    ("☁️", ["cloud", "overcast"]),
    ("☀️", ["sunny", "clear"]),
    ("🌬️", ["wind"]),
]


class WeatherFetcher:
    def __init__(self, location):
        self.location = location

    def get_weather(self):
        """Return formatted weather text, or None if it could not be fetched."""
        # "|" separators so multi-word conditions ("Patchy rain nearby") parse cleanly
        url = f"https://wttr.in/{quote(self.location)}?format=%C|%t|%w|%S|%s"
        try:
            response = requests.get(url, timeout=30)
            if response.status_code != 200:
                logger.error(f"Failed to fetch weather data: HTTP {response.status_code}")
                return None

            condition, temperature, wind, dawn, sunset = (
                part.strip() for part in response.text.strip().split("|")
            )

            lowered = condition.lower()
            selected_emoji = next(
                (
                    emoji
                    for emoji, keywords in EMOJIS
                    if any(keyword in lowered for keyword in keywords)
                ),
                "",
            )

            output = f"{selected_emoji} {condition}\n".lstrip()
            output += f"🌡️ {temperature}\n"
            output += f"💨 {wind}\n"
            output += f"🌞 {dawn}\n"
            output += f"🌛 {sunset}\n"
            return output
        except Exception as e:
            logger.error(f"Failed to fetch weather data: {e}")
            return None

# Example usage:
# location = "Swansea"
# weather_fetcher = WeatherFetcher(location)
# weather_data = weather_fetcher.get_weather()
# print(weather_data)
