
def request_as_hash_of_values(request):
    class MultiDict(dict):
        'Dictionary that returns only last value when get is used and value is a list'
        def get(self, *args, **kwargs):
            v = super(MultiDict, self).get(*args, **kwargs)
            if isinstance(v, list):
                return v[-1]
            return v
            
    ret = MultiDict()
    
    for key, value in request:
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        if key in ret:
            if isinstance(ret[key], list):
                ret[key].append(value)
            else:
                ret[key] = [ ret[key], value ]
        else:
            ret[key] = value

    return ret
