package Origin::SNMP;

use Dancer qw/:syntax :script/;

use SNMP::Info;
use Try::Tiny;
use Module::Load ();
use Path::Class 'dir';


=head1 NAME

Origin::SNMP

=head1 DESCRIPTION

Stolen from App::Netdisco::Util::SNMP and Netdisco::Core::Macsuck

=cut

sub try_connect {
  my ($device, $class, $comm, $mode, $snmp_args, $reclass) = @_;
  my %comm_args = _mk_info_commargs($comm);
  my $debug_comm = ( $comm->{community}
      ? $ENV{SHOW_COMMUNITY} ? $comm->{community} : '<hidden>'
      : "v3user:$comm->{user}" );
  my $info = undef;

  try {
      debug
        sprintf '[%s] try_connect with ver: %s, class: %s, comm: %s',
        $snmp_args->{DestHost}, $snmp_args->{Version}, $class, $debug_comm;
      Module::Load::load $class;

      $info = $class->new(%$snmp_args, %comm_args);
      $info = ($mode eq 'read' ? _try_read($info, $device, $comm)
                               : _try_write($info, $device, $comm));

      # first time a device is discovered, re-instantiate into specific class
      if ($reclass and $info and $info->device_type ne $class) {
          $class = $info->device_type;
          debug
            sprintf '[%s] try_connect with ver: %s, new class: %s, comm: %s',
            $snmp_args->{DestHost}, $snmp_args->{Version}, $class, $debug_comm;

          Module::Load::load $class;
          $info = $class->new(%$snmp_args, %comm_args);
      }
  }
  catch {
      debug $_;
  };

  return $info;
}

sub _try_read {
  my ($info, $device, $comm) = @_;

  return undef unless (
    (not defined $info->error)
    and defined $info->uptime
    and ($info->layers or $info->description)
    and $info->class
  );

  $device->in_storage
    ? $device->update({snmp_ver => $info->snmp_ver})
    : $device->set_column(snmp_ver => $info->snmp_ver);

  if ($comm->{community}) {
      $device->in_storage
        ? $device->update({snmp_comm => $comm->{community}})
        : $device->set_column(snmp_comm => $comm->{community});
  }

  # regardless of device in storage, save the hint
  $device->update_or_create_related('community',
    {snmp_auth_tag => $comm->{tag}}) if $comm->{tag};

  return $info;
}

sub _try_write {
  my ($info, $device, $comm) = @_;

  my $loc = $info->load_location;
  $info->set_location($loc) or return undef;
  return undef unless ($loc eq $info->load_location);

  $device->in_storage
    ? $device->update({snmp_ver => $info->snmp_ver})
    : $device->set_column(snmp_ver => $info->snmp_ver);

  # one of these two cols must be set
  $device->update_or_create_related('community', {
    ($comm->{tag} ? (snmp_auth_tag => $comm->{tag}) : ()),
    ($comm->{community} ? (snmp_comm_rw => $comm->{community}) : ()),
  });

  return $info;
}

sub _mk_info_commargs {
  my $comm = shift;
  return () unless ref {} eq ref $comm and scalar keys %$comm;

  return (Community => $comm->{community})
    if exists $comm->{community};

  my $seclevel =
    (exists $comm->{auth} ?
    (exists $comm->{priv} ? 'authPriv' : 'authNoPriv' )
                          : 'noAuthNoPriv');

  return (
    SecName  => $comm->{user},
    SecLevel => $seclevel,
    ( exists $comm->{auth} ? (
      AuthProto => uc ($comm->{auth}->{proto} || 'MD5'),
      AuthPass  => ($comm->{auth}->{pass} || ''),
      ( exists $comm->{priv} ? (
        PrivProto => uc ($comm->{priv}->{proto} || 'DES'),
        PrivPass  => ($comm->{priv}->{pass} || ''),
      ) : ()),
    ) : ()),
  );
}

sub _build_mibdirs {
  my $home = (setting('mibhome') || dir(($ENV{NETDISCO_HOME} || $ENV{HOME}), 'netdisco-mibs'));
  return map { dir($home, $_)->stringify }
             @{ setting('mibdirs') || _get_mibdirs_content($home) };
}

sub _get_mibdirs_content {
  my $home = shift;
  # warning 'Netdisco SNMP work will be slow - loading ALL MIBs. Consider setting mibdirs.';
  my @list = map {s|$home/||; $_} grep {-d} glob("$home/*");
  return \@list;
}

sub _build_communities {
  my ($device, $mode) = @_;
  $mode ||= 'read';

  my $config = (setting('snmp_auth') || []);
  my $stored_tag = eval { $device->community->snmp_auth_tag };
  my $snmp_comm_rw = eval { $device->community->snmp_comm_rw };
  my @communities = ();

  # try last-known-good read
  push @communities, {read => 1, community => $device->snmp_comm}
    if defined $device->snmp_comm and $mode eq 'read';

  # try last-known-good write
  push @communities, {write => 1, community => $snmp_comm_rw}
    if $snmp_comm_rw and $mode eq 'write';

  # new style snmp config
  foreach my $stanza (@$config) {
      # user tagged
      my $tag = '';
      if (1 == scalar keys %$stanza) {
          $tag = (keys %$stanza)[0];
          $stanza = $stanza->{$tag};

          # corner case: untagged lone community
          if ($tag eq 'community') {
              $tag = $stanza;
              $stanza = {community => $tag};
          }
      }

      # defaults
      $stanza->{tag} ||= $tag;
      $stanza->{read} = 1 if !exists $stanza->{read};
      $stanza->{only} ||= ['any'];
      $stanza->{only} = [$stanza->{only}] if ref '' eq ref $stanza->{only};

      die "error: config: snmpv3 stanza in snmp_auth must have a tag\n"
        if not $stanza->{tag}
           and !exists $stanza->{community};

      if ($stanza->{$mode} and check_acl($device->ip, $stanza->{only})) {
          if ($stored_tag and $stored_tag eq $stanza->{tag}) {
              # last known-good by tag
              unshift @communities, $stanza
          }
          else {
              push @communities, $stanza
          }
      }
  }

  # legacy config (note: read strings tried before write)
  if ($mode eq 'read') {
      push @communities, map {{
        read => 1,
        community => $_,
      }} @{setting('community') || []};
  }
  else {
      push @communities, map {{
        write => 1,
        community => $_,
      }} @{setting('community_rw') || []};
  }

  # but first of all, use external command if configured
  unshift @communities, _get_external_community($device, $mode)
    if setting('get_community') and length setting('get_community');

  return @communities;
}

sub _get_external_community {
  my ($device, $mode) = @_;
  my $cmd = setting('get_community');
  my $ip = $device->ip;
  my $host = $device->dns || $ip;

  if (defined $cmd and length $cmd) {
      # replace variables
      $cmd =~ s/\%HOST\%/$host/egi;
      $cmd =~ s/\%IP\%/$ip/egi;

      my $result = `$cmd`;
      return () unless defined $result and length $result;

      my @lines = split (m/\n/, $result);
      foreach my $line (@lines) {
          if ($line =~ m/^community\s*=\s*(.*)\s*$/i) {
              if (length $1 and $mode eq 'read') {
                  return map {{
                    read => 1,
                    community => $_,
                  }} split(m/\s*,\s*/,$1);
              }
          }
          elsif ($line =~ m/^setCommunity\s*=\s*(.*)\s*$/i) {
              if (length $1 and $mode eq 'write') {
                  return map {{
                    write => 1,
                    community => $_,
                  }} split(m/\s*,\s*/,$1);
              }
          }
      }
  }

  return ();
}

=head2 snmp_comm_reindex( $snmp, $device, $vlan )

Takes an established L<SNMP::Info> instance and makes a fresh connection using
community indexing, with the given C<$vlan> ID. Works for all SNMP versions.

=cut

sub snmp_comm_reindex {
  my ($snmp, $device, $vlan) = @_;
  my $ver = $snmp->snmp_ver;

  if ($ver == 3) {
      my $prefix = '';
      my @comms = _build_communities($device, 'read');
      foreach my $c (@comms) {
          next unless $c->{tag}
            and $c->{tag} eq (eval { $device->community->snmp_auth_tag } || '');
          $prefix = $c->{context_prefix} and last;
      }
      $prefix ||= 'vlan-';

      debug
        sprintf '[%s] reindexing to "%s%s" (ver: %s, class: %s)',
        $device->ip, $prefix, $vlan, $ver, $snmp->class;
      $snmp->update(Context => ($prefix . $vlan));
  }
  else {
      my $comm = $snmp->snmp_comm;

      debug sprintf '[%s] reindexing to vlan %s (ver: %s, class: %s)',
        $device->ip, $vlan, $ver, $snmp->class;
      $snmp->update(Community => $comm . '@' . $vlan);
  }
}


sub _get_vlan_list {
  my ($device, $snmp) = @_;

  return () unless $snmp->cisco_comm_indexing;

  my %vlans;
  my $i_vlan = $snmp->i_vlan || {};
  my $trunks = $snmp->i_vlan_membership || {};
  my $i_type = $snmp->i_type || {};

  # get list of vlans in use
  while (my ($idx, $vlan) = each %$i_vlan) {
      # hack: if vlan id comes as 1.142 instead of 142
      $vlan =~ s/^\d+\.//;
      
      # VLANs are ports interfaces capture VLAN, but don't count as in use
      # Port channels are also 'propVirtual', but capture while checking
      # trunk VLANs below
      if (exists $i_type->{$idx} and $i_type->{$idx} eq 'propVirtual') {
        $vlans{$vlan} ||= 0;
      }
      else {
        ++$vlans{$vlan};
      }
      foreach my $t_vlan (@{$trunks->{$idx}}) {
        ++$vlans{$t_vlan};
      }
  }

  unless (scalar keys %vlans) {
      return ();
  }


  my @ok_vlans = ();
  foreach my $vlan (sort keys %vlans) {
      if ($vlan == 0 or $vlan > 4094) {
          debug sprintf ' [%s] macsuck - invalid VLAN number %s',
            $device->ip, $vlan;
          next;
      }

      push @ok_vlans, $vlan;
  }

  return @ok_vlans;
}


1;
