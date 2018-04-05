#!/usr/bin/env python3

import logging

from elan.network import NetworkConfiguration
from elan.neuron import Dendrite

logging.basicConfig()

if __name__ == "__main__":
    dendrite = Dendrite()
    conf = NetworkConfiguration()
    dendrite.subscribe_conf('ipv4', conf.set_ip_v4)
    dendrite.subscribe_conf('ipv6', conf.set_ip_v6)

    dendrite.wait_complete()
