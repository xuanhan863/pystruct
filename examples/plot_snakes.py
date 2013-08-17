"""
==============================================
Conditional Interactions on the Snakes Dataset
==============================================
This example uses the snake dataset introduced in
Nowozin, Rother, Bagon, Sharp, Yao, Kohli: Decision Tree Fields ICCV 2011

This dataset is specifically designed to require the pairwise interaction terms
to be conditioned on the input, in other words to use non-trival edge-features.

The task is as following: a "snake" of length ten wandered over a grid. For
each cell, it had the option to go up, down, left or right (unless it came from
there). The input consists of these decisions, while the desired output is an
annotation of the snake from 0 (head) to 9 (tail).  See the plots for an
example.

As input features we use a 3x3 window around each pixel (and pad with background
where necessary). We code the five different input colors (for up, down, left, right,
background) using a one-hot encoding. This is a rather naive approach, not using any
information about the dataset (other than that it is a 2d grid).

The task can not be solved using the simple DirectionalGridCRF - which can only
infer head and tail (which are also possible to infer just from the unary
features). If we add edge-features that contain the features of the nodes that are
connected by the edge, the CRF can solve the task.

From an inference point of view, this task is very hard.  QPBO move-making is
not able to solve it alone, so we use the relaxed AD3 inference for learning.
"""
import numpy as np

from sklearn.preprocessing import label_binarize
from sklearn.metrics import confusion_matrix, accuracy_score

from pystruct.learners import OneSlackSSVM
from pystruct.datasets import load_snakes
from pystruct.utils import SaveLogger, make_grid_edges, edge_list_to_features
from pystruct.models import EdgeFeatureGraphCRF


def one_hot_colors(x):
    x = x / 255
    flat = np.dot(x.reshape(-1, 3),  2 **  np.arange(3))
    one_hot = label_binarize(flat, classes=[1, 2, 3, 4, 6])
    return one_hot.reshape(x.shape[0], x.shape[1], 5)


def neighborhood_feature(x):
    """Add a 3x3 neighborhood around each pixel as a feature."""
    # position 3 is background.
    features = np.zeros((x.shape[0], x.shape[1], 5, 5))
    features[:, :, 3, :] = 1
    #features[1:, 1:, :, 0] = x[:-1, :-1, :]
    features[:, 1:, :, 0] = x[:, :-1, :]
    #features[:-1, 1:, :, 2] = x[1:, :-1, :]
    features[1:, :, :, 1] = x[:-1, :, :]
    #features[:-1, :-1, :, 4] = x[1:, 1:, :]
    features[:-1, :, :, 2] = x[1:, :, :]
    #features[1:, :-1, :, 6] = x[:-1, 1:, :]
    features[:, :-1, :, 3] = x[:, 1:, :]
    features[:, :, :, 4] = x[:, :, :]
    return features.reshape(x.shape[0] * x.shape[1], -1)


def prepare_data(X):
    X_directions = []
    X_edge_features = []
    for x in X:
        # get edges in grid
        right, down = make_grid_edges(x, return_lists=True)
        edges = np.vstack([right, down])
        # use 3x3 patch around each point
        features = neighborhood_feature(x)
        # simple edge feature that encodes just if an edge is horizontal or
        # vertical
        edge_features_directions = edge_list_to_features([right, down])
        # edge feature that contains features from the nodes that the edge connects
        edge_features = np.zeros((edges.shape[0], features.shape[1], 4))
        edge_features[:len(right), :, 0] = features[right[:, 0]]
        edge_features[:len(right), :, 1] = features[right[:, 1]]
        edge_features[len(right):, :, 0] = features[down[:, 0]]
        edge_features[len(right):, :, 1] = features[down[:, 1]]
        X_directions.append((features, edges, edge_features_directions))
        X_edge_features.append((features, edges, edge_features))
    return X_directions, X_edge_features




def main():
    snakes = load_snakes()
    X_train, Y_train = snakes['X_train'], snakes['Y_train']

    X_train = [one_hot_colors(x) for x in X_train]
    Y_train_flat = [y.ravel() for y in Y_train]

    X_train_directions, X_train_edge_features = prepare_data(X_train)

    # first, train on X with directions only:
    logger = SaveLogger(save_every=10, file_name="snakes_C1_4neighbors_bb.pickle")
    crf = EdgeFeatureGraphCRF(inference_method='qpbo')
    ssvm = OneSlackSSVM(crf, inference_cache=50, C=1, verbose=2,
                        show_loss_every=100, inactive_threshold=1e-5, tol=1e-1,
                        switch_to="ad3", n_jobs=1, logger=logger)
    ssvm.fit(X_train_directions, Y_train_flat)

    # Evaluate using confusion matrix.
    # Clearly the middel of the snake is the hardest part.
    X_test, Y_test = snakes['X_test'], snakes['Y_test']
    X_test = [one_hot_colors(x) for x in X_test]
    Y_test_flat = [y.ravel() for y in Y_test]
    X_test_directions, X_test_edge_features = prepare_data(X_test)
    Y_pred = ssvm.predict(X_test_directions)
    print("Results using only directional features for edges")
    print("Test accuracy: %.3f" % accuracy_score(np.hstack(Y_test_flat), np.hstack(Y_pred)))
    print(confusion_matrix(np.hstack(Y_test_flat), np.hstack(Y_pred)))

    # now, use more informative edge features:
    crf = EdgeFeatureGraphCRF(inference_method='qpbo')
    ssvm = OneSlackSSVM(crf, inference_cache=50, C=1, verbose=2,
                        show_loss_every=100, inactive_threshold=1e-5, tol=1e-1,
                        switch_to="ad3", n_jobs=1, logger=logger)
    ssvm.fit(X_train_edge_features, Y_train_flat)
    Y_pred = ssvm.predict(X_test_edge_features)
    print("Results using also input features for edges")
    print("Test accuracy: %.3f" % accuracy_score(np.hstack(Y_test_flat), np.hstack(Y_pred)))
    print(confusion_matrix(np.hstack(Y_test_flat), np.hstack(Y_pred)))


if __name__ == "__main__":
    main()
    # results directional grid C=0.1 0.795532646048
    # results one-hot grid C=0.1 0.788395453344
    # completely flat C=1 svc 0.767909066878
    # non-one-hot flat: 0.765662172879
    # with directional grid 3x3 features C=0.1: 0.870737509913
    # ad3 refit C=0.1 0.882632831086
    # unary inference: 0.825270948982
    # pairwise feature classe C=0.1: 0.933254031192
    #final primal objective: 62.272486 gap: 24.587289
    # ad3bb C=0.1 :1.0  test: 0.99703823371
    # tol=.1
    # ad3bb C=0.0001 : 0.751255617235
    # ad3bb C=0.001 0.962727993656
    # ad3bb C=0.01 0.983478720592
    # qpbo C=0.1 : 93 / 90
    # ad3 relaxed 4 neighborhood 0.9997
