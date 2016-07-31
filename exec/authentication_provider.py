#!/usr/bin/env python3

from origin.authentication import AuthenticationProvider
from origin.neuron import Dendrite

if __name__ == "__main__":

    dendrite = Dendrite()
    provider = AuthenticationProvider(dendrite=dendrite)

    
    dendrite.subscribe_conf('agent', cb=provider.agent_conf) 
    dendrite.subscribe_conf('authentication', cb=provider.new_authentication_conf)

    dendrite.wait_complete()
