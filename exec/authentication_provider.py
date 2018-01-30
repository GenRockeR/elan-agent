#!/usr/bin/env python3

from elan.authentication import AuthenticationProvider
from elan.neuron import Dendrite

if __name__ == "__main__":

    dendrite = Dendrite()
    provider = AuthenticationProvider(dendrite=dendrite)

    
    dendrite.subscribe_conf('authentication', cb=provider.new_authentication_conf)

    dendrite.wait_complete()
