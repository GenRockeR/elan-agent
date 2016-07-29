 #!/bin/env python
 
from aiohttp import web
from origin import freeradius, neuron
from origin.freeradius.utils import request_as_hash_of_values

import json
import asyncio


dendrite = neuron.Dendrite()

async def call_service(service, data):
    return asyncio.get_event_loop().run_in_executor( dendrite.call, service, data )

async def post_auth(request):
    radius_request = json.loads( await request.content.read() )
    
    response = freeradius.post_auth(radius_request)

    return web.json_response(response)

async def accounting(request):
    radius_request = json.loads( await request.content.read() )
    
    response = freeradius.accounting(radius_request)

    return web.json_response(response)

async def authorize(request):
    radius_request = json.loads( await request.content.read() ) 
    source = request.GET['source']
    provider = request.GET['provider']
    
    response = await call_service(
            'authentication/external/authorize',
            dict( 
                    provider=provider,
                    source=source,
                    **request_as_hash_of_values(radius_request)
            )
    )

    return web.json_response(response)


async def authenticate(request):
    radius_request = json.loads( await request.content.read() )
    source = request.GET['source']
    provider = request.GET['provider']
    
    response = await call_service(
            'authentication/external/authenticate', 
            dict(
                    provider=provider,
                    source=source,
                    **request_as_hash_of_values(radius_request)
            )
    )

    return web.json_response(response)



async def provider_failed(request):
    radius_request = json.loads( await request.content.read() )
    
    response = freeradius.AuthenticationProviderFailed(radius_request)

    return web.json_response(response)

async def provider_failed_in_group(request):
    radius_request = json.loads( await request.content.read() )
    
    response = freeradius.AuthenticationProviderFailedInGroup(radius_request)

    return web.json_response(response)
 
async def group_all_failed(request):
    radius_request = json.loads( await request.content.read() )
    
    response = freeradius.AuthenticationGroupFailed(radius_request)

    return web.json_response(response)



 
app = web.Application()
app.router.add_route('POST', '/nac/post-auth',  post_auth)
app.router.add_route('POST', '/nac/accounting', accounting)
app.router.add_route('POST', '/authentication/authorize', authorize)
app.router.add_route('POST', '/authentication/authenticate', authenticate)
app.router.add_route('POST', '/authentication/provider/failed', provider_failed)
app.router.add_route('POST', '/authentication/provider/failed-in-group', provider_failed_in_group)
app.router.add_route('POST', '/authentication/group/all-failed', group_all_failed)

loop = asyncio.get_event_loop()
handler = app.make_handler()
f = loop.create_server(handler, '127.0.0.1', 8080)
srv = loop.run_until_complete(f)
try:
    loop.run_forever()
except KeyboardInterrupt:
    pass
finally:
    srv.close()
    loop.run_until_complete(srv.wait_closed())
    loop.run_until_complete(handler.finish_connections(1.0))
    loop.run_until_complete(app.finish())
loop.close()
