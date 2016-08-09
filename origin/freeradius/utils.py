
def request_as_hash_of_values(request):
    class MultiDict(dict):
        'Dictionary that returns only last value when get is used and value is a list'
        def get(self, *args, **kwargs):
            v = super(MultiDict, self).get(*args, **kwargs)
            if isinstance(v, list):
                return v[-1]
            return v
            
    ret = MultiDict()
    
    for key, properties in request.items():
        values = properties['value']
        ret[key] = values        

    return ret
