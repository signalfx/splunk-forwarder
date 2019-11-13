import asyncio
import gzip
import json
import socket
import threading
from contextlib import contextmanager

from sanic import Sanic, response


def bind_tcp_socket(host="127.0.0.1", port=0):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))

    return (sock, sock.getsockname()[1])


# Fake the /v2/datapoint endpoint and just stick all of the metrics in a
# list
# pylint: disable=unused-variable
def _make_fake_ingest(datapoints):
    app = Sanic()

    @app.middleware("request")
    async def compress_request(request):
        if "Content-Encoding" in request.headers:
            if "gzip" in request.headers["Content-Encoding"]:
                request.body = gzip.decompress(request.body)

    @app.post("/v2/datapoint")
    async def handle_datapoints(request):
        is_json = "application/json" in request.headers.get("content-type")

        if not is_json:
            return response.text("Bad Content Type", status=400)

        dp_map = json.loads(request.body)

        out = []
        for typ, dps in dp_map.items():
            for dp in dps:
                dp["type"] = typ
                out.append(dp)

        datapoints.extend(out)

        return response.json("OK")

    return app


# Starts up a new set of backend services that will run on a random port.  The
# returned object will have properties on it for datapoints, events, and dims.
# The fake servers will be stopped once the context manager block is exited.
# pylint: disable=too-many-locals,too-many-statements
@contextmanager
def start(ip_addr="127.0.0.1", ingest_port=0):
    # Data structures are thread-safe due to the GIL
    _datapoints = []

    ingest_app = _make_fake_ingest(_datapoints)

    [ingest_sock, _ingest_port] = bind_tcp_socket(ip_addr, ingest_port)

    loop = asyncio.new_event_loop()

    async def start_server():
        ingest_app.config.REQUEST_TIMEOUT = ingest_app.config.KEEP_ALIVE_TIMEOUT = 1000
        ingest_server = ingest_app.create_server(sock=ingest_sock, access_log=False)

        loop.create_task(ingest_server)

    loop.create_task(start_server())
    threading.Thread(target=loop.run_forever).start()

    class FakeBackend:  # pylint: disable=too-few-public-methods
        ingest_host = ip_addr
        ingest_port = _ingest_port
        ingest_url = f"http://{ingest_host}:{ingest_port}"

        datapoints = _datapoints

        def reset_datapoints(self):
            self.datapoints.clear()

    try:
        yield FakeBackend()
    finally:
        ingest_sock.close()
        loop.stop()
