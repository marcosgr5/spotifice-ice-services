#!/usr/bin/env python3

import logging
import sys
import threading
import time
import uuid
from contextlib import contextmanager

import Ice
import IceStorm
from gst_player import GstPlayer

Ice.loadSlice('-I{} spotifice_v3.ice'.format(Ice.getSliceDir()))
import Spotifice

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MediaRender")

class MediaRenderI(Spotifice.MediaRender):
    def __init__(self, player):
        self.player = player
        self.server = None
        self.stream_manager = None
        
        self.current_track = None
        self.state = Spotifice.PlaybackState.STOPPED
        self.repeat = False
        
        self.current_playlist = None
        self.playlist_index = -1
        self.history = []

        self.player.on_eos = self.on_eos_callback

    def on_eos_callback(self):
        """Callback llamado por GStreamer cuando acaba el stream de audio."""
        logger.info("Fin de pista detectado (EOS).")
        threading.Thread(target=self._handle_eos).start()

    def _handle_eos(self):
        """Lógica para decidir qué hacer al acabar la canción."""
        try:
            if self.current_playlist:
                try:
                    self.next()
                except Exception:
                    self.stop()
            elif self.repeat and self.current_track:
                self.play()
            else:
                self.stop()
        except Exception as e:
            logger.error(f"Error gestionando EOS: {e}")
            self.stop()

    def ensure_server_bound(self):
        if not self.server or not self.stream_manager: 
            raise Spotifice.BadReference(reason="No MediaServer or Session bound")

    def bind_media_server(self, media_server, stream_manager, current=None):
        media_server.ice_ping()
        stream_manager.ice_ping()
        self.server = media_server
        self.stream_manager = stream_manager
        logger.info(f"Bound to MediaServer")

    def unbind_media_server(self, current=None):
        self.stop(current)
        self.server = None
        if self.stream_manager:
            try: self.stream_manager.close()
            except: pass
        self.stream_manager = None

    def load_track(self, track_id, current=None, _internal_call=False):
        if not _internal_call:
            self.current_playlist = None
            self.playlist_index = -1
            self.history = []

        if not self.server: 
            raise Spotifice.BadReference(reason="No MediaServer bound")

        was_playing = (self.state == Spotifice.PlaybackState.PLAYING)
        if was_playing:
            self.stop(current)

        try:
            self.current_track = self.server.get_track_info(track_id)
            logger.info(f"Track cargado: {self.current_track.title}")
        except Exception as e:
            raise Spotifice.TrackError(reason=str(e))

    def get_current_track(self, current=None): 
        return self.current_track

    def load_playlist(self, playlist_id, current=None):
        if not self.server: raise Spotifice.BadReference("No server")
        
        try:
            playlist = self.server.get_playlist(playlist_id)
        except Exception:
            raise Spotifice.PlaylistError(playlist_id, "Playlist not found")
            
        if not playlist.track_ids: 
            raise Spotifice.PlaylistError(playlist_id, "Empty playlist")

        self.current_playlist = playlist
        self.playlist_index = 0
        self.history = []
        
        self.load_track(self.current_playlist.track_ids[0], current, _internal_call=True)

    def play(self, current=None):
        if not self.current_track:
            raise Spotifice.PlayerError("No track loaded")

        def get_chunk_hook(size):
            try: return self.stream_manager.get_audio_chunk(size)
            except Exception as e: 
                logger.error(e)
                return b""
        
        if self.state == Spotifice.PlaybackState.PAUSED:
            self.player.resume()
            self.state = Spotifice.PlaybackState.PLAYING
            return

        if self.state == Spotifice.PlaybackState.PLAYING:
            return 

        self.ensure_server_bound()
        
        try:
            self.stream_manager.open_stream(self.current_track.id)
            
            self.player.configure(get_chunk_hook, self.on_eos_callback)
            
            if not self.player.confirm_play_starts(): 
                raise Spotifice.PlayerError("Failed start")
        except Exception as e:
            raise Spotifice.PlayerError(str(e))
        
        self.state = Spotifice.PlaybackState.PLAYING
        
        if not self.history or self.history[-1] != self.current_track.id:
             self.history.append(self.current_track.id)

    def stop(self, current=None):
        try: 
            if self.stream_manager:
                self.stream_manager.close_stream()
        except: pass
        self.player.stop()
        self.state = Spotifice.PlaybackState.STOPPED

    def pause(self, current=None):
        if not self.current_track:
            raise Spotifice.PlayerError("No track loaded")
            
        if self.state == Spotifice.PlaybackState.PLAYING:
            self.player.pause()
            self.state = Spotifice.PlaybackState.PAUSED

    def get_status(self, current=None):
        tid = self.current_track.id if self.current_track else ""
        return Spotifice.PlaybackStatus(self.state, tid, self.repeat)

    def set_repeat(self, val, current=None): 
        self.repeat = val

    def next(self, current=None):
        if not self.current_playlist:
            raise Spotifice.PlaylistError("No playlist active")

        new_index = self.playlist_index + 1
        
        if new_index >= len(self.current_playlist.track_ids):
            if self.repeat:
                new_index = 0
            else:
                self.stop()
                return 

        self.playlist_index = new_index
        track_id = self.current_playlist.track_ids[self.playlist_index]
        
        should_play = (self.state == Spotifice.PlaybackState.PLAYING)
        
        self.load_track(track_id, current, _internal_call=True)
        
        if should_play:
            self.play(current)

    def previous(self, current=None):
        if not self.current_playlist:
             raise Spotifice.PlaylistError("No playlist active")
             
        new_index = self.playlist_index - 1
        if new_index < 0:
            if self.repeat:
                new_index = len(self.current_playlist.track_ids) - 1
            else:
                new_index = 0 

        self.playlist_index = new_index
        track_id = self.current_playlist.track_ids[self.playlist_index]
        
        should_play = (self.state == Spotifice.PlaybackState.PLAYING)
        self.load_track(track_id, current, _internal_call=True)
        if should_play:
            self.play(current)


def announcement_loop(communicator, my_proxy, interval):
    props = communicator.getProperties()
    topic_manager_prx = props.getProperty("IceStorm.TopicManager.Proxy")
    if not topic_manager_prx: return

    try:
        topic_manager = IceStorm.TopicManagerPrx.checkedCast(communicator.stringToProxy(topic_manager_prx))
        topic_name = props.getPropertyWithDefault("Discovery.TopicName", "DiscoveryTopic")
        
        try: topic = topic_manager.retrieve(topic_name)
        except IceStorm.NoSuchTopic: topic = topic_manager.create(topic_name)

        publisher = Spotifice.AnnounceListenerPrx.uncheckedCast(topic.getPublisher())
        
        logger.info(f"Anunciando render en {topic_name} cada {interval}s")
        while True:
            try: publisher.server_up(my_proxy)
            except: pass
            time.sleep(interval)
            
    except Exception as e:
        logger.error(f"Error announce loop: {e}")

def main(ic, player):
    props = ic.getProperties()
    
    identity_str = props.getPropertyWithDefault("MediaRender.Identity", str(uuid.uuid4()))
    identity = ic.stringToIdentity(identity_str)
    adapter = ic.createObjectAdapter("MediaRenderAdapter")

    servant = MediaRenderI(player)
    proxy = adapter.add(servant, identity)
    render_prx = Spotifice.MediaRenderPrx.uncheckedCast(proxy)
    
    logger.info(f"MediaRender ready: {identity_str}")

    announce_interval = int(props.getPropertyWithDefault("Discovery.AnnounceIntervalSecs", "15"))
    announce_thread = threading.Thread(target=announcement_loop, args=(ic, render_prx, announce_interval), daemon=True)
    announce_thread.start()

    adapter.activate()
    ic.waitForShutdown()

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit("Usage: python3 media_render.py <config-file>")
    player = GstPlayer()
    player.start()
    try:
        with Ice.initialize(sys.argv[1]) as communicator:
            main(communicator, player)
    except: player.shutdown()