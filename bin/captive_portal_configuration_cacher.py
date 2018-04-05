#!/usr/bin/env python3

from elan.captive_portal import CONF_PATH, GUEST_ACCESS_CONF_PATH, Administrator
from elan.neuron import Dendrite, Synapse


class ConfigurationCacher():

    def __init__(self):
        self.synapse = Synapse()

    def cp_conf_updated(self, data, path):
        pipe = self.synapse.pipeline()
        pipe.delete(CONF_PATH)
        for profile in data:
            pipe.hset(CONF_PATH, profile['id'], profile)
        pipe.execute()

    def ga_conf_updated(self, data, path):
        pipe = self.synapse.pipeline()
        pipe.delete(GUEST_ACCESS_CONF_PATH)
        for profile in data:
            pipe.hset(GUEST_ACCESS_CONF_PATH, profile['id'], profile)
        pipe.execute()

    def admins_conf_updated(self, data, path):
            Administrator.delete_all()
            for profile in data:
                Administrator.add(**profile)


cacher = ConfigurationCacher()
dendrite = Dendrite()
# dendrite.subscribe_conf('captive-portal', cb=cacher.cp_conf_updated)
dendrite.subscribe_conf('guest-access', cb=cacher.ga_conf_updated)
dendrite.subscribe_conf('administrator', cb=cacher.admins_conf_updated)

dendrite.wait_complete()
