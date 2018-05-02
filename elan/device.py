import re

from .neuron import Synapse, Dendrite

REDIS_LIFETIME = 60 * 24 * 60 * 60  # 60 days in seconds
MAC_HOSTNAME_PATH = 'mac:{mac}:hostname:{source}'
MAC_FINGERPRINT_PATH = 'mac:{mac}:fingerprint:{source}'

synapse = Synapse()
dendrite = Dendrite()


def seen_fingerprint(mac, fingerprint, source, hostname=''):
    new = store_fingerprint(mac, fingerprint, source)
    if new:
        notify_fingerprint(mac, fingerprint, source)
    return new


def store_fingerprint(mac, fingerprint, source, lifetime=REDIS_LIFETIME):
    '''
    Stores ``fingerprint`` from ``source`` for ``mac`` with expiry time of ``lifetime``
    Returns True if new fingerprint or False if unchanged (but lifetime has been expanded)
    '''
    key = MAC_FINGERPRINT_PATH.format(mac=mac, source=source)

    if synapse.get(key) == fingerprint:
        synapse.expire(key, lifetime)
        return False
    else:
        synapse.set(key, fingerprint, ex=lifetime)
        return True


def notify_fingerprint(mac, fingerprint, source, hostname):
    dendrite.publish('mac/fingerprint', dict(mac=mac, source=source, hostname=hostname, fingerprint=fingerprint))


def notify_known_fingerprints():
    count = 0
    for key in synapse.scan_iter(match=MAC_FINGERPRINT_PATH.format(mac='*', source='*')):
        m = re.match(MAC_FINGERPRINT_PATH.format(mac='(?P<mac>.+)', source='(?P<source>.+)'), key)
        if m:
            mac = m.group('mac')
            source = m.group('source')
            fingerprint = synapse.get(key)

            if fingerprint:
                notify_fingerprint(mac, fingerprint, source)
                count += 1
    return count


def seen_hostname(mac, hostname, source):
    new = store_hostname(mac, hostname, source)
    if new:
        notify_hostname(mac, hostname, source)
    return new


def store_hostname(mac, hostname, source, lifetime=REDIS_LIFETIME):
    key = MAC_HOSTNAME_PATH.format(source=source, mac=mac)

    if synapse.get(key) == hostname:
        synapse.expire(key, lifetime)
        return False
    else:
        synapse.set(key, hostname, ex=lifetime)
        return True


def notify_hostname(mac, hostname, source):
    dendrite.publish('mac/hostname', dict(mac=mac, name=hostname, source=source))


def notify_known_hostnames():
    count = 0
    for key in synapse.scan_iter(match=MAC_HOSTNAME_PATH.format(mac='*', source='*')):
        m = re.match(MAC_HOSTNAME_PATH.format(mac='(?P<mac>.+)', source='(?P<source>.+)'), key)
        if m:
            mac = m.group('mac')
            source = m.group('source')
            hostname = synapse.get(key)

            if hostname:
                notify_hostname(mac, hostname, source)
                count += 1
    return count

