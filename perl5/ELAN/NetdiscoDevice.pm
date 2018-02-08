package ELAN::NetdiscoDevice;

sub new {
  my ($class, $ip) = @_;
  my $self = {};
  bless $self, $class;

  $self->{ip} = $ip;

  return $self;
}

sub in_storage {
}

sub update {
  my $self = shift;
  my $args = shift;

  for my $k (keys %$args) {
    $self->{$k} = $args->{$k};
  }
}

sub set_column { update(shift, {@_}); }

sub update_or_create_related {
  my $self = shift;
  my $related = shift;
  my $args = shift;

  $self->{$related} = {} unless $self->{$related};

  for my $k (keys %$args) {
    $self->{$related}->{$k} = $args->{$k};
  }
}

1;
