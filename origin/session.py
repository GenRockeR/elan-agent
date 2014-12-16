from origin.neuron import Dendrite
import datetime


LAST_SEEN_PATH = 'device:macs:last_seen'
MAC_PORT_PATH = 'device:mac:port'
MAC_VLANS_PATH = 'device:mac:{mac}:vlans'
MAC_VLAN_IPS_PATH = 'device:mac:{mac}:vlan:{vlan}'
MAC_AUTH_SESSION_PATH = 'device:auth'

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
        if old_port is not None and old_port != port:
            end(mac)

    pipe = dendrite.synapse.pipe

    pipe.zadd(LAST_SEEN_PATH, [time, dict(mac=mac)])
    if vlan is not None:
        pipe.zadd(LAST_SEEN_PATH, [ time, dict(mac=mac, vlan=vlan)])
        pipe.sadd(MAC_VLANS_PATH.format(mac=mac), vlan)
        if ip is not None:
            pipe.zadd(LAST_SEEN_PATH, [ time, dict(mac=mac, vlan=vlan, ip=ip)])
            pipe.sadd(MAC_VLAN_IPS_PATH.format(mac=mac, vlan=vlan), ip)
    added = bool(pipe.execute())[0]
    
        
    if added: # new session(s) created: inform Control Center and keep mac port
        if port is not None:
            dendrite.synapse.hset(MAC_PORT_PATH, mac, port)
            
        if ip is not None and vlan is not None:
            notify_new_IP_session(mac=mac, vlan=vlan, ip=ip, port=port, start=time)
        elif vlan is not None:
            notify_new_VLAN_session(mac=mac, vlan=vlan, port=port, start=time)
        else:
            notify_new_MAC_session(mac=mac, port=port, start=time)
    elif port is not None and old_port is None:
        notify_MAC_port(mac=mac, port=port, time=time)
 
    return added
                    

def end(mac, vlan=None, ip=None, time=None):
    # TODO: should be in redis transaction ?
    if time is None:
        time = (datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds() #Epoch

    pipe = dendrite.synapse.pipe
    
    if ip is not None and vlan is None: raise 'Error: when ending IP, VLAN should be specified...' 
    
    pipe.zrem(LAST_SEEN_PATH, dict(mac=mac))
    
    # find all Objects to end (if mac, end also vlans and IPs, if vlan, end also IPs)
    if vlan is None:
        vlans = dendrite.synapse.smembers(MAC_VLANS_PATH.format(mac=mac))
        for v in vlans:
            pipe.zrem(LAST_SEEN_PATH, dict(mac=mac, vlan=v))
            ips = dendrite.synapse.smembers(MAC_VLAN_IPS_PATH.format(mac=mac, vlan=v))
            for i in ips:
                pipe.zrem(LAST_SEEN_PATH, dict(mac=mac, vlan=v, ip=i))
            pipe.delete(MAC_VLAN_IPS_PATH.format(mac=mac, vlan=v))
        pipe.delete(MAC_VLANS_PATH.format(mac=mac))
        
    else:
        if ip is None:
            ips = dendrite.synapse.smembers(MAC_VLAN_IPS_PATH.format(mac=mac, vlan=vlan))
            for i in ips:
                pipe.zrem(LAST_SEEN_PATH, dict(mac=mac, vlan=vlan, ip=i))
            pipe.delete(MAC_VLAN_IPS_PATH.format(mac=mac, vlan=vlan))
        else:
            pipe.zrem(LAST_SEEN_PATH, dict(mac=mac, vlan=v, ip=ip))
            pipe.srem(MAC_VLAN_IPS_PATH.format(mac=mac, vlan=vlan), ip)
        pipe.srem(MAC_VLANS_PATH.format(mac=mac), vlan)

        
    if vlan is None:
        vlans = dendrite.synapse.smembers(MAC_VLANS_PATH.format(mac=mac))
    else:
        vlans = set([vlan])

    pipe.execute()
    
    if ip is not None and vlan is not None:
        notify_end_IP_session(mac=mac, vlan=vlan, ip=ip, start=time)
    elif vlan is not None:
        notify_end_VLAN_session(mac=mac, vlan=vlan, start=time)
    else:
        dendrite.synapse.hrem(MAC_PORT_PATH, mac)
        notify_end_MAC_session(mac=mac, start=time)            


def add_authentication_session(mac, **session):
    '''
    add authentication session to device
    authentication can be ad vitam (explicitly set till disconnect=False), till a date (till=epoch) or till disconnect (till_disconnect=True) (default if till and till_disconnect not specified)
    source can be: dot1x, mac, captive-portal, guest-access
    '''
    
    #cleanup:
    remove_expired_authentication_session(mac)
    
    if 'till_disconnect' not in session:
        if 'till' not in session:
            session['till_disconnect'] = True
        else:
            session['till_disconnect'] = False
    
    current_sessions = dendrite.synapse.hget(MAC_AUTH_SESSION_PATH, mac)
    
    if session not in current_sessions:
        current_sessions.append(session)
        dendrite.synapse.hset(MAC_AUTH_SESSION_PATH, mac, current_sessions)

def remove_till_disconnect_authentication_session(mac):
    
    #TODO: redis transaction
    current_sessions = dendrite.synapse.hget(MAC_AUTH_SESSION_PATH, mac)
    new_sessions = []
    for session in current_sessions:
        if 'till_disconnect' not in session or not session['till_disconnect']:
            new_sessions.append(session)
            
    dendrite.synapse.hset(MAC_AUTH_SESSION_PATH, mac, new_sessions)

def remove_expired_authentication_session(mac, date=None):
    '''
    remove all sessions that have expired
    '''
    
    if date is None:
        date = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

    #TODO: redis transaction
    current_sessions = dendrite.synapse.hget(MAC_AUTH_SESSION_PATH, mac) or []
    new_sessions = []
    for session in current_sessions:
        if 'till' not in session or session['till'] > date:
            new_sessions.append(session)
            
    dendrite.synapse.hset(MAC_AUTH_SESSION_PATH, mac, new_sessions)
    
def get_network_assignments(mac, port=None, current_auth_sessions=None):
    if current_auth_sessions is None:
        current_auth_sessions = dendrite.synapse.hget(MAC_AUTH_SESSION_PATH, mac)
    if port is None:
        port = dendrite.synapse.hget(MAC_PORT_PATH, mac)

    # cleanup
    remove_expired_authentication_session(mac)
        
    return dendrite.sync_post('agent/self/net-assignments', {'auth_sessions': current_auth_sessions, 'mac': mac, 'port': port})


def notify_new_MAC_session(mac, port=None, start=None):
    ''' start is Epoch '''
    dendrite.post('mac/{mac}/session'.format(mac=mac), {'start': format_date(start), 'port': port})

def notify_end_MAC_session(mac, end=None):
    ''' start is Epoch '''
    dendrite.post('mac/{mac}/session/current/end'.format(mac=mac), {'end': format_date(end)})

def notify_MAC_port(mac, port, time=None):
    dendrite.post('mac/{mac}/session/current/port'.format(mac=mac), {'time': format_date(time), 'port': port})


def notify_new_VLAN_session(mac, vlan, port=None, start=None):
    ''' start is Epoch '''
    dendrite.post('mac/{mac}/session/current/vlan/{vlan}'.format(mac=mac, vlan=vlan), {'start': format_date(start), 'port': port})

def notify_end_VLAN_session(mac, vlan, end=None):
    ''' start is Epoch '''
    dendrite.post('mac/{mac}/session/current/vlan/{vlan}/current/end'.format(mac=mac, vlan=vlan), {'end': format_date(end)})
    

    
def notify_new_IP_session(mac, vlan, ip, port=None, start=None):
    ''' start is Epoch '''
    dendrite.post('mac/{mac}/session/current/vlan/{vlan}/current/ip/{ip}'.format(mac=mac, vlan=vlan, ip=ip), {'start': format_date(start), 'port': port})


def notify_end_IP_session(mac, vlan, ip, end=None):
    ''' start is Epoch '''
    dendrite.post('mac/{mac}/session/current/vlan/{vlan}/current/ip/{ip}/current/end'.format(mac=mac, vlan=vlan, ip=ip), {'end': format_date(end)})


def notify_new_authorization_session(mac, vlan, start=None, **kwargs):
    '''
        start and end are Epoch
        kwargs can contain type, login, authentication_provider, till_disconnect 
    '''
    kwargs['start'] = format_date(start)

    
    dendrite.post('mac/{mac}/authorization/vlan/{vlan}'.format(mac=mac, vlan=vlan), kwargs)

def notify_end_authorization_session(mac, vlan, end=None, **kwargs):
    ''' start is Epoch '''

    kwargs['end'] = format_date(end)

    dendrite.post('mac/{mac}/authorization/vlan/{vlan}/current/end'.format(mac=mac, vlan=vlan), kwargs)

