#!/usr/bin/env python3

import subprocess, os, sys
import yaml, re
from origin.utils import reload_service

file_h = open('/etc/suricata/suricata.yaml', 'r')

conf = yaml.load(file_h)
os.chdir(conf['default-rule-path'])

rules_updated = False

base_url = 'http://127.0.0.1:8000/ids-rules/open/'

for rule in conf['rule-files']:
    output = subprocess.check_output(['zsync', base_url + rule + '.zsync'])
    if re.search('downloading from', output):
        rules_updated = True
    
if rules_updated and len(sys.argv) > 1 and sys.argv[1] != '--no-rule-reload' :
    # send USR2 SIG to suricata to reload the rules
    reload_service('suricata')


