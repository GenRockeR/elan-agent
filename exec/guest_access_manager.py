#!/usr/bin/env python3

from elan.captive_portal import GuestAccessManager
from elan.neuron import Dendrite

if __name__ == "__main__":
    dendrite = Dendrite()
    manager = GuestAccessManager()
    dendrite.subscribe_conf('guest-access/active-authorizations', manager.new_authorizations)

    
    dendrite.wait_complete()
