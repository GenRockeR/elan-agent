import trackerd

def test_shouldLogPacket_broadcast_OK():
    assert( trackerd.shouldLogPacket({'wan_mac': 'ff:ff:ff:ff:ff:01', 'lan_mac': '01:02:03:04:05:06'}) == True )

def test_shouldLogPacket_broadcast():
    assert( trackerd.shouldLogPacket({'wan_mac': 'ff:ff:ff:ff:ff:ff', 'lan_mac': '01:02:03:04:05:06'}) == False )
    assert( trackerd.shouldLogPacket({'lan_mac': 'ff:ff:ff:ff:ff:ff', 'wan_mac': '01:02:03:04:05:07'}) == False )
    assert( trackerd.shouldLogPacket({'wan_mac': 'ff:ff:ff:ff:ff:ff', 'lan_mac': 'ff:ff:ff:ff:ff:ff'}) == False )

def test_shouldLogPacket_IANA():
    assert( trackerd.shouldLogPacket({'wan_mac': '00:00:5e:05:06:07', 'lan_mac': '01:02:03:04:05:06'}) == False )
    assert( trackerd.shouldLogPacket({'lan_mac': '00:00:5e:05:06:07', 'wan_mac': '01:02:03:04:05:07'}) == False )
    assert( trackerd.shouldLogPacket({'wan_mac': '00:00:5e:05:06:07', 'lan_mac': '00:00:5e:05:06:07'}) == False )
    assert( trackerd.shouldLogPacket({'wan_mac': '01:00:5e:05:06:07', 'lan_mac': '01:02:03:04:05:06'}) == False )
    assert( trackerd.shouldLogPacket({'lan_mac': '01:00:5e:05:06:07', 'wan_mac': '01:02:03:04:05:07'}) == False )
    assert( trackerd.shouldLogPacket({'wan_mac': '01:00:5e:05:06:07', 'lan_mac': '01:00:5e:05:06:07'}) == False )
    assert( trackerd.shouldLogPacket({'wan_mac': '02:00:5e:05:06:07', 'lan_mac': '01:02:03:04:05:06'}) == False )
    assert( trackerd.shouldLogPacket({'lan_mac': '02:00:5e:05:06:07', 'wan_mac': '01:02:03:04:05:07'}) == False )
    assert( trackerd.shouldLogPacket({'wan_mac': '02:00:5e:05:06:07', 'lan_mac': '02:00:5e:05:06:07'}) == False )
