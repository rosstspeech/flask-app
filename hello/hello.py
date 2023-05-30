from aiohttp import web

async def hello(request: web.Request) -> web.Response:
    broken_url = request.path_qs.split("?")
    if len(broken_url)>1:
        return web.json_response({"params":broken_url[1]})
    else:
        return web.json_response({"error":"no-params"})