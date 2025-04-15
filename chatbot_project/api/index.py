from wsgiref.handlers import SimpleHandler
from chatbot_project.wsgi import application
from io import BytesIO

def handler(request, response):
    env = {
        'REQUEST_METHOD': request.method,
        'PATH_INFO': request.path,
        'QUERY_STRING': request.query,
        'CONTENT_TYPE': request.headers.get('content-type', ''),
        'CONTENT_LENGTH': str(len(request.body or b'')),
        'wsgi.input': BytesIO(request.body or b''),
        'wsgi.errors': BytesIO(),
        'wsgi.version': (1, 0),
        'wsgi.run_once': False,
        'wsgi.url_scheme': 'http',
        'wsgi.multithread': False,
        'wsgi.multiprocess': False,
        'SERVER_NAME': 'localhost',
        'SERVER_PORT': '8000',
    }

    result = []

    def start_response(status, headers):
        response.status_code = int(status.split()[0])
        for key, val in headers:
            response.headers[key] = val
        return result.append

    handler = SimpleHandler(env['wsgi.input'], response.body, env['wsgi.errors'], env)
    handler.request_handler = application
    handler.run(application)

    response.body = b''.join(result)
