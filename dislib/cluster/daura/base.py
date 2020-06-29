from itertools import chain

from pycompss.api.api import compss_wait_on
from pycompss.api.parameter import COLLECTION_IN, INOUT
from pycompss.api.task import task
from sklearn.base import BaseEstimator

import numpy as np


class Daura(BaseEstimator):

    def __init__(self, cutoff):
        """ Perform Daura clustering.

        See:
        lockhartlab.squarespace.com/blog/2018/1/14/clustering-with-daura-et-al

        Parameters
        ----------
        cutoff : float
            Distance to determine the neighbors of a sample.
        """
        self.cutoff = cutoff

    def fit_predict(self, distances):
        """ Compute Daura clustering.

        Parameters
        ----------
        distances : ds-array (n_samples, n_samples)
            Pairwise distances between the samples.

        Returns
        -------
        clusters : List[ List[ int ] ]
            A list of clusters. Each cluster is a list of sample indices,
            starting with the cluster center.
        """
        cutoff = self.cutoff
        neighbors = []

        for i, row in _indexed(distances._blocks, distances, 0):
            blocks_neighbors = []
            for j, block in _indexed(row, distances, 1):
                blocks_neighbors.append(_get_neighbors(block, j, cutoff))
            neighbors.append(_merge_neighbors(blocks_neighbors, i))

        clusters = []
        while True:
            candidates = []
            for i, nb_row in _indexed(neighbors, distances, 0):
                candidates.append(_find_candidate_cluster(nb_row, i))
            new_cluster = compss_wait_on(_find_largest_cluster(candidates))
            if len(new_cluster) > 1:
                clusters.append(new_cluster)
                for i, nb_row in _indexed(neighbors, distances, 0):
                    _remove_neighbors(nb_row, new_cluster, i)
            else:
                break
        return clusters


@task(returns=1)
def _get_neighbors(block, start_col, cutoff):
    return [np.flatnonzero(r <= cutoff) + start_col for r in block]


@task(row_blocks_neighbors=COLLECTION_IN, returns=1)
def _merge_neighbors(row_blocks_neighbors, start_idx):
    row_neighs = [set(chain(*nb)) for nb in zip(*row_blocks_neighbors)]
    for i, nb in enumerate(row_neighs):
        nb.discard(start_idx + i)
    return row_neighs


@task(returns=1)
def _find_candidate_cluster(row_neighbors, start_row):
    argmax = max(range(len(row_neighbors)),
                 key=lambda i: len(row_neighbors[i]))
    cluster = [start_row + argmax]
    cluster.extend(sorted(row_neighbors[argmax]))
    return cluster


@task(candidates=COLLECTION_IN, returns=1)
def _find_largest_cluster(candidates):
    return max(candidates, key=len)


@task(row_neighbors=INOUT)
def _remove_neighbors(row_neighbors, to_remove, start_row):
    for r in to_remove:
        if 0 <= r - start_row < len(row_neighbors):
            row_neighbors[r - start_row] = set()
    for nb in row_neighbors:
        nb.difference_update(to_remove)


def _indexed(iterable, indexing_array, axis):
    it = iter(iterable)
    yield 0, next(it)
    i = indexing_array._top_left_shape[axis]
    for item in it:
        yield i, item
        i += indexing_array._reg_shape[axis]
