#!/usr/bin/python

# Imports
import os
import pickle

from pycompss.api.task import task
from pycompss.api.api import compss_wait_on
from pycompss.util.serialization.serializer import deserialize_from_file


@task(returns=1)
def nested_task(clf, params):
    with open('/home/bscuser/git/dislib/examples/nested_task_dir.out', 'w') as file:
        file.write(str(os.getcwd()))
    with open('/home/bscuser/git/dislib/examples/nested_task_objs.out', 'w') as file:
        file.write(str(clf))
        file.write(str(params))
    return 5


def main(file_out, cll, clf_path, params):
    with open('/home/bscuser/git/dislib/examples/compss_task_dir.out', 'w') as file:
        file.write(str(os.getcwd()))

    clf = deserialize_from_file(clf_path)
    print('lali')
    print(clf_path)
    print('lali')
    print(cll)
    print(dir(cll))
    print('lali')
    cll = deserialize_from_file(cll)
    with open(params, 'rb') as f:
        params = pickle.load(f)
    nested_return = compss_wait_on(nested_task(clf, params))

    with open('/home/bscuser/git/dislib/examples/compss_task_return.out', 'w') as file:
        file.write(str(nested_return))

    with open(file_out, 'w') as file:
            file.write('lools'+str(len(cll))+str(cll))


if __name__ == '__main__':
    import sys
    main(*sys.argv[1:])
