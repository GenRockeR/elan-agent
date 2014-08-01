import netifaces, subprocess, re

def get_ip6_address(if_name):
    ''' returns first ip6 address found as string, None if not found'''
    try:
        return netifaces.ifaddresses(if_name)[netifaces.AF_INET6][0]['addr']
    except (KeyError, IndexError):
        return None
    
def get_ip4_address(if_name):
    ''' returns first ip4 address found as string, None if not found'''
    try:
        return netifaces.ifaddresses(if_name)[netifaces.AF_INET][0]['addr']
    except (KeyError, IndexError):
        return None
    
def get_ether_address(if_name):
    try:
        return netifaces.ifaddresses(if_name)[netifaces.AF_PACKET][0]['addr']
    except (KeyError, IndexError):
        return None

def ip4_to_mac(ip):
    p = subprocess.Popen(['ip','neigh', 'show', ip], stdout=subprocess.PIPE)
    output = str(p.communicate()[0])
    m = re.search(r'[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]', output)
    if m:
        return str(m.group(0))

