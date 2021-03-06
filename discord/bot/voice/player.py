import asyncio
import random
import re
import traceback

import bot.node_controller.NodeVoiceClient
import discord
import logging_manager
from bot.node_controller.controller import NoNodeReadyException
from bot.now_playing_message import NowPlayingMessage
from bot.type.error import Error
from bot.type.errors import Errors
from bot.type.queue import Queue
from bot.type.song import Song
from bot.type.soundcloud_type import SoundCloudType
from bot.type.spotify_song import SpotifySong
from bot.type.spotify_type import SpotifyType
from bot.type.url import Url
from bot.type.variable_store import VariableStore
from bot.type.youtube_type import YouTubeType
from discord.ext import commands
from discord.ext.commands import Cog


class Player(Cog):
    def __init__(self, bot, parent):
        self.bot = bot
        self.parent = parent

    async def pre_player(self, ctx, bypass=None):
        if (
            self.parent.guilds[ctx.guild.id].song_queue.qsize() > 0
            or bypass is not None
        ):
            if bypass is None:
                small_dict = await self.parent.guilds[
                    ctx.guild.id
                ].song_queue.get()
            else:
                small_dict = bypass
            self.parent.guilds[
                ctx.guild.id
            ].now_playing_message = NowPlayingMessage(
                message=await self.parent.send_embed_message(
                    ctx=ctx, message=" Loading ... ", delete_after=None
                ),
                ctx=ctx,
            )
            if small_dict.stream is None:
                if small_dict.link is not None:
                    # url
                    _type = Url.determine_source(small_dict.link)
                    if _type == Url.youtube:
                        youtube_dict = Song.copy_song(
                            await self.parent.youtube.youtube_url(
                                small_dict.link, ctx.guild.id
                            ),
                            small_dict,
                        )
                    elif _type == Url.soundcloud:
                        youtube_dict = Song.copy_song(
                            await self.parent.soundcloud.soundcloud_track(
                                small_dict.link
                            ),
                            small_dict,
                        )
                    else:
                        self.parent.log.warning(
                            "Incompatible Song Type: " + _type
                        )
                        return
                else:
                    if small_dict.title is None:
                        self.parent.log.warning(small_dict)
                    # term
                    youtube_dict = Song.copy_song(
                        await self.parent.youtube.youtube_term(small_dict),
                        small_dict,
                    )
                if isinstance(youtube_dict, Error):
                    if youtube_dict.reason != Errors.error_please_retry:
                        await self.parent.send_error_message(
                            ctx, youtube_dict.reason
                        )
                        await self.parent.guilds[
                            ctx.guild.id
                        ].now_playing_message.message.delete()
                        await self.pre_player(ctx)
                        return
                    await self.parent.guilds[
                        ctx.guild.id
                    ].now_playing_message.message.delete()
                    await self.pre_player(ctx, bypass=small_dict)
                    return
                youtube_dict.user = small_dict.user
                youtube_dict.image_url = small_dict.image_url
                await self.player(ctx, youtube_dict)
                if hasattr(youtube_dict, "title"):
                    asyncio.ensure_future(
                        self.parent.mongo.append_most_played(youtube_dict.title)
                    )
                if hasattr(youtube_dict, "loadtime"):
                    asyncio.ensure_future(
                        self.parent.mongo.append_response_time(
                            youtube_dict.loadtime
                        )
                    )
            else:
                await self.player(ctx, small_dict)
                if hasattr(small_dict, "title"):
                    asyncio.ensure_future(
                        self.parent.mongo.append_most_played(small_dict.title)
                    )
                if hasattr(small_dict, "loadtime"):
                    asyncio.ensure_future(
                        self.parent.mongo.append_response_time(
                            small_dict.loadtime
                        )
                    )

            asyncio.ensure_future(self.preload_song(ctx=ctx))

    async def extract_infos(self, url, ctx):
        url_type = Url.determine_source(url=url)
        if url_type == Url.youtube:
            return await self.extract_first_infos_youtube(url=url, ctx=ctx)
        if url_type == Url.spotify:
            return await self.extract_first_infos_spotify(url=url, ctx=ctx)
        if url_type == Url.soundcloud:
            return await self.extract_first_infos_soundcloud(url=url, ctx=ctx)
        return await self.extract_first_infos_other(url=url, ctx=ctx)

    async def extract_first_infos_youtube(self, url, ctx):
        youtube_type = Url.determine_youtube_type(url=url)
        if youtube_type == Url.youtube_url:
            __song = Song()
            __song.user = ctx.message.author
            __song.link = url
            return [__song]
        if youtube_type == Url.youtube_playlist:
            __songs = []
            __song_list = await self.parent.youtube.youtube_playlist(url)
            if len(__song_list) == 0:
                await self.parent.send_error_message(ctx, Errors.spotify_pull)
                return []
            for track in __song_list:
                track.user = ctx.message.author
                __songs.append(track)
            return __songs

    async def extract_first_infos_soundcloud(self, url, ctx):
        soundcloud_type = Url.determine_soundcloud_type(url)
        if soundcloud_type == Url.soundcloud_track:
            song: Song = await self.parent.soundcloud.soundcloud_track(url)
            if song.title is None:
                self.parent.send_error_message(ctx=ctx, message=Errors.default)
            if isinstance(song, Error):
                self.parent.send_error_message(ctx=ctx, message=song.reason)
                return []
            song.user = ctx.message.author
            return [song]
        if soundcloud_type == Url.soundcloud_set:
            songs: list = await self.parent.soundcloud.soundcloud_playlist(
                url=url
            )
            for song in songs:
                song.user = ctx.message.author
            return songs

    async def extract_first_infos_spotify(self, url, ctx):
        spotify_type = Url.determine_spotify_type(url=url)
        __songs = []
        __song = Song()
        __song.user = ctx.message.author
        if spotify_type == Url.spotify_playlist:
            __song_list = await self.parent.spotify.spotify_playlist(url)
            if len(__song_list) == 0:
                await self.parent.send_error_message(
                    ctx=ctx, message=Errors.spotify_pull
                )
                return []
            for track in __song_list:
                track: SpotifySong
                __song = Song(song=__song)
                __song.title = track.title
                __song.image_url = track.image_url
                __song.artist = track.artist
                __song.song_name = track.song_name
                __songs.append(__song)
            return __songs
        if spotify_type == Url.spotify_track:
            track = await self.parent.spotify.spotify_track(url)
            if track is not None:
                __song.title = track.title
                __song.image_url = track.image_url
                __song.artist = track.artist
                __song.song_name = track.song_name
                return [__song]
            return []
        if spotify_type == Url.spotify_artist:
            song_list = await self.parent.spotify.spotify_artist(url)
            for track in song_list:
                __song = Song(song=__song)
                __song.title = track
                __songs.append(__song)
            return __songs
        if spotify_type == Url.spotify_album:
            song_list = await self.parent.spotify.spotify_album(url)
            for track in song_list:
                __song = Song(song=__song)
                __song.title = track
                __songs.append(__song)
            return __songs

    async def extract_first_infos_other(self, url, ctx):
        if url == "charts":
            __songs = []
            __song = Song()
            __song.user = ctx.message.author
            song_list = await self.extract_first_infos_spotify(
                "https://open.spotify.com/playlist/37i9dQZEVXbMDoHDwVN2tF?si=vgYiEOfYTL-ejBdn0A_E2g",
                ctx,
            )
            for track in song_list:
                track.user = ctx.message.author
                __songs.append(track)
            return __songs
        __song = Song()
        __song.title = url
        __song.user = ctx.message.author
        return [__song]

    async def add_to_queue(
        self, url, ctx, first_index_push=False, playskip=False, shuffle=False
    ):
        if playskip:
            self.parent.guilds[ctx.guild.id].song_queue = Queue()

        songs: list = await self.extract_infos(url=url, ctx=ctx)
        for __song in songs:
            __song: Song
            __song.guild_id = ctx.guild.id
        if len(songs) != 0:
            song_1: Song = songs.__getitem__(0)
            if isinstance(song_1, Error):
                await self.parent.send_error_message(
                    ctx=ctx, message=songs[0].reason
                )
                return
        if len(songs) > 1:
            if shuffle:
                random.shuffle(songs)
            self.parent.guilds[ctx.guild.id].song_queue.queue.extend(songs)
            await self.parent.send_embed_message(
                ctx=ctx,
                message=":asterisk: Added "
                + str(len(songs))
                + " Tracks to Queue. :asterisk:",
            )
        elif len(songs) == 1:
            if first_index_push:
                self.parent.guilds[ctx.guild.id].song_queue.queue.extendleft(
                    songs
                )
            else:
                self.parent.guilds[ctx.guild.id].song_queue.queue.extend(songs)
            title = ""
            if songs[0].title is not None:
                title = songs[0].title
            else:
                try:
                    title = songs[0].link
                except AttributeError:
                    pass
            if self.parent.guilds[ctx.guild.id].voice_client.is_playing():
                if not playskip:
                    await self.parent.send_embed_message(
                        ctx, ":asterisk: Added **" + title + "** to Queue."
                    )

        try:
            if playskip:
                if self.parent.guilds[ctx.guild.id].voice_client is not None:
                    if self.parent.guilds[
                        ctx.guild.id
                    ].voice_client.is_playing():
                        self.parent.guilds[ctx.guild.id].voice_client.stop()
            if not self.parent.guilds[ctx.guild.id].voice_client.is_playing():
                await self.pre_player(ctx)
        except Exception as e:
            self.parent.log.error(traceback.format_exc())
            self.parent.log.error(logging_manager.debug_info(str(e)))

    async def join_check(self, ctx, url):
        if url is None:
            await self.parent.send_error_message(
                ctx, "You need to enter something to play."
            )
            return False
        if self.parent.guilds[ctx.guild.id].voice_channel is None:
            if ctx.author.voice is not None:
                self.parent.guilds[
                    ctx.guild.id
                ].voice_channel = ctx.author.voice.channel
            else:
                await self.parent.send_error_message(
                    ctx, "You need to be in a channel."
                )
                return False
        if not await self.parent.control_check.same_channel_check(ctx):
            return False
        return True

    async def join_channel(self, ctx):
        if self.parent.guilds[ctx.guild.id].voice_client is None:
            try:
                if (
                    ctx.author.voice.channel.user_limit
                    <= len(ctx.author.voice.channel.members)
                    and ctx.author.voice.channel.user_limit != 0
                ):
                    if ctx.guild.me.guild_permissions.administrator is False:
                        await self.parent.send_embed_message(
                            ctx,
                            "Error while joining your channel. :frowning: (1)",
                        )
                        return False
                else:
                    self.parent.guilds[
                        ctx.guild.id
                    ].voice_client = await bot.node_controller.NodeVoiceClient.NodeVoiceChannel.from_channel(
                        ctx.author.voice.channel, self.parent.node_controller
                    ).connect()
            except (
                TimeoutError,
                discord.HTTPException,
                discord.ClientException,
                discord.DiscordException,
            ) as e:
                self.parent.log.warning(
                    logging_manager.debug_info("channel_join " + str(e))
                )
                self.parent.guilds[ctx.guild.id].voice_channel = None
                await self.parent.send_embed_message(
                    ctx, "Error while joining your channel. :frowning: (2)"
                )
                return False
            except NoNodeReadyException as nn:
                await self.parent.send_error_message(ctx, str(nn))
                return False
        return True

    # @commands.cooldown(1, 0.5, commands.BucketType.guild)
    @commands.command(aliases=["p"])
    async def play(self, ctx, *, url: str = None):
        """
        Plays a song.
        :param ctx:
        :param url:
        :return:
        """
        if not await self.play_check(ctx, url):
            return
        await self.add_to_queue(url, ctx)

    @commands.command(aliases=["pn"])
    async def playnext(self, ctx, *, url: str = None):
        """
        Adds a song to the first position in the queue.
        """
        if not await self.play_check(ctx, url):
            return
        await self.add_to_queue(url, ctx, first_index_push=True)

    @commands.command(aliases=["ps"])
    async def playskip(self, ctx, *, url: str = None):
        """
        Queues a song and instantly skips to it.
        :param ctx:
        :param url:
        :return:
        """
        if not await self.play_check(ctx, url):
            return
        await self.add_to_queue(url, ctx, playskip=True)

    @commands.command(aliases=["sp"])
    async def shuffleplay(self, ctx, *, url: str = None):
        """
        Queues multiple songs in random order.
        :param ctx:
        :param url:
        :return:
        """
        if not await self.play_check(ctx, url):
            return
        await self.add_to_queue(url, ctx, shuffle=True)

    async def play_check(self, ctx, url):
        if not await self.join_check(ctx, url):
            return False
        if not await self.join_channel(ctx=ctx):
            return False

        yt = YouTubeType(url)
        sp = SpotifyType(url)
        sc = SoundCloudType(url)

        if yt.valid or sp.valid or sc.valid or url.lower() == "charts":
            return True
        if re.match(VariableStore.url_pattern, url) is not None:
            await self.parent.send_embed_message(
                ctx, "This is not a valid/supported url."
            )
            return False
        return True

    def sync_song_conclusion(self, ctx, error=None):
        if len(self.parent.guilds[ctx.guild.id].song_queue.queue) == 0:
            self.parent.guilds[ctx.guild.id].now_playing = None
        if error is not None:
            self.parent.log.error(str(error))
            function = asyncio.run_coroutine_threadsafe(
                self.parent.send_error_message(ctx, str(error)), self.bot.loop
            )
            try:
                function.result()
            except Exception as e:
                self.parent.log.error(e)
        function = asyncio.run_coroutine_threadsafe(
            self.parent.clear_presence(ctx), self.bot.loop
        )
        try:
            function.result()
        except Exception as e:
            self.parent.log.error(traceback.format_exc())
            self.parent.log.error(logging_manager.debug_info(str(e)))
        function = asyncio.run_coroutine_threadsafe(
            self.empty_channel(ctx), self.bot.loop
        )
        try:
            function.result()
        except Exception as e:
            self.parent.log.error(traceback.print_exc())
            self.parent.log.error(logging_manager.debug_info(str(e)))
        function = asyncio.run_coroutine_threadsafe(
            self.pre_player(ctx), self.bot.loop
        )
        try:
            function.result()
        except Exception as e:
            self.parent.log.error(logging_manager.debug_info(str(e)))

    async def song_conclusion(self, ctx, error=None):
        if len(self.parent.guilds[ctx.guild.id].song_queue.queue) == 0:
            self.parent.guilds[ctx.guild.id].now_playing = None
        if error is not None:
            self.parent.log.error(str(error))
            await self.parent.send_error_message(ctx, str(error))

        # catch all one after another to make most of them succeed

        tasks = [
            self.parent.guilds[ctx.guild.id].now_playing_message.stop(),
            self.parent.clear_presence(ctx),
            self.empty_channel(ctx),
            self.pre_player(ctx),
        ]
        for task in tasks:
            try:
                await task
            except Exception as e:
                self.parent.log.error(str(e))

    async def player(self, ctx, small_dict):
        if isinstance(small_dict, Error):
            error_message = small_dict.reason
            await self.parent.send_error_message(ctx, error_message)
            if error_message in (Errors.no_results_found, Errors.default):
                await self.parent.guilds[
                    ctx.guild.id
                ].now_playing_message.message.delete()
                return

            small_dict = Song.copy_song(
                await self.parent.youtube.youtube_url(
                    small_dict.link, ctx.guild.id
                ),
                small_dict,
            )

            if isinstance(small_dict, Error):
                self.parent.log.error(small_dict.reason)
                await self.parent.send_error_message(ctx, small_dict.reason)
                return

        try:
            self.parent.guilds[ctx.guild.id].now_playing = small_dict
            if self.parent.guilds[ctx.guild.id].voice_client is None:
                return
            volume = getattr(
                self.parent.guilds[ctx.guild.id],
                "volume",
                await self.parent.mongo.get_volume(ctx.guild.id),
            )
            if small_dict.codec == "opus":
                self.parent.log.debug("Using OPUS Audio.")
                # source = await FFmpegOpusAudioB.from_probe(
                #    small_dict.stream,
                #    volume=volume,
                # before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                # commented, because of spamming messages of failed reconnects.
                # )
            else:
                # only used for backup soundcloud atm
                self.parent.log.debug("Using PCM Audio.")
                # source = PCMVolumeTransformerB(
                #   FFmpegPCMAudioB(
                #      small_dict.stream,
                #     before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                # ),
                # volume=volume,
                # )
            try:
                small_dict.guild_id = ctx.guild.id
                self.parent.guilds[ctx.guild.id].voice_client.play(
                    small_dict
                    # source,
                    # after=lambda error: self.song_conclusion(ctx, error=error),
                )
                self.parent.guilds[ctx.guild.id].voice_client.set_after(
                    self.song_conclusion, ctx, error=None
                )
            except discord.ClientException:
                if ctx.guild.voice_client is None:
                    if (
                        self.parent.guilds[ctx.guild.id].voice_channel
                        is not None
                    ):
                        self.parent.guilds[
                            ctx.guild.id
                        ].voice_client = await self.parent.guilds[
                            ctx.guild.id
                        ].voice_channel.connect(
                            timeout=10, reconnect=True
                        )
                        small_dict.guild_id = ctx.guild.id
                        self.parent.guilds[ctx.guild.id].voice_client.play(
                            small_dict,
                            # after=lambda error: self.song_conclusion(
                            #    ctx, error=error
                            # ),
                        )
                        self.parent.guilds[ctx.guild.id].voice_client.set_after(
                            self.song_conclusion, ctx, error=None
                        )
            full, empty = await self.parent.mongo.get_chars(ctx.guild.id)
            self.parent.guilds[
                ctx.guild.id
            ].now_playing_message = NowPlayingMessage(
                ctx=ctx,
                message=self.parent.guilds[
                    ctx.guild.id
                ].now_playing_message.message,
                song=self.parent.guilds[ctx.guild.id].now_playing,
                full=full,
                empty=empty,
                discord_music=self.parent,
                voice_client=self.parent.guilds[ctx.guild.id].voice_client,
            )
            await self.parent.guilds[ctx.guild.id].now_playing_message.send()

        except (Exception, discord.ClientException) as e:
            self.parent.log.debug(
                logging_manager.debug_info(traceback.format_exc(e))
            )

    async def preload_song(self, ctx):
        """
        Preload of the next song.
        :param ctx:
        :return:
        """
        try:
            if self.parent.guilds[ctx.guild.id].song_queue.qsize() > 0:
                i = 0
                for item in self.parent.guilds[ctx.guild.id].song_queue.queue:
                    item: Song
                    if item.stream is None:
                        backup_title: str = str(item.title)
                        if item.link is not None:
                            youtube_dict = await self.parent.youtube.youtube_url(
                                item.link, ctx.guild.id
                            )
                            youtube_dict.user = item.user
                        else:
                            if item.title is not None:
                                youtube_dict = await self.parent.youtube.youtube_term(
                                    item
                                )
                            else:
                                youtube_dict = await self.parent.youtube.youtube_term(
                                    item
                                )
                            youtube_dict.user = item.user
                        j: int = 0

                        for _song in self.parent.guilds[
                            ctx.guild.id
                        ].song_queue.queue:
                            _song: Song
                            if _song.title == backup_title:
                                self.parent.guilds[
                                    ctx.guild.id
                                ].song_queue.queue[j] = Song.copy_song(
                                    youtube_dict,
                                    self.parent.guilds[
                                        ctx.guild.id
                                    ].song_queue.queue[j],
                                )
                                break
                            j -= -1
                        break
                    i += 1
        except IndexError:
            pass
        except AttributeError as e:
            traceback.print_exc()

    async def empty_channel(self, ctx):
        """
        Leaves the channel if the bot is alone
        :param ctx:
        :return:
        """
        if len(self.parent.guilds[ctx.guild.id].voice_channel.members) == 1:
            if (
                self.parent.guilds[ctx.guild.id].voice_channel.members[0]
                == ctx.guild.me
            ):
                if ctx.guild.id not in (
                    671367903018483722,
                    619567786590470147,
                    561858486430859264,
                ):
                    self.parent.guilds[ctx.guild.id].song_queue = Queue()
                    await self.parent.guilds[
                        ctx.guild.id
                    ].voice_client.disconnect()
                    await self.parent.send_embed_message(
                        ctx=ctx,
                        message="I've left the channel, because it was empty.",
                    )
