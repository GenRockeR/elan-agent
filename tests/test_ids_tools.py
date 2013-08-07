from origin.ids_tools import alert_from_fastlog

def test_alert_from_fast():
    # unparsable alert return None 
    alert = alert_from_fastlog('')
    assert(  alert == None )
    alert = alert_from_fastlog('08/06/2013-08:02:10.099424  [**] [1:2404001:3151] ET CNC Shadowserver Reported CnC Server IP (group 2) [**] [Classification: A Network Trojan was Detected] [Priority: 1] {TCP} 192.168.0.57:35180 -> 109.235.253.55:81')
    assert(  alert == {
                'timestamp': '2013-08-06T08:02:10.099424+0200',
                'priority': '1',
                'classification': 'A Network Trojan was Detected',
                'msg' : 'ET CNC Shadowserver Reported CnC Server IP (group 2)',
                'protocol': 'TCP',
                'src_ip': '192.168.0.57',
                'src_port': '35180',
                'dst_ip': '109.235.253.55',
                'dst_port': '81'
            }
    )
    alert = alert_from_fastlog('08/07/2013-18:44:10.351713  [**] [1:6666666:3151] ON Testing [**] [Classification: A Network Trojan was Detected] [Priority: 1] {UDP} 2a01:0e34:ee2e:e2a0:fd57:58fd:fd31:90c6:123 -> 2a01:0e0b:2070:0000:0000:0000:0000:0001:123')
    assert(  alert == {
                'timestamp': '2013-08-07T18:44:10.351713+0200',
                'priority': '1',
                'classification': 'A Network Trojan was Detected',
                'msg' : 'ON Testing',
                'protocol': 'UDP',
                'src_ip': '2a01:0e34:ee2e:e2a0:fd57:58fd:fd31:90c6',
                'src_port': '123',
                'dst_ip': '2a01:0e0b:2070:0000:0000:0000:0000:0001',
                'dst_port': '123'
            }
    )
