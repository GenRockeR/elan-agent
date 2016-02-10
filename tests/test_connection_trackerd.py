connection_trackerd = __import__("connection-trackerd")

def test_ignorePacket_broadcast_OK():
    assert( connection_trackerd.ignorePacket({'wan_mac': 'ff:ff:ff:ff:ff:01', 'lan_mac': '01:02:03:04:05:06'}) == False )

def test_ignorePacket_broadcast():
    assert( connection_trackerd.ignorePacket({'wan_mac': 'ff:ff:ff:ff:ff:ff', 'lan_mac': '01:02:03:04:05:06'}) == True )
    assert( connection_trackerd.ignorePacket({'lan_mac': 'ff:ff:ff:ff:ff:ff', 'wan_mac': '01:02:03:04:05:07'}) == True )
    assert( connection_trackerd.ignorePacket({'wan_mac': 'ff:ff:ff:ff:ff:ff', 'lan_mac': 'ff:ff:ff:ff:ff:ff'}) == True )

def test_ignorePacket_IANA():
    assert( connection_trackerd.ignorePacket({'wan_mac': '00:00:5e:05:06:07', 'lan_mac': '01:02:03:04:05:06'}) == True )
    assert( connection_trackerd.ignorePacket({'lan_mac': '00:00:5e:05:06:07', 'wan_mac': '01:02:03:04:05:07'}) == True )
    assert( connection_trackerd.ignorePacket({'wan_mac': '00:00:5e:05:06:07', 'lan_mac': '00:00:5e:05:06:07'}) == True )
    assert( connection_trackerd.ignorePacket({'wan_mac': '01:00:5e:05:06:07', 'lan_mac': '01:02:03:04:05:06'}) == True )
    assert( connection_trackerd.ignorePacket({'lan_mac': '01:00:5e:05:06:07', 'wan_mac': '01:02:03:04:05:07'}) == True )
    assert( connection_trackerd.ignorePacket({'wan_mac': '01:00:5e:05:06:07', 'lan_mac': '01:00:5e:05:06:07'}) == True )
    assert( connection_trackerd.ignorePacket({'wan_mac': '02:00:5e:05:06:07', 'lan_mac': '01:02:03:04:05:06'}) == True )
    assert( connection_trackerd.ignorePacket({'lan_mac': '02:00:5e:05:06:07', 'wan_mac': '01:02:03:04:05:07'}) == True )
    assert( connection_trackerd.ignorePacket({'wan_mac': '02:00:5e:05:06:07', 'lan_mac': '02:00:5e:05:06:07'}) == True )
    assert( connection_trackerd.ignorePacket({'wan_mac': '33:33:ff:ff:ff:01', 'lan_mac': '01:02:03:04:05:06'}) == True )
    assert( connection_trackerd.ignorePacket({'wan_mac': 'ff:ff:ff:ff:ff:01', 'lan_mac': '33:33:03:04:05:06'}) == True )
