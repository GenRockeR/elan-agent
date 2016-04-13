from django.conf.urls import patterns, url
from captive_portal import views

urlpatterns = patterns('',
    url(r'^login$', views.login, name='login' ),
    url(r'^logout$', views.logout, name='logout' ),
    url(r'^status$', views.status, name='status' ),
    url(r'^guest-access$', views.guest_access, name='guest-access' ),

    url(r'^admin-login$', views.admin_login, name='admin-login' ),
    url(r'^admin-logout$', views.admin_logout, name='admin-logout' ),
    url(r'^dashboard$', views.dashboard, name='dashboard' ),
    url(r'^conf/ipv4$', views.admin_ipv4_conf, name='admin-ipv4' ),
    url(r'^conf/ipv6$', views.admin_ipv6_conf, name='admin-ipv6' ),

    url(r'', views.redirect2status ),
)
