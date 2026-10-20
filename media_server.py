#!/usr/bin/env python3

import logging
import sys
import json
import hashlib
import secrets
import time
import threading
import uuid
from pathlib import Path
from typing import Optional

import Ice
import IceStorm

Ice.loadSlice("-I{} spotifice_v3.ice".format(Ice.getSliceDir()))
import Spotifice

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("MediaServer")

class StreamedFile:
    def __init__(self, track_info, media_dir):
        self.track = track_info
        filepath = media_dir / track_info.filename
        try:
            self.file = open(filepath, "rb")
        except Exception as e:
            raise Spotifice.IOError(track_info.filename, f"Error opening media file: {e}")

    def read(self, size):
        return self.file.read(size)

    def close(self):
        try:
            if self.file: self.file.close()
        except Exception as e:
            logger.error(f"Error closing file: {e}")

class SecureStreamManagerI(Spotifice.SecureStreamManager):
    def __init__(self, user_info, media_dir, tracks_db):
        self.user_info = user_info
        self.media_dir = media_dir
        self.tracks = tracks_db
        self.stream: Optional[StreamedFile] = None

    def get_user_info(self, current=None):
        return self.user_info

    def close(self, current=None):
        self.close_stream(current)
        if current:
            current.adapter.remove(current.id)

    def open_stream(self, track_id, current=None):
        if track_id not in self.tracks:
            raise Spotifice.TrackError(track_id, "Track not found")
        if self.stream:
            self.stream.close()
        try:
            self.stream = StreamedFile(self.tracks[track_id], self.media_dir)
        except Exception as e:
            raise Spotifice.IOError(track_id, str(e))

    def close_stream(self, current=None):
        if self.stream:
            self.stream.close()
            self.stream = None

    def get_audio_chunk(self, chunk_size, current=None):
        if not self.stream:
            raise Spotifice.StreamError("No stream", "No hay stream abierto")
        try:
            data = self.stream.read(chunk_size)
            if not data:
                self.close_stream()
            return data
        except Exception as e:
            raise Spotifice.IOError("Read Error", str(e))

class MediaServerI(Spotifice.MediaServer):
    def __init__(self, media_dir, playlist_dir, users_file, communicator, my_proxy):
        self.media_dir = Path(media_dir)
        self.playlist_dir = Path(playlist_dir)
        self.users_file = Path(users_file)
        self.communicator = communicator
        self.my_proxy = my_proxy
        
        self.tracks = {}
        self.playlists = {}
        self.users = {}

        self.load_media()
        self.load_playlists()
        self.load_users()

    def load_media(self):
        if not self.media_dir.exists(): return
        for filepath in sorted(Path(self.media_dir).iterdir()):
            if filepath.suffix.lower() == ".mp3":
                self.tracks[filepath.name] = self.track_info(filepath)

    def load_playlists(self):
        if not self.playlist_dir.exists(): return
        for filepath in sorted(self.playlist_dir.iterdir()):
            if filepath.suffix.lower() == ".playlist":
                try:
                    with open(filepath, "r") as f: data = json.load(f)
                    valid_ids = [tid for tid in data.get("track_ids", []) if tid in self.tracks]
                    playlist = Spotifice.Playlist(
                        id=data.get("id"), name=data.get("name"),
                        description=data.get("description", ""), owner=data.get("owner", ""),
                        created_at=0, track_ids=valid_ids
                    )
                    self.playlists[playlist.id] = playlist
                except Exception: pass

    def load_users(self):
        try:
            with open(self.users_file, "r") as f: self.users = json.load(f)
        except Exception: pass

    @staticmethod
    def track_info(filepath):
        return Spotifice.TrackInfo(id=filepath.name, title=filepath.stem, filename=filepath.name)

    @staticmethod
    def verify_password(password, salt, digest):
        calc = hashlib.md5((password + salt).encode("utf-8")).hexdigest()
        return secrets.compare_digest(calc, digest)

    def get_all_tracks(self, current=None):
        return list(self.tracks.values())

    def get_track_info(self, track_id, current=None):
        if track_id not in self.tracks: raise Spotifice.TrackError(track_id, "Track not found")
        return self.tracks[track_id]

    def get_all_playlists(self, current=None):
        return list(self.playlists.values())

    def get_playlist(self, playlist_id, current=None):
        if playlist_id not in self.playlists: raise Spotifice.PlaylistError(playlist_id, "Playlist not found")
        return self.playlists[playlist_id]

    def authenticate(self, media_render, username, password, current=None):
        user_data = self.users.get(username)
        if not user_data or not self.verify_password(password, user_data["salt"], user_data["digest"]):
            raise Spotifice.AuthError("Credenciales inválidas")
        info = Spotifice.UserInfo(username=username, fullname=user_data.get("fullname"), 
                                email=user_data.get("email"), is_premium=user_data.get("is_premium"), created_at=0)
        session_servant = SecureStreamManagerI(info, self.media_dir, self.tracks)
        if current:
            return Spotifice.SecureStreamManagerPrx.checkedCast(current.adapter.addWithUUID(session_servant))
        raise Spotifice.AuthError("Error interno")

    def find_track(self, track_id, listener, current=None):
        if track_id in self.tracks:
            try:
                listener.track_found(self.tracks[track_id], self.my_proxy)
                logger.info(f"Encontrado track {track_id}, notificado al listener.")
            except Exception as e:
                logger.error(f"Error notificando listener para track {track_id}: {e}")

    def find_playlist(self, playlist_id, listener, current=None):
        if playlist_id in self.playlists:
            try:
                listener.playlist_found(self.playlists[playlist_id], self.my_proxy)
                logger.info(f"Encontrada playlist {playlist_id}, notificado al listener.")
            except Exception as e:
                logger.error(f"Error notificando listener para playlist {playlist_id}: {e}")

def announcement_loop(communicator, my_proxy, interval):
    props = communicator.getProperties()
    topic_manager_prx = props.getProperty("IceStorm.TopicManager.Proxy")
    if not topic_manager_prx:
        logger.warning("No IceStorm.TopicManager.Proxy, skipping announcements")
        return

    try:
        topic_manager = IceStorm.TopicManagerPrx.checkedCast(communicator.stringToProxy(topic_manager_prx))
        topic_name = props.getPropertyWithDefault("Discovery.TopicName", "DiscoveryTopic")
        
        try:
            topic = topic_manager.retrieve(topic_name)
        except IceStorm.NoSuchTopic:
            topic = topic_manager.create(topic_name)

        publisher = Spotifice.AnnounceListenerPrx.uncheckedCast(topic.getPublisher())
        
        logger.info(f"Iniciando anuncios en {topic_name} cada {interval}s")
        while True:
            try:
                publisher.server_up(my_proxy)
            except Exception as e:
                logger.warning(f"Error en anuncio: {e}")
            time.sleep(interval)
            
    except Exception as e:
        logger.error(f"Error en hilo de anuncios: {e}")

def main(ic):
    props = ic.getProperties()
    media_dir = props.getPropertyWithDefault("MediaServer.Content", "media")
    playlist_dir = props.getPropertyWithDefault("MediaServer.Playlists", "playlists")
    users_file = props.getPropertyWithDefault("MediaServer.UsersFile", "users.json")

    identity_str = props.getPropertyWithDefault("MediaServer.Identity", str(uuid.uuid4()))
    identity = ic.stringToIdentity(identity_str)
    adapter = ic.createObjectAdapter("MediaServerAdapter")

    servant = MediaServerI(media_dir, playlist_dir, users_file, ic, None)
    
    proxy = adapter.add(servant, identity)
    media_server_prx = Spotifice.MediaServerPrx.uncheckedCast(proxy)
    servant.my_proxy = media_server_prx
    
    logger.info(f"MediaServer ready: {identity_str}")

    topic_manager_prx = props.getProperty("IceStorm.TopicManager.Proxy")
    if topic_manager_prx:
        try:
            tm = IceStorm.TopicManagerPrx.checkedCast(ic.stringToProxy(topic_manager_prx))
            finder_topic_name = props.getPropertyWithDefault("Finder.TopicName", "FinderTopic")
            try:
                topic = tm.retrieve(finder_topic_name)
            except IceStorm.NoSuchTopic:
                topic = tm.create(finder_topic_name)
            
            topic.subscribeAndGetPublisher({"reliability": "ordered"}, media_server_prx)
            logger.info(f"Suscrito a {finder_topic_name}")
        except Exception as e:
            logger.error(f"Error configurando FinderTopic: {e}")

    announce_interval = int(props.getPropertyWithDefault("Discovery.AnnounceIntervalSecs", "15"))
    announce_thread = threading.Thread(target=announcement_loop, args=(ic, media_server_prx, announce_interval), daemon=True)
    announce_thread.start()

    adapter.activate()
    ic.waitForShutdown()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python3 media_server.py <config-file>")
    with Ice.initialize(sys.argv[1]) as communicator:
        main(communicator)
