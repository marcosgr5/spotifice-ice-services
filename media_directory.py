#!/usr/bin/env python3
import sys
import logging
import Ice
import IceStorm

Ice.loadSlice('-I{} spotifice_v3.ice'.format(Ice.getSliceDir()))
import Spotifice

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MediaDirectory")

class MediaDirectoryI(Spotifice.MediaDirectory):
    def __init__(self):
        self.servers = {}
        self.renders = {}

    def server_up(self, proxy, current=None):
        if not proxy:
            return
        
        identity_str = Ice.identityToString(proxy.ice_getIdentity())
        
        try:
            server_prx = Spotifice.MediaServerPrx.checkedCast(proxy)
            if server_prx:
                self.servers[identity_str] = server_prx
                logger.info(f"Registrado MediaServer: {identity_str}")
                return

            render_prx = Spotifice.MediaRenderPrx.checkedCast(proxy)
            if render_prx:
                self.renders[identity_str] = render_prx
                logger.info(f"Registrado MediaRender: {identity_str}")
                return
                
        except Ice.Exception as e:
            logger.error(f"Error comprobando tipo de proxy {identity_str}: {e}")

    def server_down(self, proxy, current=None):
        if not proxy:
            return

        identity_str = Ice.identityToString(proxy.ice_getIdentity())
        
        if identity_str in self.servers:
            del self.servers[identity_str]
            logger.info(f"Eliminado MediaServer: {identity_str}")
        
        if identity_str in self.renders:
            del self.renders[identity_str]
            logger.info(f"Eliminado MediaRender: {identity_str}")

    def get_media_servers(self, current=None):
        return list(self.servers.values())

    def get_media_renders(self, current=None):
        return list(self.renders.values())


def main(communicator):
    props = communicator.getProperties()
    
    adapter = communicator.createObjectAdapter("MediaDirectoryAdapter")
    
    servant = MediaDirectoryI()
    
    identity_str = props.getPropertyWithDefault("MediaDirectory.Identity", "directory")
    identity = communicator.stringToIdentity(identity_str)
    
    subscriber_proxy = adapter.add(servant, identity)
    
    topic_manager_prx = props.getProperty("IceStorm.TopicManager.Proxy")
    if not topic_manager_prx:
        logger.error("Propiedad IceStorm.TopicManager.Proxy no definida")
        return

    try:
        topic_manager = IceStorm.TopicManagerPrx.checkedCast(
            communicator.stringToProxy(topic_manager_prx))
            
        topic_name = props.getPropertyWithDefault("Discovery.TopicName", "DiscoveryTopic")
        
        try:
            topic = topic_manager.retrieve(topic_name)
        except IceStorm.NoSuchTopic:
            topic = topic_manager.create(topic_name)
            
        qos = {"reliability": "ordered"}
        try:
            topic.subscribeAndGetPublisher(qos, subscriber_proxy)
        except IceStorm.AlreadySubscribed:
            topic.unsubscribe(subscriber_proxy)
            topic.subscribeAndGetPublisher(qos, subscriber_proxy)
            
        logger.info(f"Suscrito a {topic_name}")

    except Ice.Exception as e:
        logger.error(f"Error conectando con IceStorm: {e}")
        return

    adapter.activate()
    communicator.waitForShutdown()
    
    try:
        topic.unsubscribe(subscriber_proxy)
    except:
        pass

if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit("Usage: python3 media_directory.py <config-file>")
    
    with Ice.initialize(sys.argv[1]) as communicator:
        main(communicator)  