class D(type):

    def __init__(cls, name, bases, dct):
        super().__init__(cls, name, bases, dct)
        cls._instance = None

    def __call__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance.__call__(*args, **kwargs)
        return cls._instance
