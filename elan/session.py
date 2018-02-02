import datetime
import re

from elan.neuron import Synapse, Dendrite

MAC_SESSION_TOPIC = 'session/mac'
VLAN_SESSION_TOPIC = 'session/vlan'
IP_SESSION_TOPIC = 'session/ip'

LAST_SEEN_PATH = 'device:macs:last_seen'

SESSION_IDS_PATH = 'device:mac:session-ids'
SESSION_IDS_SEQUENCE_PATH = 'device:mac:session-ids:sequence'

MAC_PORT_PATH = 'device:mac:port'
MAC_LAST_PORT_PATH = 'device:mac:last_port'

MAC_VLANS_PATH = 'device:mac:{mac}:vlans'
MAC_VLAN_IPS_PATH = 'device:mac:{mac}:vlan:{vlan}:ips'
MAC_AUTH_SESSION_PATH = 'device:mac:{mac}:authentication'

synapse = Synapse()
dendrite = Dendrite()


def format_date(date):
    if not date:
        return datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    else:
        return datetime.datetime.utcfromtimestamp(date).strftime('%Y-%m-%dT%H:%M:%SZ')


def is_online(mac, vlan=None, ip=None):
    ''' returns True if Mac (optionnaly, on VLAN, with IP) is connected '''

    data = dict(mac=mac)
    if vlan is not None:
        data['vlan'] = vlan
    if ip is not None:
        data['ip'] = ip

    return bool(synapse.zscore(LAST_SEEN_PATH, data))


def get_current_session_ids():
    '''
    return current existing sessions as hash: tuples of mac, vlan, ip (vlan and ip may be None) as keys and id as value.
    '''
    return {field_to_mac_vlan_ip(field): value for field, value in synapse.hscan_iter(SESSION_IDS_PATH)}


def notify_current_sessions():
    '''
    resends all notifications of current sessions, including port.
    returns number notifications sent
    '''
    ip_sessions, vlan_sessions, mac_sessions = set(), set(), set()
    current_sessions = get_current_session_ids()

    count = 0

    for mac, vlan, ip in current_sessions:
        if ip is not None:
            ip_sessions.add((mac, vlan, ip))
        elif vlan is not None:
            vlan_sessions.add((mac, vlan))
        else:
            mac_sessions.add(mac)

    for mac, vlan, ip in ip_sessions:
        notify_new_IP_session(mac, mac_local_id=current_sessions[(mac, None, None)],
                              vlan=vlan, vlan_local_id=current_sessions[(mac, vlan, None)],
                              ip=ip, ip_local_id=current_sessions[(mac, vlan, ip)],
                              port=mac_port(mac)
        )
        vlan_sessions.discard((mac, vlan))
        mac_sessions.discard(mac)
        count += 1

    for mac, vlan in vlan_sessions:
        notify_new_VLAN_session(mac, mac_local_id=current_sessions[(mac, None, None)],
                                vlan=vlan, vlan_local_id=current_sessions[(mac, vlan, None)],
                                port=mac_port(mac)
        )
        mac_sessions.discard(mac)
        count += 1

    for mac in mac_sessions:
        notify_new_MAC_session(mac, mac_local_id=current_sessions[(mac, None, None)],
                               port=mac_port(mac)
        )
        count += 1

    return count


def mac_has_ip_on_vlan(mac, ip, vlan):
    return synapse.sismember(MAC_VLAN_IPS_PATH.format(mac=mac, vlan=vlan), ip)


def mac_port(mac):
    return synapse.hget(MAC_PORT_PATH, mac)


def seen(mac, vlan=None, port=None, ip=None, time=None):
    '''
    marks mac as seen on VLAN 'vlan', on Port 'port' with IP 'ip' at Time 'time' and notifies CC if new session.
    time should be epoch.
    ip ignored if vlan not specified
    returns 3 booleans whether MAC, VLAN and IP were new
    '''
    if time is None:
        time = (datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds()  # Epoch

    # if port has changed, end previous session
    if port is not None:
        old_port = mac_port(mac)
        if(
            old_port is not None
            and
            (
                port['local_id'] != old_port['local_id']
                or
                (
                    # Interface may be unknown in new or old port, assume it did not change
                    port['interface'] is not None
                    and
                    old_port['interface'] is not None
                    and
                    port['interface'] != old_port['interface']
                )
                or
                (
                    # SSID may be unknown in new or old port, assume it did not change
                    port.get('ssid', None) is not None
                    and
                    old_port.get('ssid', None) is not None
                    and
                    port.get('ssid', None) != old_port.get('ssid', None)
                )
            )
        ):
            end(mac)
        elif old_port is not None:
            # make sure we do not set to None SSID or Interface if the info we receive does not contain that information
            if old_port['interface'] is not None:
                port['interface'] = old_port['interface']
            if old_port.get('ssid', None) is not None:
                port['ssid'] = old_port['ssid']

    pipe = synapse.pipeline()

    pipe.zadd(LAST_SEEN_PATH, time, dict(mac=mac))
    if vlan is not None:
        pipe.zadd(LAST_SEEN_PATH, time, dict(mac=mac, vlan=vlan))
        pipe.sadd(MAC_VLANS_PATH.format(mac=mac), vlan)
        if ip is not None:
            pipe.zadd(LAST_SEEN_PATH, time, dict(mac=mac, vlan=vlan, ip=ip))
            pipe.sadd(MAC_VLAN_IPS_PATH.format(mac=mac, vlan=vlan), ip)
    results = pipe.execute()

    mac_added = bool(results[0])
    vlan_added = False
    if len(results) > 1:
        vlan_added = bool(results[1])
    ip_added = False
    if len(results) > 3:
        ip_added = bool(results[3])

    if mac_added or vlan_added or ip_added:
        local_id = synapse.get_unique_id(SESSION_IDS_SEQUENCE_PATH)

    if mac_added:
        pipe.hset(SESSION_IDS_PATH, session_ids_field(mac=mac), local_id)
        mac_local_id = local_id
    else:
        pipe.hget(SESSION_IDS_PATH, session_ids_field(mac=mac))

    if vlan_added:
        pipe.hset(SESSION_IDS_PATH, session_ids_field(mac=mac, vlan=vlan), local_id)
        vlan_local_id = local_id
    else:
        pipe.hget(SESSION_IDS_PATH, session_ids_field(mac=mac, vlan=vlan))

    if ip_added:
        pipe.hset(SESSION_IDS_PATH, session_ids_field(mac=mac, vlan=vlan, ip=ip), local_id)

    results = pipe.execute()
    if not mac_added:
        mac_local_id = results[0]
    if not vlan_added:
        vlan_local_id = results[1]

    if port is not None and port != old_port:
        pipe.hset(MAC_PORT_PATH, mac, port)
        pipe.hset(MAC_LAST_PORT_PATH, mac, port)  # Keep track of last port when port is deleted
        pipe.execute()
        if not mac_added:  # TODO check if can write 'and not vlan_added and not ip_added': in CC will port be updated if mac already present and new vlan or ip session ?
            notify_MAC_port(mac=mac, mac_local_id=mac_local_id, port=port)

    if ip_added:
        notify_new_IP_session(mac=mac, vlan=vlan, ip=ip, port=port, start=time, mac_local_id=mac_local_id, vlan_local_id=vlan_local_id, ip_local_id=local_id)
    elif vlan_added:
        notify_new_VLAN_session(mac=mac, vlan=vlan, port=port, start=time, mac_local_id=mac_local_id, vlan_local_id=local_id)
    elif mac_added:
        notify_new_MAC_session(mac=mac, port=port, start=time, mac_local_id=local_id)

    return mac_added, vlan_added, ip_added


def session_ids_field(mac, vlan=None, ip=None):
    'formats mac vlan and ip to be stored in redis hash field'

    if ip is not None:
        return 'mac={mac},vlan={vlan},ip={ip}'.format(mac=mac, vlan=vlan, ip=ip)
    if vlan is not None:
        return 'mac={mac},vlan={vlan}'.format(mac=mac, vlan=vlan)
    return 'mac={mac}'.format(mac=mac)


def field_to_mac_vlan_ip(field):
    'return tuple of mac, vlan and ip from Session IDs redis hash field.'
    m = re.match('mac=(?P<mac>.+?)($|,vlan=(?P<vlan>.+?)($|,ip=(?P<ip>.+?)$))', field)
    return  m.group('mac'), m.group('vlan'), m.group('ip')


def end(mac, vlan=None, ip=None, time=None):
    '''
    Ends a Mac, Vlan or IP session. If ip no specified, will delete all ip sessions for the vlan. If vlan not specified, will delete all vlan and ip sessions associated with that mac.
    Note that it will not delete mac session if this was the last vlan session that is being deleted (same with vlan for ips). This is the responsibility of the caller to check that.
    '''
    if time is None:
        time = (datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds()  # Epoch

    pipe = synapse.pipeline()

    if ip is not None and vlan is None:
        raise Exception('Error: when ending IP, VLAN should be specified...')

    data = dict(mac=mac)
    pipe.hget(SESSION_IDS_PATH, session_ids_field(**data))

    # find all Objects to end (if mac, end also vlans and IPs, if vlan, end also IPs)
    if vlan is None:
        pipe.hdel(SESSION_IDS_PATH, session_ids_field(**data))
        pipe.zrem(LAST_SEEN_PATH, data)
        vlans = synapse.smembers(MAC_VLANS_PATH.format(mac=mac))
        pipe.delete(MAC_VLANS_PATH.format(mac=mac))
    else:
        data = dict(mac=mac, vlan=vlan)
        pipe.hget(SESSION_IDS_PATH, session_ids_field(**data))
        vlans = [vlan]
    for v in vlans:
        data = dict(mac=mac, vlan=v)
        if ip is None:
            pipe.hdel(SESSION_IDS_PATH, session_ids_field(**data))
            pipe.zrem(LAST_SEEN_PATH, data)
            pipe.srem(MAC_VLANS_PATH.format(mac=mac), v)
            ips = synapse.smembers(MAC_VLAN_IPS_PATH.format(mac=mac, vlan=v))
            pipe.delete(MAC_VLAN_IPS_PATH.format(mac=mac, vlan=v))
        else:
            data = dict(mac=mac, vlan=v, ip=ip)
            pipe.hget(SESSION_IDS_PATH, session_ids_field(**data))
            ips = [ip]
        for i in ips:
            data = dict(mac=mac, vlan=v, ip=i)
            pipe.hdel(SESSION_IDS_PATH, session_ids_field(**data))
            pipe.zrem(LAST_SEEN_PATH, data)

    results = pipe.execute()

    mac_local_id = results[0]
    if vlan is not None:
        vlan_local_id = results[1]
        if ip is not None:
            ip_local_id = results[2]

    if ip is not None:
        if ip_local_id:
            notify_end_IP_session(mac=mac, mac_local_id=mac_local_id, vlan=vlan, vlan_local_id=vlan_local_id, ip=ip, ip_local_id=ip_local_id, end=time)
    elif vlan is not None:
        if vlan_local_id:
            notify_end_VLAN_session(mac=mac, mac_local_id=mac_local_id, vlan=vlan, vlan_local_id=vlan_local_id, end=time)
    elif mac_local_id:
        synapse.hdel(MAC_PORT_PATH, mac)
        remove_till_disconnect_authentication_session(mac)
        notify_end_MAC_session(mac=mac, mac_local_id=mac_local_id, end=time)


def add_authentication_session(mac, **session):
    '''
    add authentication session to device
    authentication can be ad vitam (explicitly set till disconnect=False), till a date (till=epoch) or till disconnect (till_disconnect=True) (default if till and till_disconnect not specified)
    source can be: dot1x, mac, captive-portal, guest-access
    '''

    if 'source' not in session:
        raise('source mandatory')

    # cleanup:
    remove_expired_authentication_session(mac)

    if 'till_disconnect' not in session:
        if 'till' not in session:
            session['till_disconnect'] = True
        else:
            session['till_disconnect'] = False

    synapse.sadd(MAC_AUTH_SESSION_PATH.format(mac=mac), session)


def get_authentication_sessions(mac, **filters):
    # cleanup
    remove_expired_authentication_session(mac)
    authentications = synapse.smembers_as_list(MAC_AUTH_SESSION_PATH.format(mac=mac))
    filtered = []
    for auth in authentications:
        for key in filters:
            if auth.get(key, None) != filters[key]:
                break
        else:
            filtered.append(auth)
    return filtered


def source_in_authentication_sessions(mac, source):
    for session in synapse.smembers_as_list(MAC_AUTH_SESSION_PATH.format(mac=mac)):
        if session['source'] == source:
            return True
    return False


def remove_authentication_sessions_by_source(mac, source):
    # TODO: redis transaction
    current_sessions = synapse.smembers_as_list(MAC_AUTH_SESSION_PATH.format(mac=mac))
    for session in current_sessions:
        if session['source'] == source:
            synapse.srem(MAC_AUTH_SESSION_PATH.format(mac=mac), session)


def remove_till_disconnect_authentication_session(mac):

    # TODO: redis transaction
    current_sessions = synapse.smembers_as_list(MAC_AUTH_SESSION_PATH.format(mac=mac))
    for session in current_sessions:
        if 'till_disconnect' in session and session['till_disconnect']:
            synapse.srem(MAC_AUTH_SESSION_PATH.format(mac=mac), session)


def remove_expired_authentication_session(mac, date=None):
    '''
    remove all sessions that have expired, or all sessions that have/will expire at date (epoch)
    '''

    if date is None:
        date = (datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds()  # now as EPOCH

    # TODO: redis transaction
    current_sessions = synapse.smembers_as_list(MAC_AUTH_SESSION_PATH.format(mac=mac)) or []
    for session in current_sessions:
        if 'till' in session and session['till'] <= date:
            synapse.srem(MAC_AUTH_SESSION_PATH.format(mac=mac), session)

# Control Center Notifications


def notify_new_MAC_session(mac, mac_local_id, port=None, start=None):
    ''' start is Epoch '''
    data = {'start': format_date(start), 'local_id': mac_local_id, 'mac': mac}
    if port:
        data['port'] = port
    dendrite.publish(MAC_SESSION_TOPIC, data)


def notify_end_MAC_session(mac, mac_local_id, end=None):
    ''' start is Epoch '''
    dendrite.publish(MAC_SESSION_TOPIC, {'end': format_date(end), 'local_id': mac_local_id, 'mac': mac})


def notify_MAC_port(mac, mac_local_id, port):
    dendrite.publish(MAC_SESSION_TOPIC, {'port': port, 'local_id': mac_local_id, 'mac': mac})


def notify_new_VLAN_session(mac, mac_local_id, vlan, vlan_local_id, port=None, start=None):
    ''' start is Epoch '''
    data = {'start': format_date(start), 'local_id': vlan_local_id, 'mac': mac, 'vlan': vlan, 'mac_local_id': mac_local_id}
    if port:
        data['port'] = port
    dendrite.publish(VLAN_SESSION_TOPIC, data)


def notify_end_VLAN_session(mac, mac_local_id, vlan, vlan_local_id, end=None):
    ''' start is Epoch '''
    dendrite.publish(
            VLAN_SESSION_TOPIC,
            {'end': format_date(end), 'mac': mac, 'vlan': vlan, 'mac_local_id': mac_local_id, 'local_id': vlan_local_id}
    )


def notify_new_IP_session(mac, mac_local_id, vlan, vlan_local_id, ip, ip_local_id, port=None, start=None):
    ''' start is Epoch '''
    data = {'start': format_date(start), 'local_id': ip_local_id, 'mac': mac, 'vlan': vlan, 'ip': ip, 'mac_local_id': mac_local_id, 'vlan_local_id': vlan_local_id}
    if port:
        data['port'] = port
    dendrite.publish(IP_SESSION_TOPIC, data)


def notify_end_IP_session(mac, mac_local_id, vlan, vlan_local_id, ip, ip_local_id, end=None):
    ''' start is Epoch '''
    dendrite.publish(
            IP_SESSION_TOPIC,
            {'end': format_date(end), 'local_id': ip_local_id, 'mac': mac, 'vlan': vlan, 'ip': ip, 'mac_local_id': mac_local_id, 'vlan_local_id': vlan_local_id}
    )


def ignore_MAC(mac):
    # Ignore broadcast packets
    if mac in ['ff:ff:ff:ff:ff:ff', '00:00:00:00:00:00']:
        return True

    # Ignore IANA Reserved MACs: http://www.iana.org/assignments/ethernet-numbers/ethernet-numbers.xml
    # name is IANA_{integer}, integer being the number of prefixed bytes.
    IANA_6_prefix = ['00:00:5e', '01:00:5e', '02:00:5e', '03:00:5e']
    if mac[0:8] in IANA_6_prefix:
        return True
    IANA_4_prefix = ['33:33']
    if mac[0:5] in IANA_4_prefix:
        return True

    return False


def ignore_IP(ip):
    # Ignore broadcast
    if ip[:6] == '0.0.0.' or ip in ('255.255.255.255', '::'):
        return True
    # Ignore multicast
    if ip[:4] in [str(v) + '.' for v in range(224, 239)]:  # 224. to 239.
        return True

    if ip == '::':
        return True

    return False

