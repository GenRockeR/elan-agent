#!/usr/bin/env perl

use strict;
use warnings;

use Switch;
use ELAN::SNMP;
use Encode;
use Redis;
use JSON;
use File::Find;
use ELAN::NetdiscoDevice;
use IO::Select;
use IO::Socket::UNIX;

use constant SNMP_POLL_REQUEST_SOCK => '/tmp/snmp-poll-request.sock';
use constant SNMP_PARSE_TRAP_SOCK => '/tmp/snmp-trap-parse.sock';
use constant SNMP_NASPORT_TO_IFINDEX_SOCK => '/tmp/snmp-nasport2ifindex.sock';

use constant SNMP_READ_PARAMS_CACHE_PATH => 'snmp:read:params'; # Per IP
use constant SNMP_DEFAULT_CREDENTIALS_PATH => 'snmp:default_credentials';
use constant MIB_BASE_PATH => '/elan-agent/nac/mibs';
use constant SWITCH_MODULES_PATH => '/elan-agent/lib/perl5';


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
my $switch_classes = ['pf::Switch'];
find ({
          follow_fast => 1, 
          wanted => sub { 
              return if -d;
              return unless $_ =~ /\.pm$/;
              my $module = $File::Find::name;
              my $path = SWITCH_MODULES_PATH.'/';
              $module =~ s#$path##;
              $module =~ s#^/##;
              $module =~ s#/#::#g;
              $module =~ s#.pm$##;
              push(@$switch_classes, $module);
          }
      },
      SWITCH_MODULES_PATH.'/pf/Switch/' );

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
  
  my $device = new ELAN::NetdiscoDevice($device_ip);
  
  my $s = ELAN::SNMP::try_connect($device, $params->{class}, $params->{credentials}, 'read', \%snmp_args, 1);
  
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
  if($connection->{version} && $connection->{version} eq '3') {
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
        my $s = $sc->new({ip => $switch_ip, pf_connection_params($connection), mode => 'production', id => 0}); # set id to avoid warnings...

        my $trap_info = $s->parseTrap($trap_str);
        if($trap_info->{trapType} ne 'unknown'){
            $trap_matches->{$sc} = $trap_info;
        }
        1;
      } or do {
          # TODO: raise up alert... to center
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
                my $s = $sc->new({ip => $switch_ip, pf_connection_params($connection), mode => 'production', id => 0}); # set id to avoid warnings...
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
              # TODO: raise up alert...
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

