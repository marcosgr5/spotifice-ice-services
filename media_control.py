#!/usr/bin/env python3
import sys
import time
import Ice
import IceStorm

Ice.loadSlice("-I{} spotifice_v3.ice".format(Ice.getSliceDir()))
import Spotifice

class MediaFinderListenerI(Spotifice.MediaFinderListener):
    def track_found(self, track, server, current=None):
        print(f"\n[!!!] CANCIÓN ENCONTRADA: {track.title} ({track.filename})\n      -> En servidor: {server}")
        
    def playlist_found(self, playlist, server, current=None):
        print(f"\n[!!!] PLAYLIST ENCONTRADA: {playlist.name} en servidor {server}")

def main(ic):
    print("--- 1. Probando Servicio de Directorio ---")
    directory_proxy_str = ic.getProperties().getPropertyWithDefault("MediaDirectory.Proxy", "directory:default -p 10002")
    directory = Spotifice.MediaDirectoryPrx.checkedCast(ic.stringToProxy(directory_proxy_str))
    
    if not directory:
        print("Error: No se puede contactar con MediaDirectory.")
        return

    servers = directory.get_media_servers()
    renders = directory.get_media_renders()
    
    print(f"Servidores detectados: {len(servers)}")
    for s in servers: print(f" - Servidor activo")
    print(f"Renders detectados: {len(renders)}")
    for r in renders: print(f" - Render activo")

    print("\n--- 2. Probando Búsqueda Global (IceStorm) ---")
    adapter = ic.createObjectAdapterWithEndpoints("ControlAdapter", "tcp")
    listener = MediaFinderListenerI()
    listener_proxy = adapter.addWithUUID(listener)
    adapter.activate()
    
    finder_listener = Spotifice.MediaFinderListenerPrx.uncheckedCast(listener_proxy)
    topic_manager_prx = ic.getProperties().getProperty("IceStorm.TopicManager.Proxy")
    
    if topic_manager_prx:
        try:
            tm = IceStorm.TopicManagerPrx.checkedCast(ic.stringToProxy(topic_manager_prx))
            topic = tm.retrieve("FinderTopic")
            finder_publisher = Spotifice.MediaFinderPrx.uncheckedCast(topic.getPublisher())

            search_term = "Science"
            print(f"Buscando canción que contenga: \"{search_term}\"...")
            finder_publisher.find_track(search_term, finder_listener)
            
            filename_search = "Portal2-01-Science_is_Fun.mp3"
            print(f"Buscando archivo exacto: \"{filename_search}\"...")
            finder_publisher.find_track(filename_search, finder_listener)
            
            print("Esperando respuestas (3 segundos)...")
            time.sleep(3)
        except Exception as e:
            print(f"Error en búsqueda: {e}")
    else:
        print("Saltando búsqueda: Falta config de IceStorm")

    adapter.destroy()

if __name__ == "__main__":
    init_data = Ice.InitializationData()
    init_data.properties = Ice.createProperties()
    init_data.properties.setProperty("IceStorm.TopicManager.Proxy", "SpotificeIceStorm/TopicManager:default -p 10005")
    init_data.properties.setProperty("MediaDirectory.Proxy", "directory:default -p 10002")
    with Ice.initialize(sys.argv, init_data) as communicator:
        main(communicator)
