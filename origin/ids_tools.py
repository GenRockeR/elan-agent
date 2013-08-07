import re
import datetime, pytz, time
from string import Template

def alert_from_fastlog(line):
    # Match something like: 
    #  08/06/2013-08:02:10.099424  [**] [1:2404001:3151] ET CNC Shadowserver Reported CnC Server IP (group 2) [**] [Classification: A Network Trojan was Detected] [Priority: 1] {TCP} 192.168.0.57:35180 -> 109.235.253.55:81
    #  08/06/2013-19:31:24.339783  [**] [1:6666666:3151] ON Testing [**] [Classification: A Network Trojan was Detected] [Priority: 1] {IPv6-ICMP} 2a01:0e34:ee2e:e2a0:4461:a271:5a9b:6267:128 -> 2a00:1450:400c:0c03:0000:0000:0000:0063:0
    m = re.match(r'(?P<timestamp>\d\d/\d\d/\d\d\d\d-\d\d:\d\d:\d\d\.\d+) *\[.*?\] *\[.*?\] *(?P<msg>.+) +\[.*?\] *\[Classification: *(?P<classification>.*?)\] *\[Priority: *(?P<priority>.*?)\] *{(?P<protocol>.*?)} *(?P<src_ip>(?:(?:\d{1,3}\.){3}\d{1,3}|(?:[0-9a-zA-z]{4}:){7}[0-9a-zA-z]{4})):(?P<src_port>\d+) *-> *(?P<dst_ip>(?:(?:\d{1,3}\.){3}\d{1,3}|(?:[0-9a-zA-z]{4}:){7}[0-9a-zA-z]{4})):(?P<dst_port>\d+)', line)
    if m:
        alert = m.groupdict()
        offset = datetime.datetime.now(pytz.timezone(time.tzname[0])).strftime('%z')
        timestamp = alert['timestamp']
        m = re.match(r'(?P<month>\d\d)/(?P<day>\d\d)/(?P<year>\d\d\d\d)-(?P<thetime>\d\d:\d\d:\d\d\.\d+)', timestamp)
        alert['timestamp'] = Template('${year}-${month}-${day}T${thetime}' + offset).substitute(m.groupdict())
        return alert
