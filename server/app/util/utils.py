import json

from numpy import float32, integer


class Float32JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, float32):
            return float(obj)
        elif isinstance(obj, integer):
            return int(obj)
        return json.JSONEncoder.default(self, obj)


class MimeTypeError(Exception):

    def __init__(self, message):
        self.message = message


class FilterError(Exception):

    def __init__(self, message):
        self.message = message


class InteractiveError(Exception):

    def __init__(self, message):
        self.message = message


def get_mime_type(default="application/json", acceptable_types=["application/json", "text/csv"], query_param=None,
                  header=None):
    mime_type = default
    if query_param:
        if query_param in acceptable_types:
            mime_type = query_param
        else:
            raise MimeTypeError(f"Unsupported mime type {query_param} specified in query parameter 'accept-type'")
    elif len(header):
        mime_type = header.best_match(acceptable_types)
        if not mime_type:
            raise MimeTypeError(f"Unsupported mime type(s) {header} in HTTP Accept header")
    return mime_type
