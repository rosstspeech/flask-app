

from dotenv import load_dotenv
import os

from aiohttp_wsgi import WSGIHandler
from httpx import HTTPStatusError
from flask_restful import Api
from aiohttp import web
from flask import Flask
import aiohttp_jinja2
import speechmatics
import asyncio
import jinja2
from threading import Thread
import queue

# ===============================================================================
#  Speechmatics Configuration
# ===============================================================================
API_KEY = "" # Speechmatics API Key
LANGUAGE = "en"
CONNECTION_URL = f"wss://eu2.rt.speechmatics.com/v2/{LANGUAGE}"

class QueueIO:
    def __init__(self):
        self._queue = queue.Queue()
        self._closed = False

    def close(self):
        self._closed = True

    def write(self, bytes_buf):
        if not self._closed:
            self._queue.put(bytes_buf, block=False)

    def read(self, _):
        if not self._closed:
            return self._queue.get()
        return None

class AudioProcessor:
    def __init__(self):
        self.wave_data = bytearray()
        self.read_offset = 0
    
    async def read(self, chunk_size):
        print("READ")
        while self.read_offset + chunk_size > len(self.wave_data):
            await asyncio.sleep(0.001)
        new_offset = self.read_offset + chunk_size
        data = self.wave_data[self.read_offset:new_offset]
        self.read_offset = new_offset
        # print(">>>>>>>>>>>>>", data)
        return data
    
    def write_audio(self, data):
        print("WRITE")
        self.wave_data.extend(data)
        return
    
# ===============================================================================
# import API Endpoints
# ===============================================================================
from hello.hello import hello

# ===============================================================================
#  Flask App Configuration
# ===============================================================================
load_dotenv()
app = Flask(__name__)
app.secret_key = 'arbex'
routes = web.RouteTableDef()

# ===============================================================================
#  Flask Socket Endpoints
# =============================================================================== 
async def socket(request):

    audio_processor = AudioProcessor()
    start_speechmatics_transcription(audio_processor)

    ws = web.WebSocketResponse()
    await ws.prepare(request) 

    while not ws.closed:
        data = await ws.receive_bytes()
        # Speechmatics
        audio_processor.write_audio(data)

# ===============================================================================
#  Flask App Functions
# ===============================================================================     
async def transcription_page(request: web.Request) -> web.Response:
    context={
        "heading": "Transcription Page"
    }
    response = aiohttp_jinja2.render_template("transcription_page.html", request, context=context)
    return response


# # Define an event handler to print the full transcript
def print_transcript(msg):
    print(f"[  FINAL] {msg['metadata']['transcript']}")
def print_partial(msg):
    print(f"[  PARTIAL] {msg['metadata']['transcript']}")
def print_start(msg):
    print(f"[ START] {msg}")
def print_info(msg):
    print(f"[ INFO] {msg}")
def print_error(msg):
    print(f"[ ERROR] {msg}")
def print_warning(msg):
    print(f"[ WARNING] {msg}")
def print_audio_added(msg):
    print(f"[ AUDIO_ADDED] {msg}")

# Removed async from function
def start_speechmatics_transcription(stream):
    print("speechmatics")
    # Define connection parameters
    conn = speechmatics.models.ConnectionSettings(
        url=CONNECTION_URL,
        auth_token=API_KEY,
        generate_temp_token=True,
    )

    # Create a transcription client
    ws = speechmatics.client.WebsocketClient(conn)
    # Register the event handler for full transcript
    ws.add_event_handler(
        event_name=speechmatics.models.ServerMessageType.AddTranscript,
        event_handler=print_transcript,
    )
    
    ws.add_event_handler(
        event_name=speechmatics.models.ServerMessageType.AddPartialTranscript,
        event_handler=print_partial,
    )

    ws.add_event_handler(
        event_name=speechmatics.models.ServerMessageType.RecognitionStarted,
        event_handler=print_start,
    )

    ws.add_event_handler(
        event_name=speechmatics.models.ServerMessageType.Info,
        event_handler=print_info
    )

    ws.add_event_handler(
        event_name=speechmatics.models.ServerMessageType.Error,
        event_handler=print_error
    )

    ws.add_event_handler(
        event_name=speechmatics.models.ServerMessageType.Warning,
        event_handler=print_warning
    )

    # ws.add_event_handler(
    #     event_name=speechmatics.models.ServerMessageType.AudioAdded,
    #     event_handler=print_audio_added
    # )

    # Define transcription parameters
    # Full list of parameters described here: https://speechmatics.github.io/speechmatics-python/models
    conf = speechmatics.models.TranscriptionConfig(
        language=LANGUAGE,
        enable_partials=True,
        max_delay=2,
    )
    settings = speechmatics.models.AudioSettings()
	# AudioRecorder sends compressed audio - removing the following defaults the type to file
    # settings.encoding = "pcm_f32le"
    smx_thread = Thread(
        target=ws.run_synchronously, args=[stream, conf, settings],
    )
    smx_thread.start()


# ===============================================================================
# Flask register app and start
# ===============================================================================
api = Api(app, catch_all_404s=True)

def create_app():
    aio_app = web.Application()
    aiohttp_jinja2.setup(
        aio_app, loader=jinja2.FileSystemLoader(os.path.join(os.getcwd(), "templates"))
    )
    wsgi = WSGIHandler(app)
    aio_app.router.add_route('*', '/{path_info: *}', wsgi.handle_request)
    aio_app.router.add_route('GET', '/listen', socket)
    aio_app.router.add_routes([
        web.get('/api/hello', hello),
        web.get('/transcription_page', transcription_page),
    ])
    return aio_app

if __name__ == "__main__":
    #----------------------------------------------------------------
    # Simple App
    aio_app = create_app()
    app_port = 5555
    web.run_app(aio_app, port=app_port)
   