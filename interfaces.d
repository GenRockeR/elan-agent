
auto eth1
iface eth1 inet manual
iface eth1 inet6 manual


auto br0
% if ipv4['type'] == 'dhcp':
iface br0 inet dhcp
% elif ipv4['type'] == 'static':
iface br0 inet static
  address ${ipv4['address']}/${ipv4['mask']}
  gateway ${ipv4['gateway']}
% else:
iface br0 inet manual
% endif
  bridge_ports eth0

  % if ipv6['type'] == 'autoconf':
  up sysctl net.ipv6.conf.br0.disable_ipv6=0
  up sysctl net.ipv6.conf.br0.autoconf=1
  % elif ipv6['type'] == 'static':
  up sysctl net.ipv6.conf.br0.disable_ipv6=0
  up sysctl net.ipv6.conf.br0.autoconf=0
  % else:
  up sysctl net.ipv6.conf.br0.disable_ipv6=1
  % endif
  
  % if ipv4['dns']:
    % for ip in ipv4['dns']:
  dns-nameservers ${ip}
    % endfor
  % endif
 

% if ipv6['type'] == 'static':
iface br0 inet6 static
  address ${ipv6['address']}/${ipv6['mask']}
  gateway ${ipv6['gateway']}
% else:
iface br0 inet6 auto
% endif
  % if ipv6['dns']:
    % for ip in ipv6['dns']:
  dns-nameservers ${ip}
    % endfor
  % endif
  