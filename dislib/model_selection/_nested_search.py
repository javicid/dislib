import sys

from pycompss.api.api import compss_wait_on
from pycompss.util.serializer import deserialize_from_file


def process_arguments(args):
    """
    Deserialize the arguments that correspond to serialized objects.
    """
    for arg in args:
        try:
            yield deserialize_from_file(arg)
        except (TypeError, FileNotFoundError):
            yield arg


def main():
    args = process_arguments(sys.argv[1:])
    res = compss_wait_on(fit_and_score(*args))


if __name__ == '__main__':
    main()
