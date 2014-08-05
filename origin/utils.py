import netifaces, subprocess, re
import ctypes
import ctypes.util

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


def if_nametoindex(name):
    if not isinstance (name, str):
        raise TypeError ('name must be a string.')
    libc = ctypes.CDLL(ctypes.util.find_library('c'))
    ret = libc.if_nametoindex (name)
    if not ret:
        raise RuntimeError("Invalid Name")
    return ret
     
def if_indextoname(index):
    if not isinstance (index, int):
        raise TypeError ('index must be an int.')
    libc = ctypes.CDLL(ctypes.util.find_library('c'))
    libc.if_indextoname.argtypes = [ctypes.c_uint32, ctypes.c_char_p]
    libc.if_indextoname.restype = ctypes.c_char_p
     
    ifname = ctypes.create_string_buffer (32)
    ifname = libc.if_indextoname (index, ifname)
    if not ifname:
        raise RuntimeError ("Inavlid Index")
    return ifname