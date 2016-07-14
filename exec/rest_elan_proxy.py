 #!/bin/env python
 
from aiohttp import web
from origin import freeradius
import json
import asyncio

async def post_auth(request):
    radius_request = json.loads( await request.content.read() )
    
    response = freeradius.post_auth(radius_request)

    return web.json_response(response)

async def accounting(request):
    radius_request = json.loads( await request.content.read() )
    
    response = freeradius.accounting(radius_request)

    return web.json_response(response)
 
app = web.Application()
app.router.add_route('POST', '/freeradius/nac/post-auth',  post_auth)
app.router.add_route('POST', '/freeradius/nac/accounting', accounting)

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
