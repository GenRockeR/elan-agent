#!/usr/bin/env perl

use strict;
use warnings;

use Switch;
use Origin::SNMP;
use Encode;
use Redis;
use JSON;
use File::Find;
use Origin::NetdiscoDevice;
use IO::Select;
use IO::Socket::UNIX;

use constant SNMP_POLL_REQUEST_SOCK => '/tmp/snmp-poll-request.sock';
use constant SNMP_PARSE_TRAP_SOCK => '/tmp/snmp-trap-parse.sock';
use constant SNMP_NASPORT_TO_IFINDEX_SOCK => '/tmp/snmp-nasport2ifindex.sock';

use constant SNMP_READ_PARAMS_CACHE_PATH => 'snmp:read:params'; # Per IP
use constant SNMP_DEFAULT_CREDENTIALS_PATH => 'snmp:default_credentials';
use constant MIB_BASE_PATH => '/elan-agent/nac/mibs';


$SIG{CHLD} = 'IGNORE'; # Avoid Zombies...

my $redis;

my $json = JSON->new();
$json->utf8()->allow_nonref();

# Need all the directories.
my $mib_paths = [];
find ({
          follow_fast => 1, 
          wanted => sub { return unless -d; push(@$mib_paths, $File::Find::name); }
      },
      MIB_BASE_PATH );


# TODO: Find a better way to load all the switches
my $switch_classes = [ 'pf::Switch', 'pf::Switch::Accton', 'pf::Switch::Accton::ES3526XA', 'pf::Switch::Accton::ES3528M', 'pf::Switch::AeroHIVE', 'pf::Switch::AeroHIVE::AP', 'pf::Switch::AlliedTelesis', 'pf::Switch::AlliedTelesis::AT8000GS', 'pf::Switch::Amer', 'pf::Switch::Amer::SS2R24i', 'pf::Switch::Aruba', 'pf::Switch::Aruba::Controller_200', 'pf::Switch::ArubaSwitch', 'pf::Switch::Avaya', 'pf::Switch::Avaya::ERS2500', 'pf::Switch::Avaya::ERS4000', 'pf::Switch::Avaya::ERS5000', 'pf::Switch::Avaya::ERS5000_6x', 'pf::Switch::Avaya::WC', 'pf::Switch::Belair', 'pf::Switch::Brocade', 'pf::Switch::Brocade::RFS', 'pf::Switch::Cisco', 'pf::Switch::Cisco::Aironet', 'pf::Switch::Cisco::Aironet_1130', 'pf::Switch::Cisco::Aironet_1242', 'pf::Switch::Cisco::Aironet_1250', 'pf::Switch::Cisco::Aironet_WDS', 'pf::Switch::Cisco::Catalyst_2900XL', 'pf::Switch::Cisco::Catalyst_2950', 'pf::Switch::Cisco::Catalyst_2960', 'pf::Switch::Cisco::Catalyst_2960G', 'pf::Switch::Cisco::Catalyst_2960_http', 'pf::Switch::Cisco::Catalyst_2970', 'pf::Switch::Cisco::Catalyst_3500XL', 'pf::Switch::Cisco::Catalyst_3550', 'pf::Switch::Cisco::Catalyst_3560', 'pf::Switch::Cisco::Catalyst_3560G', 'pf::Switch::Cisco::Catalyst_3750', 'pf::Switch::Cisco::Catalyst_3750G', 'pf::Switch::Cisco::Catalyst_4500', 'pf::Switch::Cisco::Catalyst_6500', 'pf::Switch::Cisco::ISR_1800', 'pf::Switch::Cisco::WiSM', 'pf::Switch::Cisco::WiSM2', 'pf::Switch::Cisco::WLC', 'pf::Switch::Cisco::WLC_2100', 'pf::Switch::Cisco::WLC_2106', 'pf::Switch::Cisco::WLC_2500', 'pf::Switch::Cisco::WLC_4400', 'pf::Switch::Cisco::WLC_5500', 'pf::Switch::Cisco::WLC_http', 'pf::Switch::constants', 'pf::Switch::Dell', 'pf::Switch::Dell::Force10', 'pf::Switch::Dell::PowerConnect3424', 'pf::Switch::Dlink', 'pf::Switch::Dlink::DES_3526', 'pf::Switch::Dlink::DES_3550', 'pf::Switch::Dlink::DGS_3100', 'pf::Switch::Dlink::DGS_3200', 'pf::Switch::Dlink::DWL', 'pf::Switch::Dlink::DWS_3026', 'pf::Switch::EdgeCore', 'pf::Switch::Enterasys', 'pf::Switch::Enterasys::D2', 'pf::Switch::Enterasys::Matrix_N3', 'pf::Switch::Enterasys::SecureStack_C2', 'pf::Switch::Enterasys::SecureStack_C3', 'pf::Switch::Enterasys::V2110', 'pf::Switch::Extreme', 'pf::Switch::Extreme::Summit', 'pf::Switch::Extreme::Summit_X250e', 'pf::Switch::Extricom', 'pf::Switch::Extricom::EXSW', 'pf::SwitchFactory', 'pf::Switch::Foundry', 'pf::Switch::Foundry::FastIron_4802', 'pf::Switch::Foundry::MC', 'pf::Switch::H3C', 'pf::Switch::H3C::S5120', 'pf::Switch::Hostapd', 'pf::Switch::HP', 'pf::Switch::HP::Controller_MSM710', 'pf::Switch::HP::E4800G', 'pf::Switch::HP::E5500G', 'pf::Switch::HP::MSM', 'pf::Switch::HP::Procurve_2500', 'pf::Switch::HP::Procurve_2600', 'pf::Switch::HP::Procurve_3400cl', 'pf::Switch::HP::Procurve_4100', 'pf::Switch::HP::Procurve_5300', 'pf::Switch::HP::Procurve_5400', 'pf::Switch::Huawei', 'pf::Switch::Huawei::S5710', 'pf::Switch::Intel', 'pf::Switch::Intel::Express_460', 'pf::Switch::Intel::Express_530', 'pf::Switch::Juniper', 'pf::Switch::Juniper::EX', 'pf::Switch::Juniper::EX2200', 'pf::Switch::LG', 'pf::Switch::LG::ES4500G', 'pf::Switch::Linksys', 'pf::Switch::Linksys::SRW224G4', 'pf::Switch::Meru', 'pf::Switch::Meru::MC', 'pf::Switch::MockedSwitch', 'pf::Switch::Motorola', 'pf::Switch::Motorola::RFS', 'pf::Switch::Netgear', 'pf::Switch::Netgear::FSM726v1', 'pf::Switch::Netgear::GS110', 'pf::Switch::Netgear::MSeries', 'pf::Switch::Nortel', 'pf::Switch::Nortel::BayStack4550', 'pf::Switch::Nortel::BayStack470', 'pf::Switch::Nortel::BayStack5500', 'pf::Switch::Nortel::BayStack5500_6x', 'pf::Switch::Nortel::BPS2000', 'pf::Switch::Nortel::ERS2500', 'pf::Switch::Nortel::ERS4000', 'pf::Switch::Nortel::ERS5000', 'pf::Switch::Nortel::ERS5000_6x', 'pf::Switch::Nortel::ES325', 'pf::Switch::PacketFence', 'pf::Switch::Ruckus', 'pf::Switch::SMC', 'pf::Switch::SMC::TS6128L2', 'pf::Switch::SMC::TS6224M', 'pf::Switch::SMC::TS8800M', 'pf::Switch::ThreeCom', 'pf::Switch::ThreeCom::E4800G', 'pf::Switch::ThreeCom::E5500G', 'pf::Switch::ThreeCom::NJ220', 'pf::Switch::ThreeCom::SS4200', 'pf::Switch::ThreeCom::SS4500', 'pf::Switch::ThreeCom::Switch_4200G', 'pf::Switch::Trapeze', 'pf::Switch::WirelessModuleTemplate', 'pf::Switch::Xirrus' ];
for my $sc (@$switch_classes) {
  eval("use $sc");
  print $@;
}

sub snmp_poll {
  my $ip = shift;
  
  # check if params are cached
  my $json_connection_params = $redis->hget(SNMP_READ_PARAMS_CACHE_PATH, $json->encode($ip));
  if($json_connection_params) {
    my $data = _snmp_poll( $ip, $json->decode($json_connection_params) );
    # check if we got an answer
    if($data) {
      return $data;
    }
    # Cached creds are not valid: delete them
    $redis->hdel(SNMP_READ_PARAMS_CACHE_PATH, $json->encode($ip));
  }

  
  # Retrieve configuration and build list of params...
  my $json_default_creds = $redis->get(SNMP_DEFAULT_CREDENTIALS_PATH);
  my $default_creds_list = [{ community => "public" }]; # always try public
  if( $json_default_creds ) {
    push( @$default_creds_list, @{$json->decode($json_default_creds)} );
  }
  foreach my $version ( reverse (1 .. 3) ) {

    foreach my $default_creds (@$default_creds_list) {
      my $credentials = {};
      if($version eq 3){
        $credentials->{user} = $default_creds->{community};
        if($default_creds->{auth_key}){
          $credentials->{auth} = {pass => $default_creds->{auth_key}, proto => $default_creds->{auth_proto}};
          if($default_creds->{priv_key}){
            $credentials->{priv} = {pass => $default_creds->{priv_key}, proto => $default_creds->{priv_proto}};
          }
        }
      } else {
        next if $default_creds->{auth_key}; # cred was for snmp v3
        $credentials->{community} = $default_creds->{community};
      }
      
      # Try conf
      my $connection_params = { version => $version, class => 'SNMP::Info', credentials => $credentials };
      # fork to try conf because if a attempt fails and we retry by just modifying  the AuthProto, it fails the same when it should succeed. seems like SNMP::Session caches the result some way...
      my $pid = open(CHILD, "-|");
      if($pid){
          # Parent
          my $result = <CHILD>;
          close CHILD;
          if($result) {
              # Store connection params for that swicth for next poll
              my $data = $json->decode($result);
              $connection_params->{class} = delete($data->{snmp_info_class});
              $redis->hset(SNMP_READ_PARAMS_CACHE_PATH, $json->encode($ip), $json->encode($connection_params));
            
              return $data;
          }
      }
      else {
          # Child
          my $data = _snmp_poll($ip, $connection_params);
          if($data) {
            print($json->encode($data))
          }
          exit 0;
      }
    }
  }
  return
}

sub _snmp_poll {
  my ($device_ip, $params) = @_;
  # params is a hash containing class, version and credentials (itself a hash containing community for v1 and 2 or username/pass for v3)
  
  my %snmp_args = (
    AutoSpecify => 0,
    DestHost => $device_ip,
    Retries => 2,
    Timeout => 1000000,
    NonIncreasing => 0,
    BulkWalk => 1,
    BulkRepeaters => 20,
    MibDirs => $mib_paths,
    IgnoreNetSNMPConf => 1,
    Debug => 0,
    DebugSNMP => 0,
    Version => $params->{version},
  );
  
  my $device = new Origin::NetdiscoDevice($device_ip);
  
  my $s = Origin::SNMP::try_connect($device, $params->{class}, $params->{credentials}, 'read', \%snmp_args, 1);
  
  return unless $s;
  
  my $data = { ip => $device_ip, ports => [], snmp_info_class => ref($s) }; # requested IP is part of the answer for tracking in in the answer_path...
  $data->{mac}              = $s->mac;
  $data->{snmp_name}        = $s->name || "";
  $data->{snmp_description} = $s->description || "";
  $data->{location}      = $s->location || "";
  $data->{layers}        = $s->layers || "";
  $data->{nb_ports}      = $s->ports || "";
  $data->{vendor}        = $s->vendor || "";
  $data->{os}            = $s->os || "";
  $data->{os_version}    = $s->os_ver || "";
  $data->{ip_index}      = $s->ip_index || "";
  $data->{ip_netmask}    = $s->ip_netmask || "";
  $data->{model}         = Encode::decode('UTF-8', $s->model || "");
  $data->{serial}        = Encode::decode('UTF-8', $s->serial || "");

  $data->{fw_mac}        = $s->fw_mac || "";
  $data->{fw_port}       = $s->fw_port || "";
  $data->{fw_status}     = $s->fw_status || "";
  $data->{qb_fdb_index}  = $s->qb_fdb_index || "";
  $data->{v_index}       = $s->v_index || "";
  $data->{bp_index}      = $s->bp_index || "";
  $data->{bp_port}       = $s->bp_port || "";
  $data->{qb_i_vlan_t}   = $s->qb_i_vlan_t || "";
  $data->{qb_fw_mac}     = $s->qb_fw_mac || "";
  $data->{qb_fw_port}    = $s->qb_fw_port || "";
  $data->{qb_fw_vlan}    = $s->qb_fw_vlan || "";
  $data->{qb_fw_status}  = $s->qb_fw_status || "";
  $data->{i_vlan}        = $s->i_vlan || "";
  $data->{i_untagged}    = $s->i_untagged || "";
  $data->{i_vlan_membership}          = $s->i_vlan_membership || "";
  $data->{i_vlan_membership_untagged} = $s->i_vlan_membership_untagged || "";

  my %portByIndex;
  foreach my $index (keys %{$s->interfaces || {}}) {
    next if $s->if_ignore->{$index};
    my $port = {
            index       => $index, 
            interface   => $s->interfaces->{$index},
            name        => $s->i_name->{$index},
            mac         => $s->i_mac->{$index},
            description => $s->i_description->{$index},
    };
    push( @{$data->{ports}}, $port);
    $portByIndex{$index} = $port;
  }
  
  # Find Mac of IP
  foreach my $ip (keys %{$s->ip_index}) {
    if( $ip eq $device_ip ){ 
      if( $portByIndex{$s->ip_index->{$ip}} && $portByIndex{$s->ip_index->{$ip}}->{mac} ){
        $data->{mac} = $portByIndex{$s->ip_index->{$ip}}->{mac};
      }
      last;
    }
  }
  
  # Treat SSIDs
  foreach my $key (keys %{$s->i_ssidlist || {}}) {
    my $index = $key;
    $index =~ s/\.\d+$//;
    if($portByIndex{$index}){
      my $port = $portByIndex{$index};
      $port->{ssids} = [] unless $portByIndex{$index}->{ssids};
      my $ssid = {ssid => $s->i_ssidlist->{$key}};
      if($s->i_ssidmac->{$key}) {
        $ssid->{mac} = $s->i_ssidmac->{$key};
      }
      if($s->i_ssidbcast->{$key}) {
        $ssid->{broadcast} = $s->i_ssidbcast->{$key};
      }
      
      push(@{$port->{ssids}}, $ssid);
    }
  }
  
  return $data;  
}

sub pf_connection_params {
  # format to connection params to pf format
  my ($connection) = @_;

  my %pf_connection_params = (SNMPVersion => $connection->{version});
  if($connection->{version} eq '3') {
    $pf_connection_params{SNMPUserNameRead} = $connection->{user};
    if($connection->{credentials}->{auth}){
      $pf_connection_params{SNMPAuthProtocolRead} = $connection->{credentials}->{auth}->{proto};
      $pf_connection_params{SNMPAuthPasswordRead} = $connection->{credentials}->{auth}->{pass};
      
      if($connection->{credentials}->{priv}){
        $pf_connection_params{SNMPPrivProtocolRead} = $connection->{credentials}->{priv}->{proto};
        $pf_connection_params{SNMPPrivPasswordRead} = $connection->{credentials}->{priv}->{pass};
      }
    }
  }
  else {
    $pf_connection_params{SNMPCommunityRead} = $connection->{community};    
  }

  return %pf_connection_params;
}

sub snmp_parse_trap {
  my ($trap_str, $switch_ip, $connection) = @_;  
  
  my $trap_matches = {};
  
  for my $sc (@$switch_classes) {
    next if $sc eq 'pf::Switch::MockedSwitch';
    if(defined(&{$sc.'::parseTrap'})){
      eval {
        my $s = $sc->new(ip => $switch_ip, pf_connection_params($connection), mode => 'production', id => 0 ); # set id to avoid warnings...

        my $trap_info = $s->parseTrap($trap_str);
        if($trap_info->{trapType} ne 'unknown'){
            $trap_matches->{$sc} = $trap_info;
        }
        1;
      } or do {
          # TODO: raise up alert... to Origin Nexus
          print("snmp_parse_trap: $sc: ", $@);
      };
    }
  }
  
  my $count = keys($trap_matches);
  if($count == 0) {
     return {trapType => 'unknown'};
  } elsif($count == 1) {
    return $trap_matches->{(keys(%$trap_matches))[0]};
  } else {
    my $answer = delete $trap_matches->{(keys(%$trap_matches))[0]};
    # check all answer are the same...
    for my $sc (keys %$trap_matches) {
      if( ! %$answer ~~ %{$trap_matches->{$sc}} ) { # keys are not the same
        # TODO: alert ON on duplicate answer for trap
        return { trapType => 'unknown' };
      }
      for my $key (keys %$answer) {
        if($answer->{$key} ne $trap_matches->{$sc}->{$key}) {
          # TODO: alert ON on duplicate answer for trap
          return { trapType => 'unknown' };
        }
      }
    }
    # If we get here, all answers are the same
    return $answer
  }
}


sub NasPortToIfIndex {
    my ($nas_port, $switch_ip, $connection) = @_;
    
    my $indexes = [];
    
    for my $sc (@$switch_classes) {
        next if $sc eq 'pf::Switch::MockedSwitch';
        eval {
            if(defined(&{$sc.'::NasPortToIfIndex'})){
                my $s = $sc->new(ip => $switch_ip, pf_connection_params($connection), mode => 'production', id => 0 ); # set id to avoid warnings...
                my $index = $s->NasPortToIfIndex($nas_port);
                my $found;
                for my $i (@$indexes) {
                    if( $i == $index ) {
                      $found = 1;
                      last;
                    }
                }
                if(! $found) {
                  push @$indexes, $index;
                }
            }
            1;
        } or do {
              # TODO: raise up alert... to Origin Nexus
              print("NasPortToIfIndex: $sc: ", $@);
        };
    }
    
    return $indexes;
}

sub start_unix_server {
  my $path = shift;
  
  unlink $path;
  
  return IO::Socket::UNIX->new(
        Type => SOCK_STREAM(),
        Local => $path,
        Listen => 1,
    );
}

my $poll_server = start_unix_server(SNMP_POLL_REQUEST_SOCK);

my $parse_trap_server = start_unix_server(SNMP_PARSE_TRAP_SOCK);

my $nasport2ifindex_server = start_unix_server(SNMP_NASPORT_TO_IFINDEX_SOCK);
       
my $sel = IO::Select->new($poll_server, $parse_trap_server, $nasport2ifindex_server);


sub handle_connection {
    my $conn = shift;
    my $channel = shift;
    
    $redis = Redis->new(); # open connections after fork

    local $/;
    my $json_request = <$conn>;
  
    my $request = $json->decode($json_request);
  
    my $answer;
    if($channel == $poll_server){
        $answer = snmp_poll($request->{ip});
    }
    elsif($channel == $parse_trap_server ) {
        $answer = snmp_parse_trap($request->{trap_str}, $request->{ip}, $request->{connection});
    }
    elsif($channel == $nasport2ifindex_server) {
        $answer = NasPortToIfIndex($request->{nas_port}, $request->{ip}, $request->{connection});
    }
  
    print $conn $json->encode($answer);
    $conn->close(); 
}


while( my @ready = $sel->can_read() ) {
    foreach my $channel (@ready) {
        my $conn = $channel->accept();
        
        # fork to take care of request...
        my $pid = fork();
        if($pid == 0) {

            handle_connection( $conn, $channel );

            exit 0;
        }
    }
}
