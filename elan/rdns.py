from elan import neuron
RDNS_PATH = 'rdns:{mac}:{source}'

synapse = neuron.Synapse()


def get_cached_rdns(source, mac=None):
    '''
    Return cached rdns for that `mac`. If not found for that mac will return latest match for any mac
    If no `mac` provided, will return latest match for any mac.
    '''
    if mac is None:
        return _get_cached_rdns(source, '*')
    rdns = _get_cached_rdns(source, mac)
    if rdns is None:
        return _get_cached_rdns(source, '*')
    return rdns


def _get_cached_rdns(source, mac):
    rdns = synapse.get(RDNS_PATH.format(source=source, mac=mac))
    if rdns is None:
        return
    # recurse to get last level of rdns:
    last_level_rdns = _get_cached_rdns(rdns, mac)

    if last_level_rdns:
        return last_level_rdns

    return rdns


def add_entries(*entries):
    '''
    Adds rdns entries to cache.
    Each entry is dict with the following keys:
    - mac
    - source
    - ttl
    - rdns
    '''
    pipe = synapse.pipeline()
    for entry in entries:
        expiry = int(entry['ttl']) + 60  # Keep it a little longer, just in case
        pipe.set(RDNS_PATH.format(mac=entry['mac'], source=entry['source']), entry['rdns'], ex=expiry)
        pipe.set(RDNS_PATH.format(mac='*', source=entry['source']), entry['rdns'], ex=expiry)
    pipe.execute()
