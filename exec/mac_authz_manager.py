#!/usr/bin/env python3

from elan.nac.manager import MacAuthorizationManager
from elan.nac import AUTHORIZATION_CHANGE_TOPIC, CHECK_AUTHZ_PATH
from elan.session import MAC_SESSION_TOPIC
from elan.neuron import Dendrite

if __name__ == "__main__":
    dendrite = Dendrite()
    manager = MacAuthorizationManager(dendrite=dendrite)
    
    def handle_disconnection(data):
        # we are only interested in deconnections
        if 'end' in data:
            manager.handle_disconnection(data['mac'])
    
    dendrite.subscribe(AUTHORIZATION_CHANGE_TOPIC, manager.handle_authz_changed)
    dendrite.subscribe(MAC_SESSION_TOPIC, handle_disconnection)
    dendrite.subscribe(CHECK_AUTHZ_PATH, manager.check_authz)

    dendrite.wait_complete()
