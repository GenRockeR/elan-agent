from origin.tracker import Tracker

t = Tracker()

def test_extablishedConnections_empty():
    assert( t.establisedConnections == {} )

def test_processPacket():
    t.processPacket(b'RT\x00\xbb\x01\x93\xd4=~\x18\x8aU\x08\x00E\x10\x00d\x1f\xf2@\x00@\x06\x99\x03\xc0\xa8\x00\x06\xc0\xa8\x008\xeb\xb1\x00\x16Z\xaa\x11\xf8%\xf1\xdai\x80\x18\x01K\xb0\xb5\x00\x00\x01\x01\x08\n\x06\xcc\xb68\x00\xe8h\x97\x93\x81\xd6\xbaM}\x8a\xb4{{x\xe0</\x1b\x150\xc3^\xbf\x01\xfb\x94\xab4\x05%\x00\xd8{\x88\x06\x05P\xe9\xae\xa0\xa6\xb5#\x10\x8d}5\x806\x03+',
                     'IN')
    expected_path = [ '192.168.0.56', '192.168.0.6', 22, 60337, 'TCP' ]
    subtree = t.establisedConnections
    for key in expected_path:
        assert( subtree.keys() == [key] )
        subtree = subtree[key]
    assert( subtree['lan_mac'] ==  '52:54:00:bb:01:93' ) 
    assert( subtree['wan_mac'] ==  'd4:3d:7e:18:8a:55' )
    assert( subtree['lan_ip'] == '192.168.0.56' ) 
    assert( subtree['wan_ip'] ==  '192.168.0.6' ) 
    assert( subtree['lan_port'] ==  22 )
    assert( subtree['wan_port'] ==  60337 )
    assert( subtree['type'] ==  'TCP' )
    assert( subtree['direction'] ==  'IN' )
    assert( subtree['size'] ==  114 )

def test_processPacket_samePacket():
    t.processPacket(b'RT\x00\xbb\x01\x93\xd4=~\x18\x8aU\x08\x00E\x10\x00d\x1f\xf2@\x00@\x06\x99\x03\xc0\xa8\x00\x06\xc0\xa8\x008\xeb\xb1\x00\x16Z\xaa\x11\xf8%\xf1\xdai\x80\x18\x01K\xb0\xb5\x00\x00\x01\x01\x08\n\x06\xcc\xb68\x00\xe8h\x97\x93\x81\xd6\xbaM}\x8a\xb4{{x\xe0</\x1b\x150\xc3^\xbf\x01\xfb\x94\xab4\x05%\x00\xd8{\x88\x06\x05P\xe9\xae\xa0\xa6\xb5#\x10\x8d}5\x806\x03+',
                     'IN')
    expected_path = [ '192.168.0.56', '192.168.0.6', 22, 60337, 'TCP' ]
    subtree = t.establisedConnections
    for key in expected_path:
        assert( subtree.keys() == [key] )
        subtree = subtree[key]
    assert( subtree['lan_mac'] ==  '52:54:00:bb:01:93' ) 
    assert( subtree['wan_mac'] ==  'd4:3d:7e:18:8a:55' )
    assert( subtree['lan_ip'] == '192.168.0.56' ) 
    assert( subtree['wan_ip'] ==  '192.168.0.6' ) 
    assert( subtree['lan_port'] ==  22 )
    assert( subtree['wan_port'] ==  60337 )
    assert( subtree['type'] ==  'TCP' )
    assert( subtree['direction'] ==  'IN' )
    assert( subtree['size'] ==  228 ) # size updated

def test_processPacket_packetOtherWay():
    # No new connection
    t.processPacket(b'\xd4=~\x18\x8aURT\x00\xbb\x01\x93\x08\x00E\x00\x004ah@\x00@\x06W\xcd\xc0\xa8\x008\xc0\xa8\x00\x06\x00\x16\xeb\xb1%\xf1\xde\x89Z\xaa\x13\x19\x80\x11\x0c\xeeO\\\x00\x00\x01\x01\x08\n\x00\xec\xf36\x06\xd1?\xe9',
                     'OUT')
    expected_path = [ '192.168.0.56', '192.168.0.6', 22, 60337, 'TCP' ]
    subtree = t.establisedConnections
    for key in expected_path:
        assert( subtree.keys() == [key] )
        subtree = subtree[key]
    assert( subtree['lan_mac'] ==  '52:54:00:bb:01:93' ) 
    assert( subtree['wan_mac'] ==  'd4:3d:7e:18:8a:55' )
    assert( subtree['lan_ip'] == '192.168.0.56' ) 
    assert( subtree['wan_ip'] ==  '192.168.0.6' ) 
    assert( subtree['lan_port'] ==  22 )
    assert( subtree['wan_port'] ==  60337 )
    assert( subtree['type'] ==  'TCP' )
    assert( subtree['direction'] ==  'IN' )
    assert( subtree['size'] ==  294 ) # size updated
    
def test_newConnection_cb_called():
    global called
    called = False
    def cb(pkt):
        global called
        called = True
        assert( pkt['direction'] == 'IN' )
        assert( pkt['lan_mac'] == '52:54:00:bb:01:93' )
        assert( pkt['wan_mac'] == 'd4:3d:7e:18:8a:55' )
        assert( pkt['lan_ip'] == '192.168.0.56' )
        assert( pkt['wan_ip'] == '192.168.0.6' )
        assert( pkt['lan_port'] == 22 )
        assert( pkt['wan_port'] == 60337 )
        assert( pkt['type'] == 'TCP' )

    tr = Tracker(new_connection_cb = cb)
    tr.processPacket(b'RT\x00\xbb\x01\x93\xd4=~\x18\x8aU\x08\x00E\x10\x004 \x03@\x00@\x06\x99"\xc0\xa8\x00\x06\xc0\xa8\x008\xeb\xb1\x00\x16Z\xaa\x12\xb8%\xf1\xde\x89\x80\x10\x01K[c\x00\x00\x01\x01\x08\n\x06\xd1?\xe8\x00\xec\xf35',
                      'IN')
    assert(called == True)
