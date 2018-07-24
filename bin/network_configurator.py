#!/usr/bin/env python3

import logging

from elan.network import NetworkConfigurator
from elan.neuron import Dendrite

logging.basicConfig()

if __name__ == "__main__":
    dendrite = Dendrite()
    configurator = NetworkConfigurator()
    dendrite.subscribe_conf('ipv4', configurator.set_ipv4)
    dendrite.subscribe_conf('ipv6', configurator.set_ipv6)

    dendrite.wait_complete()
