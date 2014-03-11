from django.conf.urls import patterns, url
from captive_portal import views
from django.shortcuts import redirect

urlpatterns = patterns('',
    url(r'^login$', views.login, name='login' ),
    url(r'^logout$', views.logout, name='logout' ),
    url(r'^status$', views.status, name='status' ),
    url(r'', views.redirect2status ),
)
