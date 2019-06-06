from math import sqrt

import numpy as np
from pycompss.api.api import compss_wait_on
from pycompss.api.parameter import COLLECTION_IN, Depth, Type
from pycompss.api.task import task
from scipy import sparse
from sklearn.metrics import mean_squared_error

from dislib.data.array import Array


class ALS(object):
    """ Alternating Least Squares recommendation.

    Implements distributed alternating least squares recommendation based on
    Zhou et al. [1]_.

    Parameters
    ----------
    max_iter : int, optional (default=100)
        Maximum number of iterations to perform.
    tol : float, optional (default=1e-4)
        Tolerance for the stopping criterion.
    n_f : int, optional (default=100)
        Number of latent factors (i.e. dimensions) for the matrices U and I.
    lambda_ : float, optional (default=0.065)
        Regularization parameters value.
    check_convergence : boolean, optional (default=True)
        Whether to test for convergence at the end of each iteration.
    random_state : int, orNone, optional (default=None)
        The seed of the pseudo random number generator used to initialize the
        items matrix I.
    arity : int, optional (default=5)
        The arity of the tasks during the merge of each matrix chunk.
    verbose : boolean, optional (default=False)
        Whether to print progress information.

    Attributes
    ----------
    users : np.array
        User matrix.
    items : np.array
        Items matrix.
    converged : boolean
        Whether the model has converged.

    References
    ----------

    .. [1] Zhou Y., Wilkinson D., Schreiber R., Pan R. (2008) Large-Scale
        Parallel Collaborative Filtering for the Netflix Prize. In: Fleischer
        R., Xu J. (eds) Algorithmic Aspects in Information and Management.
        AAIM 2008. Lecture Notes in Computer Science, vol 5034. Springer,
        Berlin, Heidelberg

    Examples
    --------
    >>> import numpy as np
    >>> from scipy.sparse import csr_matrix
    >>> from dislib.data import load_data
    >>> data = np.array([[0, 0, 5], [3, 0, 5], [3, 1, 2]])
    >>> ratings = csr_matrix(data).transpose().tocsr()
    >>> train = load_data(x=ratings, subset_size=1)
    >>> from dislib.recommendation import ALS
    >>> als = ALS()
    >>> als.fit(train)
    >>> print('Ratings for user 0: %s' % als.predict_user(user_id=0))
    """

    def __init__(self, random_state=None, n_f=100, lambda_=0.065,
                 tol=1e-4, max_iter=100, arity=5,
                 check_convergence=True, verbose=False):
        # params
        self._seed = random_state
        self._n_f = n_f
        self._lambda = lambda_
        self._tol = tol
        self._max_iter = max_iter
        self._verbose = verbose
        self._arity = arity
        self._check_convergence = check_convergence
        self.converged = False
        self.users = None
        self.items = None

    def _update(self, r, x, axis):
        """ Returns updated matrix M given U (if x=U), or matrix U given M
        otherwise

        Parameters
        ----------
        r : Dataset
            copy of R with items as samples (if x=U), users as samples
            otherwise
        x : Dataset
            User or Item feature matrix
        """
        res = []
        for darray in r.iterator(axis=axis):
            params = (self._n_f, self._lambda, axis)
            chunk_res = _update_chunk(darray._blocks, x, params)
            res.append(chunk_res)

        while len(res) > 1:
            q = []

            while len(res) > 0:
                # we pop the future objects to merge
                to_merge = res[:self._arity]
                del res[:self._arity]
                # if it's a single object, just add it to next step
                aux = _merge(*to_merge) if len(to_merge) > 1 else to_merge[0]
                q.append(aux)
            res = q

        return res.pop()

    def _has_finished(self, i):
        return i >= self._max_iter or self.converged

    def _has_converged(self, last_rmse, rmse):
        return abs(last_rmse - rmse) < self._tol

    def _compute_rmse(self, dataset, U, I):
        rmses = [_get_rmse(sb._blocks, U, I) for sb in
                 dataset.iterator(axis=0)]
        rmses = np.array(compss_wait_on(rmses))
        # remove NaN errors that come from empty chunks
        return np.mean(rmses[~np.isnan(rmses)])

    def fit(self, dataset, test=None):
        """ Fits a model using training data. Training data is also used to
        check for convergence unless test data is provided.

        Parameters
        ----------
        dataset : Dataset
            darray where each row represents the ratings of a given item.
        test : csr_matrix
            Sparse matrix used to check convergence with users as rows and
            items as columns. If not passed, uses training data to check
            convergence.
        """

        n_u = dataset.shape[0]
        n_i = dataset.shape[1]

        if self._verbose:
            print("Item blocks: %s" % n_i)
            print("User blocks: %s" % n_u)

        if self._seed:
            np.random.seed(self._seed)

        self.converged = False
        users = None
        items = np.random.rand(n_i, self._n_f)

        # Assign average rating as first feature
        average_ratings = dataset.mean(axis='columns').collect()

        items[:, 0] = average_ratings
        # items[:, 0] = average_ratings.flatten()

        rmse, last_rmse = np.inf, np.NaN
        i = 0
        while not self._has_finished(i):
            last_rmse = rmse

            users = self._update(r=dataset, x=items, axis=0)
            # print("users matrix:\n%s\n" % users)
            items = self._update(r=dataset, x=users, axis=1)
            # print("items matrix:\n%s\n" % items)

            if self._check_convergence:
                # if test is not None:
                #     rmse = compss_wait_on(
                #         _get_rmse(test._blocks, users, items))
                #     self.converged = self._has_converged(last_rmse, rmse)
                #     if self._verbose:
                #         print("Test RMSE: %.3f  [%s]" % (
                #             rmse, abs(last_rmse - rmse)))
                #
                # else:
                #     rmse = self._compute_train_rmse(dataset, users, items)
                #     self.converged = self._has_converged(last_rmse, rmse)
                #     if self._verbose:
                #         print("Train RMSE: %.3f  [%s]" % (
                #             rmse, abs(last_rmse - rmse)))

                _test = dataset if test is None else test
                rmse = compss_wait_on(self._compute_rmse(_test, users, items))
                self.converged = self._has_converged(last_rmse, rmse)
                if self._verbose:
                    print("%s RMSE: %.3f  [%s]" % (
                        "Train" if test is None else "test",
                        rmse, abs(last_rmse - rmse)))

                    # else:
                    #     rmse = self._compute_train_rmse(dataset, users, items)
                    #     self.converged = self._has_converged(last_rmse, rmse)
                    #     if self._verbose:
                    #         print("Train RMSE: %.3f  [%s]" % (
                    #             rmse, abs(last_rmse - rmse)))
            i += 1

        self.users = compss_wait_on(users)
        self.items = compss_wait_on(items)

        return users, items

    def predict_user(self, user_id):
        """ Returns the expected ratings for user_id. Each index represents
        the rating for i-th item. If the user was not present in the training
        set, a np.NaN vector is returned.

        Parameters
        ----------
        user_id : int

        Returns
        -------
        ratings : np.array containing all estimated items ratings for user_id.
        """
        if self.users is None or self.items is None:
            raise Exception("Model not trained, call first model.fit()")
        if user_id > self.users.shape[1]:
            return np.full([self.items.shape[1]], np.nan)

        return self.users[user_id].dot(self.items.T)


@task(returns=np.array)
def _merge(*chunks):
    res = np.vstack(chunks)
    return res


@task(blocks={Type: COLLECTION_IN, Depth: 2}, returns=np.array)
def _update_chunk(blocks, x, params):
    n_f, lambda_, axis = params
    print("Params: %s" % list(params))
    r_chunk = Array._merge_blocks(blocks)
    if axis == 1:
        r_chunk = r_chunk.transpose()

    n = r_chunk.shape[0]
    y = np.zeros((n, n_f), dtype=np.float32)
    n_c = np.array(
        [len(sparse.find(r_chunk[i])[0]) for i in
         range(0, r_chunk.shape[0])])
    for element in range(0, n):
        indices = sparse.find(r_chunk[element])[1]

        x_xt = x[indices].T.dot(x[indices])

        a_i = x_xt + lambda_ * n_c[element] * np.eye(n_f)
        v_i = x[indices].T.dot(r_chunk[element, indices].toarray().T)

        # TODO: decide if atol should be changed when default is changed
        y[element] = sparse.linalg.cg(a_i, v_i, atol='legacy')[0].reshape(-1)

    return y


@task(blocks={Type: COLLECTION_IN, Depth: 2}, returns=1)
def _get_rmse(blocks, users, items):
    test = Array._merge_blocks(blocks)
    x_idxs, y_idxs, recs = sparse.find(test)
    indices = zip(x_idxs, y_idxs)

    rmse = np.NaN
    if len(recs) > 0:
        preds = [users[x].dot(items[y].T) for x, y in indices]
        rmse = sqrt(mean_squared_error(recs, preds))

    return rmse
