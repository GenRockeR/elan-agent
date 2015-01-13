from origin.neuron import Dendrite
import datetime


LAST_SEEN_PATH = 'device:macs:last_seen'

SESSION_IDS_PATH = 'device:mac:session-ids'
SESSION_IDS_SEQUENCE_PATH = 'device:mac:session-ids:sequence'


MAC_PORT_PATH = 'device:mac:port'
MAC_LAST_PORT_PATH = 'device:mac:last_port'

MAC_VLANS_PATH = 'device:mac:{mac}:vlans'
MAC_VLAN_IPS_PATH = 'device:mac:{mac}:vlan:{vlan}:ips'
MAC_AUTH_SESSION_PATH = 'device:mac:{mac}:authentication'

dendrite = Dendrite('session')

def format_date(date):
    if not date:
        return datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    else:
        return datetime.datetime.utcfromtimestamp(date).strftime('%Y-%m-%dT%H:%M:%SZ')



def seen(mac, vlan=None, port=None, ip=None, time=None ):
    '''
    marks mac as seen on VLAN 'vlan', on Port 'port' with IP 'ip' at Time 'time' and notifies CC if new session.
    time should be epoch.
    ip ignored if vlan not specified
    returns true if MAC was new
    '''
    if time is None:
        time = (datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds() #Epoch

    # if port has changed, end previous session
    if port is not None:
        old_port = dendrite.synapse.hget(MAC_PORT_PATH, mac)
        if old_port is not None and port != old_port:
            end(mac)

    pipe = dendrite.synapse.pipe

    pipe.zadd(LAST_SEEN_PATH, time, dict(mac=mac))
    if vlan is not None:
        vlan = int(vlan) # make sure to store it as int as it may be provided as a string...
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
        local_id = dendrite.synapse.get_unique_id(SESSION_IDS_SEQUENCE_PATH)

        if mac_added:
            pipe.hset(SESSION_IDS_PATH, dict(mac=mac), local_id)
            mac_local_id = local_id
        else:
            pipe.hget(SESSION_IDS_PATH, dict(mac=mac))
            
        if vlan_added:
            pipe.hset(SESSION_IDS_PATH, dict(mac=mac, vlan=vlan), local_id)
            vlan_local_id = local_id
        else:
            pipe.hget(SESSION_IDS_PATH, dict(mac=mac, vlan=vlan))
            
        if ip_added:
            pipe.hset(SESSION_IDS_PATH, dict(mac=mac, vlan=vlan, ip=ip), local_id)
            
        results = pipe.execute()
        if not mac_added:
            mac_local_id = results[0] 
        if not vlan_added:
            vlan_local_id = results[1] 
    
    if port is not None and port != old_port:
        pipe.hset(MAC_PORT_PATH, mac, port)
        pipe.hset(MAC_LAST_PORT_PATH, mac, port) # Keep track of last port when port is deleted
        pipe.execute()
        if not mac_added: # TODO check if can write 'and not vlan_added and not ip_added': in CC will port be updated if mac already present and new vlan or ip session ? 
            notify_MAC_port(mac=mac, port=port, time=time)
            
    if ip_added:
        notify_new_IP_session(   mac=mac, vlan=vlan, ip=ip, port=port, start=time, mac_local_id=mac_local_id, vlan_local_id=vlan_local_id, ip_local_id=local_id)
    elif vlan_added:
        notify_new_VLAN_session( mac=mac, vlan=vlan,        port=port, start=time, mac_local_id=mac_local_id, vlan_local_id=local_id)
    elif mac_added:
        notify_new_MAC_session(  mac=mac,                   port=port, start=time, mac_local_id=local_id)
 
    return mac_added
                    

def end(mac, vlan=None, ip=None, time=None):
    '''
    Ends a Mac, Vlan or IP session. If ip no specified, will delete all ip session for the vlan. If vlan not specified, will delete all vlan and ip sessions associated with that mac.
    Note that it will not delete mac session if this was the last vlan session that is being deleted (same with vlan and ips). This is the responsibility of the caller that should check that. 
    '''
    # TODO: should be in redis transaction ?
    if time is None:
        time = (datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds() #Epoch

    pipe = dendrite.synapse.pipe
    
    if ip is not None and vlan is None: raise 'Error: when ending IP, VLAN should be specified...' 
    
    data = dict(mac=mac)
    pipe.hget(SESSION_IDS_PATH, data)
    
    
    # find all Objects to end (if mac, end also vlans and IPs, if vlan, end also IPs)
    if vlan is None:
        pipe.hdel(SESSION_IDS_PATH, data)
        pipe.zrem(LAST_SEEN_PATH, data)
        vlans = dendrite.synapse.smembers(MAC_VLANS_PATH.format(mac=mac))
        for v in vlans:
            data = dict(mac=mac, vlan=v)
            pipe.hdel(SESSION_IDS_PATH, data)
            pipe.zrem(LAST_SEEN_PATH, data)
            ips = dendrite.synapse.smembers(MAC_VLAN_IPS_PATH.format(mac=mac, vlan=v))
            for i in ips:
                data = dict(mac=mac, vlan=v, ip=i)
                pipe.hdel(SESSION_IDS_PATH, data)
                pipe.zrem(LAST_SEEN_PATH, data)
            pipe.delete(MAC_VLAN_IPS_PATH.format(mac=mac, vlan=v))
        pipe.delete(MAC_VLANS_PATH.format(mac=mac))
        
    else:
        vlan = int(vlan) # vlan is stored as an int.
        data = dict(mac=mac, vlan=vlan)
        pipe.hget(SESSION_IDS_PATH, data)
        if ip is None:
            pipe.hdel(SESSION_IDS_PATH, data)
            pipe.zrem(LAST_SEEN_PATH, data)
            pipe.srem(MAC_VLANS_PATH.format(mac=mac), vlan)
            ips = dendrite.synapse.smembers(MAC_VLAN_IPS_PATH.format(mac=mac, vlan=vlan))
            for i in ips:
                data = dict(mac=mac, vlan=vlan, ip=i)
                pipe.hdel(SESSION_IDS_PATH, data)
                pipe.zrem(LAST_SEEN_PATH, data)
            pipe.delete(MAC_VLAN_IPS_PATH.format(mac=mac, vlan=vlan))
        else:
            data = dict(mac=mac, vlan=vlan, ip=ip)
            pipe.hget(SESSION_IDS_PATH, data)
            pipe.hdel(SESSION_IDS_PATH, data)
            pipe.zrem(LAST_SEEN_PATH, data)
            pipe.srem(MAC_VLAN_IPS_PATH.format(mac=mac, vlan=vlan), ip)

        
    results = pipe.execute()
    
    mac_local_id = results[0]
    if vlan is not None:
        vlan_local_id = results[1]
        if ip is not None:
            ip_local_id = results[2]
    
    if ip is not None: 
        if ip_local_id:
            notify_end_IP_session(  mac=mac, mac_local_id=mac_local_id, vlan=vlan, vlan_local_id=vlan_local_id, ip=ip, ip_local_id=ip_local_id, end=time)
    elif vlan is not None:
        if vlan_local_id:
            notify_end_VLAN_session(mac=mac, mac_local_id=mac_local_id, vlan=vlan, vlan_local_id=vlan_local_id, end=time)
    elif mac_local_id:
        dendrite.synapse.hdel(MAC_PORT_PATH, mac)
        remove_till_disconnect_authentication_session(mac)
        notify_end_MAC_session( mac=mac, mac_local_id=mac_local_id, end=time)            


def add_authentication_session(mac, **session):
    '''
    add authentication session to device
    authentication can be ad vitam (explicitly set till disconnect=False), till a date (till=epoch) or till disconnect (till_disconnect=True) (default if till and till_disconnect not specified)
    source can be: dot1x, mac, captive-portal, guest-access
    '''
    
    if 'source' not in session:
        raise('source mandatory') 
    
    #cleanup:
    remove_expired_authentication_session(mac)
    
    if 'till_disconnect' not in session:
        if 'till' not in session:
            session['till_disconnect'] = True
        else:
            session['till_disconnect'] = False
    
    dendrite.synapse.sadd(MAC_AUTH_SESSION_PATH.format(mac=mac), session)

def get_authentication_sessions(mac):
    return dendrite.synapse.smembers_as_list(MAC_AUTH_SESSION_PATH.format(mac=mac))

def source_in_authentication_sessions(mac, source):
    for session in dendrite.synapse.smembers_as_list(MAC_AUTH_SESSION_PATH.format(mac=mac)):
        if session['source'] == source:
            return True
    return False

def remove_authentication_sessions_by_source(mac, source):
    #TODO: redis transaction
    current_sessions = dendrite.synapse.smembers_as_list(MAC_AUTH_SESSION_PATH.format(mac=mac))
    for session in current_sessions:
        if session['source'] == source:
            dendrite.synapse.srem(MAC_AUTH_SESSION_PATH.format(mac=mac), session)

def remove_till_disconnect_authentication_session(mac):
    
    #TODO: redis transaction
    current_sessions = dendrite.synapse.smembers_as_list(MAC_AUTH_SESSION_PATH.format(mac=mac))
    for session in current_sessions:
        if 'till_disconnect' in session and session['till_disconnect']:
            dendrite.synapse.srem(MAC_AUTH_SESSION_PATH.format(mac=mac), session)
            
def remove_expired_authentication_session(mac, date=None):
    '''
    remove all sessions that have expired
    '''
    
    if date is None:
        date = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

    #TODO: redis transaction
    current_sessions = dendrite.synapse.smembers_as_list(MAC_AUTH_SESSION_PATH.format(mac=mac)) or []
    for session in current_sessions:
        if 'till'in session and session['till'] <= date:
            dendrite.synapse.srem(MAC_AUTH_SESSION_PATH.format(mac=mac), session)
    

# Control Center Notifications

def notify_new_MAC_session(mac, mac_local_id, port=None, start=None):
    ''' start is Epoch '''
    dendrite.post('mac/{mac}/session'.format(mac=mac), {'start': format_date(start), 'port': port, 'local_id': mac_local_id})

def notify_end_MAC_session(mac, mac_local_id, end=None):
    ''' start is Epoch '''
    dendrite.post('mac/{mac}/session/local_id:{local_id}/end'.format(mac=mac, local_id=mac_local_id), {'end': format_date(end)})

def notify_MAC_port(mac, mac_local_id, port, time=None):
    dendrite.post('mac/{mac}/session/local_id:{mac_local_id}/port'.format(mac=mac, mac_local_id=mac_local_id), {'time': format_date(time), 'port': port})


def notify_new_VLAN_session(mac, mac_local_id, vlan, vlan_local_id, port=None, start=None):
    ''' start is Epoch '''
    dendrite.post(
            'mac/{mac}/session/local_id:{mac_local_id}/vlan/{vlan}'.format(
                    mac=mac, vlan=vlan, mac_local_id=mac_local_id
            ),
            {'start': format_date(start), 'port': port, 'local_id': vlan_local_id}
    )

def notify_end_VLAN_session(mac, mac_local_id, vlan, vlan_local_id, end=None):
    ''' start is Epoch '''
    dendrite.post(
              'mac/{mac}/session/local_id:{mac_local_id}/vlan/{vlan}/local_id:{vlan_local_id}/end'.format(
                         mac=mac, vlan=vlan, mac_local_id=mac_local_id, vlan_local_id=vlan_local_id
              ), 
              {'end': format_date(end)}
    )
    

    
def notify_new_IP_session(mac, mac_local_id, vlan, vlan_local_id, ip, ip_local_id, port=None, start=None):
    ''' start is Epoch '''
    dendrite.post(
              'mac/{mac}/session/local_id:{mac_local_id}/vlan/{vlan}/local_id:{vlan_local_id}/ip/{ip}'.format(
                         mac=mac, vlan=vlan, ip=ip, mac_local_id=mac_local_id, vlan_local_id=vlan_local_id
              ), 
              {'start': format_date(start), 'port': port, 'local_id': ip_local_id}
    )


def notify_end_IP_session(mac, mac_local_id, vlan, vlan_local_id, ip, ip_local_id, end=None):
    ''' start is Epoch '''
    dendrite.post(
              'mac/{mac}/session/local_id:{mac_local_id}/vlan/{vlan}/local_id:{vlan_local_id}/ip/{ip}/local_id:{ip_local_id}/end'.format(
                          mac=mac, vlan=vlan, ip=ip, mac_local_id=mac_local_id, vlan_local_id=vlan_local_id, ip_local_id=ip_local_id
              ), 
              {'end': format_date(end)}
    )



