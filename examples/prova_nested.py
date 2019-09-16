from pycompss.api.api import compss_wait_on
from pycompss.api.compss import compss
from pycompss.api.parameter import FILE_IN, FILE_OUT, COLLECTION_INOUT, \
    COLLECTION_IN
from pycompss.api.task import task

from dislib.classification import RandomForestClassifier, CascadeSVM


@task()
def create_clf():
    return CascadeSVM()


@task(parts=COLLECTION_INOUT)
def create_collection(parts):
    parts[:] = [{i: i} for i in range(10)]
    return parts


@compss(runcompss="runcompss", flags="-d --python_interpreter=python3",
        working_dir='/home/bscuser/.COMPSs/prova_dins',
        app_name="/home/bscuser/git/dislib/examples/nested_app.py")
@task(file_out=FILE_OUT, cll=COLLECTION_IN, params=FILE_IN, returns=int)
def nested_fit_and_score(file_out, cll, clf, params):
    pass


def main():
    cll = [{} for _ in range(10)]
    create_collection(cll)
    clf = create_clf()
    file_out = 'out.txt'
    cll = compss_wait_on(cll)
    print(cll)
    ret = nested_fit_and_score(file_out, cll, clf, '/home/bscuser/git/dislib'
                                                   '/examples/params.pickle')
    print(compss_wait_on(file_out))
    ret = compss_wait_on(ret)
    if ret != 0:  # Return code should be 0
        raise RuntimeError('@compss task failed with return code ' + str(ret))


if __name__ == '__main__':
    main()
    print('Finished')
