from django.conf.urls import patterns, url
from captive_portal import views

urlpatterns = patterns('',
    url(r'^login$', views.login, name='login' ),
    url(r'^logout$', views.logout, name='logout' ),
    url(r'^status$', views.status, name='status' ),
    url(r'^guest-access$', views.guest_access, name='guest-access' ),
    url(r'', views.redirect2status ),
)
