#!/usr/bin/env python3

from elan.ids import generate_suricata_conf
from elan.neuron import Dendrite
from elan.utils import reload_service


def ip_conf_changed(*args, **kwargs):
    if generate_suricata_conf():
        reload_service('suricata')


if __name__ == "__main__":
    dendrite = Dendrite()
    dendrite.subscribe_conf('ipv4/current', ip_conf_changed)
    dendrite.subscribe_conf('ipv6/current', ip_conf_changed)

    dendrite.wait_complete()
