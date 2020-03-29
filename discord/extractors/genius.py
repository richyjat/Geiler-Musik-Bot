"""
Genius
"""
import re
import traceback
import urllib.parse
from typing import Tuple

import aiohttp
import async_timeout
from bs4 import BeautifulSoup

import logging_manager
from bot.type.errors import Errors
from bot.type.exceptions import BasicError, NoResultsFound

# pulled from my project ArtistWordRanker:
# https://github.com/tooxo/ArtistWordRanker


class Genius:
    """
    Genius
    """

    @staticmethod
    async def search_genius(track_name: str, artist: str):
        """
        Search Genius
        @param track_name:
        @param artist:
        @return:
        """
        base_url = "https://genius.com/api/search/multi?q="
        url = base_url + urllib.parse.quote(
            re.sub(r"\(.+\)", string=track_name, repl="")
            + " "
            + re.sub(r"\(.+\)", string=artist, repl="")
        )
        async with async_timeout.timeout(timeout=8):
            async with aiohttp.request("GET", url=url) as resp:
                if resp.status not in (200, 301, 302):
                    raise BasicError(Errors.default)
                response = await resp.json()
                try:
                    for cat in response["response"]["sections"]:
                        for item in cat["hits"]:
                            if not item["index"] == "song":
                                continue
                            if item["result"]["url"].endswith("lyrics"):
                                return item["result"]["url"]
                except (IndexError, ValueError, TypeError):
                    traceback.print_exc()
                    raise NoResultsFound(Errors.no_results_found)
                raise NoResultsFound(Errors.no_results_found)

    @staticmethod
    async def extract_from_genius(url: str) -> Tuple[str, str]:
        """
        Extract lyrics from genius
        @param url:
        @return:
        """
        async with async_timeout.timeout(timeout=8):
            async with aiohttp.request("GET", url=url) as resp:
                if resp.status not in (200, 301, 302):
                    logging_manager.LoggingManager().info(
                        "Genius search failed with: " + url
                    )
                    raise BasicError(Errors.default)
                soup = BeautifulSoup(await resp.text(), "html.parser")
                div = soup.find("div", {"class", "lyrics"})
                artist = soup.find(
                    "a",
                    {
                        "class": "header_with_cover_art-primary_"
                        "info-primary_artist"
                    },
                ).text
                title = soup.find(
                    "h1", {"class": "header_with_cover_art-primary_info-title"}
                ).text
                text = div.text
                text = re.sub(r"<.+>", "", text)
                return (
                    LyricsCleanup.clean_up(lyrics=text),
                    artist + " - " + title,
                )


class LyricsCleanup:
    """
    LyricsCleanup
    """

    @staticmethod
    def remove_html_tags(lyrics: str):
        """
        This removes any other html tags from the lyrics
        (the regex was stolen from here: https://www.regextester.com/93515)
        :param lyrics: input lyrics
        :return: filtered lyrics
        """
        html_tag_regex = r"<[^>]*>"
        return re.sub(pattern=html_tag_regex, string=lyrics, repl="")

    @staticmethod
    def remove_double_spaces(lyrics: str) -> str:
        """
        Remove double spaces from the lyrics
        @param lyrics:
        @return:
        """
        while "  " in lyrics:
            lyrics = lyrics.replace("  ", " ")
        return lyrics

    @staticmethod
    def remove_start_and_end_spaces(lyrics: str) -> str:
        """
        Remove spaces at the start and the end of the lyrics
        @param lyrics:
        @return:
        """
        start_of_line = r"^[ ]+"
        end_of_line = r"[ ]+$"
        lyrics = re.sub(pattern=start_of_line, string=lyrics, repl="")
        lyrics = re.sub(pattern=end_of_line, string=lyrics, repl="")
        return lyrics

    @staticmethod
    def clean_up(lyrics: str) -> str:
        """
        runs all of them
        :param lyrics:
        :return:
        """
        return LyricsCleanup.remove_start_and_end_spaces(
            LyricsCleanup.remove_double_spaces(
                LyricsCleanup.remove_html_tags(lyrics=lyrics)
            )
        )
