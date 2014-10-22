from origin.neuron import Dendrite
import datetime


LAST_SEEN_PATH = 'device:last_seen'

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
    ip ignore if vlan not specified
    '''
    if time is None:
        time = (datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds() #Epoch

    args = [ time, dict(mac=mac) ]
    if vlan is not None:
        args.extend([ time, dict(mac=mac, vlan=vlan)])
        if ip is not None:
            args.extend([ time, dict(mac=mac, vlan=vlan, ip=ip)])
    added = bool(dendrite.synapse.zadd(LAST_SEEN_PATH, *args))
    
    if added: # new session(s) created: inform Control Center
        if ip is not None and vlan is not None:
            notify_new_IP_session(mac=mac, vlan=vlan, ip=ip, port=port, start=time)
        elif vlan is not None:
            notify_new_VLAN_session(mac=mac, vlan=vlan, port=port, start=time)
        else:
            notify_new_MAC_session(mac=mac, port=port, start=time)
    elif port:
        notify_MAC_port(mac=mac, port=port, time=time)
                    

def end(mac, vlan=None, port=None, ip=None, time=None):
    if time is None:
        time = (datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds() #Epoch

    args = [ time, dict(mac=mac) ]
    if vlan is not None:
        args.extend([ time, dict(mac=mac, vlan=vlan)])
        if ip is not None:
            args.extend([ time, dict(mac=mac, vlan=vlan, ip=ip)])
    dendrite.synapse.zrem(LAST_SEEN_PATH, *args)

    if ip is not None and vlan is not None:
        notify_end_IP_session(mac=mac, vlan=vlan, ip=ip, start=time)
    elif vlan is not None:
        notify_end_VLAN_session(mac=mac, vlan=vlan, start=time)
    else:
        notify_end_MAC_session(mac=mac, start=time)            

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



def notify_new_authorization_session(mac, vlan, start=None, end=None, **kwargs):
    '''
        start and end are Epoch
        kwargs can contain type, login, authentication_provider, till_disconnect 
    '''
    kwargs['start'] = format_date(start)
    if end:
        kwargs['end'] = format_date(end)
    
    dendrite.post('mac/{mac}/authorization/vlan/{vlan}'.format(mac=mac, vlan=vlan), kwargs)

def notify_end_authorization_session(mac, vlan, end=None, **kwargs):
    ''' start is Epoch '''

    kwargs['end'] = format_date(end)

    dendrite.post('mac/{mac}/authorization/vlan/{vlan}/current/end'.format(mac=mac, vlan=vlan), kwargs)
